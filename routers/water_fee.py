from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/water_fee",
    tags=["Water Fee"]
)

@router.get("/", response_class=HTMLResponse)
async def water_fee_page(request: Request):
    return templates.TemplateResponse("water_fee.html", {"request": request})