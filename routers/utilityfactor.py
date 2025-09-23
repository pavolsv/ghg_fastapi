from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import List

from model import Utility, UtilityFactor
from database import get_session

router = APIRouter(prefix="/utilityfactor", tags=["utilityfactor"])
template = Jinja2Templates(directory="templates")


# 列出所有係數
@router.get("/", response_class=HTMLResponse)
async def utility_factor_page(request: Request, session: Session = Depends(get_session)):
    factors = session.exec(select(UtilityFactor)).all()
    utilities = session.exec(select(Utility)).all()

    utility_map = {utility.id: utility.utility_name for utility in utilities}

    return template.TemplateResponse(
        "utilityfactor.html",
        {
            "request": request,
            "factors": factors,
            "utilities": utilities,
            "utility_map": utility_map
        }
    )


@router.post("/", response_class=HTMLResponse)
async def create_utility_factor_from_form(
    request: Request,
    session: Session = Depends(get_session),
    utility_id: int = Form(...),
    utility_factor_year: int = Form(...),
    utility_factor_value: float = Form(...),
    utility_factor_unit: str = Form(...),
    utility_factor_source: str = Form(...)
):

    factor = UtilityFactor(
        utility_id=utility_id,
        utility_factor_year=utility_factor_year,
        utility_factor_value=utility_factor_value,
        utility_factor_unit=utility_factor_unit,
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
