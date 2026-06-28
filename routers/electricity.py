from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from audit_log import add_change_log
from database import engine
from model import Device, UtilityBill
from services.device_aggregator import recompute_device_emission

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/electricity", tags=["electricity"])


def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def electricity_page(request: Request, session: Session = Depends(get_session)):
    devices = session.exec(
        select(Device).where(Device.emission_type == "能源間接排放")
    ).all()
    return templates.TemplateResponse("electricity.html", {
        "request": request,
        "device_options": [{"id": d.id, "name": d.name} for d in devices],
    })


@router.get("/api/records")
async def list_records(session: Session = Depends(get_session)):
    bills = session.exec(
        select(UtilityBill)
        .where(UtilityBill.bill_type == "electricity")
        .order_by(UtilityBill.created_at.desc())
    ).all()
    return JSONResponse({
        "data": [
            {
                "id": b.id,
                "bill_month": b.bill_month,
                "period_start": b.period_start,
                "period_end": b.period_end,
                "usage_amount": b.usage_amount,
                "unit": b.unit,
                "target_year": b.target_year,
                "target_usage": b.target_usage,
                "device_id": b.device_id,
            }
            for b in bills
        ]
    })


@router.post("/records/create")
async def create_record(
    request: Request,
    bill_month: str = Form(...),
    period_start: str = Form(...),
    period_end: str = Form(...),
    usage_amount: float = Form(...),
    target_year: int = Form(...),
    target_usage: float = Form(...),
    device_id: int = Form(...),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if not device:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "找不到對應排放源，請先建立設備"},
        )

    bill = UtilityBill(
        bill_type="electricity",
        bill_month=bill_month,
        period_start=period_start,
        period_end=period_end,
        usage_amount=usage_amount,
        unit="度",
        target_year=target_year,
        target_usage=target_usage,
        device_id=device_id,
    )
    session.add(bill)
    session.flush()

    recompute_device_emission(session, device)

    add_change_log(
        session=session,
        module="electricity",
        entity_name="UtilityBill",
        record_key=str(bill.id),
        action_type="CREATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"bill_month={bill_month}, period={period_start}~{period_end}, "
            f"usage={usage_amount}, target_year={target_year}, "
            f"target_usage={target_usage}, device_id={device_id}"
        ),
    )
    session.commit()
    return JSONResponse({"success": True, "id": bill.id})


@router.post("/records/update/{bill_id}")
async def update_record(
    request: Request,
    bill_id: int,
    bill_month: str = Form(...),
    period_start: str = Form(...),
    period_end: str = Form(...),
    usage_amount: float = Form(...),
    target_year: int = Form(...),
    target_usage: float = Form(...),
    device_id: int = Form(...),
    session: Session = Depends(get_session),
):
    bill = session.get(UtilityBill, bill_id)
    if not bill or bill.bill_type != "electricity":
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "找不到該筆紀錄"},
        )

    old_device_id = bill.device_id
    bill.bill_month = bill_month
    bill.period_start = period_start
    bill.period_end = period_end
    bill.usage_amount = usage_amount
    bill.target_year = target_year
    bill.target_usage = target_usage
    bill.device_id = device_id
    session.add(bill)
    session.flush()

    affected_ids = {old_device_id, device_id} - {None}
    for did in affected_ids:
        device = session.get(Device, did)
        if device:
            recompute_device_emission(session, device)

    add_change_log(
        session=session,
        module="electricity",
        entity_name="UtilityBill",
        record_key=str(bill_id),
        action_type="UPDATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"bill_month={bill_month}, period={period_start}~{period_end}, "
            f"usage={usage_amount}, target_year={target_year}, "
            f"target_usage={target_usage}, device_id={device_id}"
        ),
    )
    session.commit()
    return JSONResponse({"success": True, "message": "紀錄已更新"})


@router.post("/records/delete/{bill_id}")
async def delete_record(
    request: Request,
    bill_id: int,
    session: Session = Depends(get_session),
):
    bill = session.get(UtilityBill, bill_id)
    if not bill or bill.bill_type != "electricity":
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "找不到該筆紀錄"},
        )

    affected_device_id = bill.device_id
    add_change_log(
        session=session,
        module="electricity",
        entity_name="UtilityBill",
        record_key=str(bill_id),
        action_type="DELETE",
        changed_by=str(request.session.get("user", "system")),
        change_details=(
            f"bill_month={bill.bill_month}, usage={bill.usage_amount}, "
            f"target_year={bill.target_year}, target_usage={bill.target_usage}"
        ),
    )
    session.delete(bill)
    session.flush()

    if affected_device_id:
        device = session.get(Device, affected_device_id)
        if device:
            recompute_device_emission(session, device)
    session.commit()
    return JSONResponse({"success": True, "message": "紀錄已刪除"})
