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
from model import Device, EmissionFactor, EmissionRecord, DataChangeLog, GWPReference
from constants.lhv_defaults import get_lhv_value
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
    boundary_snapshots = snapshot.get("boundary_snapshots")
    if not isinstance(boundary_snapshots, list) or not boundary_snapshots:
        return "資料缺口：尚未建立邊界與排放源資料，無法產生 3.4 節內容。"

    lines: list[str] = []
    for boundary in boundary_snapshots:
        if not isinstance(boundary, dict):
            continue
        boundary_name = str(boundary.get("boundary_name", "未命名邊界")).strip() or "未命名邊界"
        lines.append(f"【{boundary_name}】")

        sources = boundary.get("sources", [])
        if not isinstance(sources, list) or not sources:
            lines.append("- 無排放源資料")
            continue

        for source in sources:
            if not isinstance(source, dict):
                continue
            source_number = str(source.get("source_number", "-")).strip() or "-"
            source_name = str(source.get("source_name", "未命名排放源")).strip() or "未命名排放源"
            unit_or_process = str(source.get("unit_or_process", "-")).strip() or "-"
            gases = source.get("gases", [])
            gas_text = "、".join(str(g) for g in gases) if isinstance(gases, list) and gases else "CO2e"
            lines.append(f"- {source_number} {source_name}（單元/程序：{unit_or_process}；氣體種類：{gas_text}）")

    return "\n".join(lines)


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
        "邊界數量：{{ boundary_summary.boundary_count }}\n"
        "排放源數量：{{ boundary_summary.source_count }}\n"
    )


def _build_template_snapshot(snapshot: dict) -> dict:
    template_snapshot = dict(snapshot)
    template_snapshot["section_3_4_text"] = _build_section_34_text(snapshot)
    return template_snapshot

def _factor_matches_device(factor: EmissionFactor, device: Device) -> bool:
    ref_code = str(device.factor_ref_code).strip()
    return (
        factor.emission_type == device.emission_type
        and (
            str(factor.original_code).strip() == ref_code
            or str(factor.code).strip() == ref_code
        )
    )


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def calculation_page(request: Request, session: Session = Depends(get_session)):
    devices = session.exec(select(Device)).all()
    records = session.exec(
        select(EmissionRecord).order_by(col(EmissionRecord.record_date).desc())
    ).all()

    all_factors = session.exec(select(EmissionFactor)).all()
    target_year = max((f.year for f in all_factors), default=datetime.now().year)

    device_map = {d.id: d.name for d in devices}
    device_unit_map = {d.id: d.unit for d in devices}
    device_to_code = {d.id: d.factor_ref_code for d in devices}
    device_emission_type_map = {d.id: d.emission_type for d in devices}

    gwp_refs = session.exec(
        select(GWPReference).order_by(GWPReference.gas_name_zh)
    ).all()
    gwp_lookup: dict[str, dict] = {}
    for g in gwp_refs:
        gwp_lookup[g.formula] = {
            "name": g.gas_name_zh,
            "gwp": float(g.gwp_value or 0),
        }

    factor_detail_map = {}
    device_calc_info = {}
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
                "refrigerant_name": gwp_info.get("name", d.refrigerant_code),
                "gwp_value": gwp_info.get("gwp", 0),
                "emission_rate": rate,
                "fill_kg": fill_kg,
                "fill_tonnes": d.fill_amount or 0,
            }
            factor_detail_map[d.id] = [
                {"gas": "冷媒", "val": gwp_info.get("gwp", 0), "formula": "填充量(kg) × GWP × 洩漏率"}
            ]
        elif etype == "能源間接排放":
            elec_factors = [f for f in all_factors if f.original_code == "ELECTRICITY" and f.gas_type == "CO2e"]
            latest_elec = max((f.year for f in elec_factors), default=target_year)
            elec_factor = next((f for f in elec_factors if f.year == latest_elec), None)
            factor_value = elec_factor.factor_value if elec_factor else 0.0
            device_calc_info[d.id] = {
                "type": "electricity",
                "factor_value": factor_value,
                "factor_year": latest_elec,
            }
            factor_detail_map[d.id] = [
                {"gas": "CO2e", "val": factor_value, "formula": "活動數據(kWh) × 排放係數(kg CO2e/kWh)"}
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