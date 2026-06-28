"""
冷媒設備排放係數對照表（來自 6.0.4 Sheet 8，取 IPCC 範圍中間值）
固定排放係數 = 年設備洩漏率（作為逸散排放計算用）
"""

REFRIGERANT_EQUIPMENT = {
    "4090": {"name": "移動式空氣清靜機", "rate": 0.15},
    "4091": {"name": "住宅及商業建築冷氣機", "rate": 0.055},
    "4092": {"name": "冰水機", "rate": 0.085},
    "4093": {"name": "工業冷凍、冷藏裝備，包括食品加工及冷藏", "rate": 0.16},
    "4094": {"name": "交通用冷凍、冷藏裝備", "rate": 0.325},
    "4095": {"name": "中、大型冷凍、冷藏裝備", "rate": 0.225},
    "4096": {"name": "獨立商用冷凍、冷藏裝備", "rate": 0.08},
    "4097": {"name": "家用冷凍、冷藏裝備", "rate": 0.003},
}

# 方便前端/後端快速查詢
def get_refrigerant_categories():
    return [
        {"code": code, "name": info["name"], "rate": info["rate"]}
        for code, info in REFRIGERANT_EQUIPMENT.items()
    ]


def get_rate_by_code(code: str) -> float:
    return REFRIGERANT_EQUIPMENT.get(code, {}).get("rate", 0.0)


def get_name_by_code(code: str) -> str:
    return REFRIGERANT_EQUIPMENT.get(code, {}).get("name", "")
