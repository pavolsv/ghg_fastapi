import os
import uuid
from typing import List
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# 引入你的電費單辨識模組
from EOCR import ocr_recognize

router = APIRouter(prefix="/ocr", tags=["OCR"])
templates = Jinja2Templates(directory="templates")
TEMP_DIR = "static/temp"


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """顯示 OCR 上傳與預覽頁面"""
    return templates.TemplateResponse("ocr/upload.html", {"request": request})

@router.get("/select", response_class=HTMLResponse)
async def select_page(request: Request):
    return templates.TemplateResponse("ocr/select.html", {"request": request})

@router.post("/process-single", response_class=JSONResponse)
async def process_single_ocr(request: Request, file: UploadFile = File(...)):
    """單張電費單辨識"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(TEMP_DIR, unique_filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        # 檢查客戶端是否已斷線
        if await request.is_disconnected():
            return JSONResponse(content={"success": False, "備註": "請求已取消"}, status_code=499)

        data = ocr_recognize(file_path)
        
        # OCR 完成後再檢查一次
        if await request.is_disconnected():
            return JSONResponse(content={"success": False, "備註": "請求已取消"}, status_code=499)
        
        remark = data.get("備註", "辨識成功")
        is_success = (remark != "辨識失敗")
        
        return JSONResponse(
            content={
                "success": is_success,
                "期間起日": data.get("期間起日", ""),
                "期間迄日": data.get("期間迄日", ""),
                "度數": data.get("用電度數", ""),
                "備註": remark
            }
        )

    except Exception as e:
        return JSONResponse(
            content={
                "success": False,
                "期間起日": "",
                "期間迄日": "",
                "度數": "",
                "備註": f"系統錯誤: {str(e)}"
            },
            status_code=500
        )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)