from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/factor_management", tags=["factor_management"])


@router.get("/", response_class=HTMLResponse)
async def factor_management_page(request: Request):
    return templates.TemplateResponse("factor_management.html", {"request": request})
