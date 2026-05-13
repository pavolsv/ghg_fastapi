from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from audit_log import add_change_log
from database import engine
from model import AppendixReference, Device, EmissionFactor, EmissionRecord, GWPReference
from constants.lhv_defaults import get_lhv_by_name, get_lhv_unit_options
from constants.refrigerant_factors import (
    get_refrigerant_categories,
    get_name_by_code,
    get_rate_by_code,
    REFRIGERANT_EQUIPMENT,
)

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


import re

def _extract_refrigerant_aliases(gwp_ref) -> list[str]:
    aliases = []
    name_zh = (gwp_ref.gas_name_zh or "")
    name_en = (gwp_ref.gas_name_en or "")
    for name_str in [name_zh, name_en]:
        parts = re.split(r'[,，、/]', name_str)
        for part in parts:
            token = part.strip()
            if token and re.match(r'^[A-Z]', token) and token != gwp_ref.formula:
                aliases.append(token)
    return aliases


def _map_lhv_unit(unit: str) -> str:
    """將舊版 LHV 單位對應到新版下拉選項的格式"""
    if not unit:
        return ""
    mapping = {
        "Kcal/公升": "千卡/公升(Kcal/l)",
        "Kcal/公斤": "公斤/兆焦耳(kg/TJ)",
        "Kcal/立方公尺": "公斤/兆焦耳(kg/TJ)",
        "Kcal/公噸": "公斤/兆焦耳(kg/TJ)",
        "Kcal/公秉": "公斤/兆焦耳(kg/TJ)",
        "MJ/公升": "公斤/兆焦耳(kg/TJ)",
        "MJ/公斤": "公斤/兆焦耳(kg/TJ)",
        "MJ/立方公尺": "公斤/兆焦耳(kg/TJ)",
        "GJ/公升": "公斤/兆焦耳(kg/TJ)",
        "GJ/公斤": "公斤/兆焦耳(kg/TJ)",
        "GJ/立方公尺": "公斤/兆焦耳(kg/TJ)",
    }
    return mapping.get(unit, unit)


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
        for alias in _extract_refrigerant_aliases(gwp):
            factor_map.setdefault(alias, label)

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

    refrigerant_names = {code: info["name"] for code, info in REFRIGERANT_EQUIPMENT.items()}

    return templates.TemplateResponse(
        "device_management.html",
        {
            "request": request,
            "devices": devices,
            "factor_map": factor_map,
            "factor_options_json": factor_options_json,
            "appendix_device_options": appendix_device_options,
            "refrigerant_names": refrigerant_names,
        },
    )


@router.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    return templates.TemplateResponse(
        "activity.html",
        {"request": request}
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
    quantity: int = Form(default=1),
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
        quantity=quantity,
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


# ========== 活動數據 API ==========

class DeviceActivityData(BaseModel):
    device_id: int
    activity_data: float
    unit: str
    data_source: Optional[str] = "manual"
    heat_value: Optional[float] = None
    lhv_unit: Optional[str] = None
    record_date: Optional[str] = None


class RefrigerantDeviceData(BaseModel):
    name: str
    device_number: Optional[str] = None
    equipment_category: str
    refrigerant_code: str
    fill_amount: float
    fill_unit: str
    location: Optional[str] = None


# ========== 冷媒設備 API ==========

@router.get("/api/refrigerant_categories")
async def list_refrigerant_categories():
    return JSONResponse(content={"success": True, "data": get_refrigerant_categories()})


@router.get("/api/refrigerant_gases")
async def list_refrigerant_gases(session: Session = Depends(get_session)):
    gases = session.exec(
        select(GWPReference).order_by(GWPReference.gas_name_zh)
    ).all()
    return JSONResponse(content={
        "success": True,
        "data": [
            {"code": g.formula, "name": g.gas_name_zh, "gwp": g.gwp_value}
            for g in gases
        ]
    })


@router.post("/refrigerant")
async def create_refrigerant_device(
    request: Request,
    data: RefrigerantDeviceData,
    session: Session = Depends(get_session),
):
    try:
        # 統一換算成公噸
        amount_ton = data.fill_amount
        if data.fill_unit == "公克":
            amount_ton = data.fill_amount / 1_000_000
        elif data.fill_unit == "公斤":
            amount_ton = data.fill_amount / 1_000

        new_device = Device(
            name=get_name_by_code(data.equipment_category) or data.name,
            device_number=data.device_number or None,
            emission_type="逸散排放",
            category="逸散排放",
            location=data.location or "",
            factor_ref_code=data.refrigerant_code,
            gas_type="HFCs",
            unit="公噸",
            fill_amount=amount_ton,
            fill_unit=data.fill_unit,
            equipment_category=data.equipment_category,
            refrigerant_code=data.refrigerant_code,
        )
        session.add(new_device)
        session.commit()
        session.refresh(new_device)

        add_change_log(
            session=session,
            module="refrigerant_device",
            entity_name="Device",
            record_key=str(new_device.id),
            action_type="CREATE",
            changed_by=str(request.session.get("user", "system")),
            change_details=f"name={new_device.name}, category={new_device.equipment_category}, refrigerant={new_device.refrigerant_code}, fill={new_device.fill_amount}公噸",
        )
        return JSONResponse(content={"success": True, "message": "冷媒設備新增成功", "device_id": new_device.id})
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


# ========== 活動數據 API ==========

@router.get("/api/activities")
async def list_device_activities(
    session: Session = Depends(get_session),
):
    try:
        devices = session.exec(select(Device).order_by(col(Device.id))).all()
        device_ids = [d.id for d in devices]

        records = {}
        if device_ids:
            recs = session.exec(
                select(EmissionRecord).where(EmissionRecord.device_id.in_(device_ids))
            ).all()
            records = {r.device_id: r for r in recs}

        factor_map = {}
        all_factors = session.exec(
            select(EmissionFactor.name, EmissionFactor.original_code)
        ).all()
        for name, code in all_factors:
            factor_map[code] = name

        # 加入 GWP 冷媒全名
        gwp_refs = session.exec(
            select(GWPReference).order_by(GWPReference.gas_name_zh)
        ).all()
        for gwp in gwp_refs:
            formula = _norm_text(gwp.formula)
            if formula:
                factor_map[formula] = gwp.gas_name_zh
                for alias in _extract_refrigerant_aliases(gwp):
                    factor_map.setdefault(alias, gwp.gas_name_zh)

        result = []
        for d in devices:
            rec = records.get(d.id)
            lhv_value = None
            lhv_unit_val = None
            if d.factor_ref_code:
                default_lhv, default_unit = get_lhv_by_name(
                    factor_map.get(d.factor_ref_code, d.factor_ref_code)
                )
                lhv_value = default_lhv if default_lhv else None
                lhv_unit_val = _map_lhv_unit(default_unit) if default_unit else None

            # 冷媒設備：factor_ref_name 從 GWP 或 factor_map 查詢
            if d.emission_type == "逸散排放" and d.refrigerant_code:
                factor_ref_name = factor_map.get(d.refrigerant_code, d.refrigerant_code)
            else:
                factor_ref_name = factor_map.get(d.factor_ref_code, "未知")

            result.append({
                "device_id": d.id,
                "name": d.name,
                "device_number": d.device_number,
                "device_code": d.device_code,
                "category": d.category,
                "emission_type": d.emission_type,
                "location": d.location,
                "factor_ref_code": d.factor_ref_code,
                "factor_ref_name": factor_ref_name,
                "gas_type": d.gas_type,
                "unit": d.unit,
                "quantity": d.quantity,
                "has_data": rec is not None,
                "activity_data": rec.activity_data if rec else None,
                "activity_unit": rec.unit if rec else (d.unit or ""),
                "data_source": rec.data_source if rec else "manual",
                "heat_value": rec.heat_value if rec else lhv_value,
                "lhv_unit": _map_lhv_unit(rec.lhv_unit if rec else (lhv_unit_val or "")),
                "record_date": rec.record_date if rec else None,
                "fill_amount": d.fill_amount,
                "fill_unit": d.fill_unit,
                "equipment_category": d.equipment_category,
                "equipment_name": get_name_by_code(d.equipment_category or ""),
                "refrigerant_code": d.refrigerant_code,
            })

        return JSONResponse(content={"success": True, "data": result})
    except Exception as e:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e), "traceback": traceback.format_exc()}
        )


@router.post("/api/activities/save")
async def save_device_activity(
    data: DeviceActivityData,
    session: Session = Depends(get_session),
):
    try:
        device = session.get(Device, data.device_id)
        if not device:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "設備不存在"}
            )

        existing = session.exec(
            select(EmissionRecord).where(EmissionRecord.device_id == data.device_id)
        ).first()

        if existing:
            existing.activity_data = data.activity_data
            existing.unit = data.unit
            existing.data_source = data.data_source or "manual"
            existing.heat_value = data.heat_value
            existing.lhv_unit = data.lhv_unit
            existing.record_date = data.record_date or existing.record_date
            session.add(existing)
            message = "活動數據更新成功"
        else:
            new_record = EmissionRecord(
                device_id=data.device_id,
                activity_data=data.activity_data,
                total_co2e=0.0,
                unit=data.unit,
                data_source=data.data_source or "manual",
                heat_value=data.heat_value,
                lhv_unit=data.lhv_unit,
                record_date=data.record_date or datetime.utcnow().strftime("%Y-%m-%d"),
            )
            session.add(new_record)
            message = "活動數據新增成功"

        session.commit()
        return JSONResponse(content={"success": True, "message": message})
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@router.get("/api/lhv_units")
async def get_lhv_units():
    return JSONResponse(content={
        "success": True,
        "data": get_lhv_unit_options()
    })
