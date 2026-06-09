"""
排放計算核心服務

三種排放類型計算：

1. 固定燃燒/移動燃燒（燃燒排放）：
    排放量(kg) = 活動數據 × LHV(→TJ) × 排放係數(kg/TJ)
    CO2e = Σ(各氣體排放量 × GWP)

2. 能源間接排放（電力）：
    CO2e(kg) = 活動數據(kWh/度) × 排放係數(kg CO2e/kWh)

3. 逸散排放（冷媒）：
    CO2e(kg) = 填充量(kg) × GWP值 × 設備洩漏率

LHV 單位轉換：
    TJ_per_unit = LHV_value × conversion_factor
    
    conversion_factor:
        Kcal → TJ: 4.1868 × 10⁻⁹
        MJ  → TJ: 1 × 10⁻⁶
        GJ  → TJ: 1 × 10⁻³

結果四捨五入到小數第 4 位
"""

from typing import Optional
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import Session, select

from model import EmissionFactor, GWPReference, Device
from constants.lhv_defaults import get_lhv_value, get_lhv_by_name
from constants.refrigerant_factors import get_rate_by_code

GWP_VALUES = {
    "CO2": 1,
    "CH4": 28,
    "N2O": 265,
}

LHV_CONVERSION = {
    "Kcal": 4.1868e-9,
    "MJ": 1e-6,
    "GJ": 1e-3,
}


def _round4(value: float) -> float:
    decimal_val = Decimal(str(value))
    return float(decimal_val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _parse_lhv_unit(lhv_unit: str) -> float:
    lhv_unit = lhv_unit.strip()
    if not lhv_unit:
        return LHV_CONVERSION["Kcal"]
    if "千卡/公升" in lhv_unit or "Kcal/l" in lhv_unit or "Kcal/公升" in lhv_unit:
        return LHV_CONVERSION["Kcal"]
    if "公斤/兆焦耳" in lhv_unit or "kg/TJ" in lhv_unit:
        return 1.0
    for prefix, factor in LHV_CONVERSION.items():
        if lhv_unit.startswith(prefix):
            return factor
    return LHV_CONVERSION["Kcal"]


def _is_lhv_in_tj(lhv_unit: str) -> bool:
    if not lhv_unit:
        return False
    u = lhv_unit.strip()
    return "kg/TJ" in u or "公斤/兆焦耳" in u


def tj_per_unit(lhv_value: float, lhv_unit: str) -> float:
    if not lhv_value or not lhv_unit:
        return 0.0
    conversion = _parse_lhv_unit(lhv_unit)
    return lhv_value * conversion


def calculate_single_gas(
    activity_value: float,
    factor_value: float,
    lhv_value: float,
    lhv_unit: str,
) -> float:
    if not activity_value or not factor_value:
        return 0.0
    tj = tj_per_unit(lhv_value, lhv_unit)
    if not tj:
        return 0.0
    emission = activity_value * factor_value * tj
    return _round4(emission)


def get_lhv_for_fuel(
    session: Session,
    original_code: str,
) -> tuple[float, str]:
    db_factor = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.original_code == original_code,
        )
    ).first()
    if db_factor and db_factor.lower_heating_value is not None and db_factor.lhv_unit:
        return db_factor.lower_heating_value, db_factor.lhv_unit
    return get_lhv_value(original_code)


def get_lhv_for_device(
    session: Session,
    device: Device,
    custom_heat_value: Optional[float] = None,
    custom_lhv_unit: Optional[str] = None,
) -> tuple[float, str]:
    if custom_heat_value and custom_heat_value > 0 and custom_lhv_unit:
        return custom_heat_value, custom_lhv_unit
    rec = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.original_code == device.factor_ref_code,
        )
    ).first()
    if rec and rec.lower_heating_value is not None and rec.lhv_unit:
        return rec.lower_heating_value, rec.lhv_unit
    lhv_val, lhv_u = get_lhv_value(device.factor_ref_code)
    if lhv_val is not None:
        return lhv_val, lhv_u
    if rec and rec.name:
        lhv_val, lhv_u = get_lhv_by_name(rec.name)
        if lhv_val is not None:
            return lhv_val, lhv_u
    return None, None


def calculate_combustion_emission(
    session: Session,
    original_code: str,
    emission_type: str,
    activity_value: float,
    lhv_value: Optional[float] = None,
    lhv_unit: Optional[str] = None,
    year: Optional[int] = None,
) -> dict[str, float]:
    result = {"CO2": 0.0, "CH4": 0.0, "N2O": 0.0, "CO2e": 0.0}
    if not activity_value:
        return result
    if lhv_value is None or lhv_unit is None:
        lhv_value, lhv_unit = get_lhv_for_fuel(session, original_code)
    if not lhv_value or not lhv_unit:
        return result
    query = select(EmissionFactor).where(
        EmissionFactor.original_code == original_code,
        EmissionFactor.emission_type == emission_type,
    )
    if year:
        year_query = query.where(EmissionFactor.year == year)
        factors = session.exec(year_query).all()
    else:
        factors = session.exec(query).all()
    if not factors:
        factors = session.exec(query).all()
    if not factors:
        return result
    latest_year = max(f.year for f in factors)
    factors = [f for f in factors if f.year == latest_year]
    for f in factors:
        if not f.factor_value:
            continue
        emission = calculate_single_gas(
            activity_value=activity_value,
            factor_value=f.factor_value,
            lhv_value=lhv_value,
            lhv_unit=lhv_unit,
        )
        gas_key = f.gas_type
        if gas_key in result:
            result[gas_key] = emission
        result["CO2e"] += emission * GWP_VALUES.get(gas_key, 1)
    result["CO2e"] = _round4(result["CO2e"])
    return result


def calculate_electricity_emission(
    session: Session,
    activity_value: float,
    year: Optional[int] = None,
) -> dict[str, float]:
    result = {"CO2e": 0.0}
    if not activity_value:
        return result
    factors = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.original_code == "ELECTRICITY",
            EmissionFactor.gas_type == "CO2e",
        ).order_by(EmissionFactor.year.desc())
    ).all()
    factor = None
    if year is not None:
        for f in factors:
            if f.year <= year:
                factor = f
                break
    if not factor and factors:
        factor = factors[0]
    if factor and factor.factor_value:
        co2e = activity_value * factor.factor_value
        result["CO2e"] = _round4(co2e)
        result["factor_value"] = factor.factor_value
        result["factor_year"] = factor.year
    return result


def calculate_refrigerant_emission(
    session: Session,
    refrigerant_code: str,
    fill_amount_tonnes: float,
    equipment_category: str,
) -> dict[str, float]:
    result = {"CO2e": 0.0}
    if not fill_amount_tonnes or not refrigerant_code:
        return result
    fill_kg = fill_amount_tonnes * 1000.0
    gwp_value = _lookup_gwp(session, refrigerant_code)
    emission_rate = get_rate_by_code(equipment_category)
    co2e = fill_kg * gwp_value * emission_rate
    result["CO2e"] = _round4(co2e)
    result["gwp_value"] = gwp_value
    result["emission_rate"] = emission_rate
    result["fill_kg"] = fill_kg
    return result


def _lookup_gwp(session: Session, refrigerant_code: str) -> float:
    gwp_ref = session.exec(
        select(GWPReference).where(GWPReference.formula == refrigerant_code)
    ).first()
    if gwp_ref and gwp_ref.gwp_value:
        return float(gwp_ref.gwp_value)
    all_gwps = session.exec(select(GWPReference)).all()
    for g in all_gwps:
        name_str = (g.gas_name_zh or "") + " " + (g.gas_name_en or "")
        if refrigerant_code in name_str:
            return float(g.gwp_value or 0)
    return 0.0


def calculate_emission_by_source(
    session: Session,
    original_code: str,
    activity_value: float,
    activity_unit: str,
    year: int,
    emission_type: str,
) -> dict[str, float]:
    result = {"CO2": 0.0, "CH4": 0.0, "N2O": 0.0, "CO2e": 0.0}
    if not activity_value:
        return result
    lhv_value, lhv_unit = get_lhv_for_fuel(session, original_code)
    if not lhv_value or not lhv_unit:
        return result
    for gas_type in ["CO2", "CH4", "N2O"]:
        factor = session.exec(
            select(EmissionFactor).where(
                EmissionFactor.original_code == original_code,
                EmissionFactor.gas_type == gas_type,
                EmissionFactor.year == year,
                EmissionFactor.emission_type == emission_type,
            )
        ).first()
        if factor and factor.factor_value:
            emission = calculate_single_gas(
                activity_value=activity_value,
                factor_value=factor.factor_value,
                lhv_value=lhv_value,
                lhv_unit=lhv_unit,
            )
            result[gas_type] = emission
            result["CO2e"] += emission * GWP_VALUES.get(gas_type, 1)
    result["CO2e"] = _round4(result["CO2e"])
    return result


def calculate_emission_simple(
    activity_value: float,
    factor_value: float,
    lhv_value: float,
    lhv_unit: str,
) -> float:
    return calculate_single_gas(
        activity_value=activity_value,
        factor_value=factor_value,
        lhv_value=lhv_value,
        lhv_unit=lhv_unit,
    )