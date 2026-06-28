from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session, select

from audit_log import add_change_log
from database import engine
from model import Device, GasRecord
from services.device_aggregator import recompute_device_emission
from services.emission_calculator import calculate_combustion_emission_v2

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/gasoline",
    tags=["Gasoline"]
)


# 對應的排放係數 original_code（移動燃燒）
FUEL_CODE_MAP = {
    "汽油": "170001",   # 車用汽油
    "柴油": "170006",   # 柴油
}


class FuelRow(BaseModel):
    date: str | None = None
    liters: float
    fuel_type: str  # "汽油" | "柴油"


class FuelCalcRequest(BaseModel):
    rows: list[FuelRow]


def get_session():
    with Session(engine) as session:
        yield session


def _list_fuel_devices(session: Session) -> list[Device]:
    return list(
        session.exec(
            select(Device)
            .where(Device.emission_type == "移動燃燒")
            .order_by(Device.id)
        ).all()
    )


def _calc_fuel_type(session: Session, fuel_type: str, total_liters: float) -> dict[str, Any]:
    """依燃油類型與總公升數，呼叫新計算服務取得各氣體排放。"""
    original_code = FUEL_CODE_MAP.get(fuel_type)
    if not original_code or not total_liters:
        return {
            "fuel_type": fuel_type,
            "liters": float(total_liters or 0),
            "CO2": 0.0,
            "CH4": 0.0,
            "N2O": 0.0,
            "CO2e": 0.0,
            "supported": False,
        }

    result = calculate_combustion_emission_v2(
        session=session,
        original_code=original_code,
        emission_type="移動燃燒",
        activity_value=float(total_liters),
        activity_unit="公升",
        year=None,
    )
    return {
        "fuel_type": fuel_type,
        "liters": float(total_liters),
        "CO2": result.co2,
        "CH4": result.ch4,
        "N2O": result.n2o,
        "CO2e": result.co2e,
        "supported": True,
    }


@router.get("/", response_class=HTMLResponse)
async def gasoline_sum_page(request: Request, session: Session = Depends(get_session)):
    device_options = [
        {"id": d.id, "name": d.name} for d in _list_fuel_devices(session)
    ]
    # 取出最近的加油紀錄，給前端顯示
    recent_records = list(
        session.exec(
            select(GasRecord).order_by(GasRecord.record_date.desc(), GasRecord.id.desc())
        ).all()
    )[:50]
    return templates.TemplateResponse(
        "gas_value_cal.html",
        {
            "request": request,
            "device_options": device_options,
            "recent_records": recent_records,
        },
    )


@router.post("/api/calculate")
async def gasoline_calculate(
    payload: FuelCalcRequest,
    session: Session = Depends(get_session),
):
    gasoline_liters = sum(r.liters for r in payload.rows if r.fuel_type == "汽油")
    diesel_liters = sum(r.liters for r in payload.rows if r.fuel_type == "柴油")

    gasoline = _calc_fuel_type(session, "汽油", gasoline_liters) if gasoline_liters else None
    diesel = _calc_fuel_type(session, "柴油", diesel_liters) if diesel_liters else None

    total_co2e = sum(item["CO2e"] for item in (gasoline, diesel) if item)
    total_liters = gasoline_liters + diesel_liters

    return JSONResponse({
        "success": True,
        "data": {
            "gasoline_liters": round(gasoline_liters, 4),
            "diesel_liters": round(diesel_liters, 4),
            "total_liters": round(total_liters, 4),
            "gasoline": gasoline,
            "diesel": diesel,
            "total_co2e": round(total_co2e, 4),
        },
    })


@router.post("/records/create")
async def create_gas_record(
    request: Request,
    device_id: int = Form(...),
    fuel_type: str = Form(...),
    liters: float = Form(...),
    record_date: str = Form(...),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
):
    """新增加油紀錄並自動加總到對應設備的活動數據。"""
    if fuel_type not in FUEL_CODE_MAP:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "燃料類型必須為「汽油」或「柴油」"},
        )
    if liters <= 0:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "公升數必須大於 0"},
        )

    device = session.get(Device, device_id)
    if not device:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "找不到對應設備，請先建立設備"},
        )

    new_record = GasRecord(
        device_id=device_id,
        fuel_type=fuel_type,
        liters=liters,
        unit="公升",
        record_date=record_date,
        note=note or None,
    )
    session.add(new_record)
    session.flush()

    # 自動加總到該設備
    recompute_device_emission(session, device)

    add_change_log(
        session=session,
        module="gasoline",
        entity_name="GasRecord",
        record_key=str(new_record.id),
        action_type="CREATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"device_id={device_id}, fuel_type={fuel_type}, liters={liters}, "
            f"record_date={record_date}"
        ),
    )
    session.commit()
    return JSONResponse(
        content={
            "success": True,
            "message": f"已將 {liters} 公升 {fuel_type} 加總到「{device.name}」",
            "record_id": new_record.id,
        }
    )


@router.post("/records/delete/{record_id}")
async def delete_gas_record(
    request: Request,
    record_id: int,
    session: Session = Depends(get_session),
):
    record = session.get(GasRecord, record_id)
    if not record:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "找不到加油紀錄"},
        )

    affected_device_id = record.device_id
    add_change_log(
        session=session,
        module="gasoline",
        entity_name="GasRecord",
        record_key=str(record_id),
        action_type="DELETE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"device_id={record.device_id}, fuel_type={record.fuel_type}, "
            f"liters={record.liters}"
        ),
    )
    session.delete(record)
    session.flush()

    if affected_device_id:
        device = session.get(Device, affected_device_id)
        if device:
            recompute_device_emission(session, device)
    session.commit()
    return JSONResponse(content={"success": True, "message": "加油紀錄已刪除"})


@router.post("/records/update/{record_id}")
async def update_gas_record(
    request: Request,
    record_id: int,
    fuel_type: str = Form(...),
    liters: float = Form(...),
    record_date: str = Form(...),
    device_id: int = Form(...),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
):
    """更新加油紀錄並重新加總到對應設備。"""
    record = session.get(GasRecord, record_id)
    if not record:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "找不到加油紀錄"},
        )

    if fuel_type not in FUEL_CODE_MAP:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "燃料類型必須為「汽油」或「柴油」"},
        )
    if liters <= 0:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "公升數必須大於 0"},
        )

    new_device = session.get(Device, device_id)
    if not new_device:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "找不到對應設備，請先建立設備"},
        )

    old_device_id = record.device_id
    record.fuel_type = fuel_type
    record.liters = liters
    record.record_date = record_date
    record.device_id = device_id
    record.note = note or None
    session.add(record)
    session.flush()

    affected_ids = {old_device_id, device_id} - {None}
    for did in affected_ids:
        device = session.get(Device, did)
        if device:
            recompute_device_emission(session, device)

    add_change_log(
        session=session,
        module="gasoline",
        entity_name="GasRecord",
        record_key=str(record_id),
        action_type="UPDATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"device_id={device_id}, fuel_type={fuel_type}, liters={liters}, "
            f"record_date={record_date}"
        ),
    )
    session.commit()
    return JSONResponse(
        content={
            "success": True,
            "message": f"已更新 {liters} 公升 {fuel_type} 到「{new_device.name}」",
        }
    )