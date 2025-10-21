from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/index",
    tags=["index"]
)

@router.get("/", response_class=HTMLResponse)
async def gasoline_sum_page(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login/", status_code=303)
    
    return templates.TemplateResponse("index.html", {"request": request, "user": request.session.get("user")})