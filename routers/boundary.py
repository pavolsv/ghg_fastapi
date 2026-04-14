from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlmodel import select, Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from model import Boundary, Year
from dependencies import get_session, get_current_user

router = APIRouter(prefix="/inventory_list", tags=["boundary"])

# ========== Pydantic 模型 ==========
class BoundaryCreate(BaseModel):
    boundary_name: str
    address: str

class BoundaryUpdate(BaseModel):
    boundary_name: str
    address: str

class BoundaryReorder(BaseModel):
    boundary_ids: List[int]

# ========== 取得邊界列表 ==========
@router.get("/boundary/{year}/list")
async def get_boundary_list(
    year: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        # 先取得 year_id
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
        
        # 取得該年度的所有邊界
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
                    "boundary_name": b.boundary_name,
                    "address": b.address,
                    "sort_order": b.sort_order
                }
                for b in boundaries
            ]
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 新增邊界 ==========
@router.post("/boundary/{year}/add")
async def add_boundary(
    year: int,
    boundary_data: BoundaryCreate,
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
        
        # 檢查邊界名稱是否重複
        existing = session.exec(
            select(Boundary).where(
                Boundary.account_id == account_id,
                Boundary.year_id == year_record.year_id,
                Boundary.boundary_name == boundary_data.boundary_name
            )
        ).first()
        
        if existing:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "邊界名稱已存在"}
            )
        
        # 取得目前最大的 sort_order
        max_sort = session.exec(
            select(Boundary).where(
                Boundary.account_id == account_id,
                Boundary.year_id == year_record.year_id
            ).order_by(Boundary.sort_order.desc())
        ).first()
        
        new_sort_order = (max_sort.sort_order + 1) if max_sort else 1
        
        # 新增邊界
        new_boundary = Boundary(
            boundary_name=boundary_data.boundary_name,
            address=boundary_data.address,
            sort_order=new_sort_order,
            account_id=account_id,
            year_id=year_record.year_id
        )
        
        session.add(new_boundary)
        session.commit()
        session.refresh(new_boundary)
        
        return JSONResponse(content={
            "success": True,
            "boundary_id": new_boundary.boundary_id,
            "message": "邊界新增成功"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 更新邊界 ==========
@router.put("/boundary/{year}/edit/{boundary_id}")
async def edit_boundary(
    year: int,
    boundary_id: int,
    boundary_data: BoundaryUpdate,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        # 檢查邊界是否存在且屬於該使用者
        boundary = session.get(Boundary, boundary_id)
        
        if not boundary or boundary.account_id != account_id:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "邊界不存在"}
            )
        
        # 檢查邊界名稱是否與其他邊界重複
        year_record = session.exec(
            select(Year).where(
                Year.account_id == account_id,
                Year.year == year
            )
        ).first()
        
        if year_record:
            existing = session.exec(
                select(Boundary).where(
                    Boundary.account_id == account_id,
                    Boundary.year_id == year_record.year_id,
                    Boundary.boundary_name == boundary_data.boundary_name,
                    Boundary.boundary_id != boundary_id
                )
            ).first()
            
            if existing:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "邊界名稱已存在"}
                )
        
        # 更新邊界
        boundary.boundary_name = boundary_data.boundary_name
        boundary.address = boundary_data.address
        boundary.updated_at = datetime.utcnow()
        
        session.add(boundary)
        session.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": "邊界更新成功"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 刪除邊界 ==========
@router.delete("/boundary/{year}/delete/{boundary_id}")
async def delete_boundary(
    year: int,
    boundary_id: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        # 檢查邊界是否存在且屬於該使用者
        boundary = session.get(Boundary, boundary_id)
        
        if not boundary or boundary.account_id != account_id:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "邊界不存在"}
            )
        
        # 檢查是否有相關聯的排放源
        if boundary.emission_sources:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "此邊界下還有排放源資料，無法刪除"}
            )
        
        # 刪除邊界
        session.delete(boundary)
        session.commit()
        
        return JSONResponse(content={
            "success": True,
            "message": "邊界刪除成功"
        })
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ========== 重新排序邊界 ==========
@router.post("/boundary/{year}/reorder")
async def reorder_boundaries(
    year: int,
    reorder_data: BoundaryReorder,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        for index, boundary_id in enumerate(reorder_data.boundary_ids):
            boundary = session.get(Boundary, boundary_id)
            if boundary and boundary.account_id == account_id:
                boundary.sort_order = index + 1
                session.add(boundary)
        
        session.commit()
        return JSONResponse(content={"success": True, "message": "排序更新成功"})
    except Exception as e:
        session.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )