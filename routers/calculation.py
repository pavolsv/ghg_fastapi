import json
import re
from pathlib import Path

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select
from datetime import datetime

from audit_log import add_change_log
from database import engine
from model import Device, EmissionFactor604, EmissionRecord, DataChangeLog, GWPReference
from constants.refrigerant_factors import get_rate_by_code

router = APIRouter(prefix="/calculation", tags=["calculation"])
templates = Jinja2Templates(directory="templates")


TEMPLATE_TAG_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _extract_path_tokens(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for segment in path.split("."):
        segment = segment.strip()
        if not segment:
            continue

        matches = re.finditer(r"([^\[\]]+)|\[(\d+)\]", segment)
        for match in matches:
            key_part = match.group(1)
            index_part = match.group(2)
            if key_part is not None:
                parts.append(key_part)
            elif index_part is not None:
                parts.append(int(index_part))
    return parts


def _resolve_template_value(source: dict, path: str):
    current = source
    for token in _extract_path_tokens(path):
        if isinstance(token, int):
            if not isinstance(current, list):
                return None
            if token < 0 or token >= len(current):
                return None
            current = current[token]
            continue

        if not isinstance(current, dict):
            return None
        if token not in current:
            return None
        current = current[token]
    return current


def _render_template_with_snapshot(template_text: str, snapshot: dict) -> tuple[str, list[str]]:
    missing_tags: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        value = _resolve_template_value(snapshot, expr)
        if value is None:
            missing_tags.append(expr)
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    rendered = TEMPLATE_TAG_PATTERN.sub(_replace, template_text)
    return rendered, sorted(set(missing_tags))


def _collect_scalar_paths(data, prefix: str = "", max_list_items: int = 3) -> list[str]:
    paths: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_collect_scalar_paths(value, next_prefix, max_list_items=max_list_items))
        return paths

    if isinstance(data, list):
        limit = min(len(data), max_list_items)
        for i in range(limit):
            next_prefix = f"{prefix}[{i}]"
            paths.extend(_collect_scalar_paths(data[i], next_prefix, max_list_items=max_list_items))
        return paths

    if prefix:
        paths.append(prefix)
    return paths


def _build_section_34_text(snapshot: dict) -> str:
    devices = snapshot.get("devices_for_section", [])
    if not devices:
        return "資料缺口：尚未建立排放源資料，無法產生 3.4 節內容。"

    lines: list[str] = []
    for d in devices:
        name = d.get("name", "未命名")
        etype = d.get("emission_type", "未分類")
        fuel = d.get("factor_ref_code", "")
        scope = "範疇一" if d.get("scope") == "scope1" else "範疇二"
        lines.append(f"- {name}（排放類型：{etype}，燃料代碼：{fuel}，{scope}）")

    return "\n".join(lines) if lines else "資料缺口：尚未建立排放源資料。"


def _default_report_template() -> str:
    return (
        "# 盤查報告片段\n"
        "\n"
        "盤查年度：{{ inventory_year }}\n"
        "生成時間：{{ generated_at }}\n"
        "公司名稱：{{ company_summary.company_name }}\n"
        "\n"
        "## 3.4 排放源之單元名稱或程序及其排放之溫室氣體種類\n"
        "{{ section_3_4_text }}\n"
        "\n"
        "總排放量：{{ summary.total_co2e }} kg CO2e\n"
        "設備數量：{{ summary.device_count }}\n"
    )


def _build_template_snapshot(snapshot: dict) -> dict:
    template_snapshot = dict(snapshot)
    from model import Device
    from database import engine
    from sqlmodel import Session, select
    with Session(engine) as session:
        devices = session.exec(select(Device)).all()
    template_snapshot["devices_for_section"] = [
        {
            "name": d.name,
            "emission_type": d.emission_type,
            "factor_ref_code": d.factor_ref_code,
            "scope": d.scope,
        }
        for d in devices
    ]
    template_snapshot["section_3_4_text"] = _build_section_34_text(template_snapshot)
    return template_snapshot

def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def calculation_page(request: Request, session: Session = Depends(get_session)):
    devices = session.exec(select(Device)).all()
    records = session.exec(
        select(EmissionRecord).order_by(col(EmissionRecord.record_date).desc())
    ).all()

    device_map = {d.id: d.name for d in devices}
    device_unit_map = {d.id: d.unit for d in devices}
    device_to_code = {d.id: d.factor_ref_code for d in devices}
    device_emission_type_map = {d.id: d.emission_type for d in devices}
    device_by_id = {d.id: d for d in devices}

    gwp_refs = session.exec(
        select(GWPReference).order_by(GWPReference.gas_name_zh)
    ).all()
    gwp_lookup: dict[str, dict] = {}
    for g in gwp_refs:
        gwp_lookup[g.formula] = {
            "name": g.gas_name_zh,
            "gwp": float(g.gwp_value or 0),
        }

    # --- 直接從 EmissionRecord 與 EmissionFactor604 組合計算過程 ---
    record_calc_map: dict[int, dict] = {}
    for r in records:
        d = device_by_id.get(r.device_id)
        calc: dict = {
            "co2": float(r.co2 or 0),
            "ch4": float(r.ch4 or 0),
            "n2o": float(r.n2o or 0),
            "co2e": float(r.total_co2e or 0),
            "activity_unit": r.activity_unit or r.unit or (d.unit if d else ""),
            "factor_year": r.factor_year,
            "factor_source": r.factor_source,
            "target_year": r.target_year,
        }

        if not d:
            record_calc_map[r.id] = calc
            continue

        etype = (d.emission_type or "").strip()

        if etype == "逸散排放" and d.refrigerant_code:
            gwp_info = gwp_lookup.get(d.refrigerant_code)
            if not gwp_info:
                from services.emission_calculator import _lookup_gwp
                gwp_val = _lookup_gwp(session, d.refrigerant_code)
                gwp_info = {"name": d.refrigerant_code, "gwp": gwp_val}
            rate = get_rate_by_code(d.equipment_category or "") or 0.0
            calc["type"] = "refrigerant"
            calc["refrigerant_name"] = gwp_info.get("name", d.refrigerant_code)
            calc["gwp_value"] = gwp_info.get("gwp", 0)
            calc["emission_rate"] = rate
            calc["fill_kg"] = (d.fill_amount or 0) * 1000.0
        elif etype == "能源間接排放" or d.factor_ref_code == "ELECTRICITY":
            year = r.factor_year
            factor = session.exec(
                select(EmissionFactor604).where(
                    EmissionFactor604.original_code == "ELECTRICITY",
                    EmissionFactor604.gas_type == "CO2e",
                    EmissionFactor604.year == year,
                )
            ).first()
            if not factor:
                factor = session.exec(
                    select(EmissionFactor604)
                    .where(
                        EmissionFactor604.original_code == "ELECTRICITY",
                        EmissionFactor604.gas_type == "CO2e",
                    )
                    .order_by(EmissionFactor604.year.desc())
                ).first()
            calc["type"] = "electricity"
            calc["factor_value"] = factor.factor_value if factor else 0.0
            calc["factor_unit"] = factor.unit if factor else ""
        else:
            factors = session.exec(
                select(EmissionFactor604).where(
                    EmissionFactor604.original_code == d.factor_ref_code,
                    EmissionFactor604.emission_type == d.emission_type,
                )
            ).all()
            gas_factors = {}
            for f in factors:
                if f.gas_type in ("CO2", "CH4", "N2O"):
                    gas_factors[f.gas_type] = {
                        "value": f.factor_value,
                        "unit": f.unit,
                    }
            calc["type"] = "combustion"
            calc["gas_factors"] = gas_factors

        record_calc_map[r.id] = calc

    # 保持模板相容用的空結構
    factor_detail_map: dict[int, list] = {}
    device_calc_info: dict[int, dict] = {}
    target_year = datetime.now().year

    return templates.TemplateResponse(
        "calculation.html",
        {
            "request": request,
            "records": records,
            "target_year": target_year,
            "device_map": device_map,
            "device_unit_map": device_unit_map,
            "device_to_code": device_to_code,
            "device_emission_type_map": device_emission_type_map,
            "factor_detail_map": factor_detail_map,
            "device_calc_info": device_calc_info,
            "record_calc_map": record_calc_map,
        },
    )


@router.post("/delete/{record_id}")
async def delete_record(
    request: Request, record_id: int, session: Session = Depends(get_session)
):
    record = session.get(EmissionRecord, record_id)
    if record:
        add_change_log(
            session=session,
            module="calculation",
            entity_name="EmissionRecord",
            record_key=str(record.id),
            action_type="DELETE",
            changed_by=str(request.session.get("user", "system")),
            change_details=(
                f"device_id={record.device_id}, record_date={record.record_date}, "
                f"activity_data={record.activity_data}, total_co2e={record.total_co2e}"
            ),
        )
        session.delete(record)
        session.commit()
    return RedirectResponse(url="/calculation/", status_code=303)


@router.get("/logs")
async def get_logs(
    limit: int = 50,
    module: str = "all",
    session: Session = Depends(get_session),
):
    normalized_limit = min(max(limit, 1), 200)
    query = select(DataChangeLog)
    if module != "all":
        query = query.where(DataChangeLog.module == module)
    logs = session.exec(
        query.order_by(col(DataChangeLog.changed_at).desc()).limit(normalized_limit)
    ).all()
    payload = [
        {
            "id": log.id,
            "module": log.module,
            "entity_name": log.entity_name,
            "record_key": log.record_key,
            "action_type": log.action_type,
            "changed_by": log.changed_by,
            "changed_at": log.changed_at.isoformat(sep=" ", timespec="seconds"),
            "change_details": log.change_details,
        }
        for log in logs
    ]
    return JSONResponse(payload)


@router.get("/report", response_class=HTMLResponse)
async def report_edit_page(request: Request, session: Session = Depends(get_session)):
    # import result module dynamically to avoid circular imports
    from routers import result as result_mod

    account_id = request.session.get("user")
    if not account_id:
        return RedirectResponse(url="/login", status_code=303)
    snapshot = result_mod._build_report_snapshot(session, account_id=account_id)
    template_snapshot = _build_template_snapshot(snapshot)
    try:
        initial_payload = result_mod._normalize_report_payload({}, snapshot)
    except Exception:
        initial_payload = {}

    payload_json = json.dumps(initial_payload, ensure_ascii=False, indent=2)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    template_text = _default_report_template()
    rendered_template, missing_template_tags = _render_template_with_snapshot(template_text, template_snapshot)

    return templates.TemplateResponse(
        "report_edit.html",
        {
            "request": request,
            "snapshot": snapshot,
            "snapshot_json": snapshot_json,
            "payload_json": payload_json,
            "template_text": template_text,
            "rendered_template": rendered_template,
            "missing_template_tags": missing_template_tags,
            "template_paths": _collect_scalar_paths(template_snapshot),
        },
    )


@router.post("/report/render", response_class=HTMLResponse)
async def render_report_template(request: Request, session: Session = Depends(get_session)):
    from routers import result as result_mod

    account_id = request.session.get("user")
    if not account_id:
        return RedirectResponse(url="/login", status_code=303)
    snapshot = result_mod._build_report_snapshot(session, account_id=account_id)
    template_snapshot = _build_template_snapshot(snapshot)

    try:
        initial_payload = result_mod._normalize_report_payload({}, snapshot)
    except Exception:
        initial_payload = {}

    form = await request.form()
    template_text = str(form.get("template_text") or _default_report_template())
    payload_json = str(form.get("payload_json") or json.dumps(initial_payload, ensure_ascii=False, indent=2))
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)

    rendered_template, missing_template_tags = _render_template_with_snapshot(template_text, template_snapshot)

    return templates.TemplateResponse(
        "report_edit.html",
        {
            "request": request,
            "snapshot": snapshot,
            "snapshot_json": snapshot_json,
            "payload_json": payload_json,
            "template_text": template_text,
            "rendered_template": rendered_template,
            "missing_template_tags": missing_template_tags,
            "template_paths": _collect_scalar_paths(template_snapshot),
        },
    )


@router.post("/report/save")
async def save_report(request: Request, session: Session = Depends(get_session)):
    from routers import result as result_mod

    form = await request.form()
    payload_json = form.get("payload_json", "")
    template_text = str(form.get("template_text", "") or "")
    account_id = request.session.get("user")
    if not account_id:
        return RedirectResponse(url="/login", status_code=303)
    snapshot = result_mod._build_report_snapshot(session, account_id=account_id)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    template_snapshot = _build_template_snapshot(snapshot)
    error = None
    try:
        payload = json.loads(payload_json)
    except Exception as exc:
        error = str(exc)
        rendered_template, missing_template_tags = _render_template_with_snapshot(
            template_text or _default_report_template(),
            template_snapshot,
        )
        return templates.TemplateResponse(
            "report_edit.html",
            {
                "request": request,
                "snapshot": snapshot,
                "snapshot_json": snapshot_json,
                "payload_json": payload_json,
                "error": error,
                "template_text": template_text or _default_report_template(),
                "rendered_template": rendered_template,
                "missing_template_tags": missing_template_tags,
                "template_paths": _collect_scalar_paths(template_snapshot),
            },
        )

    outdir = Path("uploads") / "ai_reports"
    outdir.mkdir(parents=True, exist_ok=True)
    filename = outdir / f"manual_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filename.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if template_text.strip():
        rendered_template, _ = _render_template_with_snapshot(template_text, template_snapshot)
        rendered_path = outdir / f"manual_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        rendered_path.write_text(rendered_template, encoding="utf-8")

    return RedirectResponse(url="/calculation/report", status_code=303)