import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from database import engine
from model import ActivityData, Boundary, CompanyInfo, Device, EmissionFactor, EmissionRecord, EmissionSource, GWPReference
from constants.lhv_defaults import get_lhv_value
from constants.refrigerant_factors import get_rate_by_code
from services.emission_calculator import (
    calculate_combustion_emission,
    calculate_electricity_emission,
    calculate_refrigerant_emission,
    compute_total_co2e_for_device,
    get_lhv_for_device,
    get_lhv_value,
)
from datetime import datetime

# ...
def _get_target_year(session: Session) -> int:
    from model import EmissionFactor
    from sqlmodel import select
    all_factors = session.exec(select(EmissionFactor)).all()
    return max((f.year for f in all_factors), default=datetime.now().year)

router = APIRouter(prefix="/result", tags=["result"])
templates = Jinja2Templates(directory="templates")
AI_REPORT_TASKS: dict[str, dict[str, Any]] = {}
AI_REPORT_LOCK = Lock()
AI_REPORT_OUTPUT_DIR = Path("uploads") / "ai_reports"
AI_REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
AI_REPORT_LOCAL_ENV_PATH = Path("env.local.txt")


def get_session():
    with Session(engine) as session:
        yield session


def _set_task(task_id: str, **fields: Any) -> None:
    with AI_REPORT_LOCK:
        current = AI_REPORT_TASKS.get(task_id, {})
        current.update(fields)
        AI_REPORT_TASKS[task_id] = current


def _get_task(task_id: str) -> dict[str, Any] | None:
    with AI_REPORT_LOCK:
        task = AI_REPORT_TASKS.get(task_id)
        return dict(task) if task else None


def _load_local_env_settings() -> dict[str, str]:
    if not AI_REPORT_LOCAL_ENV_PATH.exists():
        return {}

    try:
        raw_text = AI_REPORT_LOCAL_ENV_PATH.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = AI_REPORT_LOCAL_ENV_PATH.read_text(encoding="utf-8-sig")

    settings: dict[str, str] = {}
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("export "):
            line = line[7:].strip()
        if line.startswith("$env:"):
            line = line[5:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        settings[key] = value

    return settings


def _get_env_value(*keys: str, default: str | None = None) -> str | None:
    for key in keys:
        env_value = os.getenv(key)
        if env_value and env_value.strip():
            return env_value.strip()

    local_settings = _load_local_env_settings()
    for key in keys:
        local_value = local_settings.get(key)
        if local_value and local_value.strip():
            return local_value.strip()

    return default


def _resolve_llm_runtime_config() -> dict[str, str]:
    provider = (_get_env_value("LLM_PROVIDER", default="gemini") or "gemini").strip().lower()

    if provider == "gemini":
        api_key = _get_env_value("GEMINI_API_KEY", "GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("未設定 GEMINI_API_KEY (或 GOOGLE_API_KEY)，無法生成 AI 報告。")

        return {
            "provider": provider,
            "api_key": api_key,
            "base_url": _get_env_value(
                "GEMINI_BASE_URL",
                default="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            or "https://generativelanguage.googleapis.com/v1beta/openai/",
            "model": _get_env_value("GEMINI_MODEL", default="gemini-2.5-flash") or "gemini-2.5-flash",
        }

    if provider == "openai":
        api_key = _get_env_value("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("未設定 OPENAI_API_KEY，無法生成 AI 報告。")

        return {
            "provider": provider,
            "api_key": api_key,
            "model": _get_env_value("OPENAI_MODEL", default="gpt-4o-mini") or "gpt-4o-mini",
        }

    raise RuntimeError("不支援的 LLM_PROVIDER，請使用 openai 或 gemini。")


def _build_report_snapshot(session: Session, account_id: int | None = None) -> dict[str, Any]:
    records = session.exec(select(EmissionRecord)).all()
    devices = session.exec(select(Device)).all()

    if account_id is None:
        boundaries = session.exec(select(Boundary)).all()
        emission_sources = session.exec(select(EmissionSource)).all()
        activity_data_rows = session.exec(select(ActivityData)).all()
        companies = session.exec(select(CompanyInfo)).all()
    else:
        boundaries = session.exec(
            select(Boundary).where(Boundary.account_id == account_id)
        ).all()
        emission_sources = session.exec(
            select(EmissionSource).where(EmissionSource.account_id == account_id)
        ).all()
        activity_data_rows = session.exec(
            select(ActivityData).where(ActivityData.account_id == account_id)
        ).all()
        companies = session.exec(
            select(CompanyInfo).where(CompanyInfo.account_id == account_id)
        ).all()

    all_factors = session.exec(select(EmissionFactor)).all()

    device_map = {device.id: device for device in devices}
    scope_display_map = {
        "scope1": "範疇一",
        "scope2": "範疇二",
    }

    emission_type_totals_raw: dict[str, float] = {}
    device_totals_raw: dict[str, float] = {}
    total_co2e = 0.0

    for record in records:
        device = device_map.get(record.device_id)
        emission_type = (device.emission_type if device else "未分類") or "未分類"
        device_name = (device.name if device else f"設備#{record.device_id}") or "未命名設備"
        emission_type = emission_type.strip() or "未分類"
        device_name = device_name.strip() or "未命名設備"

        # 重新計算 CO2e：舊紀錄可能 total_co2e=0，必須與詳細表格一致
        if device:
            co2e_value = compute_total_co2e_for_device(
                session=session,
                device=device,
                activity_data=float(record.activity_data or 0),
                custom_heat_value=record.heat_value,
                custom_lhv_unit=record.lhv_unit,
            )
        else:
            co2e_value = float(record.total_co2e or 0.0)
        total_co2e += co2e_value
        emission_type_totals_raw[emission_type] = emission_type_totals_raw.get(emission_type, 0.0) + co2e_value
        device_totals_raw[device_name] = device_totals_raw.get(device_name, 0.0) + co2e_value

    emission_type_totals = [
        {"emission_type": key, "total_co2e": round(value, 4)}
        for key, value in sorted(
            emission_type_totals_raw.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    top_devices = [
        {"device_name": key, "total_co2e": round(value, 4)}
        for key, value in sorted(
            device_totals_raw.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
    ]

    scope_source_counts_raw: dict[str, int] = {}
    for source in emission_sources:
        raw_scope = (source.scope or "").strip().lower()
        display_scope = scope_display_map.get(raw_scope, (source.scope or "未分類").strip() or "未分類")
        scope_source_counts_raw[display_scope] = scope_source_counts_raw.get(display_scope, 0) + 1

    scope_source_counts = [
        {"scope": key, "source_count": value}
        for key, value in sorted(scope_source_counts_raw.items(), key=lambda item: item[0])
    ]

    activity_source_ids = {row.source_id for row in activity_data_rows}
    completed_activity_source_count = sum(1 for source in emission_sources if source.source_id in activity_source_ids)
    total_source_count = len(emission_sources)
    activity_coverage_rate = (
        round((completed_activity_source_count / total_source_count) * 100, 2) if total_source_count else 0.0
    )

    records_with_heat_value = sum(1 for record in records if record.heat_value is not None)
    heat_value_coverage_rate = round((records_with_heat_value / len(records)) * 100, 2) if records else 0.0

    company = companies[0] if companies else None
    company_summary = {
        "company_name": (company.company_name if company else None),
        "tax_id": (company.tax_id if company else None),
        "address": (company.address if company else None),
        "owner": (company.owner if company else None),
        "contact_person": (company.contact_person if company else None),
        "email": (company.email if company else None),
        "telephone": (company.telephone if company else None),
    }

    numeric_sources: dict[str, float] = {
        "summary.total_co2e": round(total_co2e, 4),
        "summary.record_count": float(len(records)),
        "summary.device_count": float(len(devices)),
        "boundary_summary.boundary_count": float(len(boundaries)),
        "boundary_summary.source_count": float(total_source_count),
        "boundary_summary.completed_activity_source_count": float(completed_activity_source_count),
        "boundary_summary.activity_coverage_rate": float(activity_coverage_rate),
        "calculation_summary.records_with_heat_value": float(records_with_heat_value),
        "calculation_summary.heat_value_coverage_rate": float(heat_value_coverage_rate),
    }

    for index, item in enumerate(emission_type_totals):
        numeric_sources[f"emission_type_totals[{index}].total_co2e"] = float(item["total_co2e"])
    for index, item in enumerate(top_devices):
        numeric_sources[f"top_devices[{index}].total_co2e"] = float(item["total_co2e"])
    for index, item in enumerate(scope_source_counts):
        numeric_sources[f"scope_source_counts[{index}].source_count"] = float(item["source_count"])

    def _normalize_emission_style(raw_emission_type: str | None) -> str:
        raw = str(raw_emission_type or "").strip().lower()
        style_map = {
            "fixed": "固定燃燒",
            "固定燃燒": "固定燃燒",
            "mobile": "移動燃燒",
            "移動燃燒": "移動燃燒",
            "fugitive": "逸散排放",
            "逸散排放": "逸散排放",
            "process": "製程排放",
            "製程排放": "製程排放",
            "electricity": "外購電力",
            "外購電力": "外購電力",
            "steam": "外購蒸汽",
            "外購蒸汽": "外購蒸汽",
            "能源間接排放": "能源間接排放",
        }
        return style_map.get(raw, str(raw_emission_type or "未分類").strip() or "未分類")

    def _infer_material_code(material_name: str, emission_style: str) -> str:
        material = material_name.strip()
        if not material:
            return ""

        candidates = [
            f
            for f in all_factors
            if str(f.name or "").strip() == material
            and (
                str(f.emission_type or "").strip() == emission_style
                or emission_style in ("未分類", "能源間接排放")
            )
        ]
        if not candidates:
            candidates = [f for f in all_factors if str(f.name or "").strip() == material]
        if not candidates:
            return ""

        latest = max(candidates, key=lambda f: int(getattr(f, "year", 0) or 0))
        return str(latest.original_code or latest.code or "").strip()

    def _infer_source_gases(source: EmissionSource, unit_or_process: str, emission_style: str) -> set[str]:
        gases_set: set[str] = set()

        if unit_or_process:
            process_key = unit_or_process.lower()
            for f in all_factors:
                try:
                    if (
                        str(f.original_code or "").strip().lower() == process_key
                        or str(f.code or "").strip().lower() == process_key
                        or str(f.name or "").strip().lower() == process_key
                    ) and f.gas_type:
                        gases_set.add(str(f.gas_type))
                except Exception:
                    continue

        if not gases_set:
            etype_keys = {
                str(source.emission_type or "").strip().lower(),
                str(emission_style or "").strip().lower(),
            }
            for f in all_factors:
                factor_etype = str(f.emission_type or "").strip().lower()
                if factor_etype in etype_keys and f.gas_type:
                    gases_set.add(str(f.gas_type))

        if not gases_set:
            gases_set.add("CO2e")

        return gases_set

    def _normalize_gas_flags(gases_set: set[str], emission_style: str) -> dict[str, str]:
        normalized = {str(g).upper().replace("₂", "2") for g in gases_set}

        if normalized == {"CO2E"}:
            if emission_style in {"固定燃燒", "移動燃燒", "製程排放", "外購電力", "外購蒸汽", "能源間接排放"}:
                normalized.update({"CO2", "CH4", "N2O"})
            elif emission_style == "逸散排放":
                normalized.add("HFCS")

        return {
            "co2": "O" if "CO2" in normalized else "",
            "ch4": "O" if "CH4" in normalized else "",
            "n2o": "O" if "N2O" in normalized else "",
            "hfcs": "O" if any(g.startswith("HFC") for g in normalized) else "",
            "pfcs": "O" if any(g.startswith("PFC") for g in normalized) else "",
            "sf6": "O" if "SF6" in normalized else "",
            "nf3": "O" if "NF3" in normalized else "",
        }

    # --- boundary-level snapshots: 列出每個邊界的排放源及推斷之氣體種類 ---
    boundary_snapshots: list[dict] = []
    emission_source_management_rows: list[dict] = []
    for b in boundaries:
        b_sources = [s for s in emission_sources if s.boundary_id == b.boundary_id]
        sources_list: list[dict] = []
        for s in b_sources:
            unit_or_process = (s.material or s.source_name or "").strip()
            emission_style = _normalize_emission_style(s.emission_type)
            gases_set = _infer_source_gases(s, unit_or_process, emission_style)

            sources_list.append({
                "source_number": s.source_number,
                "source_name": s.source_name,
                "unit_or_process": unit_or_process,
                "gases": sorted(list(gases_set)),
            })

            scope_key = str(s.scope or "").strip().lower()
            is_indirect = scope_key == "scope2" or emission_style in {"外購電力", "外購蒸汽", "能源間接排放"}
            material_name = str(s.material or "").strip()
            material_code = _infer_material_code(material_name, emission_style)
            gas_flags = _normalize_gas_flags(gases_set, emission_style)

            emission_source_management_rows.append({
                "boundary_name": str(b.boundary_name or "").strip(),
                "process_code": str(s.source_number or "").strip(),
                "process_name": str(s.source_name or "").strip(),
                "equipment_code": str(s.source_number or "").strip(),
                "equipment_name": str(s.source_name or "").strip(),
                "material_code": material_code,
                "material_name": material_name,
                "directness": "間接排放" if is_indirect else "直接排放",
                "emission_style": emission_style,
                "gas_flags": gas_flags,
                "is_biomass_energy": "是" if "生質" in material_name else "否",
                "is_cogen": "是" if "汽電共生" in (str(s.source_name or "") + material_name) else "否",
            })

        boundary_snapshots.append({
            "boundary_id": b.boundary_id,
            "boundary_name": b.boundary_name,
            "sources": sources_list,
        })

    return {
        "inventory_year": _get_target_year(session),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_co2e": round(total_co2e, 4),
            "record_count": len(records),
            "device_count": len(devices),
        },
        "company_summary": company_summary,
        "boundary_summary": {
            "boundary_count": len(boundaries),
            "source_count": total_source_count,
            "completed_activity_source_count": completed_activity_source_count,
            "activity_coverage_rate": activity_coverage_rate,
        },
        "calculation_summary": {
            "records_with_heat_value": records_with_heat_value,
            "heat_value_coverage_rate": heat_value_coverage_rate,
        },
        "scope_source_counts": scope_source_counts,
        "emission_type_totals": emission_type_totals,
        "top_devices": top_devices,
        "boundary_snapshots": boundary_snapshots,
        "emission_source_management_rows": emission_source_management_rows,
        "numeric_sources": numeric_sources,
    }


def _normalize_report_payload(payload: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    compliance_sections = normalized.get("compliance_template_sections")
    if not isinstance(compliance_sections, dict):
        compliance_sections = {}

    summary = snapshot.get("summary", {}) if isinstance(snapshot.get("summary"), dict) else {}
    company_summary = snapshot.get("company_summary", {}) if isinstance(snapshot.get("company_summary"), dict) else {}
    boundary_summary = snapshot.get("boundary_summary", {}) if isinstance(snapshot.get("boundary_summary"), dict) else {}
    calculation_summary = (
        snapshot.get("calculation_summary", {})
        if isinstance(snapshot.get("calculation_summary"), dict)
        else {}
    )
    scope_source_counts = snapshot.get("scope_source_counts", [])
    if not isinstance(scope_source_counts, list):
        scope_source_counts = []
    emission_type_totals = snapshot.get("emission_type_totals", [])
    if not isinstance(emission_type_totals, list):
        emission_type_totals = []
    reduction_actions = normalized.get("reduction_actions")
    if not isinstance(reduction_actions, list):
        reduction_actions = []

    def _clean_string_list(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        values: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text:
                values.append(text)
        return values

    def _fallback_company_basic_info() -> list[str]:
        lines: list[str] = []
        company_name = company_summary.get("company_name")
        address = company_summary.get("address")
        owner = company_summary.get("owner")
        if company_name:
            lines.append(f"事業名稱：{company_name}")
        if address:
            lines.append(f"事業地址：{address}")
        if owner:
            lines.append(f"事業負責人：{owner}")
        tax_id = company_summary.get("tax_id")
        if tax_id:
            lines.append(f"統一編號：{tax_id}")
        if not lines:
            lines.append("資料缺口：未提供事業名稱、地址與負責人等公司基本資料。")
        return lines

    def _fallback_boundary_setting() -> list[str]:
        lines: list[str] = []
        boundary_count = int(boundary_summary.get("boundary_count", 0) or 0)
        source_count = int(boundary_summary.get("source_count", 0) or 0)
        if boundary_count > 0:
            lines.append(f"盤查邊界數量：{boundary_count}")
        else:
            lines.append("資料缺口：未建立廠（場）或組織邊界資料。")

        if source_count > 0:
            lines.append(f"納入邊界之排放源數量：{source_count}")

        if scope_source_counts:
            scope_parts: list[str] = []
            for item in scope_source_counts:
                if not isinstance(item, dict):
                    continue
                scope_name = str(item.get("scope", "未分類")).strip() or "未分類"
                scope_count = int(item.get("source_count", 0) or 0)
                scope_parts.append(f"{scope_name}{scope_count}項")
            if scope_parts:
                lines.append("範疇分布：" + "、".join(scope_parts))
        else:
            lines.append("資料缺口：缺少範疇一/二排放源分類資料。")
        return lines

    def _fallback_source_identification() -> list[str]:
        lines: list[str] = []
        top_types = emission_type_totals[:3]
        for item in top_types:
            if not isinstance(item, dict):
                continue
            emission_type = str(item.get("emission_type", "未分類")).strip() or "未分類"
            total_value = item.get("total_co2e", 0)
            lines.append(f"排放類型：{emission_type}，排放量：{total_value} kg CO2e")
        if not lines:
            lines.append("資料缺口：尚無可用之排放源鑑別或排放類型統計資料。")
        return lines

    def _fallback_emission_calculation() -> list[str]:
        lines: list[str] = []
        record_count = int(summary.get("record_count", 0) or 0)
        total_co2e = summary.get("total_co2e", 0)
        if record_count > 0:
            lines.append(f"年排放量總計：{total_co2e} kg CO2e（依既有紀錄彙總）")
            lines.append(f"排放量計算紀錄筆數：{record_count}")
        else:
            lines.append("資料缺口：尚無排放量計算紀錄，無法產出年排放量。")

        heat_record_count = int(calculation_summary.get("records_with_heat_value", 0) or 0)
        heat_coverage_rate = calculation_summary.get("heat_value_coverage_rate", 0)
        if heat_record_count > 0:
            lines.append(f"含低位熱值資料筆數：{heat_record_count}（覆蓋率 {heat_coverage_rate}%）")
        else:
            lines.append("資料缺口：缺少低位熱值或燃料性質資料。")
        return lines

    def _fallback_other_regulatory_items() -> list[str]:
        lines: list[str] = []
        for action in reduction_actions[:3]:
            if not isinstance(action, dict):
                continue
            title = str(action.get("title", "")).strip()
            detail = str(action.get("detail", "")).strip()
            if title and detail:
                lines.append(f"減量措施：{title}。說明：{detail}")
            elif title:
                lines.append(f"減量措施：{title}")
        if not lines:
            lines.append("資料缺口：尚未提供事業執行減量措施及佐證說明。")
        return lines

    def _ensure_section(key: str, fallback: list[str]) -> None:
        cleaned = _clean_string_list(compliance_sections.get(key))
        compliance_sections[key] = cleaned if cleaned else fallback

    _ensure_section("company_basic_info", _fallback_company_basic_info())
    _ensure_section("boundary_setting", _fallback_boundary_setting())
    _ensure_section("source_identification", _fallback_source_identification())
    _ensure_section("emission_calculation", _fallback_emission_calculation())
    _ensure_section("other_regulatory_items", _fallback_other_regulatory_items())

    normalized["compliance_template_sections"] = compliance_sections
    return normalized


def _generate_report_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 套件，請執行: pip install openai") from exc

    config = _resolve_llm_runtime_config()
    provider = config["provider"]
    if provider == "gemini":

        # Gemini 提供 OpenAI-compatible endpoint，可沿用既有訊息格式與 JSON 模式。
        client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
        model = config["model"]
    elif provider == "openai":
        client = OpenAI(api_key=config["api_key"])
        model = config["model"]
    else:
        raise RuntimeError("不支援的 LLM_PROVIDER，請使用 openai 或 gemini。")

    system_prompt = (
        "你是企業溫室氣體盤查顧問。"
        "你只能使用使用者提供的 JSON 事實資料。"
        "嚴禁捏造數字、法規條文、額外排放係數。"
        "若資料不足，必須明確寫出資料缺口。"
        "你必須輸出單一 JSON object，不能有 markdown code fence。"
        "輸出欄位固定為：executive_summary(字串),"
        "compliance_template_sections(物件，且必含 company_basic_info/boundary_setting/source_identification/emission_calculation/other_regulatory_items 五個字串陣列),"
        "current_state_findings(字串陣列),"
        "reduction_actions(物件陣列，每項含 title/detail/expected_impact),"
        "assumptions(字串陣列),"
        "data_gaps(字串陣列),"
        "citations(物件陣列，每項含 metric/source_path/value)。"
        "請盡量貼合盤查報告書章節範本，內容順序依序為：公司基本資料、盤查邊界設定、排放源鑑別、排放量計算、其他主管機關規定事項。"
        "若任何章節資料不足，該章節至少要有一行以『資料缺口：』開頭的說明。"
        "citations.source_path 必須對應到輸入中的 numeric_sources 鍵名，"
        "citations.value 必須填對應數值。"
    )
    user_prompt = json.dumps(snapshot, ensure_ascii=False)

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("LLM 沒有回傳內容。")

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM 回傳格式不是有效 JSON。") from exc


def _validate_report_payload(payload: dict[str, Any], snapshot: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("報告內容格式錯誤：payload 必須為 JSON object。")

    required_string_fields = ["executive_summary"]
    required_list_fields = [
        "current_state_findings",
        "reduction_actions",
        "assumptions",
        "data_gaps",
        "citations",
    ]

    for field in required_string_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"報告欄位缺失或格式錯誤：{field}")

    for field in required_list_fields:
        value = payload.get(field)
        if not isinstance(value, list):
            raise ValueError(f"報告欄位缺失或格式錯誤：{field}")

    compliance_sections = payload.get("compliance_template_sections")
    if not isinstance(compliance_sections, dict):
        raise ValueError("報告欄位缺失或格式錯誤：compliance_template_sections")

    required_compliance_sections = [
        "company_basic_info",
        "boundary_setting",
        "source_identification",
        "emission_calculation",
        "other_regulatory_items",
    ]
    for section in required_compliance_sections:
        section_value = compliance_sections.get(section)
        if not isinstance(section_value, list):
            raise ValueError(f"盤查章節欄位缺失或格式錯誤：compliance_template_sections.{section}")

    numeric_sources = snapshot.get("numeric_sources", {})
    citations = payload.get("citations", [])
    if not citations:
        raise ValueError("報告缺少 citations，無法驗證數值來源。")

    matched_citations = 0
    for index, citation in enumerate(citations):
        if not isinstance(citation, dict):
            raise ValueError(f"citations[{index}] 格式錯誤")

        source_path = citation.get("source_path")
        value = citation.get("value")
        if not isinstance(source_path, str) or source_path not in numeric_sources:
            raise ValueError(f"citations[{index}] source_path 不存在於 numeric_sources")
        if not isinstance(value, (int, float, str)):
            raise ValueError(f"citations[{index}] value 不是有效數字")

        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"citations[{index}] value 不是有效數字") from exc

        source_value = float(numeric_sources[source_path])
        if abs(source_value - numeric_value) > 1e-3:
            raise ValueError(
                f"citations[{index}] value 與資料來源不一致 (source={source_value}, output={numeric_value})"
            )
        matched_citations += 1

    if matched_citations == 0:
        raise ValueError("報告沒有可驗證的數值引用。")


def _build_docx_report(payload: dict[str, Any], snapshot: dict[str, Any], task_id: str) -> Path:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("缺少 python-docx 套件，請執行: pip install python-docx==1.1.2") from exc

    document = Document()
    document.add_heading("溫室氣體盤查報告範例", level=1)
    document.add_paragraph(f"盤查年度：{snapshot.get('inventory_year')}")
    document.add_paragraph(f"生成時間：{snapshot.get('generated_at')}")
    document.add_paragraph(f"總排放量：{snapshot.get('summary', {}).get('total_co2e')} kg CO2e")

    document.add_heading("一、執行摘要", level=2)
    document.add_paragraph(str(payload.get("executive_summary", "")))

    compliance_sections = payload.get("compliance_template_sections", {})

    document.add_heading("二、公司基本資料", level=2)
    for item in compliance_sections.get("company_basic_info", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("三、盤查邊界設定", level=2)
    for item in compliance_sections.get("boundary_setting", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("四、排放源鑑別", level=2)
    for item in compliance_sections.get("source_identification", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("五、排放量計算", level=2)
    for item in compliance_sections.get("emission_calculation", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("六、其他主管機關規定事項", level=2)
    for item in compliance_sections.get("other_regulatory_items", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("七、現狀分析與洞察", level=2)
    for item in payload.get("current_state_findings", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("八、減碳建議與策略", level=2)
    for item in payload.get("reduction_actions", []):
        if isinstance(item, dict):
            title = str(item.get("title", "未命名建議"))
            detail = str(item.get("detail", ""))
            impact = str(item.get("expected_impact", ""))
            document.add_paragraph(f"{title}", style="List Number")
            if detail:
                document.add_paragraph(f"說明：{detail}")
            if impact:
                document.add_paragraph(f"預期效益：{impact}")
        else:
            document.add_paragraph(str(item), style="List Number")

    document.add_heading("九、假設條件", level=2)
    for item in payload.get("assumptions", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("十、資料缺口", level=2)
    for item in payload.get("data_gaps", []):
        document.add_paragraph(str(item), style="List Bullet")

    document.add_heading("十一、數值引用", level=2)
    for citation in payload.get("citations", []):
        metric = citation.get("metric", "") if isinstance(citation, dict) else ""
        source_path = citation.get("source_path", "") if isinstance(citation, dict) else ""
        value = citation.get("value", "") if isinstance(citation, dict) else ""
        document.add_paragraph(f"{metric}: {value} (來源: {source_path})", style="List Bullet")

    file_path = AI_REPORT_OUTPUT_DIR / f"ai_report_{task_id}.docx"
    document.save(str(file_path))
    return file_path


def _run_ai_report_task(task_id: str, snapshot: dict[str, Any]) -> None:
    _set_task(task_id, status="processing", message="正在呼叫 LLM 生成報告...")
    try:
        payload = _generate_report_payload(snapshot)
        payload = _normalize_report_payload(payload, snapshot)
        _set_task(task_id, status="processing", message="正在驗證報告內容...")
        _validate_report_payload(payload, snapshot)

        _set_task(task_id, status="processing", message="正在轉換為 Word 檔案...")
        file_path = _build_docx_report(payload, snapshot, task_id)
        _set_task(
            task_id,
            status="completed",
            message="報告生成完成，可下載。",
            completed_at=datetime.now().isoformat(),
            file_path=str(file_path),
        )
    except Exception as exc:
        _set_task(
            task_id,
            status="failed",
            message="報告生成失敗，請檢查設定後再試。",
            completed_at=datetime.now().isoformat(),
            error=str(exc),
        )


@router.get("/", response_class=HTMLResponse)
async def result_page(request: Request, session: Session = Depends(get_session)):
    records = session.exec(select(EmissionRecord)).all()
    devices = session.exec(select(Device)).all()
    all_factors = session.exec(select(EmissionFactor)).all()
    device_map = {device.id: device for device in devices}

    # --- build factor lookup maps (same logic as calculation page) ---
    def _factor_matches_device(factor: EmissionFactor, device: Device) -> bool:
        ref_code = str(device.factor_ref_code).strip()
        return (
            factor.emission_type == device.emission_type
            and (
                str(factor.original_code).strip() == ref_code
                or str(factor.code).strip() == ref_code
            )
        )

    target_year = max((f.year for f in all_factors), default=datetime.now().year)

    gwp_refs = session.exec(select(GWPReference).order_by(GWPReference.gas_name_zh)).all()
    gwp_lookup: dict[str, dict] = {}
    for g in gwp_refs:
        gwp_lookup[g.formula] = {"name": g.gas_name_zh, "gwp": float(g.gwp_value or 0)}

    factor_detail_map: dict[int, list[dict]] = {}
    device_calc_info: dict[int, dict] = {}

    for d in devices:
        etype = str(d.emission_type or "").strip()
        if etype == "逸散排放" and d.refrigerant_code:
            from services.emission_calculator import _lookup_gwp
            gwp_info = gwp_lookup.get(d.refrigerant_code)
            if not gwp_info:
                gwp_val = _lookup_gwp(session, d.refrigerant_code)
                gwp_info = {"name": d.refrigerant_code, "gwp": gwp_val}
            rate = get_rate_by_code(d.equipment_category or "")
            fill_kg = (d.fill_amount or 0) * 1000.0
            device_calc_info[d.id] = {
                "type": "refrigerant",
                "gwp_value": gwp_info.get("gwp", 0),
                "emission_rate": rate,
                "fill_kg": fill_kg,
            }
            factor_detail_map[d.id] = [
                {"gas": "CO2e", "val": gwp_info.get("gwp", 0)}
            ]
        elif etype == "能源間接排放":
            elec_factors = [f for f in all_factors if f.original_code == "ELECTRICITY" and f.gas_type == "CO2e"]
            latest_elec = max((f.year for f in elec_factors), default=target_year)
            elec_factor = next((f for f in elec_factors if f.year == latest_elec), None)
            factor_value = elec_factor.factor_value if elec_factor else 0.0
            device_calc_info[d.id] = {
                "type": "electricity",
                "factor_value": factor_value,
            }
            factor_detail_map[d.id] = [
                {"gas": "CO2e", "val": factor_value}
            ]
        else:
            matched = [f for f in all_factors if _factor_matches_device(f, d)]
            if not matched:
                factor_detail_map[d.id] = []
                device_calc_info[d.id] = {"type": "combustion", "has_lhv": False}
                continue
            latest_year = max(f.year for f in matched)
            latest_factors = [f for f in matched if f.year == latest_year]
            factor_detail_map[d.id] = [
                {"gas": f.gas_type, "val": f.factor_value}
                for f in latest_factors
            ]
            lhv_val, lhv_unit = get_lhv_value(d.factor_ref_code)
            device_calc_info[d.id] = {
                "type": "combustion",
                "has_lhv": lhv_val is not None,
                "lhv_value": lhv_val,
                "lhv_unit": lhv_unit,
            }

    # --- helper: compute gas breakdown for one record (透過 services 統一入口) ---
    def _gas_breakdown(record: EmissionRecord) -> dict[str, float]:
        device = device_map.get(record.device_id)
        if not device:
            return {"CO2e": round(float(record.total_co2e or 0), 4)}

        etype = (device.emission_type or "").strip()
        activity = float(record.activity_data or 0.0)

        if etype == "逸散排放" and device.refrigerant_code:
            result = calculate_refrigerant_emission(
                session=session,
                refrigerant_code=device.refrigerant_code,
                fill_amount_tonnes=device.fill_amount or 0,
                equipment_category=device.equipment_category or "",
            )
            return {"CO2e": round(float(result.get("CO2e", record.total_co2e or 0)), 4)}

        if etype == "能源間接排放":
            result = calculate_electricity_emission(
                session=session,
                activity_value=activity,
                year=None,
            )
            return {"CO2e": round(float(result.get("CO2e", record.total_co2e or 0)), 4)}

        # 固定燃燒 / 移動燃燒 — 走服務
        lhv_value, lhv_unit = get_lhv_for_device(
            session=session,
            device=device,
            custom_heat_value=record.heat_value,
            custom_lhv_unit=record.lhv_unit,
        )
        result = calculate_combustion_emission(
            session=session,
            original_code=device.factor_ref_code or "",
            emission_type=etype or "固定燃燒",
            activity_value=activity,
            lhv_value=lhv_value,
            lhv_unit=lhv_unit,
            year=None,
        )
        return {
            "CO2": round(float(result.get("CO2", 0) or 0), 4),
            "CH4": round(float(result.get("CH4", 0) or 0), 4),
            "N2O": round(float(result.get("N2O", 0) or 0), 4),
            "CO2e": round(float(result.get("CO2e", record.total_co2e or 0) or 0), 4),
        }

    # --- aggregate with gas breakdown ---
    scope_order = ["scope1", "scope2"]
    scope_display = {
        "scope1": "範疇一：直接排放",
        "scope2": "範疇二：能源間接排放",
    }
    emission_type_to_scope: dict[str, str] = {
        "固定燃燒": "scope1",
        "移動燃燒": "scope1",
        "逸散排放": "scope1",
        "能源間接排放": "scope2",
    }

    scope_data: list[dict] = []
    scope_totals: dict[str, float] = {"scope1": 0.0, "scope2": 0.0}
    emission_type_totals_raw: dict[str, float] = {}

    for scope_key in scope_order:
        emission_types_in_scope: dict[str, dict] = {}

        for record in records:
            device = device_map.get(record.device_id)
            etype = ((device.emission_type if device else "未分類") or "未分類").strip()
            dev_name = ((device.name if device else f"設備#{record.device_id}") or "未命名").strip()
            factor_code = (device.factor_ref_code if device else "") or ""

            if emission_type_to_scope.get(etype, "scope1") != scope_key:
                continue

            co2e_stored = float(record.total_co2e or 0.0)
            gases = _gas_breakdown(record)
            co2e_val = gases.get("CO2e", co2e_stored)

            emission_type_totals_raw[etype] = emission_type_totals_raw.get(etype, 0.0) + co2e_val

            if etype not in emission_types_in_scope:
                emission_types_in_scope[etype] = {
                    "emission_type": etype,
                    "devices": {},
                    "type_total_co2e": 0.0,
                    "type_gas_totals": {"CO2": 0.0, "CH4": 0.0, "N2O": 0.0},
                }

            et_data = emission_types_in_scope[etype]
            et_data["type_total_co2e"] += co2e_val
            for g in ("CO2", "CH4", "N2O"):
                et_data["type_gas_totals"][g] = et_data["type_gas_totals"].get(g, 0.0) + gases.get(g, 0.0)

            if dev_name not in et_data["devices"]:
                et_data["devices"][dev_name] = {
                    "device_name": dev_name,
                    "factor_code": factor_code,
                    "records": [],
                    "total_co2e": 0.0,
                    "gas_totals": {"CO2": 0.0, "CH4": 0.0, "N2O": 0.0},
                }

            dev_data = et_data["devices"][dev_name]
            dev_data["records"].append({
                "record_date": record.record_date,
                "activity_data": record.activity_data,
                "unit": record.unit or "",
                "heat_value": record.heat_value,
                "co2e": co2e_val,
                "gases": gases,
            })
            dev_data["total_co2e"] += co2e_val
            for g in ("CO2", "CH4", "N2O"):
                dev_data["gas_totals"][g] = dev_data["gas_totals"].get(g, 0.0) + gases.get(g, 0.0)
            scope_totals[scope_key] += co2e_val

        type_list = []
        for etype_key in sorted(emission_types_in_scope.keys()):
            et = emission_types_in_scope[etype_key]
            device_list = []
            for dev_key in sorted(et["devices"].keys()):
                dev = et["devices"][dev_key]
                dev["total_co2e"] = round(dev["total_co2e"], 4)
                for g in ("CO2", "CH4", "N2O"):
                    dev["gas_totals"][g] = round(dev["gas_totals"][g], 4)
                device_list.append(dev)
            for g in ("CO2", "CH4", "N2O"):
                et["type_gas_totals"][g] = round(et["type_gas_totals"][g], 4)
            type_list.append({
                "emission_type": etype_key,
                "devices": device_list,
                "type_total_co2e": round(et["type_total_co2e"], 4),
                "type_gas_totals": et["type_gas_totals"],
            })

        scope_total = round(scope_totals[scope_key], 4)
        if type_list or scope_total > 0:
            scope_data.append({
                "scope_key": scope_key,
                "scope_name": scope_display.get(scope_key, scope_key),
                "emission_types": type_list,
                "scope_total_co2e": scope_total,
            })

    total_co2e = round(sum(scope_totals.values()), 4)
    emission_type_labels = list(emission_type_totals_raw.keys())
    emission_type_values = [round(emission_type_totals_raw[k], 4) for k in emission_type_labels]
    record_count = len(records)
    device_count = len(devices)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "inventory_year": _get_target_year(session),
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_co2e": total_co2e,
            "record_count": record_count,
            "device_count": device_count,
            "scope_data": scope_data,
            "emission_type_labels": emission_type_labels,
            "emission_type_values": emission_type_values,
        },
    )


@router.post("/generate-ai-report")
async def generate_ai_report(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    try:
        _resolve_llm_runtime_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    account_id = request.session.get("user")
    snapshot = _build_report_snapshot(session, account_id=account_id)
    if snapshot["summary"]["record_count"] == 0:
        raise HTTPException(status_code=400, detail="目前沒有排放紀錄，無法生成報告。")

    task_id = str(uuid4())
    _set_task(
        task_id,
        status="pending",
        message="任務已建立，準備開始。",
        created_at=datetime.now().isoformat(),
        completed_at=None,
        file_path=None,
        error=None,
    )
    background_tasks.add_task(_run_ai_report_task, task_id, snapshot)

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "任務已建立，請輪詢狀態。",
    }


@router.get("/ai-report-status/{task_id}")
async def get_ai_report_status(task_id: str):
    task = _get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到對應的報告任務。")

    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "message": task.get("message", ""),
        "error": task.get("error"),
        "download_url": f"/result/download-ai-report/{task_id}"
        if task.get("status") == "completed"
        else None,
    }


@router.get("/download-ai-report/{task_id}")
async def download_ai_report(task_id: str):
    task = _get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到對應的報告任務。")
    if task.get("status") != "completed":
        raise HTTPException(status_code=409, detail="報告尚未完成，請稍後再試。")

    file_path_raw = task.get("file_path")
    if not file_path_raw:
        raise HTTPException(status_code=500, detail="報告檔案路徑不存在。")

    file_path = Path(file_path_raw)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="報告檔案不存在。")

    filename = f"ai_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    return FileResponse(
        str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
