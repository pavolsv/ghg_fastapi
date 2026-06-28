"""匯入台電電力排碳係數 CSV 到 emission_factor_604"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import csv
from sqlmodel import Session, select
from database import engine, create_db_and_tables
from model import EmissionFactor604

create_db_and_tables()

CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)),
    "台電系統發購電量及電力排碳係數(105-113) (1).csv")

def main():
    rows = []
    with open(CSV, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            year = r['年度']
            factor = r['電力排碳係數']
            rows.append((year, float(factor)))

    with Session(engine) as session:
        # 清除舊的電力資料
        for obj in session.exec(select(EmissionFactor604).where(
            EmissionFactor604.original_code == "ELECTRICITY"
        )).all():
            session.delete(obj)
        session.commit()

        for year, factor in rows:
            ef = EmissionFactor604(
                code=year,
                original_code="ELECTRICITY",
                gas_type="CO2e",
                emission_type="能源間接排放",
                name=f"{year}年電力排碳係數",
                factor_value=factor,
                unit="kgCO2e/kWh",
            )
            session.add(ef)

        session.commit()

    print(f"已匯入 {len(rows)} 筆電力係數")
    for y, v in rows:
        print(f"  {y}: {v} kgCO2e/kWh")


if __name__ == "__main__":
    main()
