import asyncio
import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from model import Device, EmissionFactor, EmissionRecord
from routers.devices import DeviceActivityData, save_device_activity


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_combustion_device(session: Session) -> Device:
    factors = [
        EmissionFactor(
            code="fuel-co2",
            gas_type="CO2",
            original_code="TEST-FUEL",
            emission_type="固定燃燒",
            name="測試燃料",
            factor_value=70000,
            unit="kg/TJ",
            year=2024,
            lower_heating_value=10,
            lhv_unit="MJ/公升",
        ),
        EmissionFactor(
            code="fuel-ch4",
            gas_type="CH4",
            original_code="TEST-FUEL",
            emission_type="固定燃燒",
            name="測試燃料",
            factor_value=3,
            unit="kg/TJ",
            year=2024,
            lower_heating_value=10,
            lhv_unit="MJ/公升",
        ),
        EmissionFactor(
            code="fuel-n2o",
            gas_type="N2O",
            original_code="TEST-FUEL",
            emission_type="固定燃燒",
            name="測試燃料",
            factor_value=0.6,
            unit="kg/TJ",
            year=2024,
            lower_heating_value=10,
            lhv_unit="MJ/公升",
        ),
    ]
    device = Device(
        name="鍋爐A",
        category="固定燃燒",
        emission_type="固定燃燒",
        location="1F",
        factor_ref_code="TEST-FUEL",
        gas_type="CO2,CH4,N2O",
        unit="公升",
    )
    session.add_all(factors)
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def _seed_electricity_device(session: Session) -> Device:
    session.add(
        EmissionFactor(
            code="electricity-co2e",
            gas_type="CO2e",
            original_code="ELECTRICITY",
            emission_type="能源間接排放",
            name="外購電力",
            factor_value=0.509,
            unit="kg CO2e/kWh",
            year=2024,
        )
    )
    device = Device(
        name="總電表",
        category="能源間接排放",
        emission_type="能源間接排放",
        location="機房",
        factor_ref_code="ELECTRICITY",
        gas_type="CO2e",
        unit="度",
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@pytest.mark.parametrize(
    ("activity_value", "expected_total"),
    [
        (100.0, 70.2430),
        (200.0, 140.4860),
    ],
)
def test_save_device_activity_persists_and_recalculates_combustion_total(
    activity_value: float,
    expected_total: float,
) -> None:
    with _make_session() as session:
        device = _seed_combustion_device(session)

        response = asyncio.run(
            save_device_activity(
                data=DeviceActivityData(
                    device_id=device.id,
                    activity_data=activity_value,
                    unit="公升",
                    data_source="manual",
                    heat_value=10,
                    lhv_unit="MJ/公升",
                    record_date="2024-05-01",
                ),
                session=session,
            )
        )

        payload = json.loads(response.body)
        assert payload["success"] is True

        record = session.exec(select(EmissionRecord).where(EmissionRecord.device_id == device.id)).one()
        assert record.total_co2e == pytest.approx(expected_total, abs=1e-4)

        updated_response = asyncio.run(
            save_device_activity(
                data=DeviceActivityData(
                    device_id=device.id,
                    activity_data=activity_value * 2,
                    unit="公升",
                    data_source="manual",
                    heat_value=10,
                    lhv_unit="MJ/公升",
                    record_date="2024-06-01",
                ),
                session=session,
            )
        )

        updated_payload = json.loads(updated_response.body)
        assert updated_payload["success"] is True

        updated_record = session.exec(select(EmissionRecord).where(EmissionRecord.device_id == device.id)).one()
        assert updated_record.total_co2e == pytest.approx(expected_total * 2, abs=1e-4)
        assert updated_record.record_date == "2024-06-01"


def test_save_device_activity_persists_electricity_total() -> None:
    with _make_session() as session:
        device = _seed_electricity_device(session)

        response = asyncio.run(
            save_device_activity(
                data=DeviceActivityData(
                    device_id=device.id,
                    activity_data=120.0,
                    unit="度",
                    data_source="manual",
                    record_date="2024-05-01",
                ),
                session=session,
            )
        )

        payload = json.loads(response.body)
        assert payload["success"] is True

        record = session.exec(select(EmissionRecord).where(EmissionRecord.device_id == device.id)).one()
        assert record.total_co2e == pytest.approx(61.08, abs=1e-4)