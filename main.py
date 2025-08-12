from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import uvicorn

from database import create_db_and_tables

from routers import gasoline as gasoline_router

app = FastAPI()
templates = Jinja2Templates(directory="templates")



app.include_router(gasoline_router.router)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    create_db_and_tables()
    uvicorn.run("main:app")

