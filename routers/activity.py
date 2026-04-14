from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlmodel import select, Session
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from model import ActivityData, EmissionSource, Boundary, Year
from dependencies import get_session, get_current_user

router = APIRouter(prefix="/inventory_list", tags=["activity"])

# ========== Pydantic 模型 ==========
class ActivityDataCreate(BaseModel):
    source_id: int
    year_value: float
    unit: str
    remark: Optional[str] = None

class ActivityDataUpdate(BaseModel):
    year_value: float
    unit: str
    remark: Optional[str] = None

class BatchActivityData(BaseModel):
    data: List[ActivityDataCreate]

# 排放係數對照表
EMISSION_FACTORS = {
    ('柴油', '公升'): 2.64,
    ('車用汽油', '公升'): 2.26,
    ('天然氣', '立方公尺'): 2.02,
    ('冷媒', '公斤'): 1810,
    ('電力', '千度'): 500,
    ('蒸氣', '公噸'): 300,
}

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
                remark=data.remark,
                account_id=account_id,
                year_id=source.year_id,
                boundary_id=source.boundary_id,
                data_source="manual"
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
                existing.remark = item.remark
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                new_data = ActivityData(
                    source_id=item.source_id,
                    year_value=item.year_value,
                    unit=item.unit,
                    remark=item.remark,
                    account_id=account_id,
                    year_id=source.year_id,
                    boundary_id=source.boundary_id,
                    data_source="batch"
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
        
        # 計算排放量
        total_emission = 0
        scope1_emission = 0
        scope2_emission = 0
        
        for source in sources:
            activity = activities.get(source.source_id)
            if not activity:
                continue
            
            factor = EMISSION_FACTORS.get((source.material, activity.unit), 1.0)
            emission = activity.year_value * factor
            
            if source.scope == 'scope1':
                scope1_emission += emission
            else:
                scope2_emission += emission
            
            total_emission += emission
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "total_emission": round(total_emission, 2),
                "scope1_emission": round(scope1_emission, 2),
                "scope2_emission": round(scope2_emission, 2),
                "total_sources": len(sources),
                "completed_sources": len(activities)
            }
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )