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

import re
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

# 明確白名單：只有這些字串會被換算；其他視為不支援。
# 注意：活動數據的單位必須與 LHV 的分母一致（公升/公斤/立方公尺/公噸/公秉）。
SUPPORTED_LHV_UNITS = (
    # 能量 / 體積
    "千卡/公升(Kcal/l)",
    "千卡/公升",
    "Kcal/l",
    "Kcal/公升",
    "兆焦耳/公升(MJ/l)",
    "MJ/l",
    "MJ/公升",
    "吉焦耳/公升(GJ/l)",
    "GJ/l",
    "GJ/公升",
    # 能量 / 質量
    "千卡/公斤(Kcal/kg)",
    "千卡/公斤",
    "Kcal/kg",
    "Kcal/公斤",
    "兆焦耳/公斤(MJ/kg)",
    "MJ/kg",
    "MJ/公斤",
    "吉焦耳/公斤(GJ/kg)",
    "GJ/kg",
    "GJ/公斤",
    # 能量 / 氣體體積
    "千卡/立方公尺(Kcal/m³)",
    "千卡/立方公尺",
    "Kcal/m³",
    "Kcal/立方公尺",
    "兆焦耳/立方公尺(MJ/m³)",
    "MJ/m³",
    "MJ/立方公尺",
    "吉焦耳/立方公尺(GJ/m³)",
    "GJ/m³",
    "GJ/立方公尺",
    # 能量 / 大量體積
    "千卡/公秉(Kcal/kL)",
    "千卡/公秉",
    "Kcal/kL",
    "Kcal/公秉",
    # 能量 / 質量（公噸）
    "千卡/公噸(Kcal/t)",
    "千卡/公噸",
    "Kcal/t",
    "Kcal/公噸",
    # 排放係數直接路線：活動數據視為能量（TJ）
    "公斤/兆焦耳(kg/TJ)",
    "公斤/兆焦耳",
    "kg/TJ",
)


def is_supported_lhv_unit(lhv_unit: str) -> bool:
    """與 _parse_lhv_unit 的支援範圍一致：只有真的能換算的單位才視為支援。"""
    return _parse_lhv_unit(lhv_unit) > 0


def _round4(value: float) -> float:
    decimal_val = Decimal(str(value))
    return float(decimal_val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


# 支援的 LHV 格式：能量 / 分母；活動數據單位必須與分母一致。
# 例子：千卡/公升(Kcal/l)、Kcal/kg、MJ/m³、GJ/公噸
_LHV_UNIT_RE = re.compile(
    r"^\s*(Kcal|千卡|MJ|兆焦耳|GJ|吉焦耳)\s*/\s*"
    r"(公升|l|公斤|kg|立方公尺|m³|m3|公噸|t|公秉|kL|kl)"
    r"(\s*\(.*\))?\s*$",
    re.IGNORECASE,
)


def _parse_lhv_unit(lhv_unit: str) -> float:
    """把 lhv_unit 解析成「每單位活動數據對應的 TJ」。

    支援的單位：
        - Kcal/...（千卡/公升、千卡/公斤、千卡/立方公尺、千卡/公噸、千卡/公秉）→ 4.1868e-9
        - MJ/...（兆焦耳/公升、兆焦耳/公斤、兆焦耳/立方公尺）                → 1e-6
        - GJ/...（吉焦耳/公升、吉焦耳/公斤、吉焦耳/立方公尺）                → 1e-3
        - 公斤/兆焦耳(kg/TJ) / kg/TJ                                          → 1.0

    前提：活動數據的單位必須與 LHV 分母一致。
    例如 LHV 為 Kcal/公斤 時，activity_value 應以「公斤」輸入；
    LHV 為 Kcal/立方公尺 時，activity_value 應以「立方公尺」輸入。

    不支援的單位 → 0.0，避免錯算。
    """
    lhv_unit = (lhv_unit or "").strip()
    if not lhv_unit:
        return 0.0

    # 排放係數已為 kg/TJ 的路線：活動數據視為 TJ
    if "kg/TJ" in lhv_unit or "公斤/兆焦耳" in lhv_unit:
        return 1.0

    # 必須符合「能量 / 支援分母」格式
    if not _LHV_UNIT_RE.match(lhv_unit):
        return 0.0

    # 依能量單位判定換算係數；分母由使用者自行與活動數據對齊
    if "千卡" in lhv_unit or "Kcal" in lhv_unit:
        return LHV_CONVERSION["Kcal"]
    if "兆焦耳" in lhv_unit or "MJ" in lhv_unit:
        return LHV_CONVERSION["MJ"]
    if "吉焦耳" in lhv_unit or "GJ" in lhv_unit:
        return LHV_CONVERSION["GJ"]

    return 0.0


def _is_lhv_in_tj(lhv_unit: str) -> bool:
    if not lhv_unit:
        return False
    u = lhv_unit.strip()
    return "kg/TJ" in u or "公斤/兆焦耳" in u


def tj_per_unit(lhv_value: float, lhv_unit: str) -> float:
    if not lhv_value or not lhv_unit:
        return 0.0
    conversion = _parse_lhv_unit(lhv_unit)
    if not conversion:
        return 0.0
    return lhv_value * conversion


def calculate_single_gas(
    activity_value: float,
    factor_value: float,
    lhv_value: float,
    lhv_unit: str,
) -> float:
    if not activity_value or not factor_value:
        return 0.0
    if activity_value < 0 or factor_value < 0:
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
    if not activity_value or activity_value < 0:
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
    if not activity_value or activity_value < 0:
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
    if not fill_amount_tonnes or fill_amount_tonnes < 0 or not refrigerant_code:
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
    if not activity_value or activity_value < 0:
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


def compute_total_co2e_for_device(
    session: Session,
    device: Device,
    activity_data: float,
    custom_heat_value: Optional[float] = None,
    custom_lhv_unit: Optional[str] = None,
) -> float:
    """根據設備排放類型計算 CO2e，作為單一計算入口。

    此函式被 routers/devices.py（儲存紀錄時寫入 total_co2e）與
    routers/result.py（彙總時重新計算舊紀錄）共用，避免兩處結果不一致。
    """
    etype = (device.emission_type or "").strip()

    if etype == "逸散排放" and device.refrigerant_code:
        result = calculate_refrigerant_emission(
            session=session,
            refrigerant_code=device.refrigerant_code,
            fill_amount_tonnes=device.fill_amount or 0,
            equipment_category=device.equipment_category or "",
        )
        return float(result.get("CO2e", 0.0) or 0.0)

    if etype == "能源間接排放":
        result = calculate_electricity_emission(
            session=session,
            activity_value=activity_data,
            year=None,
        )
        return float(result.get("CO2e", 0.0) or 0.0)

    # 固定燃燒 / 移動燃燒
    lhv_value, lhv_unit = get_lhv_for_device(
        session=session,
        device=device,
        custom_heat_value=custom_heat_value,
        custom_lhv_unit=custom_lhv_unit,
    )
    result = calculate_combustion_emission(
        session=session,
        original_code=device.factor_ref_code or "",
        emission_type=etype or "固定燃燒",
        activity_value=activity_data,
        lhv_value=lhv_value,
        lhv_unit=lhv_unit,
        year=None,
    )
    return float(result.get("CO2e", 0.0) or 0.0)