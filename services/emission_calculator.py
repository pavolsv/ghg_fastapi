"""
排放計算核心服務（v2）

計算方式：活動數據 × 官方公告排放係數（EmissionFactor604）
完全移除低位熱值（LHV）與 TJ 換算層。

支援排放類型：
1. 固定燃燒 / 移動燃燒：
   排放量(kg) = 活動數據 × EmissionFactor604.factor_value
   CO2e = CO₂×1 + CH₄×28 + N₂O×265

2. 能源間接排放（電力）：
   CO2e(kg) = 用電度數 × 當年度電力排放係數

3. 逸散排放（冷媒）：
    CO2e(kg) = 活動數據(kg) × GWP × 設備洩漏率

結果四捨五入到小數第 4 位（ROUND_HALF_UP）。
"""

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from constants.refrigerant_factors import get_rate_by_code
from model import Device, EmissionFactor604, GWPReference


GWP_VALUES = {
    "CO2": 1,
    "CH4": 28,
    "N2O": 265,
}

# 係數單位 → 活動數據單位
# 例如 KgCO2/L 代表活動數據應以「公升」輸入
_FACTOR_UNIT_TO_ACTIVITY_UNIT = {
    "KgCO2/Kg": "公斤",
    "KgCH4/Kg": "公斤",
    "KgN2O/Kg": "公斤",
    "KgCO2/L": "公升",
    "KgCH4/L": "公升",
    "KgN2O/L": "公升",
    "KgCO2/M3": "立方公尺",
    "KgCH4/M3": "立方公尺",
    "KgN2O/M3": "立方公尺",
    "kgCO2e/kWh": "度",
}


class EmissionResult(BaseModel):
    co2: float
    ch4: float
    n2o: float
    co2e: float
    factor_year: Optional[int]
    gwp_version: str
    activity_unit: Optional[str]
    factor_source: str
    details: dict


def _round4(value: float) -> float:
    decimal_val = Decimal(str(value))
    return float(decimal_val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _round10(value: float) -> float:
    decimal_val = Decimal(str(value))
    return float(decimal_val.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP))


def _normalize_factor_unit(unit: str) -> str:
    u = (unit or "").strip().replace(" ", "").replace("/", "/")
    return u


def parse_activity_unit(factor_unit: str) -> Optional[str]:
    """從 EmissionFactor604 的 unit 解析活動數據應使用的單位。"""
    u = _normalize_factor_unit(factor_unit)
    # 先精確比對
    if u in _FACTOR_UNIT_TO_ACTIVITY_UNIT:
        return _FACTOR_UNIT_TO_ACTIVITY_UNIT[u]
    # 模糊比對（大小寫不敏感）
    u_upper = u.upper()
    if "/KG" in u_upper:
        return "公斤"
    if "/L" in u_upper:
        return "公升"
    if "/M3" in u_upper or "/M³" in u_upper:
        return "立方公尺"
    if "/KWH" in u_upper:
        return "度"
    return None


def get_factor_604(
    session: Session,
    original_code: str,
    emission_type: str,
    gas_type: str,
    year: Optional[int] = None,
) -> Optional[EmissionFactor604]:
    """查詢官方公告係數，回傳的 factor_value 四捨五入到小數第 10 位。"""
    query = select(EmissionFactor604).where(
        EmissionFactor604.original_code == original_code,
        EmissionFactor604.emission_type == emission_type,
        EmissionFactor604.gas_type == gas_type,
    )
    if year is not None:
        year_query = query.where(EmissionFactor604.year == year)
        result = session.exec(year_query).first()
        if result:
            result.factor_value = _round10(result.factor_value)
            return result
    result = session.exec(query).first()
    if result:
        result.factor_value = _round10(result.factor_value)
    return result


def _validate_activity_value(value: float) -> None:
    if value < 0:
        raise ValueError("活動數據不可為負數")


def _validate_activity_unit(factor_unit: str, activity_unit: str) -> None:
    expected = parse_activity_unit(factor_unit)
    if expected and activity_unit != expected:
        raise ValueError(
            f"活動數據單位「{activity_unit}」與係數單位「{factor_unit}」不一致，應使用「{expected}」"
        )


def calculate_combustion_emission_v2(
    session: Session,
    original_code: str,
    emission_type: str,
    activity_value: float,
    activity_unit: str,
    year: Optional[int] = None,
) -> EmissionResult:
    """固定/移動燃燒排放計算（使用 EmissionFactor604）。"""
    _validate_activity_value(activity_value)

    gases = {"CO2": 0.0, "CH4": 0.0, "N2O": 0.0}
    details = {"factors": {}, "missing": []}
    factor_year = year

    for gas in ("CO2", "CH4", "N2O"):
        factor = get_factor_604(
            session=session,
            original_code=original_code,
            emission_type=emission_type,
            gas_type=gas,
            year=year,
        )
        if not factor or factor.factor_value is None:
            details["missing"].append(gas)
            details["factors"][gas] = None
            continue

        _validate_activity_unit(factor.unit, activity_unit)

        emission = activity_value * factor.factor_value
        gases[gas] = emission
        details["factors"][gas] = {
            "factor_value": factor.factor_value,
            "unit": factor.unit,
            "year": factor.year,
        }
        if factor_year is None:
            factor_year = factor.year

    co2e = _round4(
        gases["CO2"] * GWP_VALUES["CO2"]
        + gases["CH4"] * GWP_VALUES["CH4"]
        + gases["N2O"] * GWP_VALUES["N2O"]
    )

    return EmissionResult(
        co2=gases["CO2"],
        ch4=gases["CH4"],
        n2o=gases["N2O"],
        co2e=co2e,
        factor_year=factor_year or 2023,
        gwp_version="AR5",
        activity_unit=activity_unit,
        factor_source="EmissionFactor604",
        details=details,
    )


def calculate_electricity_emission_v2(
    session: Session,
    activity_value: float,
    target_year: int,
    activity_unit: str = "度",
) -> EmissionResult:
    """電力排放計算（依 target_year 選對應年度係數）。"""
    _validate_activity_value(activity_value)

    factor = session.exec(
        select(EmissionFactor604).where(
            EmissionFactor604.original_code == "ELECTRICITY",
            EmissionFactor604.gas_type == "CO2e",
            EmissionFactor604.code == str(target_year),
        )
    ).first()

    if not factor:
        # fallback：取最新年度
        factor = session.exec(
            select(EmissionFactor604)
            .where(
                EmissionFactor604.original_code == "ELECTRICITY",
                EmissionFactor604.gas_type == "CO2e",
            )
            .order_by(EmissionFactor604.year.desc())
        ).first()

    if not factor or factor.factor_value is None:
        raise ValueError(f"找不到 {target_year} 年或最新的電力排放係數")

    _validate_activity_unit(factor.unit, activity_unit)

    co2e = _round4(activity_value * factor.factor_value)

    return EmissionResult(
        co2=co2e,
        ch4=0.0,
        n2o=0.0,
        co2e=co2e,
        factor_year=factor.year,
        gwp_version="AR5",
        activity_unit=activity_unit,
        factor_source="EmissionFactor604",
        details={
            "factor_value": factor.factor_value,
            "unit": factor.unit,
            "year": factor.year,
        },
    )


def _lookup_gwp(session: Session, refrigerant_code: str) -> float:
    """從 GWPReference 查詢 GWP 值。找不到時靜默回傳 0。"""
    gwp_ref = session.exec(
        select(GWPReference).where(GWPReference.formula == refrigerant_code)
    ).first()
    if gwp_ref and gwp_ref.gwp_value:
        return float(gwp_ref.gwp_value)
    all_gwps = session.exec(select(GWPReference)).all()
    code = (refrigerant_code or "").strip()
    for g in all_gwps:
        if code and (code == (g.formula or "").strip()
                     or code == (g.gas_name_zh or "").strip()
                     or code == (g.gas_name_en or "").strip()):
            return float(g.gwp_value or 0)
    return 0.0


def _convert_to_kg(value: float, unit: str) -> float:
    """將活動數據依單位換算成公斤。僅接受「公斤」「公克」。"""
    u = (unit or "").strip()
    if u == "公斤":
        return value
    if u == "公克":
        return value / 1000.0
    raise ValueError(
        f"冷媒活動數據單位「{unit or '(空)'}」不支援，僅接受「公斤」或「公克」"
    )


def calculate_refrigerant_emission_v2(
    session: Session,
    refrigerant_code: str,
    activity_value: float,
    activity_unit: str = "",
    equipment_category: str = "",
) -> EmissionResult:
    """冷媒逸散排放計算（以活動數據為主）。

    公式: co2e(kg) = activity(kg) × GWP × 洩漏率
    單位: 僅接受「公斤」或「公克」（內部統一轉成公斤）
    必填: refrigerant_code、equipment_category
    靜默: GWP 查不到時 co2e=0
    """
    _validate_activity_value(activity_value)

    if not refrigerant_code:
        raise ValueError("冷媒代碼不可為空")

    if not equipment_category:
        raise ValueError("設備類別不可為空")

    activity_kg = _convert_to_kg(activity_value, activity_unit)
    gwp_value = _lookup_gwp(session, refrigerant_code)
    emission_rate = get_rate_by_code(equipment_category)

    if emission_rate is None:
        raise ValueError(f"找不到設備類別「{equipment_category}」的洩漏率")

    co2e = _round4(activity_kg * gwp_value * emission_rate)

    return EmissionResult(
        co2=0.0,
        ch4=0.0,
        n2o=0.0,
        co2e=co2e,
        factor_year=None,
        gwp_version="AR5",
        activity_unit=activity_unit or "公斤",
        factor_source="GWPReference",
        details={
            "activity_value": activity_value,
            "activity_unit": activity_unit or "公斤",
            "activity_kg": activity_kg,
            "gwp_value": gwp_value,
            "emission_rate": emission_rate,
            "refrigerant_code": refrigerant_code,
        },
    )


def compute_total_co2e_for_device_v2(
    session: Session,
    device: Device,
    activity_data: float,
    activity_unit: Optional[str] = None,
    target_year: Optional[int] = None,
) -> EmissionResult:
    """根據設備排放類型計算排放量，作為單一計算入口。"""
    etype = (device.emission_type or "").strip()
    unit = (activity_unit or device.unit or "").strip()

    if etype == "逸散排放" and device.refrigerant_code:
        return calculate_refrigerant_emission_v2(
            session=session,
            refrigerant_code=device.refrigerant_code,
            activity_value=activity_data,
            activity_unit=unit,
            equipment_category=device.equipment_category or "",
        )

    if etype == "能源間接排放" or device.factor_ref_code == "ELECTRICITY":
        year = target_year
        if year is None:
            # 嘗試從 record_date 或當前年度推斷
            year = datetime.now().year
        return calculate_electricity_emission_v2(
            session=session,
            activity_value=activity_data,
            target_year=year,
            activity_unit=unit or "度",
        )

    # 固定燃燒 / 移動燃燒
    return calculate_combustion_emission_v2(
        session=session,
        original_code=device.factor_ref_code or "",
        emission_type=etype or "固定燃燒",
        activity_value=activity_data,
        activity_unit=unit,
    )


# 向後相容舊函式名稱（僅保留介面，內部轉調 v2）
# 若未來完全移除，可刪除以下別名
def calculate_combustion_emission(*args, **kwargs):
    raise RuntimeError("已棄用，請使用 calculate_combustion_emission_v2")


def calculate_electricity_emission(*args, **kwargs):
    raise RuntimeError("已棄用，請使用 calculate_electricity_emission_v2")


def calculate_refrigerant_emission(*args, **kwargs):
    raise RuntimeError("已棄用，請使用 calculate_refrigerant_emission_v2")


def compute_total_co2e_for_device(*args, **kwargs):
    raise RuntimeError("已棄用，請使用 compute_total_co2e_for_device_v2")
