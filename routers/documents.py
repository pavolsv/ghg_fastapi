import shutil

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from audit_log import add_change_log
from database import engine
from model import UtilityBill
from EOCR import ocr_recognize

router = APIRouter(prefix="/documents", tags=["documents"])
templates = Jinja2Templates(directory="templates")

BILL_TYPE_CONFIG = {
    "electricity": {"title": "電費單", "default_unit": "度"},
    "water": {"title": "水費單", "default_unit": "立方公尺"},
    "fuel": {"title": "加油單據", "default_unit": "公升"},
}

FUEL_TYPE_OPTIONS = ["車用汽油", "柴油"]


def get_session():
    with Session(engine) as session:
        yield session

@router.post("/ocr_upload")
async def ocr_upload(
    bill_type: str = Form(...),
    file: UploadFile = File(...),

):
    if bill_type not in BILL_TYPE_CONFIG:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "無效的單據類型"},
        )


    file_location = f"uploads/{file.filename}"
    
    try:
        # 1. 儲存上傳的檔案
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. 立即呼叫 OCR 模組，並傳遞檔案路徑
        ocr_result = ocr_recognize(file_location)
        
        # 3. 將辨識結果回傳
        return JSONResponse(content=ocr_result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"上傳失敗: {str(e)}"},
        )
        
@router.get("/{bill_type}", response_class=HTMLResponse)
async def document_manage_page(
    request: Request,
    bill_type: str,
    session: Session = Depends(get_session),
):
    if bill_type not in BILL_TYPE_CONFIG:
        return RedirectResponse(url="/documents/electricity", status_code=303)

    query = select(UtilityBill).where(UtilityBill.bill_type == bill_type)

    bills = list(session.exec(query).all())
    bills.sort(key=lambda bill: (bill.bill_month, bill.id or 0), reverse=True)

    total_usage = sum(float(bill.usage_amount) for bill in bills)

    # 燃料帳單：分別計算汽油、柴油用量
    gasoline_total = sum(
        float(b.usage_amount) for b in bills if b.fuel_type == "車用汽油"
    ) if bill_type == "fuel" else None
    diesel_total = sum(
        float(b.usage_amount) for b in bills if b.fuel_type == "柴油"
    ) if bill_type == "fuel" else None

    return templates.TemplateResponse(
        "document_management.html",
        {
            "request": request,
            "bill_type": bill_type,
            "bill_title": BILL_TYPE_CONFIG[bill_type]["title"],
            "default_unit": BILL_TYPE_CONFIG[bill_type]["default_unit"],
            "bills": bills,
            "total_usage": total_usage,
            "gasoline_total": gasoline_total,
            "diesel_total": diesel_total,
            "fuel_type_options": FUEL_TYPE_OPTIONS,
        },
    )


@router.post("/create")
async def create_bill(
    request: Request,
    bill_type: str = Form(...),
    bill_month: str = Form(default=""),
    period_start: str = Form(default=""),
    period_end: str = Form(default=""),
    fuel_date: str = Form(default=""),
    usage_amount: float = Form(...),
    unit: str = Form(...),
    fuel_type: str = Form(default=""),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
):
    if bill_type not in BILL_TYPE_CONFIG:
        return RedirectResponse(url="/documents/electricity", status_code=303)

    # 加油單據：從單一日期欄導出 bill_month 與 period
    if bill_type == "fuel" and fuel_date:
        bill_month = fuel_date[:7]
        period_start = fuel_date
        period_end = fuel_date

    new_bill = UtilityBill(
        bill_type=bill_type,
        bill_month=bill_month,
        period_start=period_start,
        period_end=period_end,
        usage_amount=usage_amount,
        unit=unit,
        note=note or None,
        fuel_type=fuel_type or None,
    )
    session.add(new_bill)
    session.flush()

    add_change_log(
        session=session,
        module="documents",
        entity_name="UtilityBill",
        record_key=str(new_bill.id),
        action_type="CREATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"bill_type={bill_type}, bill_month={bill_month}, period={period_start}~{period_end}, "
            f"usage_amount={usage_amount}, unit={unit}"
        ),
    )
    session.commit()
    return RedirectResponse(url=f"/documents/{bill_type}", status_code=303)


@router.post("/delete/{bill_id}")
async def delete_bill(
    request: Request,
    bill_id: int,
    bill_type: str = Form(...),
    session: Session = Depends(get_session),
):
    bill = session.get(UtilityBill, bill_id)
    if bill:
        add_change_log(
            session=session,
            module="documents",
            entity_name="UtilityBill",
            record_key=str(bill.id),
            action_type="DELETE",
            changed_by=str(request.session.get("user", "system")),
            change_details=(
                f"bill_type={bill.bill_type}, bill_month={bill.bill_month}, "
                f"usage_amount={bill.usage_amount}, unit={bill.unit}"
            ),
        )
        session.delete(bill)
        session.commit()

    redirect_type = bill_type if bill_type in BILL_TYPE_CONFIG else "electricity"
    return RedirectResponse(url=f"/documents/{redirect_type}", status_code=303)


@router.post("/update/{bill_id}")
async def update_bill(
    request: Request,
    bill_id: int,
    bill_type: str = Form(...),
    bill_month: str = Form(default=""),
    period_start: str = Form(default=""),
    period_end: str = Form(default=""),
    fuel_date: str = Form(default=""),
    usage_amount: float = Form(...),
    unit: str = Form(...),
    fuel_type: str = Form(default=""),
    note: str = Form(default=""),
    session: Session = Depends(get_session),
):
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    redirect_type = bill_type if bill_type in BILL_TYPE_CONFIG else "electricity"

    # 加油單據：從單一日期欄導出 bill_month 與 period
    if bill_type == "fuel" and fuel_date:
        bill_month = fuel_date[:7]
        period_start = fuel_date
        period_end = fuel_date

    bill = session.get(UtilityBill, bill_id)
    if not bill or bill.bill_type != redirect_type:
        if is_ajax:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "找不到單據資料"},
            )
        return RedirectResponse(url=f"/documents/{redirect_type}", status_code=303)

    old_bill_month = bill.bill_month
    old_period_start = bill.period_start
    old_period_end = bill.period_end
    old_usage_amount = bill.usage_amount
    old_unit = bill.unit
    old_note = bill.note

    bill.bill_month = bill_month
    bill.period_start = period_start
    bill.period_end = period_end
    bill.usage_amount = usage_amount
    bill.unit = unit
    bill.note = note or None
    bill.fuel_type = fuel_type or None

    add_change_log(
        session=session,
        module="documents",
        entity_name="UtilityBill",
        record_key=str(bill.id),
        action_type="UPDATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"bill_month: {old_bill_month} -> {bill.bill_month}, "
            f"period: {old_period_start}~{old_period_end} -> {bill.period_start}~{bill.period_end}, "
            f"usage_amount: {old_usage_amount} -> {bill.usage_amount}, "
            f"unit: {old_unit} -> {bill.unit}, "
            f"note: {old_note or '-'} -> {bill.note or '-'}"
        ),
    )
    session.add(bill)
    session.commit()

    if is_ajax:
        return JSONResponse(
            content={
                "success": True,
                "bill": {
                    "id": bill.id,
                    "bill_month": bill.bill_month,
                    "period_start": bill.period_start,
                    "period_end": bill.period_end,
                    "usage_amount": bill.usage_amount,
                    "unit": bill.unit,
                    "note": bill.note or "",
                    "fuel_type": bill.fuel_type or "",
                },
            }
        )

    return RedirectResponse(url=f"/documents/{redirect_type}", status_code=303)
