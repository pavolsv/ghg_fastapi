from logging.config import fileConfig
import os
import sys
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# --- START: 導入和路徑設定 ---
# 確保 Python 可以找到您的專案模組
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import SQLModel 
# 導入您的資料模型 (這行必須確保 CompanyInfo 和所有模型被載入)
from model import CompanyInfo, GWPReference  # noqa: F401 
from model import *
# --- END: 導入和路徑設定 ---


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata 現在指向 SQLModel 的 metadata
target_metadata = SQLModel.metadata

# DATABASE_URL has highest priority, then DATABASE_FILE, then default local file
DEFAULT_DB_FILE = Path(__file__).parent.parent.joinpath("database.db").resolve()
db_url_from_env = os.getenv("DATABASE_URL")
db_file_from_env = os.getenv("DATABASE_FILE")

if db_url_from_env:
    SQLITE_URL = db_url_from_env
else:
    db_file = Path(db_file_from_env).resolve() if db_file_from_env else DEFAULT_DB_FILE
    SQLITE_URL = f"sqlite:///{db_file.as_posix()}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    
    url = SQLITE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # 🎯 關鍵修正：啟用 SQLite 的批次模式，處理 ALTER COLUMN
        render_as_batch=True 
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    
    # 建立一個包含 URL 的字典配置
    connectable = engine_from_config(
        {'sqlalchemy.url': SQLITE_URL}, # 使用定義好的 URL
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            # 🎯 關鍵修正：啟用 SQLite 的批次模式，處理 ALTER COLUMN
            render_as_batch=True,
            # 啟用型別比較，確保 autogenerate 能偵測到型別變動
            compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()