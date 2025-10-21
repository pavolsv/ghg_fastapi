from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Form
from fastapi.responses import JSONResponse
from sqlmodel import create_engine, Session, SQLModel, select
from model import Account


templates = Jinja2Templates(directory="templates") 
router = APIRouter(
    prefix="/register",
    tags=["register"]
)


@router.get("/", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/")
async def register_account(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    print(email, username, password)

    db = "sqlite:///database.db"
    engine = create_engine(db, echo=True)

    filed_name = [ "email", "account", "password"]
    filed_data = {"email":email, "account":username, "password":password}
    remind = ["此電子郵件已有人使用!", "此帳號已有人使用!", "此密碼已有人使用!"]

    is_legal = True
    with Session(engine) as session:
        for i in range(3):
            statement = select(Account).where(getattr(Account, filed_name[i]) == filed_data[filed_name[i]])
            data = session.exec(statement).all()
            if data != []:
                is_legal = False
                return templates.TemplateResponse("register.html", {"request": request , "message":remind[i]})
    

        if is_legal:
            new_account = Account(account=username, email=email, password=password)
            session.add(new_account)  # 將資料加入 session
            session.commit()           # 提交到資料庫
            return templates.TemplateResponse("login.html", {"request": request })