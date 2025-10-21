import random
import string

from captcha.image import ImageCaptcha
from fastapi import APIRouter, Request, Response
from fastapi import Form
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import create_engine, Session, select

from model import Account

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/login", tags=["login"])


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/captcha-image")
async def get_captcha_image(request: Request):
    characters = string.ascii_letters + string.digits
    captcha_text = "".join(random.choice(characters) for _ in range(4))
    print(captcha_text)
    request.session["captcha_code"] = captcha_text

    print(request.session["captcha_code"])

    image = ImageCaptcha(width=220, height=80, font_sizes=[40, 50])
    data = image.generate(captcha_text)

    return Response(content=data.getvalue(), media_type="image/jpeg")


@router.post("/")
async def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    VerificationCode: str = Form(...),
):

    print(f"從表單接收到的用戶名: {username}")
    print(f"從表單接收到的密碼: {password}")
    print(f"從表單接收到的密碼: {VerificationCode}")

    db = "sqlite:///database.db"
    engine = create_engine(db, echo=True)

    with Session(engine) as session:
        statement = select(Account).where(Account.account == username, Account.password == password)  # type: ignore
        existing_utilities = session.exec(statement).all()

        session_captcha_code = request.session.pop("captcha_code", "")

        context = {"request": request, "username_value": username}

        if existing_utilities:
            if VerificationCode == session_captcha_code:
                request.session["user"] = existing_utilities[
                    0
                ].id  # 如果登入成功，則將使用者帳號的id儲存到session中，用來做後續的資料權限的驗證
                return RedirectResponse(url="/index/", status_code=303)
            else:
                context["message"] = "驗證碼錯誤！"
                return templates.TemplateResponse("login.html", context)
        else:
            return templates.TemplateResponse(
                "login.html", {"request": request, "message": "帳號或密碼錯誤！"}
            )
