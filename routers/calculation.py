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
from services.report_editor import get_report_section_definitions, list_report_drafts

router = APIRouter(prefix="/calculation", tags=["calculation"])
templates = Jinja2Templates(directory="templates")

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


@router.get("/report", response_class=HTMLResponse)
async def report_editor_page(request: Request, session: Session = Depends(get_session)):
    account_id = request.session.get("user")
    if not account_id:
        return RedirectResponse(url="/login", status_code=303)

    draft_summaries = list_report_drafts(session, int(account_id))
    requested_draft_id = str(request.query_params.get("draft_id") or "").strip()
    active_draft_id = requested_draft_id or (draft_summaries[0]["draft_id"] if draft_summaries else "")

    return templates.TemplateResponse(
        "report_editor.html",
        {
            "request": request,
            "report_sections": get_report_section_definitions(),
            "draft_summaries": draft_summaries,
            "active_draft_id": active_draft_id,
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