from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import create_engine, Session, select
from model import Year
from dependencies import get_session, get_current_user

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/create", tags=["create"])

class SurveyCreate(BaseModel):
    year: int

@router.post("/")
async def create_survey(
    survey: SurveyCreate,
    request: Request,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    # 檢查是否已存在該年度的盤查
    existing = session.exec(
        select(Year).where(
            Year.year == survey.year,
            Year.account_id == account_id
        )
    ).first()

    if existing:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "該年度已存在盤查"
            }
        )

    # 新增年度
    new_inventory = Year(
        year=survey.year,
        account_id=account_id
    )
    session.add(new_inventory)
    session.commit()
    session.refresh(new_inventory)

    return JSONResponse(content={
        "success": True,
        "year": new_inventory.year,
        "redirect_url": f"/inventory_list/boundary/{new_inventory.year}"
    })