import os
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine
import model

# DATABASE_URL has highest priority, then DATABASE_FILE, then default local file
default_db_file = Path(__file__).parent.joinpath("database.db").resolve()
db_file_from_env = os.getenv("DATABASE_FILE")

if _db_url := os.getenv("DATABASE_URL"):
    db: str = _db_url
    DB_FILE = None
else:
    DB_FILE = Path(db_file_from_env).resolve() if db_file_from_env else default_db_file
    db = f"sqlite:///{DB_FILE.as_posix()}"
# For typical local usage with SQLModel/SQLAlchemy and SQLite
engine = create_engine(db, echo=True)


def ensure_schema_updates():
    with engine.begin() as conn:
        try:
            # --- EmissionFactor 表迁移 ---
            ef_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info('emissionfactor')"
                ).fetchall()
            }

            ef_required = {
                "factor_source": "TEXT",
                "calculation_method": "TEXT",
                "updated_at": "DATETIME",
                "lower_heating_value": "FLOAT",
                "lhv_unit": "TEXT",
            }

            for column_name, column_ddl in ef_required.items():
                if column_name not in ef_columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE emissionfactor ADD COLUMN {column_name} {column_ddl}"
                    )

            # 移除 factor_version 栏位（SQLite 不支持 DROP COLUMN，保留但不再使用）

            conn.exec_driver_sql(
                "UPDATE emissionfactor SET updated_at=CURRENT_TIMESTAMP WHERE updated_at IS NULL"
            )

            # --- Device 表迁移 ---
            dev_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info('device')"
                ).fetchall()
            }

            if "emission_type" not in dev_columns and len(dev_columns) > 0:
                conn.exec_driver_sql(
                    "ALTER TABLE device ADD COLUMN emission_type TEXT DEFAULT '固定燃燒'"
                )

            dev_new_columns = {
                "device_number": "TEXT",
                "device_code": "TEXT",
                "quantity": "INTEGER DEFAULT 1",
                "fill_amount": "FLOAT",
                "fill_unit": "TEXT",
                "equipment_category": "TEXT",
                "refrigerant_code": "TEXT",
            }
            for col_name, col_ddl in dev_new_columns.items():
                if col_name not in dev_columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE device ADD COLUMN {col_name} {col_ddl}"
                    )

            # --- AppendixReference 表迁移 ---
            try:
                app_columns = {
                    row[1]
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info('appendix_reference')"
                    ).fetchall()
                }
                if len(app_columns) > 0:
                    app_required = {
                        "source_sheet": "TEXT",
                        "note": "TEXT",
                    }
                    for column_name, column_ddl in app_required.items():
                        if column_name not in app_columns:
                            conn.exec_driver_sql(
                                f"ALTER TABLE appendix_reference ADD COLUMN {column_name} {column_ddl}"
                            )
            except Exception:
                pass

            # --- ActivityData 表遷移 ---
            try:
                ad_columns = {
                    row[1]
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info('activity_data')"
                    ).fetchall()
                }
                if len(ad_columns) > 0:
                    ad_new_columns = {
                        "lower_heating_value": "FLOAT",
                        "lhv_unit": "TEXT",
                    }
                    for col_name, col_ddl in ad_new_columns.items():
                        if col_name not in ad_columns:
                            conn.exec_driver_sql(
                                f"ALTER TABLE activity_data ADD COLUMN {col_name} {col_ddl}"
                            )
            except Exception:
                pass

            # --- EmissionRecord 表遷移 ---
            try:
                er_columns = {
                    row[1]
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info('emissionrecord')"
                    ).fetchall()
                }
                if len(er_columns) > 0:
                    er_new_columns = {
                        "unit": "TEXT",
                        "data_source": "TEXT DEFAULT 'manual'",
                        "lhv_unit": "TEXT",
                    }
                    for col_name, col_ddl in er_new_columns.items():
                        if col_name not in er_columns:
                            conn.exec_driver_sql(
                                f"ALTER TABLE emissionrecord ADD COLUMN {col_name} {col_ddl}"
                            )
            except Exception:
                pass

            # --- ReportSnapshot 表遷移 ---
            try:
                rs_columns = {
                    row[1]
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info('reportsnapshot')"
                    ).fetchall()
                }
                if len(rs_columns) > 0:
                    rs_new_columns = {
                        "account_id": "INTEGER",
                        "inventory_year": "INTEGER",
                        "snapshot_payload": "TEXT",
                        "created_by": "TEXT",
                        "created_at": "DATETIME",
                    }
                    for col_name, col_ddl in rs_new_columns.items():
                        if col_name not in rs_columns:
                            conn.exec_driver_sql(
                                f"ALTER TABLE reportsnapshot ADD COLUMN {col_name} {col_ddl}"
                            )
            except Exception:
                pass

            # --- ReportDraft 表遷移 ---
            try:
                rd_columns = {
                    row[1]
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info('reportdraft')"
                    ).fetchall()
                }
                if len(rd_columns) > 0:
                    rd_new_columns = {
                        "account_id": "INTEGER",
                        "title": "TEXT",
                        "status": "TEXT",
                        "sections_payload": "TEXT",
                        "exported_file_path": "TEXT",
                        "created_by": "TEXT",
                        "created_at": "DATETIME",
                        "updated_at": "DATETIME",
                    }
                    for col_name, col_ddl in rd_new_columns.items():
                        if col_name not in rd_columns:
                            conn.exec_driver_sql(
                                f"ALTER TABLE reportdraft ADD COLUMN {col_name} {col_ddl}"
                            )
            except Exception:
                pass

        except Exception:
            # 新環境或尚未建立資料表時，create_all 會處理
            pass


def create_db_and_tables():
    # Ensure models are imported so their tables are registered on metadata
    try:
        import model  # noqa: F401
    except Exception:
        # If models cannot be imported, still attempt create_all and surface errors
        pass

    SQLModel.metadata.create_all(engine)
    ensure_schema_updates()


def get_session():
    with Session(engine) as session:
        yield session

