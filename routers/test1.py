from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlmodel import Session, select

from database import engine
from model import gwp_list

router = APIRouter(prefix="/test1", tags=["test1"])

templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def show_test1(request: Request):
    with Session(engine) as session:
        gwps = session.exec(select(gwp_list)).all()
        print("Debug: Retrieved gwp_list:", gwps)
    return templates.TemplateResponse("test1.html", {"request": request, "gwps": gwps})
