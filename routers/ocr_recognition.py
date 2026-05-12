from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
import shutil
import os
from GASOCR import ocr_recognize

router = APIRouter(prefix="/ocr", tags=["OCR"])
templates = Jinja2Templates(directory="templates")
TEMP_DIR = "static/temp"

@router.get("/upload", response_class=HTMLResponse) 
async def upload_page(request: Request): 
    """顯示 OCR 上傳與預覽頁面""" 
    return templates.TemplateResponse("ocr/upload.html", {"request": request})

@router.post("/process", response_class=HTMLResponse)
async def process_ocr(request: Request):
    os.makedirs(TEMP_DIR, exist_ok=True)
    
   
    form_data = await request.form()
    

    files = [v for v in form_data.getlist("files") if not isinstance(v, str)]
    
    if not files:
        print("警告：收到的資料中沒有有效的檔案物件")
        return HTMLResponse("<tr><td colspan='8' style='text-align:center;'>未收到有效檔案，請重試</td></tr>")

    results = []
    for file in files:
        file_path = os.path.join(TEMP_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 執行辨識
        data = ocr_recognize(file_path)
        data['filename'] = file.filename
        results.append(data)

    return templates.TemplateResponse("ocr/result_table.html", {
        "request": request,
        "results": results
    })