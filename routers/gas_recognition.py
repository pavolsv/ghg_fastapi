import os
import uuid
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from GOCR import gas_recognize

router = APIRouter(prefix="/gas", tags=["Gas OCR"])
templates = Jinja2Templates(directory="templates")
TEMP_DIR = "static/temp"


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """顯示加油收據 OCR 上傳與預覽頁面"""
    return templates.TemplateResponse("ocr/upload_gas.html", {"request": request})


@router.post("/process-single", response_class=JSONResponse)
async def process_single_gas(request: Request, file: UploadFile = File(...)):
    """單張加油收據辨識"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(TEMP_DIR, unique_filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        if await request.is_disconnected():
            return JSONResponse(content={"success": False, "備註": "請求已取消"}, status_code=499)

        data = gas_recognize(file_path)
        
        if await request.is_disconnected():
            return JSONResponse(content={"success": False, "備註": "請求已取消"}, status_code=499)
        
        remark = data.get("備註", "辨識成功")
        is_success = (remark != "辨識失敗")
        
        return JSONResponse(
            content={
                "success": is_success,
                "日期": data.get("日期", ""),
                "油品": data.get("油品", ""),
                "用量": data.get("用量", ""),
                "備註": remark
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "日期": "",
                "油品": "",
                "用量": "",
                "備註": f"系統錯誤: {str(e)}"
            },
            status_code=500
        )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)