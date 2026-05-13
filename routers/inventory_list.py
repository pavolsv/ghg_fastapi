from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from model import Year, Boundary, EmissionSource, ActivityData
from dependencies import get_session, get_current_user

router = APIRouter(prefix="/inventory_list", tags=["inventory_list"])
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def inventory_list(
    request: Request,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    # 取得該使用者所有年度資料，依年份倒序排序
    years = session.exec(
        select(Year).where(Year.account_id == account_id).order_by(Year.year.desc())
    ).all()

    return templates.TemplateResponse(
        "inventory_list.html",
        {
            "request": request,
            "years": years
        }
    )

@router.get("/boundary/{year}", response_class=HTMLResponse)
async def boundary_page(
    request: Request,
    year: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    # 確認該年度是否存在
    year_record = session.exec(
        select(Year).where(
            Year.account_id == account_id,
            Year.year == year
        )
    ).first()
    
    if not year_record:
        return RedirectResponse(url="/inventory_list", status_code=302)
    
    return templates.TemplateResponse(
        "boundary.html",
        {
            "request": request,
            "year": year,
            "active_page": "boundary"
        }
    )

@router.get("/emission/{year}", response_class=HTMLResponse)
async def emission_page(
    request: Request,
    year: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    year_record = session.exec(
        select(Year).where(
            Year.account_id == account_id,
            Year.year == year
        )
    ).first()
    
    if not year_record:
        return RedirectResponse(url="/inventory_list", status_code=302)
    
    return templates.TemplateResponse(
        "emission.html",
        {
            "request": request,
            "year": year,
            "active_page": "emission"
        }
    )

# ========== 活動數據頁面（直接使用設備資料） ==========
@router.get("/activity/", response_class=HTMLResponse)
@router.get("/activity/{year}", response_class=HTMLResponse)
@router.get("/emission/{year}/activity", response_class=HTMLResponse)
async def activity_page(
    request: Request,
    year: Optional[int] = None,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    return templates.TemplateResponse(
        "activity.html",
        {
            "request": request,
            "year": year,
            "active_page": "activity"
        }
    )

# 刪除年度及其所有相關資料
@router.delete("/{year}/delete")
async def delete_year(
    year: int,
    session: Session = Depends(get_session),
    account_id: int = Depends(get_current_user)
):
    try:
        print(f"🔍 嘗試刪除年度 {year}，使用者 {account_id}")
        
        # 取得 year_id
        year_record = session.exec(
            select(Year).where(
                Year.account_id == account_id,
                Year.year == year
            )
        ).first()
        
        if not year_record:
            print(f"❌ 年度 {year} 不存在")
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "年度不存在"}
            )
        
        year_id = year_record.year_id
        print(f"✅ 找到年度記錄，year_id: {year_id}")
        
        # 1️⃣ 先刪除活動數據
        activity_data_list = session.exec(
            select(ActivityData).where(ActivityData.year_id == year_id)
        ).all()
        print(f"📊 找到 {len(activity_data_list)} 筆活動數據")
        
        for item in activity_data_list:
            session.delete(item)
        
        # 2️⃣ 再刪除排放源
        emission_list = session.exec(
            select(EmissionSource).where(EmissionSource.year_id == year_id)
        ).all()
        print(f"📊 找到 {len(emission_list)} 筆排放源")
        
        for item in emission_list:
            session.delete(item)
        
        # 3️⃣ 最後刪除邊界
        boundary_list = session.exec(
            select(Boundary).where(Boundary.year_id == year_id)
        ).all()
        print(f"📊 找到 {len(boundary_list)} 筆邊界")
        
        for item in boundary_list:
            session.delete(item)
        
        # 4️⃣ 刪除年度本身
        session.delete(year_record)
        
        # 5️⃣ 提交事務
        session.commit()
        print(f"✅ 年度 {year} 所有資料刪除成功")
        
        return JSONResponse(content={
            "success": True,
            "message": f"{year} 年度盤查資料已全部刪除"
        })
        
    except Exception as e:
        # 如果發生錯誤，回滾事務
        session.rollback()
        print(f"❌ 刪除失敗：{str(e)}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"刪除失敗：{str(e)}"}
        )