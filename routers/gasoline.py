from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session

from database import engine
from services.emission_calculator import (
    calculate_combustion_emission,
    get_lhv_for_fuel,
)
from constants.lhv_defaults import get_lhv_value

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/gasoline",
    tags=["Gasoline"]
)


# 對應的排放係數 original_code（移動燃燒）
FUEL_CODE_MAP = {
    "汽油": "170001",   # 車用汽油
    "柴油": "170006",   # 柴油
}


class FuelRow(BaseModel):
    date: str | None = None
    liters: float
    fuel_type: str  # "汽油" | "柴油"


class FuelCalcRequest(BaseModel):
    rows: list[FuelRow]


def get_session():
    with Session(engine) as session:
        yield session


def _calc_fuel_type(session: Session, fuel_type: str, total_liters: float) -> dict[str, Any]:
    """依燃油類型與總公升數，呼叫統一計算服務取得各氣體排放。"""
    original_code = FUEL_CODE_MAP.get(fuel_type)
    if not original_code or not total_liters:
        return {
            "fuel_type": fuel_type,
            "liters": float(total_liters or 0),
            "lhv_value": 0.0,
            "lhv_unit": "",
            "tj": 0.0,
            "CO2": 0.0,
            "CH4": 0.0,
            "N2O": 0.0,
            "CO2e": 0.0,
            "supported": False,
        }

    # 取熱值（DB → code defaults fallback）
    lhv_value, lhv_unit = get_lhv_for_fuel(session, original_code)
    if not lhv_value or not lhv_unit:
        lhv_value, lhv_unit = get_lhv_value(original_code)
    lhv_value = float(lhv_value or 0)
    lhv_unit = str(lhv_unit or "")

    # 移動燃燒
    result = calculate_combustion_emission(
        session=session,
        original_code=original_code,
        emission_type="移動燃燒",
        activity_value=float(total_liters),
        lhv_value=lhv_value,
        lhv_unit=lhv_unit,
        year=None,
    )
    return {
        "fuel_type": fuel_type,
        "liters": float(total_liters),
        "lhv_value": lhv_value,
        "lhv_unit": lhv_unit,
        "CO2": float(result.get("CO2", 0) or 0),
        "CH4": float(result.get("CH4", 0) or 0),
        "N2O": float(result.get("N2O", 0) or 0),
        "CO2e": float(result.get("CO2e", 0) or 0),
        "supported": True,
    }


@router.get("/", response_class=HTMLResponse)
async def gasoline_sum_page(request: Request):
    return templates.TemplateResponse("gas_value_cal.html", {"request": request})


@router.post("/api/calculate")
async def gasoline_calculate(
    payload: FuelCalcRequest,
    session: Session = Depends(get_session),
):
    gasoline_liters = sum(r.liters for r in payload.rows if r.fuel_type == "汽油")
    diesel_liters = sum(r.liters for r in payload.rows if r.fuel_type == "柴油")

    gasoline = _calc_fuel_type(session, "汽油", gasoline_liters) if gasoline_liters else None
    diesel = _calc_fuel_type(session, "柴油", diesel_liters) if diesel_liters else None

    total_co2e = sum(item["CO2e"] for item in (gasoline, diesel) if item)
    total_liters = gasoline_liters + diesel_liters

    return JSONResponse({
        "success": True,
        "data": {
            "gasoline_liters": round(gasoline_liters, 4),
            "diesel_liters": round(diesel_liters, 4),
            "total_liters": round(total_liters, 4),
            "gasoline": gasoline,
            "diesel": diesel,
            "total_co2e": round(total_co2e, 4),
        },
    })