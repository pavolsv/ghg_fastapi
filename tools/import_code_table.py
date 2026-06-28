"""
從 代碼檔V2 匯入各節代碼到 appendix_reference 表
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from sqlmodel import Session, select
from database import engine, create_db_and_tables
from model import AppendixReference

create_db_and_tables()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(BASE, "溫室氣體盤查作業相關代碼檔V2 (4).ods")

# 各 section 在 ODS 中的欄位配置
SECTIONS = {
    "boundary": {
        "type": "boundary",
        "cols": (1, 2),
        "sheet": 1,
    },
    "verification_body": {
        "type": "verification_body",
        "cols": (7, 8),
        "sheet": 1,
    },
    "competent_authority": {
        "type": "competent_authority",
        "cols": (11, 12),
        "sheet": 1,
    },
    "industry": {
        "type": "industry",
        "cols": (15, 16),
        "sheet": 1,
    },
    "city": {
        "type": "city",
        "cols": (19, 20, 21),  # name(縣市), name(區), code
        "sheet": 1,
        "mode": "city",
    },
    "process": {
        "type": "process",
        "cols": (25, 26),
        "sheet": 1,
    },
    "factor_code": {
        "type": "factor_code",
        "cols": (30, 31),
        "sheet": 1,
    },
    "test_method": {
        "type": "test_method",
        "cols": (39,),
        "sheet": 1,
        "mode": "name_only",
    },
    "usage": {
        "type": "usage",
        "cols": (48, 49),
        "sheet": 1,
    },
}


def main():
    print("=" * 60)
    print("匯入代碼檔V2 → appendix_reference")
    print("=" * 60)

    df = pd.read_excel(FILE, sheet_name=1, engine="odf")

    total = 0
    with Session(engine) as session:
        for key, cfg in SECTIONS.items():
            atype = cfg["type"]
            cols = cfg["cols"]
            mode = cfg.get("mode", "")

            data = df.iloc[:, cols[0]:cols[-1]+1].copy()
            data = data.dropna(how="all")

            count = 0
            for i in range(len(data)):
                row = data.iloc[i]
                vals = [str(v).strip() for v in row if pd.notna(v)]

                if mode == "name_only":
                    if vals and vals[0] not in ("NaN", "nan", ""):
                        name = vals[0]
                        code = name  # 用 name 當 code 避免衝突
                    else:
                        continue
                elif mode == "city":
                    if len(vals) >= 3 and vals[2] not in ("NaN", "nan", ""):
                        code = vals[2]
                        name = f"{vals[0]}{vals[1]}" if vals[1] not in ("NaN", "nan", "") else vals[0]
                    else:
                        continue
                else:
                    code = vals[0] if len(vals) >= 1 and vals[0] not in ("NaN", "nan", "") else ""
                    name = vals[1] if len(vals) >= 2 and vals[1] not in ("NaN", "nan", "") else ""
                    if not code and not name:
                        continue

                if mode == "name_only":
                    existing = session.exec(
                        select(AppendixReference).where(
                            AppendixReference.appendix_type == atype,
                            AppendixReference.name == name
                        )
                    ).first()
                else:
                    existing = session.exec(
                        select(AppendixReference).where(
                            AppendixReference.appendix_type == atype,
                            AppendixReference.code == code
                        )
                    ).first()

                if not existing:
                    session.add(AppendixReference(
                        appendix_type=atype, code=code, name=name
                    ))
                    count += 1

            session.commit()
            print(f"  {atype:<25} 新增 {count} 筆")
            total += count

    print(f"\n總計新增 {total} 筆")


if __name__ == "__main__":
    main()
