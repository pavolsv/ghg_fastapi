from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from database import engine
from model import Device, EmissionRecord
from routers.calculation import TARGET_YEAR

router = APIRouter(prefix="/result", tags=["result"])
templates = Jinja2Templates(directory="templates")


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def result_page(request: Request, session: Session = Depends(get_session)):
    records = session.exec(select(EmissionRecord)).all()
    devices = session.exec(select(Device)).all()
    device_map = {device.id: device for device in devices}

    total_co2e = round(sum(record.total_co2e for record in records), 4)

    emission_type_totals = {}
    for record in records:
        device = device_map.get(record.device_id)
        emission_type = (device.emission_type if device else "未分類") or "未分類"
        emission_type_totals[emission_type] = round(
            emission_type_totals.get(emission_type, 0.0) + record.total_co2e,
            4,
        )

    emission_type_labels = list(emission_type_totals.keys())
    emission_type_values = [emission_type_totals[label] for label in emission_type_labels]

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "inventory_year": TARGET_YEAR,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_co2e": total_co2e,
            "emission_type_labels": emission_type_labels,
            "emission_type_values": emission_type_values,
        },
    )
