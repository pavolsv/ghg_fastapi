from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlmodel import create_engine, Session, SQLModel, select
from fastapi import Form
from model import CompanyInfo

templates = Jinja2Templates(directory="templates")

router = APIRouter(
    prefix="/set",
    tags=["set"]
)

db = "sqlite:///database.db"
engine = create_engine(db, echo=True)

@router.get("/", response_class=HTMLResponse)
async def register_page(request: Request):
        
        user_id = request.session.get("user")

        if not user_id:
            return RedirectResponse(url="/login", status_code=303)
        
        with Session(engine) as session:
            # 查詢該帳號是否已有公司資料
            statement = select(CompanyInfo).where(CompanyInfo.account_id == user_id)
            existing = session.exec(statement).first()

            # 傳給前端的資料，如果沒有資料就給空字串
            user_data = {
            "companyName": existing.company_name if existing else "",
            "taxId": existing.tax_id if existing else "",
            "address": existing.address if existing else "",
            "owner": existing.owner if existing else "",
            "contact_person": existing.contact_person if existing else "",
            "telephone": existing.telephone if existing else "",
            "email": existing.email if existing else "",
            "URL": existing.URL if existing else ""
            
            
            }

        return templates.TemplateResponse("set.html", {"request": request, "user": user_data})


@router.post("/")
async def set_company_info(
    request: Request,
    companyName: str = Form(...),
    taxId: str = Form(...),
    address: str = Form(...),
    owner: str = Form(...),
    contact_person : str = Form(...),
    telephone : str = Form(...),
    email : str = Form(...),
    URL : str = Form(...),

):

    with Session(engine) as session:
        # 查詢該帳號是否已有公司資料
        user_id = request.session.get("user")
        statement = select(CompanyInfo).where(CompanyInfo.account_id == user_id)
        existing = session.exec(statement).first()

        if existing:
            # 更新
            existing.company_name = companyName
            existing.tax_id = taxId
            existing.address = address
            existing.owner = owner
            existing.contact_person = contact_person
            existing.telephone = telephone
            existing.email = email
            existing.URL = URL
            session.add(existing)
        else:
            # 新增
            new_info = CompanyInfo(
                account_id=request.session["user"],
                company_name=companyName,
                tax_id=taxId,
                address=address,
                owner=owner,
                contact_person=contact_person,
                telephone=telephone,
                email=email,
                URL=URL
            )
            session.add(new_info)

        session.commit()

        statement = select(CompanyInfo).where(CompanyInfo.account_id == request.session["user"])
        updated = session.exec(statement).first()

        user_data = {
            "companyName": updated.company_name,
            "taxId": updated.tax_id,
            "address": updated.address,
            "owner": updated.owner
        }
        return RedirectResponse(
        url=router.prefix + "/", # 導向回 /set/ 頁面
        status_code=303 
    )