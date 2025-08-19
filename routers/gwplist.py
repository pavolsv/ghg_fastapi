from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from database import get_session, engine  # Import engine
from io import BytesIO
from model import gwp_list
import pandas as pd
from sqlmodel import SQLModel


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


create_db_and_tables()

templates = Jinja2Templates(directory="templates")
router = APIRouter(
    prefix="/gwplist", tags=["gwplist"]
)


@router.get("/", response_class=HTMLResponse)
async def upload_excel_page(request: Request):
    return templates.TemplateResponse("upload_gwp.html", {"request": request})


@router.post("/")
async def upload_and_save_excel(
    request: Request,
    file: UploadFile = File(...),
    sheet_name: str = Form("附表二"),
    session: Session = Depends(get_session)
):


    try:
        contents = await file.read()

        # 指定分頁
        df = pd.read_excel(
            BytesIO(contents),
            sheet_name=sheet_name,
        )

        if df.empty:
            raise HTTPException(
                status_code=400, detail="讀取的 Excel 分頁或行範圍內沒有資料。")

        # 3. 寫入資料庫
        for _, row in df.iterrows():
            product_code = row['原(燃)物料或產品代碼']
            chemical_name = row['縮寫/通用名稱/化學名稱']
            gwp = row.get('溫暖化潛勢')
            status = row.get('備註說明')

            # Convert empty strings to None
            product_code = None if pd.isna(product_code) or str(
                product_code).strip() == "" else str(product_code)
            chemical_name = None if pd.isna(chemical_name) or str(
                chemical_name).strip() == "" else str(chemical_name)
            status = None if pd.isna(status) or str(
                status).strip() == "" else status

            try:
                gwp = float(gwp) if gwp is not None else None
            except (TypeError, ValueError):
                gwp = None

            record = gwp_list(
                product_code=product_code if product_code is not None else "",
                chemical_name=chemical_name if chemical_name is not None else "",
                gwp=gwp,
                status=status
            )
            session.add(record)
        session.commit()

        message = f"成功上傳 {len(df)} 筆資料，從 '{file.filename}' 的 '{sheet_name}' 分頁寫入資料庫。"

        return templates.TemplateResponse("upload_gwp.html", {"request": request, "message": message})

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"讀取錯誤：{e}。請檢查分頁名稱或欄位名稱。")
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Excel 檔案中缺少必要的欄位：{e}。")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"處理檔案或資料庫寫入時發生錯誤：{e}")
