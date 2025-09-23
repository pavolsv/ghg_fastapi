from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, SQLModel
from database import get_session, engine
from io import BytesIO
from model import gwp_list
import pandas as pd


templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/gwplist", tags=["gwplist"])

@router.get("/", response_class=HTMLResponse)
async def upload_excel_page(request: Request):
    return templates.TemplateResponse("upload_gwp.html", {"request": request})

@router.post("/")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    sheet_name: str = Form("附表二"),
    session: Session = Depends(get_session)
):
    try:
        # Read uploaded file contents
        contents = await file.read()

        # Load specified sheet from Excel file
        df = pd.read_excel(BytesIO(contents), sheet_name=sheet_name)

        if df.empty:
            raise HTTPException(
                status_code=400, detail="讀取的 Excel 分頁或行範圍內沒有資料。"
            )

        # Helper to clean cell values
        def clean_value(val):
            if pd.isna(val) or str(val).strip() == "":
                return None
            return str(val)

        # Insert each row into the database
        for _, row in df.iterrows():
            product_code = clean_value(row.get('原(燃)物料或產品代碼'))
            chemical_name = clean_value(row.get('縮寫/通用名稱/化學名稱'))
            gwp = row.get('溫暖化潛勢')
            status = clean_value(row.get('備註說明'))

            try:
                gwp = float(gwp) if gwp is not None else None
            except (TypeError, ValueError):
                gwp = None

            record = gwp_list(
                product_code=product_code or "",
                chemical_name=chemical_name or "",
                gwp=gwp,
                status=status
            )
            session.add(record)

        session.commit()

        message = (
            f"成功上傳 {len(df)} 筆資料，從 '{file.filename}' 的 '{sheet_name}' 分頁寫入資料庫。"
        )
        return templates.TemplateResponse(
            "upload_gwp.html", {"request": request, "message": message}
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"讀取錯誤：{e}。請檢查分頁名稱或欄位名稱。"
        )
    except KeyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Excel 檔案中缺少必要的欄位：{e}。"
        )
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"處理檔案或資料庫寫入時發生錯誤：{e}"
        )
