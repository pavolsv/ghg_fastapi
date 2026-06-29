"""
排放源管理 — 展開式列表
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, col

from database import engine
from model import Device, EmissionFactor604, EmissionRecord
from services.emission_calculator import parse_activity_unit

router = APIRouter(prefix="/emission-source", tags=["emission-source"])
templates = Jinja2Templates(directory="templates")

CATEGORIES = {
    "固定燃燒": {"icon": "flame", "label": "固定燃燒"},
    "移動燃燒": {"icon": "car", "label": "交通運輸"},
    "逸散排放": {"icon": "snowflake", "label": "設備冷媒"},
    "能源間接排放": {"icon": "zap", "label": "外購電力"},
}


def get_fuels_for_category(category: str):
    fuels = []
    if category == "逸散排放":
        with Session(engine) as session:
            from model import GWPReference
            gases = session.exec(
                select(GWPReference).where(
                    GWPReference.gwp_value > 0
                ).order_by(col(GWPReference.gas_name_zh))
            ).all()
            for g in gases:
                fuels.append({
                    "code": g.formula,
                    "name": f"{g.gas_name_zh} ({g.formula}, GWP={g.gwp_value})",
                })
    elif category == "能源間接排放":
        with Session(engine) as session:
            factors = session.exec(
                select(EmissionFactor604).where(
                    EmissionFactor604.original_code == "ELECTRICITY"
                ).order_by(col(EmissionFactor604.code).desc())
            ).all()
            for f in factors:
                fuels.append({
                    "code": f.code,
                    "name": f"{f.code}年 ({f.factor_value} kg CO₂e/kWh)",
                })
    else:
        with Session(engine) as session:
            factors = session.exec(
                select(EmissionFactor604).where(
                    EmissionFactor604.emission_type == category
                ).order_by(col(EmissionFactor604.name).asc())
            ).all()
            seen = set()
            for f in factors:
                if f.original_code not in seen:
                    seen.add(f.original_code)
                    fuels.append({"code": f.original_code, "name": f.name})
    return fuels


def get_equipment_types():
    """回傳冷媒設備類型清單"""
    from constants.refrigerant_factors import REFRIGERANT_EQUIPMENT
    result = []
    for code, info in REFRIGERANT_EQUIPMENT.items():
        result.append({"code": code, "name": info["name"]})
    return result


PREFIX_MAP = {
    "固定燃燒": ("GS", 2),
    "移動燃燒": ("GV", 2),
    "能源間接排放": ("GP", 2),
    "逸散排放": ("GF", 4),
}


def _generate_device_code(session, emission_type: str) -> str:
    """自動產生裝置編碼，補最小可用號碼"""
    prefix, digits = PREFIX_MAP.get(emission_type, ("XX", 2))
    existing = session.exec(
        select(Device.device_code).where(
            Device.device_code.like(f"{prefix}%")
        )
    ).all()
    used = set()
    for code in existing:
        if code:
            try:
                used.add(int(code[len(prefix):]))
            except ValueError:
                pass
    n = 1
    while n in used:
        n += 1
    return f"{prefix}{n:0{digits}d}"


def _renumber_device_codes(session, emission_type: str):
    """刪除設備後，將同類別所有裝置編碼遞補成連續號碼"""
    prefix, digits = PREFIX_MAP.get(emission_type, ("XX", 2))
    devices = session.exec(
        select(Device).where(
            Device.emission_type == emission_type,
            Device.device_code.isnot(None),
            Device.device_code.like(f"{prefix}%")
        ).order_by(Device.device_code)
    ).all()
    for i, device in enumerate(devices, start=1):
        device.device_code = f"{prefix}{i:0{digits}d}"
        session.add(device)


def _derive_device_code_display(device: Device) -> str:
    """顯示用：優先用 device.device_code，否則以 PREFIX_MAP + id 推導。"""
    if device.device_code:
        return device.device_code
    prefix, digits = PREFIX_MAP.get(device.emission_type, ("XX", 2))
    return f"{prefix}{device.id:0{digits}d}"


@router.get("/", response_class=HTMLResponse)
async def emission_source_home(request: Request):
    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        category_fuels = {}
        for cat_key in CATEGORIES:
            category_fuels[cat_key] = get_fuels_for_category(cat_key)

        all_devices = session.exec(
            select(Device).where(Device.account_id == user_id).order_by(col(Device.id).desc())
        ).all()
        device_groups: dict[str, list] = {}
        device_code_map: dict[int, str] = {}
        for d in all_devices:
            device_groups.setdefault(d.emission_type, []).append(d)
            device_code_map[d.id] = _derive_device_code_display(d)

        # 各設備活動數據查詢
        records = session.exec(select(EmissionRecord)).all()
        device_activity: dict[int, tuple[float, str]] = {}
        for r in records:
            if r.activity_data:
                device_activity[r.device_id] = (float(r.activity_data), r.unit or "")

    equipment_types = get_equipment_types()

    return templates.TemplateResponse(
        "emission_source_home.html",
        {
            "request": request,
            "categories": CATEGORIES,
            "category_fuels": category_fuels,
            "device_groups": device_groups,
            "equipment_types": equipment_types,
            "device_activity": device_activity,
            "device_code_map": device_code_map,
        },
    )


@router.post("/create")
async def create_emission_source(request: Request):
    from audit_log import add_change_log

    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    form = await request.form()
    name = str(form.get("name", "")).strip()
    emission_type = str(form.get("emission_type", "")).strip()
    factor_ref_code = str(form.get("factor_ref_code", "")).strip()
    quantity = int(form.get("quantity", 1))
    equipment_category = str(form.get("equipment_category", "")).strip()

    if not name or not emission_type or not factor_ref_code:
        return RedirectResponse(url=f"/emission-source/", status_code=303)

    if emission_type == "逸散排放" and not equipment_category:
        return RedirectResponse(url=f"/emission-source/?cat={emission_type}", status_code=303)

    with Session(engine) as session:
        if emission_type == "逸散排放":
            device_unit = "公斤"
        elif emission_type == "能源間接排放":
            device_unit = "度"
        else:
            factor = session.exec(
                select(EmissionFactor604).where(
                    EmissionFactor604.original_code == factor_ref_code,
                    EmissionFactor604.emission_type == emission_type,
                )
            ).first()
            device_unit = parse_activity_unit(factor.unit) if factor else "單位"

        scope = "scope2" if emission_type == "能源間接排放" else "scope1"

        device = Device(
            account_id=user_id,
            name=name,
            location="",
            gas_type="",
            factor_ref_code=factor_ref_code,
            emission_type=emission_type,
            category=emission_type,
            unit=device_unit,
            quantity=quantity,
            scope=scope,
            refrigerant_code=factor_ref_code if emission_type == "逸散排放" else None,
            equipment_category=equipment_category if emission_type == "逸散排放" and equipment_category else None,
        )
        device.device_code = _generate_device_code(session, emission_type)
        session.add(device)
        session.flush()

        add_change_log(
            session=session,
            module="devices",
            entity_name="Device",
            record_key=str(device.id),
            action_type="CREATE",
            changed_by=str(user_id),
            change_details=f"name={name}, category={emission_type}, fuel={factor_ref_code}",
        )
        session.commit()

    return RedirectResponse(url=f"/emission-source/?cat={emission_type}", status_code=303)


@router.post("/delete/{device_id}")
async def delete_emission_source(request: Request, device_id: int):
    from audit_log import add_change_log

    user_id = request.session.get("user")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        device = session.get(Device, device_id)
        if device and device.account_id == user_id:
            emission_type = device.emission_type
            add_change_log(
                session=session,
                module="devices",
                entity_name="Device",
                record_key=str(device.id),
                action_type="DELETE",
                changed_by=str(user_id),
                change_details=f"name={device.name}, type={device.emission_type}",
            )
            session.delete(device)
            _renumber_device_codes(session, emission_type)
            session.commit()
    return RedirectResponse(url="/emission-source/", status_code=303)