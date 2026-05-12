from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select
from typing import Optional

from audit_log import add_change_log
from database import engine
from model import Device, EmissionFactor, EmissionRecord, DataChangeLog, UtilityBill, GWPReference

router = APIRouter(prefix="/calculation", tags=["calculation"])
templates = Jinja2Templates(directory="templates")

# 定義系統盤查年度：鎖定 2024，避免抓到舊年度導致重複計算
TARGET_YEAR = 2024


def _factor_matches_device(factor: EmissionFactor, device: Device) -> bool:
    """支援設備參照代碼可能是 original_code 或 code 的兩種情況。"""
    ref_code = str(device.factor_ref_code).strip()
    return (
        factor.emission_type == device.emission_type
        and (
            str(factor.original_code).strip() == ref_code
            or str(factor.code).strip() == ref_code
        )
    )


def _build_gwp_map(session: Session, version: str = "AR5") -> dict[str, float]:
    """建立 gas_type -> GWP 乘數對照；缺值時提供常用預設。"""
    gwp_rows = session.exec(
        select(GWPReference).where(GWPReference.version == version)
    ).all()

    gwp_map: dict[str, float] = {}
    for row in gwp_rows:
        key = str(row.formula or "").strip().upper()
        if not key:
            continue
        value = float(row.gwp_value or 0)
        gwp_map[key] = value if value > 0 else 1.0

    # 常見氣體保底值
    gwp_map.setdefault("CO2", 1.0)
    gwp_map.setdefault("CO2E", 1.0)
    gwp_map.setdefault("CH4", 28.0)
    gwp_map.setdefault("N2O", 265.0)
    return gwp_map


def _sum_utility_bill_usage(session: Session, bill_type: str, fuel_type: Optional[str] = None) -> float:
    query = select(UtilityBill).where(UtilityBill.bill_type == bill_type)
    if fuel_type is not None:
        query = query.where(UtilityBill.fuel_type == fuel_type)
    bills = session.exec(query).all()
    return round(sum(float(b.usage_amount or 0) for b in bills), 4)


def _resolve_auto_usage_total(session: Session, device: Device) -> Optional[float]:
    emission_type = str(device.emission_type or "").strip()
    factor_ref_code = str(device.factor_ref_code or "").strip().upper()
    device_name = str(device.name or "").strip()

    if emission_type == "能源間接排放" and factor_ref_code == "ELECTRICITY":
        return _sum_utility_bill_usage(session, bill_type="electricity")

    if emission_type == "移動燃燒" and device_name == "車用汽油":
        return _sum_utility_bill_usage(session, bill_type="fuel", fuel_type="車用汽油")

    if emission_type == "移動燃燒" and device_name == "柴油":
        return _sum_utility_bill_usage(session, bill_type="fuel", fuel_type="柴油")

    return None


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

    # 2. 先抓全部係數，後續依設備挑最新年度，避免出現「未知」或抓錯年度
    all_factors = session.exec(select(EmissionFactor)).all()

    # 3. 建立各式對照 Map
    # 燃料名稱對照表 (代碼 -> 名稱)，同時支援 original_code / code
    factor_name_map: dict[str, str] = {}
    for f in sorted(all_factors, key=lambda x: x.year, reverse=True):
        for key in (str(f.original_code).strip(), str(f.code).strip()):
            if key and key not in factor_name_map:
                factor_name_map[key] = f.name

    # 設備 ID -> 名稱 / 單位 / 代碼 的對照表
    device_map = {d.id: d.name for d in devices}
    device_unit_map = {d.id: d.unit for d in devices}
    device_to_code = {d.id: d.factor_ref_code for d in devices}
    device_emission_type_map = {d.id: d.emission_type for d in devices}

    # 4. 建立計算過程明細 Map（按設備精確過濾 emission_type，避免係數混用）
    # { device_id: [{"gas": "CO2", "val": 0.5}, ...] }
    factor_detail_map = {}
    for d in devices:
        matched = [f for f in all_factors if _factor_matches_device(f, d)]
        if not matched:
            factor_detail_map[d.id] = []
            continue

        latest_year = max(f.year for f in matched)
        latest_factors = [f for f in matched if f.year == latest_year]
        factor_detail_map[d.id] = [
            {"gas": f.gas_type, "val": f.factor_value}
            for f in latest_factors
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

    # 10. 汽油總用量（用於車用汽油設備自動帶入活動數據）
    gasoline_total_usage = round(
        sum(float(b.usage_amount or 0) for b in gasoline_bills),
        4,
    )
    electricity_total_usage = round(
        sum(float(b.usage_amount or 0) for b in electricity_bills),
        4,
    )
    diesel_total_usage = round(
        sum(float(b.usage_amount or 0) for b in diesel_bills),
        4,
    )

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
            "gasoline_total_usage": gasoline_total_usage,
            "electricity_total_usage": electricity_total_usage,
            "diesel_total_usage": diesel_total_usage,
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
    device = session.get(Device, device_id)
    if not device:
        return RedirectResponse(url="/calculation/", status_code=303)

    auto_usage_total = _resolve_auto_usage_total(session, device)
    usage_source = "manual"
    if auto_usage_total is not None:
        usage = float(auto_usage_total)
        usage_source = "utility_bill_total"

    if usage <= 0:
        return RedirectResponse(url="/calculation/", status_code=303)

    # 5. 先找到設備對應係數（支援 original_code / code），再挑最新年度
    factors_by_type = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.emission_type == device.emission_type,
        )
    ).all()
    factors_all_years = [f for f in factors_by_type if _factor_matches_device(f, device)]

    if not factors_all_years:
        return RedirectResponse(url="/calculation/", status_code=303)

    latest_year = max(f.year for f in factors_all_years)
    factors = [f for f in factors_all_years if f.year == latest_year]

    gwp_map = _build_gwp_map(session, version="AR5")

    def gwp_multiplier(gas_type: str) -> float:
        return float(gwp_map.get(str(gas_type).strip().upper(), 1.0))

    if heat_value and heat_value > 0:
        # 熱值計算公式：用量 × 熱值 × 排放係數 × 4186.8 × 10⁻⁹ × 10⁻³
        # = usage(公升) × heat_value(kcal/公升) × factor_value × GWP × 4.1868×10⁻⁹
        total_val = sum(
            usage * heat_value * f.factor_value * gwp_multiplier(f.gas_type) * 4.1868e-9
            for f in factors
        )
    else:
        # 標準計算（含 GWP 轉換）
        total_val = sum(usage * f.factor_value * gwp_multiplier(f.gas_type) for f in factors)
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
            f"activity_data={usage}, total_co2e={new_record.total_co2e}, usage_source={usage_source}"
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
