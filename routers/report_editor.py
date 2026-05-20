from pathlib import Path
from typing import Any

import bleach
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session

from database import engine
from model import ReportDraft
from services.report_editor import (
    create_report_draft,
    export_report_draft,
    generate_section_content,
    get_report_draft,
    get_report_section_definitions,
    insert_section_data,
    list_report_drafts,
    update_report_section,
)

router = APIRouter(prefix="/reports", tags=["report_editor"])

ALLOWED_TAGS = ["b", "strong", "i", "em", "u", "br", "p", "ul", "ol", "li"]


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/sections")
async def list_report_sections():
    return {"sections": get_report_section_definitions()}


@router.post("/drafts")
async def create_draft(request: Request, session: Session = Depends(get_session)):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    created_by = str(request.session.get("username") or account_id)
    draft = create_report_draft(session, int(account_id), created_by)
    return {
        "draft_id": draft.draft_id,
        "snapshot_id": draft.snapshot_id,
        "status": draft.status,
        "sections": get_report_section_definitions(),
    }


@router.get("/drafts")
async def get_draft_list(request: Request, session: Session = Depends(get_session)):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    return {"drafts": list_report_drafts(session, int(account_id))}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, request: Request, session: Session = Depends(get_session)):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    try:
        draft, snapshot_payload = get_report_draft(session, draft_id, int(account_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "draft_id": draft.draft_id,
        "snapshot_id": draft.snapshot_id,
        "status": draft.status,
        "title": draft.title,
        "sections_payload": draft.sections_payload,
        "snapshot_generated_at": snapshot_payload.get("generated_at"),
        "inventory_year": snapshot_payload.get("inventory_year"),
    }


@router.patch("/drafts/{draft_id}/sections/{section_id}")
async def save_section(
    draft_id: str,
    section_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    body = await request.json()
    content_raw = str(body.get("content", ""))
    content = bleach.clean(content_raw, tags=ALLOWED_TAGS, strip=True)

    try:
        draft, _snapshot_payload = get_report_draft(session, draft_id, int(account_id))
        changed_by = str(request.session.get("username") or account_id)
        updated = update_report_section(
            session=session,
            draft=draft,
            section_id=section_id,
            content=content,
            changed_by=changed_by,
            source="manual",
            citations=[],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "draft_id": updated.draft_id,
        "section_id": section_id,
        "updated_at": updated.updated_at.isoformat(timespec="seconds"),
    }


@router.post("/drafts/{draft_id}/sections/{section_id}/generate")
async def generate_section(
    draft_id: str,
    section_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    try:
        draft, snapshot_payload = get_report_draft(session, draft_id, int(account_id))
        changed_by = str(request.session.get("username") or account_id)
        section_data = generate_section_content(
            session=session,
            draft=draft,
            snapshot_payload=snapshot_payload,
            section_id=section_id,
            changed_by=changed_by,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(section_data)


@router.post("/drafts/{draft_id}/sections/{section_id}/insert-data")
async def insert_data(
    draft_id: str,
    section_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    try:
        draft, snapshot_payload = get_report_draft(session, draft_id, int(account_id))
        changed_by = str(request.session.get("username") or account_id)
        section_data = insert_section_data(
            session=session,
            draft=draft,
            snapshot_payload=snapshot_payload,
            section_id=section_id,
            changed_by=changed_by,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(section_data)


@router.post("/drafts/{draft_id}/export")
async def export_draft(draft_id: str, request: Request, session: Session = Depends(get_session)):
    account_id = request.session.get("user")
    if not account_id:
        raise HTTPException(status_code=401, detail="未登入")

    try:
        draft, snapshot_payload = get_report_draft(session, draft_id, int(account_id))
        file_path = export_report_draft(session=session, draft=draft, snapshot_payload=snapshot_payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = Path(file_path).name
    return FileResponse(
        str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
