import shutil

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from audit_log import add_change_log
from database import engine
from model import UtilityBill, Device
from EOCR import ocr_recognize
from file_utils import safe_upload_path
from services.device_aggregator import recompute_device_emission

router = APIRouter(prefix="/documents", tags=["documents"])
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads"

BILL_TYPE_CONFIG = {
    "electricity": {"title": "電費單", "default_unit": "度"},

    "fuel": {"title": "加油單據", "default_unit": "公升"},
}

FUEL_TYPE_OPTIONS = ["車用汽油", "柴油"]


def get_session():
    with Session(engine) as session:
        yield session


def _list_devices_for_bill(session: Session, bill_type: str) -> list[Device]:
    """回傳可掛載該類型帳單的設備清單（依 emission_type 篩選）。"""
    if bill_type == "electricity":
        stmt = select(Device).where(Device.emission_type == "能源間接排放")
    elif bill_type == "fuel":
        stmt = select(Device).where(Device.emission_type == "移動燃燒")
    else:
        stmt = select(Device)
    return list(session.exec(stmt.order_by(Device.id)).all())


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


    try:
        file_location = str(safe_upload_path(UPLOAD_DIR, file.filename))
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

    # 燃料模式：改用設備分組區塊顯示
    if bill_type == "fuel":
        devices = _list_devices_for_bill(session, bill_type)
        fuel_bills = list(session.exec(
            select(UtilityBill).where(UtilityBill.bill_type == "fuel")
        ).all())

        device_groups = []
        for d in devices:
            bills = [b for b in fuel_bills if b.device_id == d.id]
            bills.sort(key=lambda b: b.period_start, reverse=True)
            total_liters = sum(float(b.usage_amount) for b in bills)
            device_groups.append({
                "device": d,
                "bills": bills,
                "total": total_liters,
            })

        # 未掛載設備的加油單
        unassigned = [b for b in fuel_bills if not b.device_id]
        unassigned.sort(key=lambda b: b.period_start, reverse=True)

        return templates.TemplateResponse(
            "document_management.html",
            {
                "request": request,
                "bill_type": bill_type,
                "bill_title": BILL_TYPE_CONFIG[bill_type]["title"],
                "default_unit": BILL_TYPE_CONFIG[bill_type]["default_unit"],
                "device_groups": device_groups,
                "unassigned": unassigned,
                "fuel_type_options": FUEL_TYPE_OPTIONS,
            },
        )

    # 非燃料模式（電費/水費）維持原狀
    query = select(UtilityBill).where(UtilityBill.bill_type == bill_type)
    bills = list(session.exec(query).all())
    bills.sort(key=lambda bill: (bill.bill_month, bill.id or 0), reverse=True)
    total_usage = sum(float(bill.usage_amount) for bill in bills)

    device_options = [
        {"id": d.id, "name": d.name}
        for d in _list_devices_for_bill(session, bill_type)
    ]

    return templates.TemplateResponse(
        "document_management.html",
        {
            "request": request,
            "bill_type": bill_type,
            "bill_title": BILL_TYPE_CONFIG[bill_type]["title"],
            "default_unit": BILL_TYPE_CONFIG[bill_type]["default_unit"],
            "bills": bills,
            "total_usage": total_usage,
            "device_options": device_options,
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
    device_id: int = Form(default=0),
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
        device_id=device_id if device_id and device_id > 0 else None,
    )
    session.add(new_bill)
    session.flush()

    # 自動加總到設備
    if new_bill.device_id:
        device = session.get(Device, new_bill.device_id)
        if device:
            recompute_device_emission(session, device)

    add_change_log(
        session=session,
        module="documents",
        entity_name="UtilityBill",
        record_key=str(new_bill.id),
        action_type="CREATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"bill_type={bill_type}, bill_month={bill_month}, period={period_start}~{period_end}, "
            f"usage_amount={usage_amount}, unit={unit}, device_id={new_bill.device_id}"
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
    affected_device_id: int | None = None
    if bill:
        affected_device_id = bill.device_id
        add_change_log(
            session=session,
            module="documents",
            entity_name="UtilityBill",
            record_key=str(bill_id),
            action_type="DELETE",
            changed_by=str(request.session.get("user", "system")),
            change_details=(
                f"bill_type={bill.bill_type}, bill_month={bill.bill_month}, "
                f"usage_amount={bill.usage_amount}, unit={bill.unit}"
            ),
        )
        session.delete(bill)
        session.flush()

        # 重新計算掛載設備的累積值
        if affected_device_id:
            device = session.get(Device, affected_device_id)
            if device:
                recompute_device_emission(session, device)
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
    device_id: int = Form(default=0),
    session: Session = Depends(get_session),
):
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    redirect_type = bill_type if bill_type in BILL_TYPE_CONFIG else "electricity"

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

    old_device_id = bill.device_id
    new_device_id = device_id if device_id and device_id > 0 else None

    bill.bill_month = bill_month
    bill.period_start = period_start
    bill.period_end = period_end
    bill.usage_amount = usage_amount
    bill.unit = unit
    bill.note = note or None
    bill.fuel_type = fuel_type or None
    bill.device_id = new_device_id

    add_change_log(
        session=session,
        module="documents",
        entity_name="UtilityBill",
        record_key=str(bill.id),
        action_type="UPDATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"usage_amount={bill.usage_amount}, unit={bill.unit}, "
            f"device_id: {old_device_id} -> {new_device_id}"
        ),
    )
    session.add(bill)
    session.flush()

    # 重新計算被影響的設備
    affected_ids = {old_device_id, new_device_id} - {None}
    for did in affected_ids:
        device = session.get(Device, did)
        if device:
            recompute_device_emission(session, device)
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
                    "device_id": bill.device_id,
                },
            }
        )

    return RedirectResponse(url=f"/documents/{redirect_type}", status_code=303)
