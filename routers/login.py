import random
import string
import io
import secrets


from captcha.image import ImageCaptcha
from fastapi import APIRouter, Request, Response
from fastapi import Form
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from fastapi import Depends

from model import Account
from dependencies import get_session
from auth_utils import verify_password

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/login", tags=["login"])


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/captcha-image")
async def get_captcha_image(request: Request):
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    captcha_text = "".join(secrets.choice(chars) for _ in range(4))
    print(captcha_text)
    request.session["captcha_code"] = captcha_text

    image = ImageCaptcha(width=220, height=80, font_sizes=[40, 50])
    data = image.generate(captcha_text)

    return Response(content=data.getvalue(), media_type="image/jpeg")


@router.post("/")
async def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    VerificationCode: str = Form(...),
    session=Depends(get_session),
):

    session_captcha_code = request.session.pop("captcha_code", "")

    statement = select(Account).where(Account.account == username)  # type: ignore
    account = session.exec(statement).first()

    context = {"request": request, "username_value": username}

    if account and verify_password(password, account.password):
        if VerificationCode.upper() == session_captcha_code.upper():
            request.session["user"] = account.id  # 如果登入成功，則將使用者帳號的id儲存到session中，用來做後續的資料權限的驗證
            request.session["username"] = account.account
            return RedirectResponse(url="/index/", status_code=303)
        else:
            context["message"] = "驗證碼錯誤！"
            return templates.TemplateResponse("login.html", context)
    else:
        return templates.TemplateResponse(
            "login.html", {"request": request, "message": "帳號或密碼錯誤！"}
        )
