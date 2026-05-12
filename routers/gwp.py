"""
GWP Reference Management
路由前綴: /gwp
支援多欄位搜尋 (formula / gas_name_zh / gas_name_en)、CRUD、ODS 批次匯入、遠端 ETL 抓取
"""

import re
import tempfile
import os
from typing import Optional

import pandas as pd
import requests
import urllib3
from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import or_
from sqlmodel import Session, select

from database import engine
from model import GWPReference

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/gwp", tags=["gwp"])

VALID_VERSIONS = {"AR4", "AR5", "AR6"}

# 政府公告 ODS 檔案網址（附表二 = 溫暖化潛勢 GWP 來自排放量清冊表單範例）
GWP_FETCH_URL = "https://ghgregistry.moenv.gov.tw/upload/Tools/AI/溫室氣體排放量清冊表單(範例).ods"

# 附表二有效資料列數
_NROWS = 300


# ---------------------------------------------------------------------------
# 搜尋 / 列表
# ---------------------------------------------------------------------------

@router.get("/list")
def list_gwp(
    q: Optional[str] = Query(None, description="關鍵字（化學式 / 中文名 / 英文名）"),
    version: Optional[str] = Query(None, description="IPCC 版本，如 AR5 / AR6"),
):
    """
    GET /gwp/list
    回傳 JSON 陣列；支援多欄位模糊搜尋。
    範例：/gwp/list?q=SF6  或  /gwp/list?q=六氟化硫&version=AR6
    """
    with Session(engine) as session:
        stmt = select(GWPReference)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    GWPReference.formula.ilike(pattern),         # type: ignore[attr-defined]
                    GWPReference.gas_name_zh.ilike(pattern),     # type: ignore[attr-defined]
                    GWPReference.gas_name_en.ilike(pattern),     # type: ignore[attr-defined]
                )
            )
        if version:
            stmt = stmt.where(GWPReference.version == version)

        rows = session.exec(stmt).all()
        return [
            {
                "id": r.id,
                "formula": r.formula,
                "gas_name_zh": r.gas_name_zh,
                "gas_name_en": r.gas_name_en,
                "gwp_value": r.gwp_value,
                "is_qualitative": r.is_qualitative,
                "version": r.version,
                "note": r.note,
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# 建立
# ---------------------------------------------------------------------------

@router.post("/create")
def create_gwp(
    gas_name_zh: str = Form(...),
    gas_name_en: str = Form(...),
    formula: str = Form(...),
    gwp_value: float = Form(0.0),
    is_qualitative: bool = Form(False),
    version: str = Form("AR5"),
    note: Optional[str] = Form(None),
):
    """POST /gwp/create — 新增一筆 GWP 參考資料"""
    if version not in VALID_VERSIONS:
        raise HTTPException(status_code=422, detail=f"version 必須為 {VALID_VERSIONS} 之一")

    record = GWPReference(
        gas_name_zh=gas_name_zh,
        gas_name_en=gas_name_en,
        formula=formula,
        gwp_value=gwp_value,
        is_qualitative=is_qualitative,
        version=version,
        note=note,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return {"ok": True, "id": record.id}


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------

@router.post("/update/{record_id}")
def update_gwp(
    record_id: int,
    gas_name_zh: str = Form(...),
    gas_name_en: str = Form(...),
    formula: str = Form(...),
    gwp_value: float = Form(0.0),
    is_qualitative: bool = Form(False),
    version: str = Form("AR5"),
    note: Optional[str] = Form(None),
):
    """POST /gwp/update/{id} — 更新指定 GWP 資料"""
    if version not in VALID_VERSIONS:
        raise HTTPException(status_code=422, detail=f"version 必須為 {VALID_VERSIONS} 之一")

    with Session(engine) as session:
        record = session.get(GWPReference, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到該筆資料")
        record.gas_name_zh = gas_name_zh
        record.gas_name_en = gas_name_en
        record.formula = formula
        record.gwp_value = gwp_value
        record.is_qualitative = is_qualitative
        record.version = version
        record.note = note
        session.add(record)
        session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 刪除
# ---------------------------------------------------------------------------

@router.post("/delete/{record_id}")
def delete_gwp(record_id: int):
    """POST /gwp/delete/{id} — 刪除指定 GWP 資料"""
    with Session(engine) as session:
        record = session.get(GWPReference, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到該筆資料")
        session.delete(record)
        session.commit()
    return {"ok": True, "deleted_id": record_id}


# ---------------------------------------------------------------------------
# 共用解析工具
# ---------------------------------------------------------------------------

def _parse_gwp_value(raw) -> tuple[float, bool]:
    """
    解析 GWP 數值欄：
    - 字串 '<1'、'<0.5' 等 → (0.0, True)
    - 數值或可轉換字串     → (float(raw), False)
    - 空值 / NaN          → (0.0, False)
    """
    if raw is None:
        return 0.0, False
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return 0.0, False
    if s.startswith("<"):
        return 0.0, True
    try:
        return float(s.replace(",", "")), False
    except ValueError:
        return 0.0, True


def process_appendix_four(file_path: str, version: str = "AR5") -> pd.DataFrame:
    """
    解析 ODS 附表二（溫暖化潛勢 GWP）。

    欄位：原(燃)物料或產品代碼, 縮寫/通用名稱/化學名稱, 溫暖化潛勢, 備註說明
    → 對應: code, gas_name_zh, gwp_raw, note
    """
    df = pd.read_excel(
        file_path,
        sheet_name="附表二",
        header=None,
        skiprows=1,
        nrows=_NROWS,
        engine="odf",
    )

    df = df.iloc[:, :4].copy()
    df.columns = ["code", "gas_name_zh", "gwp_raw", "note"]

    df["code"] = df["code"].astype(str).str.strip()
    df["gas_name_zh"] = df["gas_name_zh"].astype(str).str.strip()
    df["gwp_raw"] = df["gwp_raw"].astype(str).str.strip()
    df["note"] = df["note"].astype(str).str.strip()

    df = df[df["gas_name_zh"].notna() & (df["gas_name_zh"] != "nan") & (df["gas_name_zh"] != "")]

    df["gas_name_en"] = df["gas_name_zh"]
    df["formula"] = df["code"]  # 原(燃)物料或產品代碼存入 formula 欄位

    gwp_parsed = df["gwp_raw"].apply(_parse_gwp_value)
    df["gwp_value"] = gwp_parsed.apply(lambda t: t[0])
    df["is_qualitative"] = gwp_parsed.apply(lambda t: t[1])

    df["version"] = version

    result = df[[
        "formula", "gas_name_zh", "gas_name_en",
        "gwp_value", "is_qualitative", "version", "note",
    ]].copy()
    result = result.reset_index(drop=True)

    return result


# ---------------------------------------------------------------------------
# 遠端 ETL 抓取：POST /gwp/fetch
# ---------------------------------------------------------------------------

@router.post("/fetch")
async def fetch_gwp(version: str = Form("AR5")):
    """
    POST /gwp/fetch
     從政府公告 ODS 下載附表二，自動解析並 upsert 到 gwpreference 資料表。
    Upsert 鍵：(formula, version)
    """
    if version not in VALID_VERSIONS:
        raise HTTPException(status_code=422, detail=f"version 必須為 {VALID_VERSIONS} 之一")

    tmp_path = "temp_gwp_fetch.ods"
    try:
        # 1. 下載
        resp = requests.get(GWP_FETCH_URL, verify=False, timeout=60)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            f.write(resp.content)

        # 2. 解析附表二
        df = process_appendix_four(tmp_path, version)

    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"下載失敗：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析失敗：{exc}") from exc
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # 3. Upsert：以 (formula, version) 為唯一鍵
    created = updated = unchanged = skipped = 0

    with Session(engine) as session:
        for _, row in df.iterrows():
            formula      = str(row["formula"]).strip()
            gas_name_zh  = str(row["gas_name_zh"]).strip()
            gas_name_en  = str(row["gas_name_en"]).strip()
            gwp_value    = float(row["gwp_value"])
            is_qualitative = bool(row["is_qualitative"])
            note         = str(row["note"]).strip() if row["note"] else None
            row_version  = str(row["version"]).strip()

            if not formula or not gas_name_zh:
                skipped += 1
                continue

            # 查詢現有記錄
            existing = session.exec(
                select(GWPReference).where(
                    GWPReference.formula == formula,
                    GWPReference.version == row_version,
                )
            ).first()

            if existing:
                # 比對是否有異動
                if (
                    existing.gwp_value    != gwp_value
                    or existing.is_qualitative != is_qualitative
                    or existing.gas_name_zh    != gas_name_zh
                    or existing.gas_name_en    != gas_name_en
                    or existing.note           != note
                ):
                    existing.gwp_value     = gwp_value
                    existing.is_qualitative = is_qualitative
                    existing.gas_name_zh   = gas_name_zh
                    existing.gas_name_en   = gas_name_en
                    existing.note          = note
                    session.add(existing)
                    updated += 1
                else:
                    unchanged += 1
            else:
                session.add(GWPReference(
                    formula=formula,
                    gas_name_zh=gas_name_zh,
                    gas_name_en=gas_name_en,
                    gwp_value=gwp_value,
                    is_qualitative=is_qualitative,
                    version=row_version,
                    note=note,
                ))
                created += 1

        session.commit()

    return {
        "ok": True,
        "version": version,
        "source": GWP_FETCH_URL,
        "summary": {
            "created": created,
            "updated": updated,
            "unchanged": unchanged,
            "skipped": skipped,
            "total_parsed": len(df),
        },
    }


# ---------------------------------------------------------------------------
# ODS 手動上傳匯入
# ---------------------------------------------------------------------------

COLUMN_MAP = {
    "縮寫/通用名稱/化學名稱": "gas_name_zh",
    "化學式": "formula",
    "溫暖化潛勢": "gwp_raw",
    "gwp值": "gwp_raw",
    "gwp": "gwp_raw",
    "英文名稱": "gas_name_en",
    "英文": "gas_name_en",
    "版本": "version",
    "備註": "note",
}


@router.post("/import")
async def import_gwp_ods(
    file: UploadFile = File(...),
    version: str = Form("AR5"),
    sheet_name: Optional[str] = Form(None),
    skip_rows: int = Form(1),
):
    """
    POST /gwp/import — 手動上傳 .ods / .xlsx 進行批次匯入。
    """
    if version not in VALID_VERSIONS:
        raise HTTPException(status_code=422, detail=f"version 必須為 {VALID_VERSIONS} 之一")

    suffix = os.path.splitext(file.filename or "")[-1].lower() or ".ods"
    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        engine_name = "odf" if suffix == ".ods" else "openpyxl"
        kwargs: dict = {"header": skip_rows, "engine": engine_name}
        if sheet_name:
            kwargs["sheet_name"] = sheet_name
        df = pd.read_excel(tmp_path, **kwargs)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"無法讀取檔案：{exc}") from exc
    finally:
        os.unlink(tmp_path)

    df.columns = [str(c).strip() for c in df.columns]
    rename = {col: COLUMN_MAP[col] for col in df.columns if col in COLUMN_MAP}
    df = df.rename(columns=rename)

    required = {"gas_name_zh", "formula", "gwp_raw"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"ODS 缺少必要欄位：{missing}。現有欄位：{list(df.columns)}",
        )

    records: list[GWPReference] = []
    skipped = 0

    for _, row in df.iterrows():
        formula = str(row.get("formula", "")).strip()
        gas_name_zh = str(row.get("gas_name_zh", "")).strip()

        if not formula or not gas_name_zh:
            skipped += 1
            continue

        gwp_value, is_qualitative = _parse_gwp_value(row.get("gwp_raw"))
        gas_name_en = str(row.get("gas_name_en", gas_name_zh)).strip() or gas_name_zh
        row_version = str(row.get("version", version)).strip() or version
        if row_version not in VALID_VERSIONS:
            row_version = version
        note = str(row.get("note", "")).strip() or None

        records.append(GWPReference(
            gas_name_zh=gas_name_zh,
            gas_name_en=gas_name_en,
            formula=formula,
            gwp_value=gwp_value,
            is_qualitative=is_qualitative,
            version=row_version,
            note=note,
        ))

    with Session(engine) as session:
        session.add_all(records)
        session.commit()

    return {"ok": True, "imported": len(records), "skipped": skipped, "version": version}
