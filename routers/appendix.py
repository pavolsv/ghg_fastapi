"""
Appendix Reference Management (附表四~七通用表)
路由前綴: /appendix
支援分類篩選、關鍵字搜尋、CRUD、ODS 批次匯入
"""
import os
import tempfile
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlmodel import Session, select

from audit_log import add_change_log
from database import engine
from model import AppendixReference

router = APIRouter(prefix="/appendix", tags=["appendix"])
templates = Jinja2Templates(directory="templates")

VALID_TYPES = {"industry", "process", "device", "material"}
SHEET_TYPE_MAP = {
    "附表四": "industry",
    "附表五": "process",
    "附表六": "device",
    "附表七": "material",
}


# ---------------------------------------------------------------------------
# 前端管理頁面
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def appendix_page(
    request: Request,
    appendix_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    if appendix_type and appendix_type not in VALID_TYPES:
        appendix_type = None

    with Session(engine) as session:
        stmt = select(AppendixReference)
        if appendix_type:
            stmt = stmt.where(AppendixReference.appendix_type == appendix_type)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    AppendixReference.code.ilike(pattern),     # type: ignore[attr-defined]
                    AppendixReference.name.ilike(pattern),     # type: ignore[attr-defined]
                )
            )
        stmt = stmt.order_by(AppendixReference.appendix_type, AppendixReference.seq)

        total = len(session.exec(stmt).all())
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = session.exec(stmt).all()

    # 簡單分頁範圍（前後各 2 頁）
    start = max(1, page - 2)
    end = min(total_pages, page + 2)
    page_range = list(range(start, end + 1))

    return templates.TemplateResponse(
        "appendix_management.html",
        {
            "request": request,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "page_range": page_range,
            "current_type": appendix_type,
            "q": q,
        },
    )


# ---------------------------------------------------------------------------
# 列表 / 搜尋 (JSON API)
# ---------------------------------------------------------------------------

@router.get("/list")
def list_appendix(
    appendix_type: Optional[str] = Query(None, description="分類：industry / process / device / material"),
    q: Optional[str] = Query(None, description="關鍵字搜尋（代碼或名稱）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    GET /appendix/list
    回傳 JSON，支援分類與關鍵字模糊搜尋。
    """
    if appendix_type and appendix_type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"appendix_type 必須為 {VALID_TYPES} 之一")

    with Session(engine) as session:
        stmt = select(AppendixReference)
        if appendix_type:
            stmt = stmt.where(AppendixReference.appendix_type == appendix_type)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    AppendixReference.code.ilike(pattern),     # type: ignore[attr-defined]
                    AppendixReference.name.ilike(pattern),     # type: ignore[attr-defined]
                )
            )
        stmt = stmt.order_by(AppendixReference.appendix_type, AppendixReference.seq)

        total = len(session.exec(stmt).all())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = session.exec(stmt).all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": [
                {
                    "id": r.id,
                    "appendix_type": r.appendix_type,
                    "seq": r.seq,
                    "code": r.code,
                    "name": r.name,
                    "source_sheet": r.source_sheet,
                    "note": r.note,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ],
        }


# ---------------------------------------------------------------------------
# 建立
# ---------------------------------------------------------------------------

@router.post("/create")
def create_appendix(
    appendix_type: str = Form(...),
    code: str = Form(...),
    name: str = Form(...),
    seq: Optional[int] = Form(None),
    source_sheet: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
):
    """POST /appendix/create"""
    if appendix_type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"appendix_type 必須為 {VALID_TYPES} 之一")

    record = AppendixReference(
        appendix_type=appendix_type,
        code=code.strip(),
        name=name.strip(),
        seq=seq,
        source_sheet=source_sheet,
        note=note,
    )
    with Session(engine) as session:
        session.add(record)
        try:
            session.commit()
            session.refresh(record)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"寫入失敗，可能已存在相同 type+code：{exc}") from exc

        add_change_log(
            session=session,
            module="appendix_management",
            entity_name="AppendixReference",
            record_key=f"{record.appendix_type}|{record.code}",
            action_type="CREATE",
            changed_by="api",
            change_details=f"created {record.appendix_type} {record.code} {record.name}",
        )
    return {"ok": True, "id": record.id}


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------

@router.post("/update/{record_id}")
def update_appendix(
    record_id: int,
    appendix_type: str = Form(...),
    code: str = Form(...),
    name: str = Form(...),
    seq: Optional[int] = Form(None),
    source_sheet: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
):
    """POST /appendix/update/{id}"""
    if appendix_type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"appendix_type 必須為 {VALID_TYPES} 之一")

    with Session(engine) as session:
        record = session.get(AppendixReference, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到該筆資料")

        record.appendix_type = appendix_type
        record.code = code.strip()
        record.name = name.strip()
        record.seq = seq
        record.source_sheet = source_sheet
        record.note = note
        record.updated_at = datetime.utcnow()
        session.add(record)
        session.commit()

        add_change_log(
            session=session,
            module="appendix_management",
            entity_name="AppendixReference",
            record_key=f"{record.appendix_type}|{record.code}",
            action_type="UPDATE",
            changed_by="api",
            change_details=f"updated {record.appendix_type} {record.code} {record.name}",
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# 刪除
# ---------------------------------------------------------------------------

@router.post("/delete/{record_id}")
def delete_appendix(record_id: int):
    """POST /appendix/delete/{id}"""
    with Session(engine) as session:
        record = session.get(AppendixReference, record_id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到該筆資料")

        key = f"{record.appendix_type}|{record.code}"
        session.delete(record)
        session.commit()

        add_change_log(
            session=session,
            module="appendix_management",
            entity_name="AppendixReference",
            record_key=key,
            action_type="DELETE",
            changed_by="api",
            change_details=f"deleted {key}",
        )
    return {"ok": True, "deleted_id": record_id}


# ---------------------------------------------------------------------------
# 共用解析工具
# ---------------------------------------------------------------------------

def _process_appendix_sheet(df: pd.DataFrame, appendix_type: str, source_sheet: str) -> pd.DataFrame:
    """
    解析單一附表 DataFrame。
    預期欄位順序：A=序號, B=代碼, C=名稱, D=(可選/合併文字)
    """
    # 只取前三欄
    df = df.iloc[:, :3].copy()
    df.columns = ["seq", "code", "name"]

    # 去除空值列
    df = df.dropna(subset=["code", "name"])

    # 清理字串
    df["seq"] = pd.to_numeric(df["seq"], errors="coerce").astype("Int64")
    df["code"] = df["code"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()

    # 再次去除清理後為空的列
    df = df[(df["code"] != "") & (df["name"] != "")]

    df["appendix_type"] = appendix_type
    df["source_sheet"] = source_sheet
    df["note"] = None

    return df[["appendix_type", "seq", "code", "name", "source_sheet", "note"]]


# ---------------------------------------------------------------------------
# ODS 批次匯入
# ---------------------------------------------------------------------------

@router.post("/import_ods")
async def import_appendix_ods(
    file: UploadFile = File(...),
):
    """
    POST /appendix/import_ods
    上傳「溫室氣體排放量清冊表單(範例).ods」，自動解析附表四~七並 upsert。
    Upsert 鍵：(appendix_type, code)
    """
    suffix = os.path.splitext(file.filename or "")[1]
    if suffix.lower() not in (".ods", ".xlsx", ".xls"):
        raise HTTPException(status_code=422, detail="僅接受 .ods / .xlsx / .xls 檔案")

    tmp_path = tempfile.mktemp(suffix=suffix)
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        engine_kwargs = {"engine": "odf"} if suffix.lower() == ".ods" else {}

        created_total = updated_total = unchanged_total = skipped_total = 0
        details = []

        with Session(engine) as session:
            for sheet_name, expected_type in SHEET_TYPE_MAP.items():
                try:
                    df = pd.read_excel(tmp_path, sheet_name=sheet_name, header=0, **engine_kwargs)
                except ValueError:
                    # 工作表不存在則略過
                    continue

                parsed_df = _process_appendix_sheet(df, expected_type, sheet_name)

                for _, row in parsed_df.iterrows():
                    atype = str(row["appendix_type"])
                    code = str(row["code"])
                    name = str(row["name"])
                    seq = int(row["seq"]) if pd.notna(row["seq"]) else None
                    source_sheet = str(row["source_sheet"]) if row["source_sheet"] else None
                    note = str(row["note"]) if row["note"] else None

                    if not code or not name:
                        skipped_total += 1
                        continue

                    existing = session.exec(
                        select(AppendixReference).where(
                            AppendixReference.appendix_type == atype,
                            AppendixReference.code == code,
                        )
                    ).first()

                    if existing:
                        changed = False
                        if existing.name != name:
                            changed = True
                            existing.name = name
                        if existing.seq != seq:
                            changed = True
                            existing.seq = seq
                        if existing.source_sheet != source_sheet:
                            changed = True
                            existing.source_sheet = source_sheet
                        if existing.note != note:
                            changed = True
                            existing.note = note

                        if changed:
                            existing.updated_at = datetime.utcnow()
                            session.add(existing)
                            updated_total += 1
                            details.append({"type": atype, "code": code, "action": "UPDATE"})
                        else:
                            unchanged_total += 1
                    else:
                        new_rec = AppendixReference(
                            appendix_type=atype,
                            code=code,
                            name=name,
                            seq=seq,
                            source_sheet=source_sheet,
                            note=note,
                        )
                        session.add(new_rec)
                        created_total += 1
                        details.append({"type": atype, "code": code, "action": "CREATE"})

            session.commit()

    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析或匯入失敗：{exc}") from exc
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {
        "ok": True,
        "created": created_total,
        "updated": updated_total,
        "unchanged": unchanged_total,
        "skipped": skipped_total,
        "details": details,
    }
