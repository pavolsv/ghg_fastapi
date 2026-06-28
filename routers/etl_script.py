import os
from typing import Optional
from datetime import datetime

import pandas as pd
import requests
import urllib3
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from audit_log import add_change_log
from database import engine
from model import AppendixReference, EmissionFactor604, ETLStatus, GWPReference, FactorCodeMap

# Allow disabling SSL verification only in dev/test via environment variable.
VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() != "false"
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/etl", tags=["etl"])
templates = Jinja2Templates(directory="templates")

URL_REGISTRY = {
    "fuel": "https://ghgregistry.moenv.gov.tw/upload/Tools/AI/溫室氣體排放量清冊表單(範例).ods",
    "electricity": "https://www.taipower.com.tw/chart/data/台電系統發購電量及電力排碳係數(105-113).csv",
}


def generate_fuel_code(material_code: str, year: int, category: str) -> str:
    """生成複合代碼，區分固定 (F) 或移動 (M)"""
    year_suffix = str(year)[-2:]
    clean_code = str(material_code).strip()
    prefix = "F" if "固定" in category else "M"
    return f"{prefix}{clean_code}-{year_suffix}"


def process_appendix_one(file_path: str, year: int = 2023):
    """
    1. 跳過前兩行說明
    2. 使用 iloc 鎖定 A, B, C, D, E, I, J 欄
    3. 使用 ffill 補全合併儲存格產生的 NaN (解決 NOT NULL 報錯)
    """
    df = pd.read_excel(file_path, sheet_name="附表一", header=None, skiprows=1)

    # 鎖定欄位：A=0(scope), B=1(cat), C=2(gas), D=3(m_code), E=4(m_name), I=8(value), J=9(unit)
    df = df.iloc[:, [0, 1, 2, 3, 4, 8, 9]]
    df.columns = ["scope", "cat", "gas", "m_code", "m_name", "value", "unit"]

    # 核心修正：補全合併儲存格，讓 CH4 和 N2O 繼承名稱與代碼
    fill_cols = ["scope", "cat", "m_code", "m_name"]
    df[fill_cols] = df[fill_cols].ffill()

    # 清除關鍵欄位為空的行 (如係數值未填)
    df = df.dropna(subset=["m_code", "gas", "value"])

    rows = []
    for _, row in df.iterrows():
        m_name = str(row["m_name"]).strip()
        category = str(row["cat"]).strip()

        # 原始代碼，如 070002
        raw_m_code = str(row["m_code"]).strip()
        # 您的業務 ID，如 F070002-23
        final_code = generate_fuel_code(raw_m_code, year, category)

        rows.append(
            {
                "code": final_code,
                "gas_type": str(row["gas"]).strip(),
                "original_code": raw_m_code,  # 增加此欄位儲存
                "name": m_name,
                "factor_value": float(row["value"]),
                "unit": str(row["unit"]).strip(),
                "year": year,
                "emission_type": category,
            }
        )

    return pd.DataFrame(rows)


def process_utility_electricity(file_path: str):
    """
    處理單頁電力數據 (對應 image_140962.png)
    1. CSV 或 Excel 讀取
    2. 鎖定年度與係數欄位
    """
    try:
        # 如果網址是 CSV 則用 read_csv，否則用 read_excel
        if file_path.endswith(".csv"):
            df = pd.read_csv(
                file_path, encoding="utf-8-sig"
            )  # utf-8-sig 處理 Excel 產生的 CSV 亂碼
        else:
            # 只有一頁時不需指定 sheet_name，預設讀取第一頁
            df = pd.read_excel(file_path, header=0)

        # 清洗資料：移除空行，確保年度與係數是數值
        df = df.dropna(subset=["年度", "電力排碳係數"])

        rows = []
        for _, row in df.iterrows():
            year_val = int(row["年度"])
            # 僅抓取關鍵年份，如 2017-2024
            if 2010 <= year_val <= 2030:
                factor_val = float(row["電力排碳係數"])

                rows.append(
                    {
                        "code": f"E-{year_val}",
                        "gas_type": "CO2e",
                        "original_code": "ELECTRICITY",
                        "name": f"{year_val}年電力排放係數",
                        "factor_value": factor_val,
                        "unit": "公斤/度",
                        "year": year_val,
                        "emission_type": "能源間接排放",  # ISO 類別 2
                    }
                )
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"電力解析錯誤: {e}")
        return pd.DataFrame()


@router.get("/", response_class=HTMLResponse)
async def etl_page(request: Request):
    with Session(engine) as session:
        fuel_count = session.exec(
            select(EmissionFactor604).where(
                EmissionFactor604.original_code != "ELECTRICITY"
            )
        ).all()
        elec_count = session.exec(
            select(EmissionFactor604).where(
                EmissionFactor604.original_code == "ELECTRICITY"
            )
        ).all()
        gwp_count = session.exec(select(GWPReference)).all()
        code_count = session.exec(select(AppendixReference)).all()

    stats = {
        "fuel": {"count": len(fuel_count), "label": "燃料係數", "icon": "flame"},
        "electricity": {"count": len(elec_count), "label": "電力係數", "icon": "zap"},
        "gwp": {"count": len(gwp_count), "label": "GWP 溫暖化潛勢", "icon": "snowflake"},
        "codes": {"count": len(code_count), "label": "代碼檔", "icon": "book-open"},
    }

    return templates.TemplateResponse(
        "etl.html", {
            "request": request,
            "stats": stats,
        }
    )


def process_refrigerant_appendix(file_path, year):
    pass


@router.get("/manage", response_class=HTMLResponse)
async def factor_management(
    request: Request,
    name: Optional[str] = None,
    gas_type: Optional[str] = None,
    category: Optional[str] = None,
    year: Optional[str] = None,
):
    # ── 逸散排放 → 查詢 GWPReference ──────────────────────────────
    if category == "逸散排放":
        with Session(engine) as session:
            gwp_query = session.query(GWPReference)
            if name:
                gwp_query = gwp_query.filter(
                    (col(GWPReference.gas_name_zh).contains(name)) |
                    (col(GWPReference.gas_name_en).contains(name)) |
                    (col(GWPReference.formula).contains(name))
                )
            if gas_type:  # 前端 gas_type 下拉重新利用為 version 篩選
                gwp_query = gwp_query.filter(col(GWPReference.version) == gas_type)
            gwp_factors = gwp_query.order_by(col(GWPReference.formula).asc()).all()
            version_list = sorted(
                {v[0] for v in session.query(col(GWPReference.version)).distinct().all() if v[0]}
            )
        return templates.TemplateResponse(
            "factor_management.html",
            {
                "request": request,
                "factors": [],
                "gwp_factors": gwp_factors,
                "name_list": [],
                "gas_list": version_list,
                "active_category": "逸散排放",
                "is_gwp": True,
            },
        )

    # ── EmissionFactor604（其他排放類型）────────────────────────────────
    with Session(engine) as session:
        query = session.query(EmissionFactor604)

        if name:
            query = query.filter(col(EmissionFactor604.name).contains(name))
        if category:
            query = query.filter(col(EmissionFactor604.emission_type).contains(category))
        if gas_type:
            matching_codes = [
                row[0]
                for row in session.query(col(EmissionFactor604.code))
                .filter(col(EmissionFactor604.gas_type) == gas_type)
                .distinct()
                .all()
            ]
            query = query.filter(col(EmissionFactor604.code).in_(matching_codes))

        factors = query.order_by(col(EmissionFactor604.code).asc()).all()

        # 依 (original_code, emission_type) 分組，將 CO2/CH4/N2O 各 gas_type 樞紐為欄位
        # 但若同組內有多個不同 code（如電力每年不同），則各 code 獨立一列
        grouped_dict: dict = {}
        for f in factors:
            if f.original_code == "ELECTRICITY":
                key = f.code
            else:
                key = (f.original_code, f.emission_type)
            if key not in grouped_dict:
                grouped_dict[key] = {
                    "code": f.original_code if f.original_code != "ELECTRICITY" else f.code,
                    "name": f.name,
                    "unit": f.unit,
                    "original_code": f.original_code,
                    "gas_values": {},
                    "gas_factors": {},
                }
            grouped_dict[key]["gas_values"][f.gas_type] = f.factor_value
            grouped_dict[key]["gas_factors"][f.gas_type] = {
                "gas_type": f.gas_type,
                "factor_value": f.factor_value,
                "unit": f.unit,
            }
        grouped_factors = list(grouped_dict.values())

        name_list = [
            n[0] for n in session.query(col(EmissionFactor604.name)).distinct().all() if n[0]
        ]
        gas_list = [
            g[0]
            for g in session.query(col(EmissionFactor604.gas_type)).distinct().all()
            if g[0]
        ]

    return templates.TemplateResponse(
        "factor_management.html",
        {
            "request": request,
            "factors": factors,
            "grouped_factors": grouped_factors,
            "gwp_factors": [],
            "name_list": name_list,
            "gas_list": gas_list,
            "active_category": category or "",
            "is_gwp": False,
        },
    )


# ── GWP CRUD（逸散排放用）────────────────────────────────────────
@router.post("/gwp/create")
async def gwp_create(
    formula: str = Form(...),
    gas_name_zh: str = Form(...),
    gas_name_en: str = Form(""),
    gwp_value: float = Form(0.0),
    version: str = Form("AR5"),
    is_qualitative: bool = Form(False),
    note: Optional[str] = Form(None),
):
    with Session(engine) as session:
        session.add(GWPReference(
            formula=formula,
            gas_name_zh=gas_name_zh,
            gas_name_en=gas_name_en,
            gwp_value=gwp_value,
            version=version,
            is_qualitative=is_qualitative,
            note=note or None,
        ))
        session.commit()
    return RedirectResponse(url="/etl/manage?category=逸散排放", status_code=303)


@router.post("/gwp/update/{record_id}")
async def gwp_update(
    record_id: int,
    formula: str = Form(...),
    gas_name_zh: str = Form(...),
    gas_name_en: str = Form(""),
    gwp_value: float = Form(0.0),
    version: str = Form("AR5"),
    is_qualitative: bool = Form(False),
    note: Optional[str] = Form(None),
):
    with Session(engine) as session:
        record = session.get(GWPReference, record_id)
        if record:
            record.formula = formula
            record.gas_name_zh = gas_name_zh
            record.gas_name_en = gas_name_en
            record.gwp_value = gwp_value
            record.version = version
            record.is_qualitative = is_qualitative
            record.note = note or None
            session.add(record)
            session.commit()
    return RedirectResponse(url="/etl/manage?category=逸散排放", status_code=303)


@router.post("/gwp/delete")
async def gwp_delete(record_id: int = Form(...)):
    with Session(engine) as session:
        record = session.get(GWPReference, record_id)
        if record:
            session.delete(record)
            session.commit()
    return RedirectResponse(url="/etl/manage?category=逸散排放", status_code=303)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

F604_PATH = os.path.join(BASE_DIR, "溫室氣體排放係數管理表6.0.4(修) (4).ods")
V2_PATH = os.path.join(BASE_DIR, "溫室氣體盤查作業相關代碼檔V2 (4).ods")
CSV_PATH = os.path.join(BASE_DIR, "台電系統發購電量及電力排碳係數(105-113) (1).csv")


def _run_import_fuel():
    """匯入 6.0.4 燃料係數 + 代碼檔對照"""
    from tools.import_604 import build_code_map, parse_sheet, FUEL_CODE_OVERRIDE

    SHEET_CONFIG = {
        "1_固定源與移動源(燃料)CO2排放係數": {"gas_type": "CO2", "factor_col": 17, "unit_col": 18},
        "2_固定源與移動源(燃料)CH4排放係數": {"gas_type": "CH4", "factor_col": 14, "unit_col": 15},
        "3_固定源與移動源(燃料)N2O排放係數": {"gas_type": "N2O", "factor_col": 14, "unit_col": 15},
    }
    EMISSION_TYPE_MAP = {"固定源": "固定燃燒", "移動源": "移動燃燒"}

    import pandas as pd
    code_map = build_code_map()
    all_rows = []
    for sheet_name, config in SHEET_CONFIG.items():
        df = pd.read_excel(F604_PATH, sheet_name=sheet_name, engine="odf", header=None)
        data = df.iloc[6:].copy()
        data[1] = data[1].ffill()
        for i in range(len(data)):
            r = data.iloc[i]
            fuel = r.iloc[3]
            etype_raw = str(r.iloc[1]).strip()
            factor_raw = r.iloc[config["factor_col"]]
            unit_raw = r.iloc[config["unit_col"]]
            if pd.isna(fuel) or str(fuel).strip() in ("", "NaN", "nan"):
                continue
            fuel_name = str(fuel).strip()
            if fuel_name.startswith("註"):
                continue
            factor_str = str(factor_raw).strip()
            if factor_str in ("", "-", "NaN", "nan"):
                continue
            emission_type = EMISSION_TYPE_MAP.get(etype_raw)
            if not emission_type:
                continue
            try:
                factor_value = float(factor_str)
            except ValueError:
                continue
            unit = str(unit_raw).strip() if pd.notna(unit_raw) else ""

            code = None
            if fuel_name in code_map:
                code = code_map[fuel_name]
            elif fuel_name in FUEL_CODE_OVERRIDE:
                code = FUEL_CODE_OVERRIDE[fuel_name]
            else:
                base = fuel_name.split("(")[0].split("（")[0].strip()
                code = code_map.get(base)
            if not code:
                continue
            all_rows.append((code, config["gas_type"], emission_type, fuel_name, factor_value, unit))

    with Session(engine) as session:
        for obj in session.exec(select(FactorCodeMap)).all():
            session.delete(obj)
        for obj in session.exec(select(EmissionFactor604)).all():
            session.delete(obj)
        session.commit()

        seen = set()
        for code, gas_type, emission_type, name, factor_value, unit in all_rows:
            if code not in seen:
                seen.add(code)
                session.add(FactorCodeMap(code=code, fuel_name_zh=name, emission_type=emission_type))
            pk = f"{code}_{gas_type}_{emission_type}_{name}"
            session.add(EmissionFactor604(
                code=pk, original_code=code, gas_type=gas_type,
                emission_type=emission_type, name=name,
                factor_value=factor_value, unit=unit, year=2023,
            ))
        session.commit()
    return len(all_rows)


def _run_import_electricity():
    """匯入台電電力係數"""
    import csv
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((r["年度"], float(r["電力排碳係數"])))
    with Session(engine) as session:
        for obj in session.exec(select(EmissionFactor604).where(
            EmissionFactor604.original_code == "ELECTRICITY"
        )).all():
            session.delete(obj)
        session.commit()
        for year, factor in rows:
            session.add(EmissionFactor604(
                code=year, original_code="ELECTRICITY", gas_type="CO2e",
                emission_type="能源間接排放", name=f"{year}年電力排碳係數",
                factor_value=factor, unit="kgCO2e/kWh", year=int(year),
            ))
        session.commit()
    return len(rows)


def _run_import_gwp():
    """更新 GWP（6.0.4 AR5 + 代碼檔V2 補充）"""
    from tools.update_gwp_ar5 import parse_gas_names, parse_ar5

    import pandas as pd
    updated = 0
    new_count = 0

    df = pd.read_excel(F604_PATH, sheet_name="4_含氟氣體之GWP值", engine="odf", header=None)
    gwp_data = df.iloc[1:]

    with Session(engine) as session:
        for i in range(len(gwp_data)):
            r = gwp_data.iloc[i]
            code = r.iloc[0]
            if pd.isna(code) or str(code).strip() in ("", "nan", "NaN"):
                continue
            code = str(code).strip()
            gas_zh, gas_en = parse_gas_names(str(r.iloc[1]) if pd.notna(r.iloc[1]) else "")
            gwp_value, is_qual, note = parse_ar5(str(r.iloc[5]))

            existing = session.exec(
                select(GWPReference).where(GWPReference.formula == code)
            ).first()
            if existing:
                existing.gwp_value = gwp_value
                existing.is_qualitative = is_qual
                if note:
                    existing.note = note
                existing.version = "AR5"
                updated += 1
            else:
                session.add(GWPReference(
                    formula=code, gas_name_zh=gas_zh, gas_name_en=gas_en,
                    gwp_value=gwp_value, version="AR5",
                    is_qualitative=is_qual, note=note,
                ))
                new_count += 1

        # 代碼檔V2 補充
        df_v2 = pd.read_excel(V2_PATH, sheet_name=1, engine="odf")
        sec10 = df_v2.iloc[:, [41,42,43,44,45]].dropna(how="all")
        sec10.columns = ["title","code","name","gwp","note"]

        existing_codes = set(session.exec(select(GWPReference.formula)).all())
        for _, r in sec10.iterrows():
            code_v2 = str(r["code"]).strip() if pd.notna(r["code"]) else ""
            if not code_v2 or code_v2 in existing_codes:
                continue
            gas_zh2, gas_en2 = parse_gas_names(str(r["name"]))
            gwp_value2, is_qual2, note2 = parse_ar5(str(r["gwp"]))
            session.add(GWPReference(
                formula=code_v2, gas_name_zh=gas_zh2, gas_name_en=gas_en2,
                gwp_value=gwp_value2, version="AR5",
                is_qualitative=is_qual2, note=note2 or (str(r["note"]) if pd.notna(r["note"]) else None),
            ))
            new_count += 1

        session.commit()
    return updated + new_count


def _run_import_codes():
    """匯取代碼檔V2 → appendix_reference"""
    from tools.import_code_table import SECTIONS

    import pandas as pd
    df = pd.read_excel(V2_PATH, sheet_name=1, engine="odf")
    total = 0
    with Session(engine) as session:
        for key, cfg in SECTIONS.items():
            atype = cfg["type"]
            cols = cfg["cols"]
            mode = cfg.get("mode", "")
            data = df.iloc[:, cols[0]:cols[-1]+1].copy()
            data = data.dropna(how="all")
            count = 0
            for i in range(len(data)):
                row = data.iloc[i]
                vals = [str(v).strip() for v in row if pd.notna(v)]
                if mode == "name_only":
                    if vals and vals[0] not in ("NaN", "nan", ""):
                        name = vals[0]
                        code = name
                    else:
                        continue
                elif mode == "city":
                    if len(vals) >= 3 and vals[2] not in ("NaN", "nan", ""):
                        code = vals[2]
                        name = f"{vals[0]}{vals[1]}" if vals[1] not in ("NaN", "nan", "") else vals[0]
                    else:
                        continue
                else:
                    code = vals[0] if len(vals) >= 1 and vals[0] not in ("NaN", "nan", "") else ""
                    name = vals[1] if len(vals) >= 2 and vals[1] not in ("NaN", "nan", "") else ""
                    if not code and not name:
                        continue

                existing = session.exec(
                    select(AppendixReference).where(
                        AppendixReference.appendix_type == atype,
                        AppendixReference.code == (code if mode != "name_only" else name)
                    )
                ).first()
                if not existing:
                    session.add(AppendixReference(
                        appendix_type=atype, code=code, name=name
                    ))
                    count += 1
            session.commit()
            total += count
    return total


@router.post("/refresh/fuel")
async def refresh_fuel():
    """重新匯入 6.0.4 燃料係數"""
    try:
        count = _run_import_fuel()
        return {"status": "success", "message": f"已匯入 {count} 筆燃料係數", "count": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/refresh/electricity")
async def refresh_electricity():
    """重新匯入台電電力係數"""
    try:
        count = _run_import_electricity()
        return {"status": "success", "message": f"已匯入 {count} 筆電力係數", "count": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/refresh/gwp")
async def refresh_gwp():
    """重新匯入 GWP"""
    try:
        count = _run_import_gwp()
        return {"status": "success", "message": f"已更新 {count} 筆 GWP", "count": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/refresh/codes")
async def refresh_codes():
    """重新匯入代碼檔"""
    try:
        count = _run_import_codes()
        return {"status": "success", "message": f"已匯入 {count} 筆代碼", "count": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/status")
async def get_etl_status():
    """取得所有 ETL 類型的最後取數狀態"""
    with Session(engine) as session:
        statuses = session.query(ETLStatus).all()
        return [
            {
                "etl_type": s.etl_type,
                "last_fetch_time": s.last_fetch_time.strftime("%Y-%m-%d %H:%M:%S") if s.last_fetch_time else None,
                "last_fetch_result": s.last_fetch_result,
                "fetched_count": s.fetched_count,
                "source_url": s.source_url,
            }
            for s in statuses
        ]
