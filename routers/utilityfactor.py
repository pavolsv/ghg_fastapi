from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, join
from typing import List, Optional

from model import Utility, UtilityFactor
from database import get_session

router = APIRouter(prefix="/utilityfactor", tags=["utilityfactor"])
template = Jinja2Templates(directory="templates")


# 列出所有係數
@router.get("/", response_class=HTMLResponse)
async def utility_factor_page(
    request: Request,
    utility_name: Optional[str] = None,
    session: Session = Depends(get_session)
):
    selected_utility = None
    filtered_utilities = session.exec(select(Utility)).all()
    utility_map = {u.id: u.utility_name for u in filtered_utilities}
    
    # 建立基本的查詢
    query = select(UtilityFactor)

    if utility_name:
        utility = session.exec(select(Utility).where(Utility.utility_name == utility_name)).first()
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
                "utilityfactor.html",
                {
                    "request": request,
                    "factors": factors,
                    "utilities": filtered_utilities,
                    "utility_map": utility_map,
                    "selected_utility": selected_utility
                }
            )

    factors = session.exec(query).all()

    return template.TemplateResponse(
        "utilityfactor.html",
        {
            "request": request,
            "factors": factors,
            "utilities": filtered_utilities,
            "utility_map": utility_map,
            "selected_utility": selected_utility
        }
    )

@router.post("/", response_class=HTMLResponse)
async def create_utility_factor_from_form(
    request: Request,
    session: Session = Depends(get_session),
    utility_id: int = Form(...),
    utility_factor_year: int = Form(...),
    utility_factor_value: float = Form(...),
    utility_factor_source: str = Form(...)
):
    if utility_id == 0:
        unit = "CO₂/kWh"
    elif utility_id == 1:
        unit = "CO₂/m³"
    else:
        unit = "不適用"

    factor = UtilityFactor(
        utility_id=utility_id,
        utility_factor_year=utility_factor_year,
        utility_factor_value=utility_factor_value,
        utility_factor_unit=unit,
        utility_factor_source=utility_factor_source
    )
    session.add(factor)
    session.commit()
    session.refresh(factor)
    return RedirectResponse(url="/utilityfactor/", status_code=303)


# 刪除
@router.post("/{factor_id}/delete", response_class=HTMLResponse)
async def delete_utility_factor(request: Request, factor_id: int, session: Session = Depends(get_session)):
    factor = session.get(UtilityFactor, factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="Factor not found")
    session.delete(factor)
    session.commit()
    return RedirectResponse(url="/utilityfactor/", status_code=303)


# API 端點
@router.get("/api/factors/", response_model=List[UtilityFactor])
def read_utility_factors_api(*, session: Session = Depends(get_session)):
    factors = session.exec(select(UtilityFactor)).all()
    return factors


@router.get("/api/factors/{factor_id}", response_model=UtilityFactor)
def read_utility_factor_by_id_api(*, session: Session = Depends(get_session), factor_id: int):
    factor = session.get(UtilityFactor, factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="Factor not found")
    return factor


@router.put("/api/factors/{factor_id}", response_model=UtilityFactor)
def update_utility_factor_api(
    *, session: Session = Depends(get_session), factor_id: int, new_factor: UtilityFactor
):
    db_factor = session.get(UtilityFactor, factor_id)
    if not db_factor:
        raise HTTPException(status_code=404, detail="Factor not found")

    db_factor.utility_id = new_factor.utility_id
    db_factor.utility_factor_year = new_factor.utility_factor_year
    db_factor.utility_factor_value = new_factor.utility_factor_value
    db_factor.utility_factor_unit = new_factor.utility_factor_unit
    db_factor.utility_factor_source = new_factor.utility_factor_source

    session.add(db_factor)
    session.commit()
    session.refresh(db_factor)
    return db_factor


@router.delete("/api/factors/{factor_id}")
def delete_utility_factor_api(*, session: Session = Depends(get_session), factor_id: int):
    factor = session.get(UtilityFactor, factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="Factor not found")
    session.delete(factor)
    session.commit()
    return {"message": "Factor deleted successfully"}