import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session, col, select

from database import engine
from model import DataChangeLog

router = APIRouter(prefix="/logs", tags=["logs"])


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/")
async def query_logs(
    module: Optional[str] = Query(default=None),
    action_type: Optional[str] = Query(default=None),
    changed_by: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    query = select(DataChangeLog)

    if module and module != "all":
        query = query.where(DataChangeLog.module == module)
    if action_type and action_type != "all":
        query = query.where(DataChangeLog.action_type == action_type)
    if changed_by:
        query = query.where(col(DataChangeLog.changed_by).contains(changed_by))
    if start_date:
        query = query.where(col(DataChangeLog.changed_at) >= start_date)
    if end_date:
        query = query.where(col(DataChangeLog.changed_at) <= (end_date + " 23:59:59"))

    count_query = query
    all_logs = session.exec(count_query).all()
    total = len(all_logs)

    offset = (page - 1) * page_size
    logs = session.exec(
        query.order_by(col(DataChangeLog.changed_at).desc())
        .offset(offset)
        .limit(page_size)
    ).all()

    return JSONResponse(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": [
                {
                    "id": log.id,
                    "module": log.module,
                    "entity_name": log.entity_name,
                    "record_key": log.record_key,
                    "action_type": log.action_type,
                    "changed_by": log.changed_by,
                    "changed_at": log.changed_at.isoformat(sep=" ", timespec="seconds"),
                    "change_details": log.change_details,
                }
                for log in logs
            ],
        }
    )


@router.get("/export/csv")
async def export_logs_csv(
    module: Optional[str] = Query(default=None),
    action_type: Optional[str] = Query(default=None),
    changed_by: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
):
    query = select(DataChangeLog)

    if module and module != "all":
        query = query.where(DataChangeLog.module == module)
    if action_type and action_type != "all":
        query = query.where(DataChangeLog.action_type == action_type)
    if changed_by:
        query = query.where(col(DataChangeLog.changed_by).contains(changed_by))
    if start_date:
        query = query.where(col(DataChangeLog.changed_at) >= start_date)
    if end_date:
        query = query.where(col(DataChangeLog.changed_at) <= (end_date + " 23:59:59"))

    logs = session.exec(
        query.order_by(col(DataChangeLog.changed_at).desc()).limit(5000)
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "模組", "實體", "主鍵", "操作類型", "操作者", "時間", "變更內容"])

    for log in logs:
        writer.writerow(
            [
                log.id,
                log.module,
                log.entity_name,
                log.record_key,
                log.action_type,
                log.changed_by,
                log.changed_at.isoformat(sep=" ", timespec="seconds"),
                log.change_details,
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


@router.get("/meta")
async def log_meta(session: Session = Depends(get_session)):
    """Return distinct module and action_type values for frontend filter dropdowns."""
    all_logs = session.exec(select(DataChangeLog)).all()
    modules = sorted({log.module for log in all_logs})
    action_types = sorted({log.action_type for log in all_logs})
    return JSONResponse({"modules": modules, "action_types": action_types})
