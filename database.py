import os
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select
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


# 係數單位 → 活動數據單位對照
_FACTOR_UNIT_TO_ACTIVITY_UNIT = {
    "KgCO2/Kg": "公斤",
    "KgCH4/Kg": "公斤",
    "KgN2O/Kg": "公斤",
    "KgCO2/L": "公升",
    "KgCH4/L": "公升",
    "KgN2O/L": "公升",
    "KgCO2/M3": "立方公尺",
    "KgCH4/M3": "立方公尺",
    "KgN2O/M3": "立方公尺",
    "kgCO2e/kWh": "度",
}


def _activity_unit_from_factor_unit(factor_unit: str) -> str | None:
    u = (factor_unit or "").strip()
    return _FACTOR_UNIT_TO_ACTIVITY_UNIT.get(u)


def _normalize_unit(unit: str) -> str:
    return (unit or "").strip().replace("/", "/").replace("m3", "M3").lower()


def ensure_schema_updates():
    with engine.begin() as conn:
        # --- 刪除舊 EmissionFactor 表 ---
        conn.exec_driver_sql("DROP TABLE IF EXISTS emissionfactor")

        # --- EmissionFactor604 表：新增 year ---
        ef604_columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info('emission_factor_604')"
            ).fetchall()
        }
        if "year" not in ef604_columns:
            conn.exec_driver_sql(
                "ALTER TABLE emission_factor_604 ADD COLUMN year INTEGER"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_emission_factor_604_year ON emission_factor_604(year)"
            )

        # --- Device 表遷移 ---
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
            "scope": "TEXT DEFAULT 'scope1'",
        }
        for col_name, col_ddl in dev_new_columns.items():
            if col_name not in dev_columns:
                conn.exec_driver_sql(
                    f"ALTER TABLE device ADD COLUMN {col_name} {col_ddl}"
                )

        # --- 新增 account_id 遷移 ---
        if "account_id" not in dev_columns:
            conn.exec_driver_sql(
                "ALTER TABLE device ADD COLUMN account_id INTEGER REFERENCES account(id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_device_account_id ON device(account_id)"
            )

        # --- EmissionRecord 表遷移 ---
        er_columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info('emissionrecord')"
            ).fetchall()
        }
        er_new_columns = {
            "co2": "FLOAT",
            "ch4": "FLOAT",
            "n2o": "FLOAT",
            "factor_year": "INTEGER",
            "gwp_version": "TEXT DEFAULT 'AR5'",
            "activity_unit": "TEXT",
            "factor_source": "TEXT",
            "calculation_version": "TEXT DEFAULT 'v2'",
            "target_year": "INTEGER",
        }
        for col_name, col_ddl in er_new_columns.items():
            if col_name not in er_columns:
                conn.exec_driver_sql(
                    f"ALTER TABLE emissionrecord ADD COLUMN {col_name} {col_ddl}"
                )

        # 移除已棄用的低位熱值欄位
        for col_name in ("heat_value", "lhv_unit"):
            if col_name in er_columns:
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE emissionrecord DROP COLUMN {col_name}"
                    )
                except Exception:
                    pass  # nosec: B110 部分 SQLite 版本不支援 DROP COLUMN，留待下次重建

        # --- AppendixReference 表遷移 ---
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
            pass  # nosec: B110

        # --- UtilityBill 表遷移 ---
        try:
            ub_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info('utilitybill')"
                ).fetchall()
            }
            if len(ub_columns) > 0:
                ub_new = {
                    "device_id": "INTEGER",
                    "target_year": "INTEGER",
                    "target_usage": "FLOAT",
                }
                for col_name, col_ddl in ub_new.items():
                    if col_name not in ub_columns:
                        conn.exec_driver_sql(
                            f"ALTER TABLE utilitybill ADD COLUMN {col_name} {col_ddl}"
                        )
                    if col_name == "device_id":
                        conn.exec_driver_sql(
                            "CREATE INDEX IF NOT EXISTS ix_utilitybill_device_id ON utilitybill(device_id)"
                        )
                # --- 新增 account_id 遷移 ---
                if "account_id" not in ub_columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE utilitybill ADD COLUMN account_id INTEGER REFERENCES account(id)"
                    )
                    conn.exec_driver_sql(
                        "CREATE INDEX IF NOT EXISTS ix_utilitybill_account_id ON utilitybill(account_id)"
                    )
        except Exception:
            pass  # nosec: B110

        # --- GasRecord 表遷移 ---
        try:
            gr_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info('gas_record')"
                ).fetchall()
            }
            if len(gr_columns) == 0:
                conn.exec_driver_sql(
                    """
                    CREATE TABLE gas_record (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id INTEGER NOT NULL,
                        fuel_type VARCHAR NOT NULL,
                        liters FLOAT NOT NULL,
                        unit VARCHAR DEFAULT '公升',
                        record_date VARCHAR NOT NULL,
                        note TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_gas_record_device_id ON gas_record(device_id)"
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_gas_record_fuel_type ON gas_record(fuel_type)"
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_gas_record_record_date ON gas_record(record_date)"
                )
        except Exception:
            pass  # nosec: B110

        # --- OrgBoundary 表遷移 ---
        try:
            ob_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    "PRAGMA table_info('org_boundary')"
                ).fetchall()
            }
            if len(ob_columns) == 0:
                conn.exec_driver_sql(
                    """
                    CREATE TABLE org_boundary (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR NOT NULL,
                        address VARCHAR NOT NULL,
                        account_id INTEGER NOT NULL REFERENCES account(id),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_org_boundary_account_id ON org_boundary(account_id)"
                )
        except Exception:
            pass  # nosec: B110

    # --- 資料補正（需使用 ORM）---
    with Session(engine) as session:
        # 1. 補 EmissionFactor604.year
        ef604_rows = session.exec(select(model.EmissionFactor604)).all()
        for row in ef604_rows:
            if row.year is None:
                if row.original_code == "ELECTRICITY":
                    try:
                        row.year = int(row.code)
                    except (ValueError, TypeError):
                        row.year = 2023
                else:
                    row.year = 2023
                session.add(row)

        # 2. 修正 Device.unit 為活動數據單位
        devices = session.exec(select(model.Device)).all()
        for dev in devices:
            if dev.emission_type == "能源間接排放" or dev.factor_ref_code == "ELECTRICITY":
                dev.unit = "度"
            elif dev.emission_type == "逸散排放":
                dev.unit = "公斤"
            else:
                factor = session.exec(
                    select(model.EmissionFactor604).where(
                        model.EmissionFactor604.original_code == dev.factor_ref_code,
                        model.EmissionFactor604.emission_type == dev.emission_type,
                    )
                ).first()
                if factor and factor.unit:
                    new_unit = _activity_unit_from_factor_unit(factor.unit)
                    if new_unit:
                        dev.unit = new_unit
                    else:
                        dev.unit = "待確認"
                else:
                    dev.unit = "待確認"
            session.add(dev)

        session.commit()


def create_db_and_tables():
    # Ensure models are imported so their tables are registered on metadata
    try:
        import model  # noqa: F401
    except Exception:
        # If models cannot be imported, still attempt create_all and surface errors
        pass  # nosec: B110

    SQLModel.metadata.create_all(engine)
    ensure_schema_updates()


def get_session():
    with Session(engine) as session:
        yield session