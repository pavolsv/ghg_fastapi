# 使用官方 Python 基礎映像檔
FROM python:3.13-slim

# 設定工作目錄
WORKDIR /app

# 將 requirements.txt 複製到容器中
COPY requirements.txt .

# 安裝所有 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 將整個專案資料夾複製到容器中
COPY . .

# 暴露應用程式運行的 port，FastAPI 預設為 8000
EXPOSE 8000

# 設定容器啟動時執行的指令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]