from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/logout",
    tags=["logout"]
)

@router.post("/")
async def logout(request: Request):
    request.session.pop("user", None)  # 刪除登入狀態
    return RedirectResponse(url="/login/", status_code=303)
