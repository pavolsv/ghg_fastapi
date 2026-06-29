"""
Helpers to aggregate activity data for a device from various sources
(electricity/water/fuel bills, gasoline records, manual entry).

v2 改為回傳多筆活動紀錄（主要支援電力跨年拆分），並使用新計算核心。
"""

from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from model import Device, EmissionRecord, GasRecord, UtilityBill
from services.emission_calculator import compute_total_co2e_for_device_v2


def _build_aggregated_activity(
    session: Session,
    device: Device,
) -> list[dict]:
    """Aggregate a device's total activity data from bills and gas records.

    Returns a list of dicts:
        [{"activity_data": float, "unit": str, "data_source": str, "target_year": int|None}]
    """
    bills = session.exec(
        select(UtilityBill).where(UtilityBill.device_id == device.id)
    ).all()
    gas_records = session.exec(
        select(GasRecord).where(GasRecord.device_id == device.id)
    ).all()

    emission_type = device.emission_type or ""
    records: list[dict] = []

    # 電力：依 target_year 分組
    if emission_type == "能源間接排放" or any(b.bill_type == "electricity" for b in bills):
        year_usage: dict[Optional[int], float] = defaultdict(float)
        for b in bills:
            if b.bill_type == "electricity":
                year = b.target_year
                usage = float(
                    b.target_usage if b.target_usage is not None else b.usage_amount or 0
                )
                year_usage[year] += usage
                year_usage[year] = round(year_usage[year], 4)

        for year, usage in year_usage.items():
            if usage > 0:
                records.append(
                    {
                        "activity_data": usage,
                        "unit": "度",
                        "data_source": "utility_bill",
                        "target_year": year,
                    }
                )
        return records

    # 移動燃燒：加油紀錄 + 燃料帳單
    if emission_type == "移動燃燒" or gas_records or any(b.bill_type == "fuel" for b in bills):
        total = sum(float(g.liters or 0) for g in gas_records)
        total += sum(float(b.usage_amount or 0) for b in bills if b.bill_type == "fuel")
        total = round(total, 4)
        if total > 0:
            records.append(
                {
                    "activity_data": total,
                    "unit": device.unit or "公升",
                    "data_source": "gas_record",
                    "target_year": None,
                }
            )
        return records

    # 其他（如水）
    water_total = sum(
        float(b.usage_amount or 0) for b in bills if b.bill_type == "water"
    )
    water_total = round(water_total, 4)
    if water_total > 0:
        records.append(
            {
                "activity_data": water_total,
                "unit": device.unit or "立方公尺",
                "data_source": "utility_bill",
                "target_year": None,
            }
        )

    return records


def recompute_device_emission(
    session: Session,
    device: Device,
) -> list[EmissionRecord]:
    """Recompute a device's EmissionRecord(s) from its bills and gas records.

    會先刪除該設備所有舊 EmissionRecord，再依聚合結果重建。
    """
    aggregated = _build_aggregated_activity(session, device)

    # 刪除該設備所有舊紀錄
    existing = session.exec(
        select(EmissionRecord).where(EmissionRecord.device_id == device.id)
    ).all()
    for rec in existing:
        session.delete(rec)

    if not aggregated:
        return []

    created_records: list[EmissionRecord] = []
    record_date = datetime.utcnow().strftime("%Y-%m-%d")

    for item in aggregated:
        result = compute_total_co2e_for_device_v2(
            session=session,
            device=device,
            activity_data=item["activity_data"],
            activity_unit=item["unit"],
            target_year=item.get("target_year"),
        )

        target_year = item.get("target_year")
        if target_year is not None:
            record_date = f"{target_year}-12-31"

        new_record = EmissionRecord(
            device_id=device.id,
            record_date=record_date,
            activity_data=item["activity_data"],
            total_co2e=result.co2e,
            unit=item["unit"],
            data_source=item["data_source"],
            co2=result.co2,
            ch4=result.ch4,
            n2o=result.n2o,
            factor_year=result.factor_year,
            gwp_version=result.gwp_version,
            activity_unit=result.activity_unit,
            factor_source=result.factor_source,
            calculation_version="v2",
            target_year=target_year,
        )
        session.add(new_record)
        created_records.append(new_record)

    return created_records