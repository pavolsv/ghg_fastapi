"""
Helpers to aggregate activity data for a device from various sources
(electricity/water/fuel bills, gasoline records, manual entry).
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from model import Device, EmissionRecord, UtilityBill, GasRecord


def _build_aggregated_activity(
    session: Session,
    device: Device,
) -> tuple[float, str, str]:
    """Aggregate a device's total activity data from bills and gas records.

    Returns (activity_data, unit, data_source).
    """
    bills = session.exec(
        select(UtilityBill).where(UtilityBill.device_id == device.id)
    ).all()
    gas_records = session.exec(
        select(GasRecord).where(GasRecord.device_id == device.id)
    ).all()

    # 電力：度（kWh）
    electricity_bills = [b for b in bills if b.bill_type == "electricity"]
    # 水：立方公尺
    water_bills = [b for b in bills if b.bill_type == "water"]
    # 燃料帳單（手動建的）
    fuel_bills = [b for b in bills if b.bill_type == "fuel"]

    # 預設沿用 Device 自己的單位
    total = 0.0
    unit = device.unit or ""
    data_source = "manual"

    emission_type = device.emission_type or ""

    if emission_type == "能源間接排放" or electricity_bills:
        total = sum(float(b.usage_amount or 0) for b in electricity_bills)
        unit = "度"
        data_source = "utility_bill"
    elif emission_type == "移動燃燒" or gas_records or fuel_bills:
        # 加油紀錄（公升）
        total = sum(float(g.liters or 0) for g in gas_records)
        # 加上手動建立的燃料帳單
        total += sum(float(b.usage_amount or 0) for b in fuel_bills)
        unit = "公升"
        data_source = "gas_record"
    else:
        total = sum(float(b.usage_amount or 0) for b in water_bills)
        if total:
            unit = "立方公尺"
            data_source = "utility_bill"

    return total, unit, data_source


def recompute_device_emission(
    session: Session,
    device: Device,
) -> Optional[EmissionRecord]:
    """Recompute a device's EmissionRecord from its bills and gas records.

    Returns the EmissionRecord (created/updated), or None if no data.
    """
    total, unit, data_source = _build_aggregated_activity(session, device)

    if total <= 0:
        # 沒有任何活動資料，刪除舊紀錄
        existing = session.exec(
            select(EmissionRecord).where(EmissionRecord.device_id == device.id)
        ).first()
        if existing:
            session.delete(existing)
        return None

    # 計算 CO2e（呼叫計算服務）
    from services.emission_calculator import compute_total_co2e_for_device

    co2e = compute_total_co2e_for_device(
        session=session,
        device=device,
        activity_data=total,
        custom_heat_value=None,
        custom_lhv_unit=None,
    )

    existing = session.exec(
        select(EmissionRecord).where(EmissionRecord.device_id == device.id)
    ).first()

    record_date = datetime.utcnow().strftime("%Y-%m-%d")
    if existing:
        existing.activity_data = total
        existing.total_co2e = co2e
        existing.unit = unit
        existing.data_source = data_source
        existing.record_date = record_date
        session.add(existing)
        return existing

    new_record = EmissionRecord(
        device_id=device.id,
        activity_data=total,
        total_co2e=co2e,
        unit=unit,
        data_source=data_source,
        record_date=record_date,
    )
    session.add(new_record)
    return new_record
