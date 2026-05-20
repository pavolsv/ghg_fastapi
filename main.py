import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from database import create_db_and_tables, engine
from model import Device, EmissionFactor
from routers import (
    activity,
    boundary,
    calculation,
    devices,
    documents,
    emission,
    etl_script,
    factor_management,
    gwp,
    index,
    inventory_list,
    login,
    logout,
    ocr_recognition,
    register,
    report_editor,
    result,
    set,
)
from routers import appendix as appendix_router
from routers import electricity as electricity_router
from routers import logs as logs_router

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key="1shh3345sknn1h1b244xf")


app.include_router(electricity_router.router)
app.include_router(documents.router)
app.include_router(register.router)
app.include_router(login.router)
app.include_router(logout.router)
app.include_router(index.router)
app.include_router(factor_management.router)
app.include_router(etl_script.router)
app.include_router(gwp.router)
app.include_router(devices.router)
app.include_router(calculation.router)
app.include_router(result.router)
app.include_router(report_editor.router)
app.include_router(set.router)
app.include_router(logs_router.router)
app.include_router(inventory_list.router)
app.include_router(emission.router)
app.include_router(activity.router)
app.include_router(boundary.router)
app.include_router(ocr_recognition.router)
app.include_router(appendix_router.router)
app.mount("/static", StaticFiles(directory="static"))


@app.on_event("startup")
async def on_startup():
    create_db_and_tables()
    # Seed 「電費單」設備（若不存在則建立）
    with Session(engine) as session:
        existing = session.exec(
            select(Device).where(
                Device.factor_ref_code == "ELECTRICITY",
                Device.emission_type == "能源間接排放",
            )
        ).first()
        if not existing:
            elec_device = Device(
                name="電費單",
                category="能源間接排放",
                emission_type="能源間接排放",
                location="-",
                factor_ref_code="ELECTRICITY",
                gas_type="CO2e",
                unit="度",
            )
            session.add(elec_device)
            session.commit()

    # Seed 「車用汽油」與「柴油」設備（移動燃燒，若不存在則建立）
    with Session(engine) as session:
        fuel_seed_configs = [
            {"keyword": "車用汽油", "device_name": "車用汽油"},
            {"keyword": "柴油", "device_name": "柴油"},
        ]
        for cfg in fuel_seed_configs:
            # 從 EmissionFactor 找移動燃燒中名稱含關鍵字的因子
            factor = session.exec(
                select(EmissionFactor).where(
                    EmissionFactor.emission_type == "移動燃燒",
                    col(EmissionFactor.name).contains(cfg["keyword"]),
                )
            ).first()
            if not factor:
                continue  # 尚未匯入係數，跳過

            existing_dev = session.exec(
                select(Device).where(
                    Device.factor_ref_code == factor.original_code,
                    Device.emission_type == "移動燃燒",
                )
            ).first()
            if not existing_dev:
                fuel_device = Device(
                    name=cfg["device_name"],
                    category="移動燃燒",
                    emission_type="移動燃燒",
                    location="-",
                    factor_ref_code=factor.original_code,
                    gas_type="CO2e",
                    unit="公升",
                )
                session.add(fuel_device)
        session.commit()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


if __name__ == "__main__":
    create_db_and_tables()
    uvicorn.run("main:app", port=8000)
