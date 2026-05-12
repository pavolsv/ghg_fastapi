from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/gasoline",
    tags=["Gasoline"]
)

@router.get("/", response_class=HTMLResponse)
async def gasoline_sum_page(request: Request):
    return templates.TemplateResponse("gas_value_cal.html", {"request": request})