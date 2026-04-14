from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select
from typing import Optional

from audit_log import add_change_log
from database import engine
from model import Device, EmissionFactor, EmissionRecord, DataChangeLog, UtilityBill

router = APIRouter(prefix="/calculation", tags=["calculation"])
templates = Jinja2Templates(directory="templates")

# 定義系統盤查年度：鎖定 2024，避免抓到舊年度導致重複計算
TARGET_YEAR = 2024


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def calculation_page(request: Request, session: Session = Depends(get_session)):
    # 1. 取得基本數據
    devices = session.exec(select(Device)).all()
    records = session.exec(
        select(EmissionRecord).order_by(col(EmissionRecord.record_date).desc())
    ).all()

    # 2. 關鍵過濾：僅抓取 TARGET_YEAR 的係數，防止明細重複列出不同年份的數據
    all_factors = session.exec(
        select(EmissionFactor).where(EmissionFactor.year == TARGET_YEAR)
    ).all()

    # 3. 建立各式對照 Map
    # 燃料名稱對照表 (代碼 -> 名稱)
    factor_name_map = {f.original_code: f.name for f in all_factors}

    # 設備 ID -> 名稱 / 單位 / 代碼 的對照表
    device_map = {d.id: d.name for d in devices}
    device_unit_map = {d.id: d.unit for d in devices}
    device_to_code = {d.id: d.factor_ref_code for d in devices}
    device_emission_type_map = {d.id: d.emission_type for d in devices}

    # 4. 建立計算過程明細 Map（按設備精確過濾 emission_type，避免係數混用）
    # { device_id: [{"gas": "CO2", "val": 0.5}, ...] }
    factor_detail_map = {}
    for d in devices:
        factor_detail_map[d.id] = [
            {"gas": f.gas_type, "val": f.factor_value}
            for f in all_factors
            if f.original_code == d.factor_ref_code
            and f.emission_type == d.emission_type
        ]

    # 6. 電費單清單供前端帶入用量
    electricity_bills = session.exec(
        select(UtilityBill)
        .where(UtilityBill.bill_type == "electricity")
        .order_by(col(UtilityBill.bill_month).desc())
    ).all()

    # 7. 電費單設備 ID（讓前端 JS 判斷是否顯示帶入選單）
    elec_device = session.exec(
        select(Device).where(
            Device.factor_ref_code == "ELECTRICITY",
            Device.emission_type == "能源間接排放",
        )
    ).first()
    elec_device_id = elec_device.id if elec_device else None

    # 8. 加油單據清單（汽油 / 柴油分別查詢）
    gasoline_bills = session.exec(
        select(UtilityBill)
        .where(UtilityBill.bill_type == "fuel", UtilityBill.fuel_type == "車用汽油")
        .order_by(col(UtilityBill.bill_month).desc())
    ).all()
    diesel_bills = session.exec(
        select(UtilityBill)
        .where(UtilityBill.bill_type == "fuel", UtilityBill.fuel_type == "柴油")
        .order_by(col(UtilityBill.bill_month).desc())
    ).all()

    # 9. 汽油 / 柴油設備 ID
    gasoline_device = session.exec(
        select(Device).where(
            Device.name == "車用汽油",
            Device.emission_type == "移動燃燒",
        )
    ).first()
    diesel_device = session.exec(
        select(Device).where(
            Device.name == "柴油",
            Device.emission_type == "移動燃燒",
        )
    ).first()
    gasoline_device_id = gasoline_device.id if gasoline_device else None
    diesel_device_id = diesel_device.id if diesel_device else None

    return templates.TemplateResponse(
        "calculation.html",
        {
            "request": request,
            "devices": devices,
            "records": records,
            "target_year": TARGET_YEAR,
            "factor_map": factor_name_map,
            "device_map": device_map,
            "device_unit_map": device_unit_map,
            "device_to_code": device_to_code,
            "device_emission_type_map": device_emission_type_map,
            "factor_detail_map": factor_detail_map,
            "electricity_bills": electricity_bills,
            "elec_device_id": elec_device_id,
            "gasoline_bills": gasoline_bills,
            "diesel_bills": diesel_bills,
            "gasoline_device_id": gasoline_device_id,
            "diesel_device_id": diesel_device_id,
        },
    )


@router.post("/calculate")
async def process_calculation(
    request: Request,
    device_id: int = Form(...),
    usage: float = Form(...),
    record_date: str = Form(...),
    heat_value: Optional[float] = Form(default=0),
    session: Session = Depends(get_session),
):
    if usage <= 0:
        return RedirectResponse(url="/calculation/", status_code=303)

    device = session.get(Device, device_id)
    if not device:
        return RedirectResponse(url="/calculation/", status_code=303)

    # 5. 計算邏輯同步鎖定 TARGET_YEAR
    # 這樣計算出的 total_co2e 才會與明細顯示的數值一致
    factors = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.original_code == device.factor_ref_code,
            EmissionFactor.emission_type == device.emission_type,
            EmissionFactor.year == TARGET_YEAR,
        )
    ).all()

    if not factors:
        return RedirectResponse(url="/calculation/", status_code=303)

    if heat_value and heat_value > 0:
        # 熱值計算公式：用量 × 熱值 × 排放係數 × 4186.8 × 10⁻⁹ × 10⁻³
        # = usage(公升) × heat_value(kcal/公升) × factor_value × 4.1868×10⁻⁹
        total_val = sum(usage * heat_value * f.factor_value * 4.1868e-9 for f in factors)
    else:
        # 標準計算
        total_val = sum(usage * f.factor_value for f in factors)
        heat_value = None

    new_record = EmissionRecord(
        device_id=device_id,
        record_date=record_date,
        activity_data=usage,
        total_co2e=round(total_val, 4),
        heat_value=heat_value if heat_value else None,
    )

    session.add(new_record)
    session.flush()

    changed_by = str(request.session.get("user", "system"))
    add_change_log(
        session=session,
        module="calculation",
        entity_name="EmissionRecord",
        record_key=str(new_record.id),
        action_type="CREATE",
        changed_by=changed_by,
        change_details=(
            f"device_id={device_id}, record_date={record_date}, "
            f"activity_data={usage}, total_co2e={new_record.total_co2e}"
        ),
    )

    session.commit()

    return RedirectResponse(url="/calculation/", status_code=303)


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
