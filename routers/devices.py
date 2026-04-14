from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from audit_log import add_change_log
from database import engine
from model import Device, EmissionFactor, GWPReference

router = APIRouter(prefix="/devices", tags=["devices"])
templates = Jinja2Templates(directory="templates")


# 取得資料庫 Session 的輔助函式
def get_session():
    with Session(engine) as session:
        yield session


@router.get("/", response_class=HTMLResponse)
async def device_manage_page(request: Request, session: Session = Depends(get_session)):
    # 1. 撈取所有設備
    devices = session.exec(select(Device).order_by(col(Device.id).desc())).all()

    # 2. 建立一個對照表 { "代碼": "名稱" }
    # 這樣我們可以在 HTML 中透過設備的 factor_ref_code 顯示對應的名稱
    all_factors = session.exec(
        select(
            EmissionFactor.name,
            EmissionFactor.original_code,
            EmissionFactor.emission_type,
        ).distinct()
    ).all()
    factor_map = {
        original_code: name for name, original_code, _emission_type in all_factors
    }
    factor_options_json = [
        {
            "name": name,
            "original_code": original_code,
            "emission_type": emission_type,
        }
        for name, original_code, emission_type in all_factors
    ]

    # 加入逸散排放（冷媒）選項，來源為 GWPReference
    gwp_refs = session.exec(
        select(GWPReference).order_by(GWPReference.gas_name_zh)
    ).all()
    for gwp in gwp_refs:
        label = f"{gwp.gas_name_zh}（{gwp.formula}）"
        factor_options_json.append({
            "name": label,
            "original_code": gwp.formula,
            "emission_type": "逸散排放",
        })
        factor_map[gwp.formula] = label

    return templates.TemplateResponse(
        "device_management.html",
        {
            "request": request,
            "devices": devices,
            "factor_map": factor_map,  # 傳送名稱對照表
            "factor_options_json": factor_options_json,
        },
    )


# ... 您的現有 import ...


@router.post("/create")
async def create_device(
    request: Request,
    name: str = Form(...),
    location: str = Form(...),
    factor_ref_code: str = Form(...),
    emission_type: str = Form(default="固定燃燒"),
    session: Session = Depends(get_session),
):
    """處理設備新增：接收多選氣體並自動帶入類型/單位"""

    # 1. 獲取多選的氣體清單 (由 JS 動態產生的 gas_type 選項)
    form_data = await request.form()
    gas_types = [value for value in form_data.getlist("gas_type") if isinstance(value, str)]
    gas_str = ",".join(gas_types)  # 存成 "CO2,CH4"

    # 2. 自動根據燃料代碼，找出該燃料的類型與單位
    if emission_type == "逸散排放":
        # 冷媒設備：從 GWPReference 查詢
        gwp_ref = session.exec(
            select(GWPReference).where(GWPReference.formula == factor_ref_code)
        ).first()
        device_category = "逸散排放"
        device_unit = "公斤"
        device_name_fallback = gwp_ref.gas_name_zh if gwp_ref else name
    else:
        base_factor = session.exec(
            select(EmissionFactor).where(EmissionFactor.original_code == factor_ref_code)
        ).first()
        device_category = base_factor.emission_type if base_factor else "未分類"
        device_unit = base_factor.unit if base_factor else "單位"
        device_name_fallback = None

    new_device = Device(
        name=name,
        location=location,
        gas_type=gas_str,
        factor_ref_code=factor_ref_code,
        emission_type=emission_type,
        category=device_category,
        unit=device_unit,
    )
    session.add(new_device)
    session.flush()

    add_change_log(
        session=session,
        module="devices",
        entity_name="Device",
        record_key=str(new_device.id),
        action_type="CREATE",
        changed_by=str(request.session.get("user", "system")),
        change_details=f"name={name}, location={location}, factor_ref_code={factor_ref_code}, gas_type={gas_str}",
    )
    session.commit()
    return RedirectResponse(url="/devices/", status_code=303)


@router.post("/delete/{device_id}")
async def delete_device(
    request: Request, device_id: int, session: Session = Depends(get_session)
):
    """刪除設備邏輯"""
    device = session.get(Device, device_id)
    if device:
        add_change_log(
            session=session,
            module="devices",
            entity_name="Device",
            record_key=str(device_id),
            action_type="DELETE",
            changed_by=str(request.session.get("user", "system")),
            change_details=f"name={device.name}, location={device.location}, category={device.category}",
        )
        session.delete(device)
        session.commit()
    return RedirectResponse(url="/devices/", status_code=303)
