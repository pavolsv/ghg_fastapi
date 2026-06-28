"""
設備活動數據 API 整合測試

使用 in-memory SQLite 並覆寫 dependency，驗證儲存後 EmissionRecord 明細正確。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import database
import main
from model import Device, EmissionFactor604


def _seed(session: Session):
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
    device = Device(
        name="測試鍋爐",
        category="固定燃燒",
        emission_type="固定燃燒",
        location="A廠",
        factor_ref_code="170006",
        gas_type="CO2,CH4,N2O",
        unit="公升",
        device_code="GS01",
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device.id


@pytest.fixture(scope="function")
def api_client():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    # 各路由模組都定義了本地 get_session，必須以原始函式物件為 key 覆寫
    import routers.devices
    import routers.calculation
    import routers.result

    for mod in (routers.devices, routers.calculation, routers.result):
        original = mod.get_session
        main.app.dependency_overrides[original] = override_get_session

    with TestClient(main.app) as client:
        with Session(engine) as session:
            _seed(session)
        yield client

    main.app.dependency_overrides.clear()


def test_save_device_activity_creates_emission_record(api_client):
    # 取得 device id
    resp = api_client.get("/devices/api/activities")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    device_id = data[0]["device_id"]

    payload = {
        "device_id": device_id,
        "activity_data": 100.0,
        "unit": "公升",
        "data_source": "manual",
    }
    resp = api_client.post("/devices/api/activities/save", json=payload)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 驗證 EmissionRecord
    resp = api_client.get("/devices/api/activities")
    record = resp.json()["data"][0]
    assert record["has_data"] is True
    assert record["activity_data"] == 100.0
    assert record["activity_unit"] == "公升"


def test_save_device_activity_unit_mismatch_returns_error(api_client):
    resp = api_client.get("/devices/api/activities")
    device_id = resp.json()["data"][0]["device_id"]

    payload = {
        "device_id": device_id,
        "activity_data": 100.0,
        "unit": "公斤",  # 柴油係數為 KgCO2/L，應報錯
        "data_source": "manual",
    }
    resp = api_client.post("/devices/api/activities/save", json=payload)
    assert resp.status_code == 500
    assert "單位" in resp.json()["message"]


def test_calculation_page_shows_record_details(api_client):
    resp = api_client.get("/devices/api/activities")
    device_id = resp.json()["data"][0]["device_id"]

    api_client.post("/devices/api/activities/save", json={
        "device_id": device_id,
        "activity_data": 100.0,
        "unit": "公升",
    })

    resp = api_client.get("/calculation/")
    assert resp.status_code == 200
    html = resp.text
    assert "266.2100" in html
    assert "CO₂" in html


def test_result_page_aggregates_total_co2e(api_client):
    resp = api_client.get("/devices/api/activities")
    device_id = resp.json()["data"][0]["device_id"]

    api_client.post("/devices/api/activities/save", json={
        "device_id": device_id,
        "activity_data": 100.0,
        "unit": "公升",
    })

    resp = api_client.get("/result")
    assert resp.status_code == 200
    html = resp.text
    assert "固定燃燒" in html
    assert "266." in html
