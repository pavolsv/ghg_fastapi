"""
標準低位熱值（LHV）參考表

資料來源：台灣環境部溫室氣體盤查指引常用參考值
單位換算基礎：1 kcal = 4.1868 × 10⁻⁹ TJ

key: original_code（來自清冊表單附表一的燃料代碼）
value: { "value": 數值, "unit": "Kcal/公升" 或 "Kcal/公斤" 或 "Kcal/立方公尺" }
"""

LHV_DEFAULTS: dict[str, dict[str, str | float]] = {
    # 液體燃料
    "170006": {"value": 8400.0, "unit": "Kcal/公升", "name": "柴油"},
    "170001": {"value": 7800.0, "unit": "Kcal/公升", "name": "車用汽油"},
    "170005": {"value": 8500.0, "unit": "Kcal/公升", "name": "煤油"},
    "170019": {"value": 9500.0, "unit": "Kcal/公升", "name": "燃料油"},
    "050001": {"value": 9000.0, "unit": "Kcal/公升", "name": "原油"},
    "050004": {"value": 10500.0, "unit": "Kcal/公斤", "name": "液化天然氣"},

    # 氣體燃料
    "050002": {"value": 8900.0, "unit": "Kcal/立方公尺", "name": "天然氣"},

    # 固體燃料
    "020012": {"value": 7000.0, "unit": "Kcal/公斤", "name": "木炭"},
    "070001": {"value": 3500.0, "unit": "Kcal/公斤", "name": "泥煤"},
}


def get_lhv_default(original_code: str) -> dict[str, str | float] | None:
    """依燃料代碼取得預設 LHV，若無則回傳 None"""
    return LHV_DEFAULTS.get(original_code)


def get_lhv_value(original_code: str) -> tuple[float, str] | tuple[None, None]:
    """
    依燃料代碼取得預設 LHV 數值與單位
    回傳: (value, unit) 或 (None, None)
    """
    data = LHV_DEFAULTS.get(original_code)
    if data:
        return float(data["value"]), str(data["unit"])
    return None, None
