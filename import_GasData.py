import pandas as pd
import os
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session
import model


def save_single_record(date_str, p98, p95, p92, diesel):

    db = "sqlite:///database.db"
    engine = create_engine(db, echo=True)

    publish_dt = datetime.strptime(date_str, "%Y-%m-%d")

    new_price = model.OilPrice(
        publish_date=publish_dt, 
        price_92=p92,
        price_95=p95,
        price_98=p98,
        price_diesel=diesel
    )

    # 4. 執行儲存
    with Session(engine) as session:
        session.add(new_price)
        session.commit()
        session.refresh(new_price) # 重新整理以獲取自動生成的 ID
        print(f"✅ 資料儲存成功！資料 ID: {new_price.id}")



# 1. 設定檔案路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(current_dir, 'gasprice.xlsx')

try:
    # 2. 讀取 Excel
    df = pd.read_excel(file_path)

    # 3. 定義必須完整的欄位
    required_columns = ['調價日期', '無鉛汽油92', '無鉛汽油95', '無鉛汽油98', '超級/高級柴油']

    # 4. 篩選：過濾掉含有空值的行
    df_clean = df.dropna(subset=required_columns).copy()

    # 5. 修改日期格式：將「調價日期」強制轉換為 yyyy--mm--dd 字串格式
    df_clean['調價日期'] = pd.to_datetime(df_clean['調價日期']).dt.strftime('%Y-%m-%d')

    # 6. 輸出每一行資料
    for index, row in df_clean.iterrows():
        data = row.to_dict()
        save_single_record(data['調價日期'], data['無鉛汽油98'], data['無鉛汽油95'], data['無鉛汽油92'], data['超級/高級柴油'])
        

except Exception as e:
    print(f"處理過程中發生錯誤: {e}")

