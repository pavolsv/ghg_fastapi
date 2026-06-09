import os
from typing import Optional
from datetime import datetime

import pandas as pd
import requests
import urllib3
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col

from audit_log import add_change_log
from database import engine
from model import EmissionFactor, ETLStatus, GWPReference

# 禁用 SSL 警告
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
        statuses = session.query(ETLStatus).all()
        status_map = {s.etl_type: s for s in statuses}
    return templates.TemplateResponse(
        "etl.html", {
            "request": request,
            "default_url": URL_REGISTRY,
            "status_map": status_map,
        }
    )


def process_refrigerant_appendix(file_path, year):
    pass


@router.post("/run")
async def run_etl(data_type: str = Form("fuel"), year: int = Form(2023)):
    target_url = URL_REGISTRY.get(data_type)
    if not target_url:
        return {"status": "error", "message": "無效的數據類型"}

    # 根據副檔名決定暫存檔名
    ext = ".csv" if "csv" in target_url.lower() else ".ods"
    file_path = f"temp_{data_type}{ext}"

    try:
        # --- 1. 下載 ---
        resp = requests.get(target_url, verify=False, timeout=30)
        with open(file_path, "wb") as f:
            f.write(resp.content)

        # --- 2. 分流解析 ---
        if data_type == "fuel":
            # 專攻附表一，解決褐煤三氣體補全問題
            data_df = process_appendix_one(file_path, year)
            msg = "燃料係數 (CO2, CH4, N2O)"
        elif data_type == "electricity":
            # 專攻電力排放係數 (0.494, 0.474)
            data_df = process_utility_electricity(file_path)
            msg = "電力排碳係數"
        else:
            return {"status": "error", "message": "目前僅支援燃料與電力"}

        # --- 3. 統一入庫 ---
        created_count = 0
        updated_count = 0
        unchanged_count = 0
        changes_detail = []

        with Session(engine) as session:
            for _, row in data_df.iterrows():
                row_dict = row.to_dict()
                row_dict.setdefault("factor_source", target_url)
                row_dict.setdefault(
                    "calculation_method",
                    "total_co2e = activity_data × emission_factor",
                )
                row_dict["updated_at"] = datetime.utcnow()

                existing_factor = session.get(
                    EmissionFactor, (row_dict["code"], row_dict["gas_type"])
                )

                action_type = "CREATE"
                detail = "factor created"

                if existing_factor:
                    changed_fields = []
                    tracked_fields = [
                        "name",
                        "factor_value",
                        "unit",
                        "year",
                        "emission_type",
                        "factor_source",
                        "calculation_method",
                    ]
                    for field_name in tracked_fields:
                        old_val = getattr(existing_factor, field_name)
                        new_val = row_dict.get(field_name)
                        if str(old_val) != str(new_val):
                            changed_fields.append(
                                {
                                    "field": field_name,
                                    "old": str(old_val),
                                    "new": str(new_val),
                                }
                            )

                    if changed_fields:
                        action_type = "UPDATE"
                        detail = "; ".join(
                            f"{c['field']}: {c['old']} -> {c['new']}" for c in changed_fields
                        )
                        updated_count += 1
                        changes_detail.append({
                            "code": row_dict["code"],
                            "gas_type": row_dict["gas_type"],
                            "name": row_dict["name"],
                            "action": "UPDATE",
                            "changes": changed_fields,
                        })
                    else:
                        action_type = "UPSERT"
                        detail = "no business field changed"
                        unchanged_count += 1
                else:
                    created_count += 1
                    changes_detail.append({
                        "code": row_dict["code"],
                        "gas_type": row_dict["gas_type"],
                        "name": row_dict["name"],
                        "action": "CREATE",
                        "changes": [],
                    })

                factor = EmissionFactor(**row_dict)
                session.merge(factor)

                add_change_log(
                    session=session,
                    module="factor_management",
                    entity_name="EmissionFactor",
                    record_key=f"{row_dict['code']}|{row_dict['gas_type']}",
                    action_type=action_type,
                    changed_by="etl_system",
                    change_details=detail,
                )

            # 更新 ETLStatus
            etl_status = session.query(ETLStatus).filter(
                col(ETLStatus.etl_type) == data_type
            ).first()
            if etl_status:
                etl_status.last_fetch_time = datetime.utcnow()
                etl_status.last_fetch_result = f"成功匯入 {len(data_df)} 筆 {msg}"
                etl_status.fetched_count = len(data_df)
                etl_status.source_url = target_url
            else:
                etl_status = ETLStatus(
                    etl_type=data_type,
                    last_fetch_time=datetime.utcnow(),
                    last_fetch_result=f"成功匯入 {len(data_df)} 筆 {msg}",
                    fetched_count=len(data_df),
                    source_url=target_url,
                )
                session.add(etl_status)

            session.commit()

        return {
            "status": "success",
            "message": f"成功匯入 {len(data_df)} 筆 {msg}",
            "summary": {
                "total": len(data_df),
                "created": created_count,
                "updated": updated_count,
                "unchanged": unchanged_count,
            },
            "changes": changes_detail[:50],  # 最多返回前50筆變動明細
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"解析失敗，請檢查頁籤名稱或格式：{str(e)}",
        }
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@router.post("/factor/create")
async def create_factor(
    request: Request,
    code: str = Form(...),
    gas_type: str = Form(...),
    original_code: str = Form(...),
    name: str = Form(...),
    factor_value: float = Form(...),
    unit: str = Form(...),
    year: int = Form(...),
    emission_type: str = Form(...),
    factor_source: str = Form(default=""),
    calculation_method: str = Form(default="total_co2e = activity_data × emission_factor"),
):
    from datetime import datetime

    if factor_value <= 0:
        return {"status": "error", "message": "係數數值必須大於 0"}

    with Session(engine) as session:
        existing = session.get(EmissionFactor, (code, gas_type))
        action_type = "UPDATE" if existing else "CREATE"

        changed_fields = []
        if existing:
            tracked = ["name", "factor_value", "unit", "year", "emission_type",
                       "factor_source", "calculation_method"]
            new_vals = dict(name=name, factor_value=factor_value, unit=unit, year=year,
                            emission_type=emission_type,
                            factor_source=factor_source, calculation_method=calculation_method)
            for field in tracked:
                old = getattr(existing, field)
                new = new_vals[field]
                if str(old) != str(new):
                    changed_fields.append(f"{field}: {old} → {new}")
            detail = "; ".join(changed_fields) if changed_fields else "no change"
        else:
            detail = f"code={code}, gas_type={gas_type}, factor_value={factor_value}"

        factor = EmissionFactor(
            code=code,
            gas_type=gas_type,
            original_code=original_code,
            name=name,
            factor_value=factor_value,
            unit=unit,
            year=year,
            emission_type=emission_type,
            factor_source=factor_source or None,
            calculation_method=calculation_method or None,
            updated_at=datetime.utcnow(),
        )
        session.merge(factor)

        add_change_log(
            session=session,
            module="factor_management",
            entity_name="EmissionFactor",
            record_key=f"{code}|{gas_type}",
            action_type=action_type,
            changed_by=str(request.session.get("user", "manual")),
            change_details=detail,
        )
        session.commit()

    return RedirectResponse(url="/etl/manage", status_code=303)


@router.post("/factor/lhv/update")
async def update_lhv(
    request: Request,
    original_code: str = Form(...),
    year: int = Form(...),
    emission_type: str = Form(...),
    lower_heating_value: float = Form(...),
    lhv_unit: str = Form(...),
):
    """更新燃料的低位熱值（同一 original_code 的所有 gas_type 一起更新）"""
    with Session(engine) as session:
        factors = session.exec(
            select(EmissionFactor).where(
                EmissionFactor.original_code == original_code,
                EmissionFactor.year == year,
                EmissionFactor.emission_type == emission_type,
            )
        ).all()

        for factor in factors:
            factor.lower_heating_value = lower_heating_value
            factor.lhv_unit = lhv_unit
            factor.updated_at = datetime.utcnow()
            session.add(factor)

        add_change_log(
            session=session,
            module="factor_management",
            entity_name="EmissionFactor",
            record_key=f"{original_code}|LHV",
            action_type="UPDATE",
            changed_by=str(request.session.get("user", "manual")),
            change_details=f"LHV={lower_heating_value} {lhv_unit}",
        )
        session.commit()

    return RedirectResponse(url="/etl/manage", status_code=303)


@router.post("/factor/delete")
async def delete_factor(
    request: Request,
    code: str = Form(...),
    gas_type: str = Form(...),
):
    with Session(engine) as session:
        factor = session.get(EmissionFactor, (code, gas_type))
        if factor:
            detail = (
                f"name={factor.name}, factor_value={factor.factor_value}, "
                f"year={factor.year}"
            )
            add_change_log(
                session=session,
                module="factor_management",
                entity_name="EmissionFactor",
                record_key=f"{code}|{gas_type}",
                action_type="DELETE",
                changed_by=str(request.session.get("user", "manual")),
                change_details=detail,
            )
            session.delete(factor)
            session.commit()

    return RedirectResponse(url="/etl/manage", status_code=303)


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

    # ── EmissionFactor（其他排放類型）────────────────────────────────
    with Session(engine) as session:
        query = session.query(EmissionFactor)

        # --- 篩選邏輯（配合分組顯示調整）---
        if name:
            query = query.filter(col(EmissionFactor.name).contains(name))
        if category:
            query = query.filter(col(EmissionFactor.emission_type).contains(category))
        if year and year.strip():
            try:
                query = query.filter(col(EmissionFactor.year) == int(year))
            except ValueError:
                pass
        if gas_type:
            # 找出含有該 gas_type 的所有 code，再撈出這些 code 的全部氣體列
            # 這樣分組後 CO2/CH4/N2O 欄位仍完整顯示
            matching_codes = [
                row[0]
                for row in session.query(col(EmissionFactor.code))
                .filter(col(EmissionFactor.gas_type) == gas_type)
                .distinct()
                .all()
            ]
            query = query.filter(col(EmissionFactor.code).in_(matching_codes))

        # --- 核心修改：預設按 Code (編號) 升冪排序 (A-Z) ---
        factors = query.order_by(
            col(EmissionFactor.code).asc(), col(EmissionFactor.year).desc()
        ).all()

        # --- 依 (code, year) 分組，將 CO2/CH4/N2O 各 gas_type 樞紐為欄位 ---
        grouped_dict: dict = {}
        for f in factors:
            key = (f.code, f.year)
            if key not in grouped_dict:
                grouped_dict[key] = {
                    "code": f.code,
                    "original_code": f.original_code,
                    "name": f.name,
                    "unit": f.unit,
                    "year": f.year,
                    "emission_type": f.emission_type,
                    "factor_source": f.factor_source,
                    "calculation_method": f.calculation_method,
                    "gas_values": {},
                    "gas_factors": {},
                }
            grouped_dict[key]["gas_values"][f.gas_type] = f.factor_value
            grouped_dict[key]["gas_factors"][f.gas_type] = {
                "code": f.code,
                "gas_type": f.gas_type,
                "original_code": f.original_code,
                "name": f.name,
                "factor_value": f.factor_value,
                "unit": f.unit,
                "year": f.year,
                "emission_type": f.emission_type,
                "factor_source": f.factor_source or "",
                "calculation_method": f.calculation_method or "",
            }
        grouped_factors = list(grouped_dict.values())

        # 獲取選單資料
        name_list = [
            n[0] for n in session.query(col(EmissionFactor.name)).distinct().all() if n[0]
        ]
        gas_list = [
            g[0]
            for g in session.query(col(EmissionFactor.gas_type)).distinct().all()
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


@router.post("/preview")
async def preview_etl(data_type: str = Form("fuel"), year: int = Form(2023)):
    """預覽導入數據：下載並解析，與現有數據對比，但不入庫"""
    target_url = URL_REGISTRY.get(data_type)
    if not target_url:
        return {"status": "error", "message": "無效的數據類型"}

    ext = ".csv" if "csv" in target_url.lower() else ".ods"
    file_path = f"temp_preview_{data_type}{ext}"

    try:
        resp = requests.get(target_url, verify=False, timeout=30)
        with open(file_path, "wb") as f:
            f.write(resp.content)

        if data_type == "fuel":
            data_df = process_appendix_one(file_path, year)
        elif data_type == "electricity":
            data_df = process_utility_electricity(file_path)
        else:
            return {"status": "error", "message": "目前僅支援燃料與電力"}

        preview_rows = []
        with Session(engine) as session:
            for _, row in data_df.iterrows():
                row_dict = row.to_dict()
                existing = session.get(
                    EmissionFactor, (row_dict["code"], row_dict["gas_type"])
                )

                if existing:
                    changed_fields = []
                    tracked_fields = [
                        "name", "factor_value", "unit", "year",
                        "emission_type",
                    ]
                    for fn in tracked_fields:
                        old_val = str(getattr(existing, fn))
                        new_val = str(row_dict.get(fn))
                        if old_val != new_val:
                            changed_fields.append({
                                "field": fn,
                                "old": old_val,
                                "new": new_val,
                            })
                    action = "UPDATE" if changed_fields else "UNCHANGED"
                else:
                    action = "NEW"
                    changed_fields = []

                preview_rows.append({
                    "code": row_dict["code"],
                    "gas_type": row_dict["gas_type"],
                    "name": row_dict["name"],
                    "factor_value": row_dict["factor_value"],
                    "action": action,
                    "changes": changed_fields,
                })

        new_count = sum(1 for r in preview_rows if r["action"] == "NEW")
        update_count = sum(1 for r in preview_rows if r["action"] == "UPDATE")
        unchanged_count = sum(1 for r in preview_rows if r["action"] == "UNCHANGED")

        return {
            "status": "success",
            "summary": {
                "total": len(preview_rows),
                "new": new_count,
                "updated": update_count,
                "unchanged": unchanged_count,
            },
            "rows": preview_rows[:100],  # 最多返回前 100 筆
        }

    except Exception as e:
        return {"status": "error", "message": f"預覽失敗：{str(e)}"}
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


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
