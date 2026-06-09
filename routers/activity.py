from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlmodel import select, Session
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from model import ActivityData, EmissionSource, Boundary, Year, EmissionFactor
from dependencies import get_session, get_current_user
from services.emission_calculator import calculate_emission_by_source
from constants.lhv_defaults import get_lhv_by_name, get_lhv_unit_options

router = APIRouter(prefix="/inventory_list", tags=["activity"])

# ========== Pydantic 模型 ==========
class ActivityDataCreate(BaseModel):
    source_id: int
    year_value: float
    unit: str
    data_source: Optional[str] = "manual"
    lower_heating_value: Optional[float] = None
    lhv_unit: Optional[str] = None
    remark: Optional[str] = None

class ActivityDataUpdate(BaseModel):
    year_value: float
    unit: str
    data_source: Optional[str] = "manual"
    lower_heating_value: Optional[float] = None
    lhv_unit: Optional[str] = None
    remark: Optional[str] = None

class BatchActivityData(BaseModel):
    data: List[ActivityDataCreate]

# ========== 取得該年度所有邊界 (供下拉選單使用) ==========
@router.get("/activity/{year}/boundaries")
async def get_year_boundaries(
    year: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        year_record = session.exec(
            select(Year).where(
                Year.account_id == account_id,
                Year.year == year
            )
        ).first()
        
        if not year_record:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "年度不存在"}
            )
        
        boundaries = session.exec(
            select(Boundary).where(
                Boundary.account_id == account_id,
                Boundary.year_id == year_record.year_id
            ).order_by(Boundary.sort_order)
        ).all()
        
        return JSONResponse(content={
            "success": True,
            "data": [
                {
                    "boundary_id": b.boundary_id,
                    "boundary_name": b.boundary_name
                }
                for b in boundaries
            ]
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 取得活動數據列表 ==========
@router.get("/activity/{year}/list")
async def get_activity_data(
    year: int,
    boundary_id: Optional[int] = None,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        year_record = session.exec(
            select(Year).where(
                Year.account_id == account_id,
                Year.year == year
            )
        ).first()
        
        if not year_record:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "年度不存在"}
            )
        
        # 先取得該年度所有排放源
        query = select(EmissionSource).where(
            EmissionSource.account_id == account_id,
            EmissionSource.year_id == year_record.year_id
        )
        
        if boundary_id:
            query = query.where(EmissionSource.boundary_id == boundary_id)
        
        sources = session.exec(query).all()
        source_ids = [s.source_id for s in sources]
        
        # 取得活動數據
        activity_data = {}
        if source_ids:
            activities = session.exec(
                select(ActivityData).where(ActivityData.source_id.in_(source_ids))
            ).all()
            activity_data = {a.source_id: a for a in activities}
        
        # 取得邊界名稱對照
        boundaries = session.exec(
            select(Boundary).where(
                Boundary.account_id == account_id,
                Boundary.year_id == year_record.year_id
            )
        ).all()
        boundary_map = {b.boundary_id: b.boundary_name for b in boundaries}
        
        result = []
        for source in sources:
            activity = activity_data.get(source.source_id)
            result.append({
                "source_id": source.source_id,
                "source_number": source.source_number,
                "source_name": source.source_name,
                "scope": source.scope,
                "scope_display": "範疇一" if source.scope == "scope1" else "範疇二",
                "emission_type": source.emission_type,
                "material": source.material,
                "quantity": source.quantity,
                "boundary_id": source.boundary_id,
                "boundary_name": boundary_map.get(source.boundary_id, ""),
                "has_data": activity is not None,
                "year_value": activity.year_value if activity else None,
                "unit": activity.unit if activity else "",
                "data_source": activity.data_source if activity else "manual",
                "lower_heating_value": activity.lower_heating_value if activity else None,
                "lhv_unit": activity.lhv_unit if activity else None,
                "remark": activity.remark if activity else None,
                "data_id": activity.data_id if activity else None
            })
        
        return JSONResponse(content={
            "success": True,
            "data": result
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 新增或更新活動數據 ==========
@router.post("/activity/{year}/save")
async def save_activity_data(
    year: int,
    data: ActivityDataCreate,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        # 檢查排放源是否存在
        source = session.get(EmissionSource, data.source_id)
        if not source or source.account_id != account_id:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "排放源不存在"}
            )
        
        # 檢查是否已有活動數據
        existing = session.exec(
            select(ActivityData).where(ActivityData.source_id == data.source_id)
        ).first()
        
        if existing:
            # 更新
            existing.year_value = data.year_value
            existing.unit = data.unit
            existing.data_source = data.data_source or "manual"
            existing.lower_heating_value = data.lower_heating_value
            existing.lhv_unit = data.lhv_unit
            existing.remark = data.remark
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            message = "活動數據更新成功"
        else:
            # 新增
            new_data = ActivityData(
                source_id=data.source_id,
                year_value=data.year_value,
                unit=data.unit,
                data_source=data.data_source or "manual",
                lower_heating_value=data.lower_heating_value,
                lhv_unit=data.lhv_unit,
                remark=data.remark,
                account_id=account_id,
                year_id=source.year_id,
                boundary_id=source.boundary_id,
            )
            session.add(new_data)
            message = "活動數據新增成功"
        
        session.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": message
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 批次儲存活動數據 ==========
@router.post("/activity/{year}/batch_save")
async def batch_save_activity_data(
    year: int,
    data: BatchActivityData,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        success_count = 0
        for item in data.data:
            source = session.get(EmissionSource, item.source_id)
            if not source or source.account_id != account_id:
                continue
            
            existing = session.exec(
                select(ActivityData).where(ActivityData.source_id == item.source_id)
            ).first()
            
            if existing:
                existing.year_value = item.year_value
                existing.unit = item.unit
                existing.data_source = item.data_source or "manual"
                existing.lower_heating_value = item.lower_heating_value
                existing.lhv_unit = item.lhv_unit
                existing.remark = item.remark
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                new_data = ActivityData(
                    source_id=item.source_id,
                    year_value=item.year_value,
                    unit=item.unit,
                    data_source=item.data_source or "manual",
                    lower_heating_value=item.lower_heating_value,
                    lhv_unit=item.lhv_unit,
                    remark=item.remark,
                    account_id=account_id,
                    year_id=source.year_id,
                    boundary_id=source.boundary_id,
                )
                session.add(new_data)
            
            success_count += 1
        
        session.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": f"成功儲存 {success_count} 筆活動數據"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 刪除活動數據 ==========
@router.delete("/activity/{year}/delete/{source_id}")
async def delete_activity_data(
    year: int,
    source_id: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        activity = session.exec(
            select(ActivityData).where(ActivityData.source_id == source_id)
        ).first()
        
        if not activity:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "活動數據不存在"}
            )
        
        session.delete(activity)
        session.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": "活動數據刪除成功"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 依物料名稱查詢低位熱值預設值 ==========
@router.get("/activity/{year}/lhv_lookup")
async def lhv_lookup(
    year: int,
    material: str,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        lhv_value, lhv_unit = get_lhv_by_name(material)

        if lhv_value is None and lhv_unit is None:
            year_record = session.exec(
                select(Year).where(
                    Year.account_id == account_id,
                    Year.year == year
                )
            ).first()
            if year_record:
                original_code = _resolve_original_code(session, material, "", year)
                if original_code:
                    factor = session.exec(
                        select(EmissionFactor).where(
                            EmissionFactor.original_code == original_code
                        )
                    ).first()
                    if factor and factor.lower_heating_value is not None:
                        lhv_value = factor.lower_heating_value
                        lhv_unit = factor.lhv_unit

        return JSONResponse(content={
            "success": True,
            "data": {
                "material": material,
                "lower_heating_value": lhv_value,
                "lhv_unit": lhv_unit,
            }
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 取得 LHV 單位選項 ==========
@router.get("/activity/{year}/lhv_units")
async def get_lhv_units():
    return JSONResponse(content={
        "success": True,
        "data": get_lhv_unit_options()
    })

# ========== 輔助：依 material 名稱解析 original_code ==========
def _resolve_original_code(session: Session, material: str, emission_type: str, year: int) -> str | None:
    """
    依 material 中文名稱 + emission_type 查找對應的 original_code。
    先嘗試精確匹配，再嘗試模糊匹配（LIKE）。
    """
    # 1. 精確匹配
    factor = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.name == material,
            EmissionFactor.emission_type == emission_type,
            EmissionFactor.year == year,
        )
    ).first()
    if factor:
        return factor.original_code

    # 2. 模糊匹配：material 包含於 factor.name
    factor = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.name.contains(material),
            EmissionFactor.emission_type == emission_type,
            EmissionFactor.year == year,
        )
    ).first()
    if factor:
        return factor.original_code

    # 3. 模糊匹配：factor.name 包含於 material
    factor = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.name.in_([material]),
            EmissionFactor.emission_type == emission_type,
            EmissionFactor.year == year,
        )
    ).first()
    if factor:
        return factor.original_code

    # 4. fallback：取該 emission_type 下最接近的（名稱最長匹配）
    all_factors = session.exec(
        select(EmissionFactor).where(
            EmissionFactor.emission_type == emission_type,
            EmissionFactor.year == year,
        )
    ).all()

    best_match = None
    best_len = 0
    for f in all_factors:
        if f.name in material or material in f.name:
            match_len = len(f.name)
            if match_len > best_len:
                best_len = match_len
                best_match = f

    if best_match:
        return best_match.original_code

    return None


# ========== 計算排放量 ==========
@router.get("/activity/{year}/calculate")
async def calculate_emissions(
    year: int,
    boundary_id: Optional[int] = None,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        year_record = session.exec(
            select(Year).where(
                Year.account_id == account_id,
                Year.year == year
            )
        ).first()

        if not year_record:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "年度不存在"}
            )

        # 取得排放源
        query = select(EmissionSource).where(
            EmissionSource.account_id == account_id,
            EmissionSource.year_id == year_record.year_id
        )

        if boundary_id:
            query = query.where(EmissionSource.boundary_id == boundary_id)

        sources = session.exec(query).all()
        source_ids = [s.source_id for s in sources]

        # 取得活動數據
        activities = {}
        if source_ids:
            acts = session.exec(
                select(ActivityData).where(ActivityData.source_id.in_(source_ids))
            ).all()
            activities = {a.source_id: a for a in acts}

        # 計算排放量（分項）
        total_co2 = 0.0
        total_ch4 = 0.0
        total_n2o = 0.0
        total_co2e = 0.0
        scope1_co2e = 0.0
        scope2_co2e = 0.0

        source_details = []

        for source in sources:
            activity = activities.get(source.source_id)
            if not activity:
                continue

            # 解析燃料代碼
            original_code = _resolve_original_code(
                session, source.material, source.emission_type, year
            )

            if not original_code:
                # fallback：嘗試用 material 直接查（可能是舊資料無法匹配）
                source_details.append({
                    "source_id": source.source_id,
                    "source_name": source.source_name,
                    "material": source.material,
                    "activity_value": activity.year_value,
                    "unit": activity.unit,
                    "co2": None,
                    "ch4": None,
                    "n2o": None,
                    "co2e": None,
                    "error": f"無法找到 '{source.material}' 的係數資料",
                })
                continue

            # 計算各氣體排放
            emission_result = calculate_emission_by_source(
                session=session,
                original_code=original_code,
                activity_value=activity.year_value,
                activity_unit=activity.unit,
                year=year,
                emission_type=source.emission_type,
            )

            co2 = emission_result["CO2"]
            ch4 = emission_result["CH4"]
            n2o = emission_result["N2O"]
            co2e = emission_result["CO2e"]

            total_co2 += co2
            total_ch4 += ch4
            total_n2o += n2o
            total_co2e += co2e

            if source.scope == 'scope1':
                scope1_co2e += co2e
            else:
                scope2_co2e += co2e

            source_details.append({
                "source_id": source.source_id,
                "source_name": source.source_name,
                "material": source.material,
                "original_code": original_code,
                "activity_value": activity.year_value,
                "unit": activity.unit,
                "co2": co2,
                "ch4": ch4,
                "n2o": n2o,
                "co2e": co2e,
            })

        return JSONResponse(content={
            "success": True,
            "data": {
                "total_co2": round(total_co2, 4),
                "total_ch4": round(total_ch4, 4),
                "total_n2o": round(total_n2o, 4),
                "total_co2e": round(total_co2e, 4),
                "scope1_co2e": round(scope1_co2e, 4),
                "scope2_co2e": round(scope2_co2e, 4),
                "total_sources": len(sources),
                "completed_sources": len(activities),
                "sources": source_details,
            }
        })
    except Exception as e:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e), "traceback": traceback.format_exc()}
        )