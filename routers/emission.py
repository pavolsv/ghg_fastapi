from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlmodel import select, Session
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from model import EmissionSource, Boundary, Year, ActivityData
from dependencies import get_session, get_current_user

router = APIRouter(prefix="/inventory_list", tags=["emission"])

# ========== Pydantic 模型 ==========
class EmissionSourceCreate(BaseModel):
    source_number: str
    source_name: str
    scope: str
    emission_type: str
    material: str
    quantity: int
    boundary_id: int

class EmissionSourceUpdate(BaseModel):
    source_number: str
    source_name: str
    emission_type: str
    material: str
    quantity: int
    boundary_id: int

# 物料清單 (與前端保持一致)
COMBUSTION_MATERIALS = [
    '木炭', '煤球', '焦炭', '泥煤', '褐煤', '亞煙煤', '其他煙煤',
    '煉焦煤', '無煙煤', '煤焦油', '原油', '頁岩油', '奧里油', '石油腦',
    '車用汽油', '車用汽油-氧化觸媒', '航空汽油/航空燃油-汽油型',
    '航空燃油-煤油型', '煤油', '其他煤油', '柴油', '生質柴油/生質汽油',
    '燃料油', '潤滑油', '石蠟', '瀝青', '石油焦', '其他石油產品',
    '天然氣', '液化天然氣', '乙烷', '液化石油氣', '焦爐氣', '煉油氣',
    '高爐氣', '掩埋沼氣/污泥沼氣', '其他氣體生質燃料', '其他液體生質燃料',
    '木材/廢材', '其他初級固體生質', '廢油', '事業廢棄物',
    '都市廢棄物-非生質部分', '油頁岩/焦油砂'
]

# ========== 取得該年度所有邊界 (供下拉選單使用) ==========
@router.get("/emission/{year}/boundaries")
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

# ========== 取得某個邊界下的排放源列表 ==========
@router.get("/emission/{year}/list")
async def get_emission_sources(
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
        
        query = select(EmissionSource).where(
            EmissionSource.account_id == account_id,
            EmissionSource.year_id == year_record.year_id
        )
        
        if boundary_id:
            query = query.where(EmissionSource.boundary_id == boundary_id)
        
        sources = session.exec(query.order_by(EmissionSource.sort_order)).all()
        
        # 取得邊界名稱對照
        boundaries = session.exec(
            select(Boundary).where(
                Boundary.account_id == account_id,
                Boundary.year_id == year_record.year_id
            )
        ).all()
        boundary_map = {b.boundary_id: b.boundary_name for b in boundaries}
        
        return JSONResponse(content={
            "success": True,
            "data": [
                {
                    "source_id": s.source_id,
                    "source_number": s.source_number,
                    "source_name": s.source_name,
                    "scope": s.scope,
                    "scope_display": "範疇一" if s.scope == "scope1" else "範疇二",
                    "emission_type": s.emission_type,
                    "emission_type_display": {
                        "fixed": "固定燃燒",
                        "mobile": "移動燃燒",
                        "fugitive": "逸散排放",
                        "process": "製程排放",
                        "electricity": "外購電力",
                        "steam": "外購蒸氣"
                    }.get(s.emission_type, s.emission_type),
                    "material": s.material,
                    "quantity": s.quantity,
                    "boundary_id": s.boundary_id,
                    "boundary_name": boundary_map.get(s.boundary_id, "")
                }
                for s in sources
            ]
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 新增排放源 ==========
@router.post("/emission/{year}/add")
async def add_emission_source(
    year: int,
    source_data: EmissionSourceCreate,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        # 取得 year_id
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
        
        # 檢查邊界是否存在且屬於該年度
        boundary = session.get(Boundary, source_data.boundary_id)
        if not boundary or boundary.account_id != account_id or boundary.year_id != year_record.year_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "無效的組織邊界"}
            )
        
        # 檢查同一個邊界下編號是否重複
        existing = session.exec(
            select(EmissionSource).where(
                EmissionSource.boundary_id == source_data.boundary_id,
                EmissionSource.source_number == source_data.source_number
            )
        ).first()
        
        if existing:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "此編號已存在"}
            )
        
        # 取得目前最大的 sort_order
        max_sort = session.exec(
            select(EmissionSource).where(
                EmissionSource.boundary_id == source_data.boundary_id
            ).order_by(EmissionSource.sort_order.desc())
        ).first()
        
        new_sort_order = (max_sort.sort_order + 1) if max_sort else 1
        
        # 新增排放源
        new_source = EmissionSource(
            source_number=source_data.source_number,
            source_name=source_data.source_name,
            scope=source_data.scope,
            emission_type=source_data.emission_type,
            material=source_data.material,
            quantity=source_data.quantity,
            sort_order=new_sort_order,
            account_id=account_id,
            year_id=year_record.year_id,
            boundary_id=source_data.boundary_id
        )
        
        session.add(new_source)
        session.commit()
        session.refresh(new_source)
        
        return JSONResponse(content={
            "success": True,
            "source_id": new_source.source_id,
            "message": "排放源新增成功"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 更新排放源 ==========
@router.put("/emission/{year}/edit/{source_id}")
async def edit_emission_source(
    year: int,
    source_id: int,
    source_data: EmissionSourceUpdate,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        # 檢查排放源是否存在
        source = session.get(EmissionSource, source_id)
        
        if not source or source.account_id != account_id:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "排放源不存在"}
            )
        
        # 檢查同一個邊界下編號是否重複 (排除自己)
        existing = session.exec(
            select(EmissionSource).where(
                EmissionSource.boundary_id == source_data.boundary_id,
                EmissionSource.source_number == source_data.source_number,
                EmissionSource.source_id != source_id
            )
        ).first()
        
        if existing:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "此編號已存在"}
            )
        
        # 更新排放源
        source.source_number = source_data.source_number
        source.source_name = source_data.source_name
        source.emission_type = source_data.emission_type
        source.material = source_data.material
        source.quantity = source_data.quantity
        source.boundary_id = source_data.boundary_id
        source.updated_at = datetime.utcnow()
        
        session.add(source)
        session.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": "排放源更新成功"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 刪除排放源 ==========
@router.delete("/emission/{year}/delete/{source_id}")
async def delete_emission_source(
    year: int,
    source_id: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        print(f"🔍 嘗試刪除排放源 {source_id}，年度 {year}，使用者 {account_id}")
        
        source = session.get(EmissionSource, source_id)
        
        if not source or source.account_id != account_id:
            print(f"❌ 排放源不存在")
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "排放源不存在"}
            )
        
        # 檢查是否有活動數據
        activity_data = session.exec(
            select(ActivityData).where(ActivityData.source_id == source_id)
        ).first()
        
        if activity_data:
            print(f"❌ 此排放源已有活動數據，無法刪除")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "此排放源已有活動數據，無法刪除"}
            )
        
        session.delete(source)
        session.commit()
        
        print(f"✅ 排放源刪除成功")
        return JSONResponse(content={
            "success": True,
            "message": "排放源刪除成功"
        })
    except Exception as e:
        session.rollback()
        print(f"❌ 刪除失敗：{str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )