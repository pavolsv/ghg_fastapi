from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from database import engine
from model import Account, Device, UtilityBill, DataChangeLog

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/index", tags=["index"])


@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login/", status_code=303)

    user_id = request.session.get("user")
    with Session(engine) as session:
        account = session.get(Account, user_id)
        device_count = session.exec(
            select(func.count()).select_from(Device).where(Device.account_id == user_id)
        ).one() or 0
        bill_count = session.exec(
            select(func.count()).select_from(UtilityBill).where(UtilityBill.account_id == user_id)
        ).one() or 0
        recent_logs = session.exec(
            select(DataChangeLog)
            .where(DataChangeLog.changed_by == str(user_id))
            .order_by(DataChangeLog.changed_at.desc())
            .limit(5)
        ).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user_id,
            "account": account,
            "device_count": device_count,
            "bill_count": bill_count,
            "recent_logs": recent_logs,
            "now_date": datetime.now().strftime("%Y-%m-%d"),
        },
    )