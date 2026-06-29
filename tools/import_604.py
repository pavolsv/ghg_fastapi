"""
匯入 6.0.4 排放係數管理表 到 emission_factor_604 + factor_code_map

使用方式:
    python tools/import_604.py

來源:
    1. 溫室氣體排放係數管理表6.0.4(修) (4).ods  → Sheet 1~3 (CO2/CH4/N2O)
    2. 溫室氣體盤查作業相關代碼檔V2 (4).ods      → Section 8 (原燃物料代碼)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
from sqlmodel import Session, select, SQLModel
from database import engine, create_db_and_tables
from model import FactorCodeMap, EmissionFactor604


# 確保新表存在
create_db_and_tables()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FACTOR_FILE = os.path.join(BASE_DIR, "溫室氣體排放係數管理表6.0.4(修) (4).ods")
CODE_FILE = os.path.join(BASE_DIR, "溫室氣體盤查作業相關代碼檔V2 (4).ods")

# 6.0.4 Sheet 1~3 的建議排放係數欄位位置不同
SHEET_CONFIG = {
    "1_固定源與移動源(燃料)CO2排放係數": {"gas_type": "CO2", "factor_col": 17, "unit_col": 18},
    "2_固定源與移動源(燃料)CH4排放係數": {"gas_type": "CH4", "factor_col": 14, "unit_col": 15},
    "3_固定源與移動源(燃料)N2O排放係數": {"gas_type": "N2O", "factor_col": 14, "unit_col": 15},
}

EMISSION_TYPE_MAP = {
    "固定源": "固定燃燒",
    "移動源": "移動燃燒",
}

# 手動對照: 6.0.4 燃料名 → 代碼檔V2 code
# (那些無法自動 exact match 的 fuel)
FUEL_CODE_OVERRIDE = {
    "原料煤": "GG0703",
    "自產煤": "GG0704",
    "燃料煤": "070003",       # 煙煤
    "亞煙煤(發電)": "070003",  # 無對應亞煙煤 code，用煙煤
    "亞煙煤(其他)": "070003",
    "煤球": "GG0700",
    "油頁岩": "GG0701",
    "焦煤": "GG0702",
    "頁岩油": "GG1701",
    "奧里油": "GG1702",
    "天然氣凝結油": "050002",  # 天然氣
    "煉油氣": "350016",
    "焦爐氣": "350014",
    "石油腦": "170011",
    "柏油": "170017",
    "蒸餘油 (燃料油)": "170008",
    "蒸餘油(燃料油)": "170008",
    "天然氣凝結油(NGLs)": "050002",
    "液化石油氣": "350008",
    "液化石油氣(LPG)": "350008",
    "液化天然氣(LNG)": "050004",
    "一般廢棄物": "GG3801",
    "事業廢棄物": "GG3800",
    "木炭": "330202",
    "掩埋場沼氣": "180486",
    "污泥沼氣": "180486",
    "木頭－固態": "R-0701",
    "黑液": "170008",         # 近似燃料油
    "其他非化石燃料": "000099",
    "其他固體生質燃料": "GG3889",
    "生質汽油": "170001",     # 近似車用汽油
    "液化天然氣": "050004",
}


def build_code_map():
    """從代碼檔V2 Section 8 建立 fuel_name → code 對照"""
    print("讀取代碼檔V2...")
    df = pd.read_excel(CODE_FILE, sheet_name=1, engine="odf")
    sec8 = df.iloc[:, [34, 35, 36]].dropna(how="all")
    sec8.columns = ["seq", "code", "name"]

    code_map = {}
    for _, row in sec8.iterrows():
        name = str(row["name"]).strip()
        code = str(row["code"]).strip()
        code_map[name] = code

    return code_map


def resolve_code(fuel_name, code_map):
    """給 fuel_name 回傳對應的 code"""
    # 1. exact match
    if fuel_name in code_map:
        return code_map[fuel_name]
    # 2. override
    if fuel_name in FUEL_CODE_OVERRIDE:
        return FUEL_CODE_OVERRIDE[fuel_name]
    # 3. 去掉括弧嘗試
    base = fuel_name.split("(")[0].split("（")[0].strip()
    if base in code_map:
        return code_map[base]
    # 4. substring match (V2 名包含 fuel_name)
    for vname, vcode in code_map.items():
        if fuel_name in vname:
            return vcode
    return None


def parse_sheet(sheet_name, config, code_map):
    """解析單一 sheet，回傳 [(code, gas_type, emission_type, name, factor_value, unit)]"""
    print(f"  解析 {sheet_name}...")
    df = pd.read_excel(FACTOR_FILE, sheet_name=sheet_name, engine="odf", header=None)
    data = df.iloc[6:].copy()

    # forward-fill emission_type (合併儲存格)
    data[1] = data[1].ffill()

    rows = []
    for i in range(len(data)):
        r = data.iloc[i]
        fuel = r.iloc[3]
        etype_raw = str(r.iloc[1]).strip()
        factor_raw = r.iloc[config["factor_col"]]
        unit_raw = r.iloc[config["unit_col"]]

        if pd.isna(fuel) or str(fuel).strip() in ("", "NaN", "nan"):
            continue

        fuel_name = str(fuel).strip()

        # 跳過註解行
        if fuel_name.startswith("註") or fuel_name == "NaN":
            continue

        # 跳過建議排放係數為 "-" 的行
        factor_str = str(factor_raw).strip()
        if factor_str in ("", "-", "NaN", "nan"):
            continue

        # 轉 emission_type
        emission_type = EMISSION_TYPE_MAP.get(etype_raw)
        if not emission_type:
            continue

        # 解析數值（四捨五入到小數第 10 位）
        try:
            factor_value = float(Decimal(factor_str).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP))
        except ValueError:
            continue

        unit = str(unit_raw).strip() if pd.notna(unit_raw) else ""

        # 查代碼
        code = resolve_code(fuel_name, code_map)
        if not code:
            print(f"    [WARN] 無法對照代碼: {fuel_name}，跳過")
            continue

        rows.append((code, config["gas_type"], emission_type, fuel_name, factor_value, unit))

    return rows


def main():
    print("=" * 60)
    print("6.0.4 排放係數匯入工具")
    print("=" * 60)

    # 1. 建立 code map
    code_map = build_code_map()
    print(f"  代碼檔V2 共 {len(code_map)} 筆對照")

    # 2. 解析 sheets
    all_rows = []
    for sheet_name, config in SHEET_CONFIG.items():
        rows = parse_sheet(sheet_name, config, code_map)
        print(f"    取得 {len(rows)} 筆")
        all_rows.extend(rows)

    print(f"\n總計解析 {len(all_rows)} 筆資料")

    # 3. 寫入資料庫
    print("\n寫入資料庫...")
    with Session(engine) as session:
        # 清空舊資料
        for obj in session.exec(select(FactorCodeMap)).all():
            session.delete(obj)
        for obj in session.exec(select(EmissionFactor604)).all():
            session.delete(obj)
        session.commit()

        # 寫入 factor_code_map
        seen_codes = set()
        for code, gas_type, emission_type, name, factor_value, unit in all_rows:
            if code not in seen_codes:
                seen_codes.add(code)
                fcm = FactorCodeMap(
                    code=code,
                    fuel_name_zh=name,
                    emission_type=emission_type,
                )
                session.add(fcm)

        # 寫入 emission_factor_604
        for code, gas_type, emission_type, name, factor_value, unit in all_rows:
            pk = f"{code}_{gas_type}_{emission_type}_{name}"
            ef = EmissionFactor604(
                code=pk,
                original_code=code,
                gas_type=gas_type,
                emission_type=emission_type,
                name=name,
                factor_value=factor_value,
                unit=unit,
                year=2023,
            )
            session.add(ef)

        session.commit()
        print(f"  寫入 factor_code_map: {len(seen_codes)} 筆")
        print(f"  寫入 emission_factor_604: {len(all_rows)} 筆")

    # 4. 驗證
    print("\n驗證資料...")
    with Session(engine) as session:
        fcm_count = session.exec(select(FactorCodeMap)).all()
        ef_count = session.exec(select(EmissionFactor604)).all()
        print(f"  factor_code_map: {len(fcm_count)} 筆")
        print(f"  emission_factor_604: {len(ef_count)} 筆")

    print("\n匯入完成")


if __name__ == "__main__":
    main()
