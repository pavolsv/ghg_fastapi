from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from datetime import datetime

from database import engine
from model import OrgBoundary

router = APIRouter(prefix="/boundary", tags=["boundary"])
templates = Jinja2Templates(directory="templates")


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def boundary_page(request: Request, session: Session = Depends(get_session)):
    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    boundaries = session.exec(
        select(OrgBoundary)
        .where(OrgBoundary.account_id == user_id)
        .order_by(OrgBoundary.created_at.desc())
    ).all()

    return templates.TemplateResponse(
        "boundary.html",
        {"request": request, "boundaries": boundaries}
    )


@router.post("/create")
async def create_boundary(
    request: Request,
    name: str = Form(...),
    address: str = Form(...),
    session: Session = Depends(get_session),
):
    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    boundary = OrgBoundary(
        name=name,
        address=address,
        account_id=user_id,
    )
    session.add(boundary)
    session.commit()
    return RedirectResponse(url="/boundary/", status_code=303)


@router.post("/update/{boundary_id}")
async def update_boundary(
    request: Request,
    boundary_id: int,
    name: str = Form(...),
    address: str = Form(...),
    session: Session = Depends(get_session),
):
    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    boundary = session.get(OrgBoundary, boundary_id)
    if boundary and boundary.account_id == user_id:
        boundary.name = name
        boundary.address = address
        boundary.updated_at = datetime.utcnow()
        session.add(boundary)
        session.commit()
    return RedirectResponse(url="/boundary/", status_code=303)


@router.post("/delete/{boundary_id}")
async def delete_boundary(
    request: Request,
    boundary_id: int,
    session: Session = Depends(get_session),
):
    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    boundary = session.get(OrgBoundary, boundary_id)
    if boundary and boundary.account_id == user_id:
        session.delete(boundary)
        session.commit()
    return RedirectResponse(url="/boundary/", status_code=303)