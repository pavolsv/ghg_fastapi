def test_report_sections_endpoint_returns_section_registry(client):
    response = client.get("/reports/sections")

    assert response.status_code == 200
    payload = response.json()
    assert "sections" in payload
    assert isinstance(payload["sections"], list)
    section_ids = [item.get("id") for item in payload["sections"]]
    assert "company_basic_info" in section_ids
    assert "emission_calculation" in section_ids
    assert "appendix" in section_ids


def test_create_draft_requires_login(client):
    response = client.post("/reports/drafts")

    assert response.status_code == 401


def test_report_draft_list_requires_login(client):
    response = client.get("/reports/drafts")

    assert response.status_code == 401


def test_calculation_report_page_redirects_when_not_logged_in(client):
    response = client.get("/calculation/report", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_report_routes_registered(client):
    route_paths = {route.path for route in client.app.routes}

    assert "/reports/drafts" in route_paths
    assert "/calculation/report" in route_paths
