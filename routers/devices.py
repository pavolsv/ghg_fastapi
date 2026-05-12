from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from audit_log import add_change_log
from database import engine
from model import AppendixReference, Device, EmissionFactor, GWPReference

router = APIRouter(prefix="/devices", tags=["devices"])
templates = Jinja2Templates(directory="templates")

EMISSION_TYPE_ORDER = {
    "固定燃燒": 0,
    "移動燃燒": 1,
    "逸散排放": 2,
    "能源間接排放": 3,
}


def _norm_text(value: object) -> str:
    return str(value or "").strip()


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
        )
    ).all()
    factor_map: dict[str, str] = {}
    factor_options_json: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for name, original_code, emission_type in all_factors:
        normalized_name = _norm_text(name)
        normalized_code = _norm_text(original_code)
        normalized_type = _norm_text(emission_type) or "未分類"
        if not normalized_name or not normalized_code:
            continue

        dedupe_key = (normalized_type, normalized_code)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        factor_options_json.append(
            {
                "name": normalized_name,
                "original_code": normalized_code,
                "emission_type": normalized_type,
            }
        )
        factor_map.setdefault(normalized_code, normalized_name)

    # 加入逸散排放（冷媒）選項，來源為 GWPReference
    gwp_refs = session.exec(
        select(GWPReference).order_by(GWPReference.gas_name_zh)
    ).all()
    for gwp in gwp_refs:
        formula = _norm_text(gwp.formula)
        if not formula:
            continue
        label = f"{gwp.gas_name_zh}（{formula}）"
        dedupe_key = ("逸散排放", formula)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        factor_options_json.append({
            "name": label,
            "original_code": formula,
            "emission_type": "逸散排放",
        })
        factor_map[formula] = label

    factor_options_json.sort(
        key=lambda item: (
            EMISSION_TYPE_ORDER.get(item["emission_type"], 99),
            item["name"],
        )
    )

    appendix_device_options = session.exec(
        select(AppendixReference)
        .where(AppendixReference.appendix_type == "device")
        .order_by(col(AppendixReference.seq), AppendixReference.code)
    ).all()

    return templates.TemplateResponse(
        "device_management.html",
        {
            "request": request,
            "devices": devices,
            "factor_map": factor_map,  # 傳送名稱對照表
            "factor_options_json": factor_options_json,
            "appendix_device_options": appendix_device_options,
        },
    )


# ... 您的現有 import ...


@router.post("/create")
async def create_device(
    request: Request,
    name: str = Form(...),
    location: str = Form(default=""),
    factor_ref_code: str = Form(...),
    emission_type: str = Form(default="固定燃燒"),
    device_number: str = Form(default=""),
    device_code: str = Form(default=""),
    session: Session = Depends(get_session),
):
    """處理設備新增：接收多選氣體並自動帶入類型/單位"""

    # 1. 獲取多選的氣體清單 (由 JS 動態產生的 gas_type 選項)
    form_data = await request.form()
    gas_types = [value for value in form_data.getlist("gas_type") if isinstance(value, str)]
    gas_str = ",".join(gas_types)  # 存成 "CO2,CH4"

    normalized_emission_type = _norm_text(emission_type)
    normalized_factor_ref = _norm_text(factor_ref_code)
    normalized_name = _norm_text(name)

    if not normalized_name or not normalized_emission_type or not normalized_factor_ref:
        return RedirectResponse(url="/devices/", status_code=303)

    # 2. 自動根據燃料代碼，找出該燃料的類型與單位
    if normalized_emission_type == "逸散排放":
        # 冷媒設備：從 GWPReference 查詢
        gwp_ref = session.exec(
            select(GWPReference).where(GWPReference.formula == normalized_factor_ref)
        ).first()
        if not gwp_ref:
            return RedirectResponse(url="/devices/", status_code=303)
        device_category = "逸散排放"
        device_unit = "公斤"
    else:
        base_factor = session.exec(
            select(EmissionFactor).where(
                EmissionFactor.original_code == normalized_factor_ref,
                EmissionFactor.emission_type == normalized_emission_type,
            )
        ).first()
        if not base_factor:
            return RedirectResponse(url="/devices/", status_code=303)
        device_category = normalized_emission_type
        device_unit = base_factor.unit or "單位"

    new_device = Device(
        name=name,
        location=location,
        gas_type=gas_str,
        factor_ref_code=normalized_factor_ref,
        emission_type=normalized_emission_type,
        category=device_category,
        unit=device_unit,
        device_number=device_number or None,
        device_code=device_code or None,
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
