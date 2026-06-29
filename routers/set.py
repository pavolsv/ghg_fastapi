from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from fastapi import Depends

from audit_log import add_change_log
from model import CompanyInfo
from dependencies import get_session
from database import engine
from sqlmodel import Session

templates = Jinja2Templates(directory="templates")

router = APIRouter(
    prefix="/set",
    tags=["set"]
)

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

    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        # 查詢該帳號是否已有公司資料
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
            action = "UPDATE"
        else:
            # 新增：如果 taxId 為空，自動生成一個唯一值
            final_tax_id = taxId.strip() if taxId and taxId.strip() else f"TEMP_{user_id}_{int(__import__('time').time())}"
            new_info = CompanyInfo(
                account_id=user_id,
                company_name=companyName,
                tax_id=final_tax_id,
                address=address,
                owner=owner,
                contact_person=contact_person,
                telephone=telephone,
                email=email,
                URL=URL
            )
            session.add(new_info)
            action = "CREATE"

        add_change_log(
            session=session,
            module="company_info",
            entity_name="CompanyInfo",
            record_key=str(user_id),
            action_type=action,
            changed_by=str(user_id),
            change_details=f"company_name={companyName}, tax_id={taxId}, owner={owner}",
        )
        session.commit()
        return RedirectResponse(
        url=router.prefix + "/",
        status_code=303
    )