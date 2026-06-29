"""溫室氣體盤查報告書：生成、編輯、下載 PDF。"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Template
from sqlmodel import Session, select

from database import engine
from model import Report, ReportChapter, ReportSubChapter
from services.llm_writer import generate_chapter
from services.pdf_exporter import html_to_pdf
from services.report_generator import (
    CHAPTER_TITLES,
    build_report_context,
    create_report_draft,
    get_chapter_content,
)

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory="templates")

PDF_OUTPUT_DIR = Path("uploads") / "reports"
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_session():
    with Session(engine) as session:
        yield session


def _chapter_context(report: Report) -> dict[str, Any]:
    """組合報告書渲染所需的完整上下文，並將章節內容中的變數進行渲染。"""
    context = build_report_context(report)
    context["chapter_titles"] = CHAPTER_TITLES

    with Session(engine) as session:
        chapters = session.exec(
            select(ReportChapter).where(ReportChapter.report_id == report.id)
        ).all()
        context["chapter_contents"] = {}
        for ch in chapters:
            raw = ch.edited_content or ch.generated_content or ""
            try:
                rendered = Template(raw).render(context)
            except Exception:
                rendered = raw
            context["chapter_contents"][ch.chapter_no] = rendered

    return context


@router.get("/", response_class=HTMLResponse)
async def list_reports(request: Request, session: Session = Depends(get_session)):
    reports = session.exec(select(Report).order_by(Report.created_at.desc())).all()
    return templates.TemplateResponse(
        "report_list.html",
        {"request": request, "reports": reports},
    )


@router.post("/")
async def create_report(
    inventory_year: int = Form(...),
    base_year: int | None = Form(None),
    org_boundary_method: str = Form("控制權法"),
    operational_boundary_note: str | None = Form(None),
):
    report = await create_report_draft(
        inventory_year=inventory_year,
        base_year=base_year,
        org_boundary_method=org_boundary_method,
        operational_boundary_note=operational_boundary_note,
    )
    return RedirectResponse(url=f"/reports/{report.id}", status_code=303)


@router.get("/{report_id}", response_class=HTMLResponse)
async def edit_report(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    chapters = session.exec(
        select(ReportChapter)
        .where(ReportChapter.report_id == report_id)
        .order_by(ReportChapter.chapter_no)
    ).all()

    sub_chapters = session.exec(
        select(ReportSubChapter)
        .where(ReportSubChapter.report_id == report_id)
        .order_by(ReportSubChapter.chapter_no, ReportSubChapter.sub_no)
    ).all()

    context = build_report_context(report)
    context.update(
        {
            "request": request,
            "report": report,
            "chapters": chapters,
            "chapter_titles": CHAPTER_TITLES,
            "sub_chapters": sub_chapters,
        }
    )
    return templates.TemplateResponse("report_edit.html", context)


@router.put("/{report_id}/chapters/{chapter_no}")
async def update_chapter(
    report_id: int,
    chapter_no: int,
    content: str = Form(...),
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    chapter = session.exec(
        select(ReportChapter).where(
            ReportChapter.report_id == report_id,
            ReportChapter.chapter_no == chapter_no,
        )
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章節不存在")

    chapter.edited_content = content
    session.add(chapter)
    session.commit()
    return {"ok": True}


@router.put("/{report_id}/chapters/{chapter_no}/title")
async def update_chapter_title(
    report_id: int,
    chapter_no: int,
    title: str = Form(...),
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    chapter = session.exec(
        select(ReportChapter).where(
            ReportChapter.report_id == report_id,
            ReportChapter.chapter_no == chapter_no,
        )
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章節不存在")

    chapter.title = title
    session.add(chapter)
    session.commit()
    return {"ok": True}


@router.put("/{report_id}/status")
async def update_report_status(
    report_id: int,
    status: str = Form(...),
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    report.status = status
    session.add(report)
    session.commit()
    return {"ok": True}


@router.put("/{report_id}/meta")
async def update_report_meta(
    report_id: int,
    inventory_year: int = Form(...),
    base_year: int = Form(...),
    org_boundary_method: str = Form(...),
    operational_boundary_note: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    report.inventory_year = inventory_year
    report.base_year = base_year
    report.org_boundary_method = org_boundary_method
    report.operational_boundary_note = operational_boundary_note
    report.updated_at = datetime.utcnow()
    session.add(report)
    session.commit()
    return {"ok": True}


@router.post("/{report_id}/sub-chapters")
async def create_sub_chapter(
    report_id: int,
    chapter_no: int = Form(...),
    title: str = Form(...),
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    existing = session.exec(
        select(ReportSubChapter).where(
            ReportSubChapter.report_id == report_id,
            ReportSubChapter.chapter_no == chapter_no,
        )
    ).all()
    next_sub_no = max([s.sub_no for s in existing] or [0]) + 1

    sub = ReportSubChapter(
        report_id=report_id,
        chapter_no=chapter_no,
        sub_no=next_sub_no,
        title=title,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return {"ok": True, "id": sub.id}


@router.put("/{report_id}/sub-chapters/{sub_chapter_id}/title")
async def update_sub_chapter_title(
    report_id: int,
    sub_chapter_id: int,
    title: str = Form(...),
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    sub = session.exec(
        select(ReportSubChapter).where(
            ReportSubChapter.id == sub_chapter_id,
            ReportSubChapter.report_id == report_id,
        )
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="小節不存在")

    sub.title = title
    sub.updated_at = datetime.utcnow()
    session.add(sub)
    session.commit()
    return {"ok": True}


@router.delete("/{report_id}/sub-chapters/{sub_chapter_id}")
async def delete_sub_chapter(
    report_id: int,
    sub_chapter_id: int,
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    sub = session.exec(
        select(ReportSubChapter).where(
            ReportSubChapter.id == sub_chapter_id,
            ReportSubChapter.report_id == report_id,
        )
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="小節不存在")

    session.delete(sub)
    session.commit()
    return {"ok": True}


@router.post("/{report_id}/chapters/{chapter_no}/regenerate")
async def regenerate_chapter(
    report_id: int,
    chapter_no: int,
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    chapter = session.exec(
        select(ReportChapter).where(
            ReportChapter.report_id == report_id,
            ReportChapter.chapter_no == chapter_no,
        )
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章節不存在")

    if chapter_no not in (1, 3, 5):
        raise HTTPException(status_code=400, detail="該章節不支援 LLM 重新生成")

    context = build_report_context(report)
    data = {
        1: context["company"],
        3: context["emission"],
        5: {
            "base_year": context["report"]["base_year"],
            "inventory_year": context["report"]["inventory_year"],
            "total_co2e": context["emission"]["total_co2e"],
        },
    }.get(chapter_no, {})

    content = await generate_chapter(chapter_no, data)
    chapter.generated_content = content
    chapter.edited_content = content
    chapter.is_generated_by_llm = True
    session.add(chapter)
    session.commit()

    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@router.get("/{report_id}/preview", response_class=HTMLResponse)
async def preview_report(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    context = _chapter_context(report)
    context["request"] = request
    return templates.TemplateResponse("report/report_full.html", context)


@router.get("/{report_id}/pdf")
async def download_pdf(
    request: Request,
    report_id: int,
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    context = _chapter_context(report)
    context["request"] = request
    html = templates.TemplateResponse(
        "report/report_full.html", context
    ).body.decode("utf-8")

    pdf_path = PDF_OUTPUT_DIR / f"report_{report_id}.pdf"
    await html_to_pdf(html, pdf_path)

    return FileResponse(
        path=pdf_path,
        filename=f"{report.inventory_year}_GHG_Report.pdf",
        media_type="application/pdf",
    )


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    session: Session = Depends(get_session),
):
    report = session.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="報告不存在")

    session.delete(report)
    session.commit()

    pdf_path = PDF_OUTPUT_DIR / f"report_{report_id}.pdf"
    if pdf_path.exists():
        pdf_path.unlink()

    return {"ok": True}
