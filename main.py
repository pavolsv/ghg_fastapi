import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from database import create_db_and_tables, engine
from model import Device, EmissionFactor604
from routers import (
    calculation,
    devices,
    documents,
    emission_source,
    etl_script,
    factor_management,
    gwp,
    index,
    login,
    logout,
    org_chart,
    register,
    result,
    set,
)

# from routers import ocr_recognition
from routers import appendix as appendix_router
from routers import electricity as electricity_router
from routers import logs as logs_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response



os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

app = FastAPI()
templates = Jinja2Templates(directory="templates")
# Security: session secret must come from environment; do not commit hard-coded secrets.
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    import secrets as _secrets

    SESSION_SECRET_KEY = _secrets.token_urlsafe(32)
    print(
        "WARNING: SESSION_SECRET_KEY not set; a temporary key has been generated. "
        "Set SESSION_SECRET_KEY in production to keep sessions stable."
    )
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)
app.add_middleware(SecurityHeadersMiddleware)


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
app.include_router(emission_source.router)
app.include_router(calculation.router)
app.include_router(result.router)
app.include_router(set.router)
app.include_router(org_chart.router)
app.include_router(logs_router.router)

# app.include_router(ocr_recognition.router)
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
                scope="scope2",
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
            # 從 EmissionFactor604 找移動燃燒中名稱含關鍵字的因子
            factor = session.exec(
                select(EmissionFactor604).where(
                    EmissionFactor604.emission_type == "移動燃燒",
                    col(EmissionFactor604.name).contains(cfg["keyword"]),
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
                    scope="scope1",
                )
                session.add(fuel_device)
        session.commit()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


if __name__ == "__main__":
    create_db_and_tables()
    uvicorn.run("main:app", port=8000)
