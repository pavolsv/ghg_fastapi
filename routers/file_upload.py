from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
import shutil
import os
from OCR import ocr_recognize

router = APIRouter()

# 確保 'uploads' 資料夾存在
if not os.path.exists("uploads"):
    os.makedirs("uploads")

@router.post("/upload")
async def upload_and_process_image(imageFile: UploadFile = File(...)):
    # 確保 'imageFile' 參數名稱和前端 FormData 的名稱一致
    file_location = f"uploads/{imageFile.filename}"
    
    try:
        # 1. 儲存上傳的檔案
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(imageFile.file, buffer)
        imageFile.file.close()

        # 2. 立即呼叫 OCR 模組，並傳遞檔案路徑
        ocr_result = ocr_recognize(file_location)
        
        # 3. 將辨識結果回傳
        return JSONResponse(content={
            "message": "檔案上傳及OCR處理成功！",
            "fileName": imageFile.filename,
            "ocr_result": ocr_result
        })

    except Exception as e:
        # 如果發生任何錯誤，刪除可能已儲存的檔案
        if os.path.exists(file_location):
            os.remove(file_location)
        return JSONResponse(content={"error": f"處理過程中發生錯誤: {e}"}, status_code=500)