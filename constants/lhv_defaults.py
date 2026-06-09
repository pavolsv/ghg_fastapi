"""
標準低位熱值（LHV）參考表

資料來源：台灣環境部溫室氣體盤查指引常用參考值
單位換算基礎：1 kcal = 4.1868 × 10⁻⁹ TJ

key: original_code（來自清冊表單附表一的燃料代碼）
value: { "value": 數值, "unit": 單位, "name": 中文名稱 }
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

LHV_BY_NAME: dict[str, dict[str, str | float]] = {
    # 固體燃料 (公斤)
    "無煙煤": {"value": 6800.0, "unit": "Kcal/公斤"},
    "煉焦煤": {"value": 7200.0, "unit": "Kcal/公斤"},
    "其他煙煤": {"value": 5800.0, "unit": "Kcal/公斤"},
    "亞煙煤": {"value": 5300.0, "unit": "Kcal/公斤"},
    "褐煤": {"value": 3800.0, "unit": "Kcal/公斤"},
    "泥煤": {"value": 3500.0, "unit": "Kcal/公斤"},
    "木炭": {"value": 7000.0, "unit": "Kcal/公斤"},
    "煤球": {"value": 6500.0, "unit": "Kcal/公斤"},
    "焦炭": {"value": 6800.0, "unit": "Kcal/公斤"},
    "煤焦油": {"value": 9000.0, "unit": "Kcal/公斤"},
    "石油焦": {"value": 8200.0, "unit": "Kcal/公斤"},
    "石蠟": {"value": 10000.0, "unit": "Kcal/公斤"},
    "瀝青": {"value": 9500.0, "unit": "Kcal/公斤"},
    "木材/廢材": {"value": 3800.0, "unit": "Kcal/公斤"},
    "其他初級固體生質": {"value": 3500.0, "unit": "Kcal/公斤"},
    "事業廢棄物": {"value": 2500.0, "unit": "Kcal/公斤"},
    "都市廢棄物-非生質部分": {"value": 2200.0, "unit": "Kcal/公斤"},
    "都市廢棄物 - 非生質部分": {"value": 2200.0, "unit": "Kcal/公斤"},
    "油頁岩/焦油砂": {"value": 4500.0, "unit": "Kcal/公斤"},

    # 液體燃料 (公升)
    "原油": {"value": 9000.0, "unit": "Kcal/公升"},
    "頁岩油": {"value": 9200.0, "unit": "Kcal/公升"},
    "奧里油": {"value": 9300.0, "unit": "Kcal/公升"},
    "石油腦": {"value": 10500.0, "unit": "Kcal/公升"},
    "車用汽油": {"value": 7800.0, "unit": "Kcal/公升"},
    "車用汽油-氧化觸媒": {"value": 7800.0, "unit": "Kcal/公升"},
    "航空汽油/航空燃油-汽油型": {"value": 8100.0, "unit": "Kcal/公升"},
    "航空燃油-煤油型": {"value": 8500.0, "unit": "Kcal/公升"},
    "煤油": {"value": 8500.0, "unit": "Kcal/公升"},
    "其他煤油": {"value": 8500.0, "unit": "Kcal/公升"},
    "柴油": {"value": 8400.0, "unit": "Kcal/公升"},
    "燃料油": {"value": 9500.0, "unit": "Kcal/公升"},
    "液化石油氣": {"value": 10800.0, "unit": "Kcal/公升"},
    "液化天然氣": {"value": 10500.0, "unit": "Kcal/公斤"},
    "乙烷": {"value": 11500.0, "unit": "Kcal/公升"},
    "潤滑油": {"value": 10000.0, "unit": "Kcal/公升"},
    "廢油": {"value": 9000.0, "unit": "Kcal/公升"},
    "生質柴油/生質汽油": {"value": 8100.0, "unit": "Kcal/公升"},
    "生質柴油": {"value": 8100.0, "unit": "Kcal/公升"},
    "生質汽油": {"value": 7800.0, "unit": "Kcal/公升"},
    "其他液體生質燃料": {"value": 7500.0, "unit": "Kcal/公升"},
    "其他石油產品": {"value": 9500.0, "unit": "Kcal/公升"},

    # 氣體燃料 (立方公尺)
    "天然氣": {"value": 8900.0, "unit": "Kcal/立方公尺"},
    "焦爐氣": {"value": 4500.0, "unit": "Kcal/立方公尺"},
    "煉油氣": {"value": 11000.0, "unit": "Kcal/立方公尺"},
    "高爐氣": {"value": 800.0, "unit": "Kcal/立方公尺"},
    "轉爐氣": {"value": 1800.0, "unit": "Kcal/立方公尺"},
    "掩埋沼氣/污泥沼氣": {"value": 5000.0, "unit": "Kcal/立方公尺"},
    "掩埋沼氣": {"value": 5000.0, "unit": "Kcal/立方公尺"},
    "污泥沼氣": {"value": 5000.0, "unit": "Kcal/立方公尺"},
    "煤氣廠氣體": {"value": 4000.0, "unit": "Kcal/立方公尺"},
    "其他氣體生質燃料": {"value": 5000.0, "unit": "Kcal/立方公尺"},

    # 外購能源
    "電力": {"value": None, "unit": None},
    "蒸氣": {"value": None, "unit": None},

    # 逸散排放 (GWP-based, 無 LHV)
    "GWP": {"value": None, "unit": None},
    "氮氣": {"value": None, "unit": None},
    "甲烷": {"value": None, "unit": None},

    # 製程排放
    "石灰石": {"value": None, "unit": None},
    "碳": {"value": None, "unit": None},
    "碳酸鹽": {"value": None, "unit": None},
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


def get_lhv_by_name(material_name: str) -> tuple[float | None, str | None]:
    """
    依物料中文名稱取得預設 LHV 數值與單位
    回傳: (value, unit) 或 (None, None)
    """
    data = LHV_BY_NAME.get(material_name)
    if data and data.get("value") is not None:
        return float(data["value"]), str(data["unit"])
    return None, None


def get_lhv_unit_options() -> list[str]:
    """取得所有可選的 LHV 單位"""
    return [
        "公斤/兆焦耳(kg/TJ)",
        "千卡/公升(Kcal/l)",
    ]


def convert_lhv(value: float, from_unit: str, to_unit: str) -> float:
    """
    LHV 單位換算
    支援: 千卡/公升(Kcal/l), 公斤/兆焦耳(kg/TJ), 公斤/千卡(Kg/Kcal)
    """
    if from_unit == to_unit:
        return value

    # 統一先轉成 Kcal/l
    if from_unit == "千卡/公升(Kcal/l)":
        kcal_per_l = value
    elif from_unit == "公斤/兆焦耳(kg/TJ)":
        # 1 Kcal = 4.1868 × 10⁻⁶ MJ
        # 1 kg/TJ = 1/(10⁶) kg/MJ = 1/(10⁶ × 4.1868 × 10⁻⁶) Kcal/l
        # ≈ 0.2388 Kcal/l
        kcal_per_l = value / 0.2388458966
    elif from_unit == "公斤/千卡(Kg/Kcal)":
        # 1 Kcal/l → reciprocal = 1 Kg/Kcal (if density = 1)
        # 1 Kg/Kcal ≈ 4186.8 Kcal/l
        kcal_per_l = 1.0 / value if value != 0 else 0
    else:
        kcal_per_l = value

    # 從 Kcal/l 轉成目標單位
    if to_unit == "千卡/公升(Kcal/l)":
        return kcal_per_l
    elif to_unit == "公斤/兆焦耳(kg/TJ)":
        return kcal_per_l * 0.2388458966
    elif to_unit == "公斤/千卡(Kg/Kcal)":
        return 1.0 / kcal_per_l if kcal_per_l != 0 else 0
    else:
        return kcal_per_l