"""
排放量計算核心服務 v2 單元測試

使用獨立的 in-memory SQLite，避免影響開發資料庫。
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from model import Device, EmissionFactor604, GWPReference
from services.emission_calculator import (
    calculate_combustion_emission_v2,
    calculate_electricity_emission_v2,
    calculate_refrigerant_emission_v2,
    compute_total_co2e_for_device_v2,
)


@pytest.fixture(scope="function")
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def _seed_diesel_factors(session: Session):
    session.add_all([
        EmissionFactor604(
            code="170006_CO2_固定燃燒_柴油",
            original_code="170006",
            gas_type="CO2",
            emission_type="固定燃燒",
            name="柴油",
            factor_value=2.6621,
            unit="KgCO2/L",
            year=2023,
        ),
        EmissionFactor604(
            code="170006_CH4_固定燃燒_柴油",
            original_code="170006",
            gas_type="CH4",
            emission_type="固定燃燒",
            name="柴油",
            factor_value=0.0002,
            unit="KgCH4/L",
            year=2023,
        ),
        EmissionFactor604(
            code="170006_N2O_固定燃燒_柴油",
            original_code="170006",
            gas_type="N2O",
            emission_type="固定燃燒",
            name="柴油",
            factor_value=0.0001,
            unit="KgN2O/L",
            year=2023,
        ),
    ])
    session.commit()


def test_calculate_combustion_diesel(session):
    _seed_diesel_factors(session)

    result = calculate_combustion_emission_v2(
        session=session,
        original_code="170006",
        emission_type="固定燃燒",
        activity_value=100.0,
        activity_unit="公升",
        year=2023,
    )

    assert result.co2 == pytest.approx(266.2100, abs=1e-4)
    assert result.ch4 == pytest.approx(0.0200, abs=1e-4)
    assert result.n2o == pytest.approx(0.0100, abs=1e-4)
    expected_co2e = round(266.21 * 1 + 0.02 * 28 + 0.01 * 265, 4)
    assert result.co2e == pytest.approx(expected_co2e, abs=1e-4)
    assert result.factor_year == 2023
    assert result.activity_unit == "公升"
    assert result.factor_source == "EmissionFactor604"


def test_calculate_combustion_missing_ch4_shows_zero(session):
    session.add_all([
        EmissionFactor604(
            code="170006_CO2_固定燃燒_柴油",
            original_code="170006",
            gas_type="CO2",
            emission_type="固定燃燒",
            name="柴油",
            factor_value=2.6621,
            unit="KgCO2/L",
            year=2023,
        ),
        EmissionFactor604(
            code="170006_N2O_固定燃燒_柴油",
            original_code="170006",
            gas_type="N2O",
            emission_type="固定燃燒",
            name="柴油",
            factor_value=0.0001,
            unit="KgN2O/L",
            year=2023,
        ),
    ])
    session.commit()

    result = calculate_combustion_emission_v2(
        session=session,
        original_code="170006",
        emission_type="固定燃燒",
        activity_value=100.0,
        activity_unit="公升",
    )

    assert result.co2 == pytest.approx(266.2100, abs=1e-4)
    assert result.ch4 == 0.0
    assert result.n2o == pytest.approx(0.0100, abs=1e-4)
    assert "CH4" in result.details["missing"]


def test_calculate_combustion_unit_mismatch_raises(session):
    _seed_diesel_factors(session)

    with pytest.raises(ValueError, match="單位"):
        calculate_combustion_emission_v2(
            session=session,
            original_code="170006",
            emission_type="固定燃燒",
            activity_value=100.0,
            activity_unit="公斤",  # 與 KgCO2/L 不符
        )


def test_calculate_electricity_by_year(session):
    session.add_all([
        EmissionFactor604(
            code="2023",
            original_code="ELECTRICITY",
            gas_type="CO2e",
            emission_type="能源間接排放",
            name="2023年電力排碳係數",
            factor_value=0.494,
            unit="kgCO2e/kWh",
            year=2023,
        ),
        EmissionFactor604(
            code="2024",
            original_code="ELECTRICITY",
            gas_type="CO2e",
            emission_type="能源間接排放",
            name="2024年電力排碳係數",
            factor_value=0.474,
            unit="kgCO2e/kWh",
            year=2024,
        ),
    ])
    session.commit()

    result_2023 = calculate_electricity_emission_v2(
        session=session,
        activity_value=1000.0,
        target_year=2023,
    )
    assert result_2023.factor_year == 2023
    assert result_2023.co2e == pytest.approx(494.0, abs=1e-4)

    result_2024 = calculate_electricity_emission_v2(
        session=session,
        activity_value=1000.0,
        target_year=2024,
    )
    assert result_2024.factor_year == 2024
    assert result_2024.co2e == pytest.approx(474.0, abs=1e-4)


def test_calculate_electricity_fallback_to_latest(session):
    session.add(
        EmissionFactor604(
            code="2024",
            original_code="ELECTRICITY",
            gas_type="CO2e",
            emission_type="能源間接排放",
            name="2024年電力排碳係數",
            factor_value=0.474,
            unit="kgCO2e/kWh",
            year=2024,
        )
    )
    session.commit()

    result = calculate_electricity_emission_v2(
        session=session,
        activity_value=1000.0,
        target_year=2022,  # 沒有 2022 年係數
    )
    assert result.factor_year == 2024
    assert result.co2e == pytest.approx(474.0, abs=1e-4)


def test_calculate_refrigerant(session):
    session.add(
        GWPReference(
            formula="R-134a",
            gas_name_zh="四氟乙烷",
            gas_name_en="HFC-134a",
            gwp_value=1430.0,
        )
    )
    session.commit()

    result = calculate_refrigerant_emission_v2(
        session=session,
        refrigerant_code="R-134a",
        fill_amount_tonnes=0.005,  # 5 公斤
        equipment_category="4097",  # 家用冷凍冷藏裝備，洩漏率 0.003
    )

    # 5 kg * 1430 * 0.003 = 21.45
    assert result.co2e == pytest.approx(21.45, abs=1e-4)
    assert result.details["gwp_value"] == 1430.0
    assert result.details["emission_rate"] == 0.003


def test_compute_total_co2e_for_device_combustion(session):
    _seed_diesel_factors(session)
    device = Device(
        name="鍋爐",
        category="固定燃燒",
        emission_type="固定燃燒",
        location="A廠",
        factor_ref_code="170006",
        gas_type="CO2,CH4,N2O",
        unit="公升",
    )
    session.add(device)
    session.commit()
    session.refresh(device)

    result = compute_total_co2e_for_device_v2(
        session=session,
        device=device,
        activity_data=100.0,
    )

    assert result.co2 == pytest.approx(266.2100, abs=1e-4)
    assert result.co2e > result.co2  # 因 CH4/N2O 貢獻
    assert result.activity_unit == "公升"
