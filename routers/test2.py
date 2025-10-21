from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from database import get_session
from model import Utility, UtilityFactor

router = APIRouter(prefix="/test2", tags=["test2"])
template = Jinja2Templates(directory="templates")


# 列出所有係數
@router.get("/", response_class=HTMLResponse)
async def test2_page(
    request: Request,
    utility_name: Optional[str] = None,
    session: Session = Depends(get_session),
):
    selected_utility = None
    filtered_utilities = session.exec(select(Utility)).all()
    utility_map = {u.id: u.utility_name for u in filtered_utilities}

    # 建立基本的查詢
    query = select(UtilityFactor)

    if utility_name:
        utility = session.exec(
            select(Utility).where(Utility.utility_name == utility_name)
        ).first()
        if utility:
            selected_utility = utility.utility_name
            # 如果找到對應的 Utility，就篩選相關的 UtilityFactor
            query = select(UtilityFactor).where(UtilityFactor.utility_id == utility.id)
            # 同時也篩選要傳給前端的 utilities 列表
            filtered_utilities = [utility]
        else:
            # 如果找不到，就將 selected_utility 設為空，並返回一個空列表給前端，
            # 避免 `None` 錯誤
            factors = []
            return template.TemplateResponse(
                "test2.html",
                {
                    "request": request,
                    "factors": factors,
                    "utilities": filtered_utilities,
                    "utility_map": utility_map,
                    "selected_utility": selected_utility,
                },
            )

    factors = session.exec(query).all()

    return template.TemplateResponse(
        "test2.html",
        {
            "request": request,
            "factors": factors,
            "utilities": filtered_utilities,
            "utility_map": utility_map,
            "selected_utility": selected_utility,
        },
    )
