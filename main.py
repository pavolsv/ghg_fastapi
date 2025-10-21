import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from database import create_db_and_tables
from routers import electricity as electricity_router
from routers import factor_management
from routers import file_upload
from routers import gasoline as gasoline_router
from routers import gwplist
from routers import index
from routers import login
from routers import logout
from routers import register
from routers import set
from routers import test1, test2
from routers import utilityfactor
from routers import water_fee as water_fee_router

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key="1shh3345sknn1h1b244xf")


app.include_router(gasoline_router.router)
app.include_router(water_fee_router.router)
app.include_router(electricity_router.router)
app.include_router(gwplist.router)
app.include_router(utilityfactor.router)
app.include_router(register.router)
app.include_router(login.router)
app.include_router(logout.router)
app.include_router(index.router)
app.include_router(file_upload.router)
app.include_router(test1.router)
app.include_router(test2.router)
app.include_router(factor_management.router)
app.include_router(set.router)
app.mount("/static", StaticFiles(directory="static"))


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


if __name__ == "__main__":
    create_db_and_tables()
    uvicorn.run("main:app")
