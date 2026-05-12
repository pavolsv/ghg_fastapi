"""
排放計算核心服務

計算公式：
    排放量(kg) = 活動數據 × 排放係數(kg/TJ) × LHV(活動單位→TJ)
    
    TJ_per_unit = LHV_value × conversion_factor
    
    conversion_factor:
        Kcal → TJ: 4.1868 × 10⁻⁹
        MJ  → TJ: 1 × 10⁻⁶
        GJ  → TJ: 1 × 10⁻³
        
    CO2e = CO2×1 + CH4×28 + N2O×265
    
結果四捨五入到小數第 4 位
"""

from typing import Optional
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import Session, select

from model import EmissionFactor, GWPReference
from constants.lhv_defaults import get_lhv_value


# GWP 值（IPCC AR5）
GWP_VALUES = {
    "CO2": 1,
    "CH4": 28,
    "N2O": 265,
}

# LHV 單位轉換因子 → TJ
LHV_CONVERSION = {
    "Kcal": 4.1868e-9,
    "MJ": 1e-6,
    "GJ": 1e-3,
}


def _parse_lhv_unit(lhv_unit: str) -> float:
    """
    解析 LHV 單位字串，回傳換算成 TJ 的乘數
    
    支援格式：
        "Kcal/公升", "Kcal/公斤", "Kcal/立方公尺"
        "MJ/公升", "MJ/公斤", "MJ/立方公尺"
        "GJ/公升", "GJ/公斤", "GJ/立方公尺"
    """
    lhv_unit = lhv_unit.strip()
    
    for prefix, factor in LHV_CONVERSION.items():
        if lhv_unit.startswith(prefix):
            return factor
    
    # 預設 fallback 為 Kcal
    return LHV_CONVERSION["Kcal"]


def tj_per_unit(lhv_value: float, lhv_unit: str) -> float:
    """
    將 LHV 換算為 TJ/活動單位
    
    例如：
        lhv_value=8400, lhv_unit="Kcal/公升" → 8400 × 4.1868e-9 = 3.5169e-5 TJ/公升
    """
    if not lhv_value or not lhv_unit:
        return 0.0
    
    conversion = _parse_lhv_unit(lhv_unit)
    return lhv_value * conversion


def calculate_single_gas(
    activity_value: float,
    factor_value: float,  # kg/TJ
    lhv_value: float,
    lhv_unit: str,
) -> float:
    """
    計算單一氣體排放量
    
    Args:
        activity_value: 活動數據數值（如 100.0 公升）
        factor_value: 官方排放係數（kg/TJ）
        lhv_value: 低位熱值數值
        lhv_unit: 低位熱值單位（如 "Kcal/公升"）
    
    Returns:
        排放量（kg），四捨五入到小數第 4 位
    """
    if not activity_value or not factor_value:
        return 0.0
    
    tj = tj_per_unit(lhv_value, lhv_unit)
    if not tj:
        return 0.0
    
    emission = activity_value * factor_value * tj
    
    # 四捨五入到小數第 4 位
    decimal_emission = Decimal(str(emission))
    rounded = decimal_emission.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return float(rounded)


def get_lhv_for_fuel(
    session: Session,
    original_code: str,
) -> tuple[float, str]:
    """
    取得燃料的 LHV。優先從 EmissionFactor 資料庫取，若無則 fallback 標準值。
    
    Returns:
        (lhv_value, lhv_unit)
    """
    # 先從資料庫取（任一筆即可，因為同一燃料的 LHV 相同）
    db_factor = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.original_code == original_code,
        )
    ).first()
    
    if db_factor and db_factor.lower_heating_value is not None and db_factor.lhv_unit:
        return db_factor.lower_heating_value, db_factor.lhv_unit
    
    # Fallback 標準值
    return get_lhv_value(original_code)


def calculate_emission_by_source(
    session: Session,
    original_code: str,
    activity_value: float,
    activity_unit: str,
    year: int,
    emission_type: str,
) -> dict[str, float]:
    """
    依燃料代碼計算 CO2 / CH4 / N2O / CO2e 排放量
    
    Args:
        session: DB session
        original_code: 燃料代碼（如 "170006"）
        activity_value: 活動數據數值
        activity_unit: 活動數據單位（如 "公升"）
        year: 年度
        emission_type: 排放類型（固定燃燒 / 移動燃燒）
    
    Returns:
        {
            "CO2": float,
            "CH4": float,
            "N2O": float,
            "CO2e": float,
        }
    """
    result = {
        "CO2": 0.0,
        "CH4": 0.0,
        "N2O": 0.0,
        "CO2e": 0.0,
    }
    
    if not activity_value:
        return result
    
    # 取得 LHV
    lhv_value, lhv_unit = get_lhv_for_fuel(session, original_code)
    if not lhv_value or not lhv_unit:
        return result
    
    # 查詢該燃料的各氣體係數
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
    
    # CO2e 也要四捨五入
    result["CO2e"] = float(
        Decimal(str(result["CO2e"])).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )
    
    return result


def calculate_emission_simple(
    activity_value: float,
    factor_value: float,
    lhv_value: float,
    lhv_unit: str,
) -> float:
    """
    簡易計算：不查資料庫，直接計算單一數值
    
    用於驗證測試
    """
    return calculate_single_gas(
        activity_value=activity_value,
        factor_value=factor_value,
        lhv_value=lhv_value,
        lhv_unit=lhv_unit,
    )
