from unittest.mock import patch

from sqlmodel import Session, select

from database import engine
from model import Device, Report, ReportSubChapter


def test_reports_list_page(client):
    response = client.get("/reports/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def _cleanup_test_reports(year: int) -> None:
    """刪除指定年度的測試報告。"""
    with Session(engine) as session:
        reports = session.exec(select(Report).where(Report.inventory_year == year)).all()
        for report in reports:
            session.delete(report)
        session.commit()


def test_create_report_and_download_pdf(client):
    test_year = 2099

    # 清理舊測試資料
    _cleanup_test_reports(test_year)

    response = client.post(
        "/reports/",
        data={
            "inventory_year": test_year,
            "base_year": test_year,
            "org_boundary_method": "控制權法",
            "operational_boundary_note": "測試營運邊界",
        },
    )
    # TestClient 會自動跟隨重新導向
    assert response.status_code == 200

    # 確認列表頁出現測試年度
    list_resp = client.get("/reports/")
    assert str(test_year) in list_resp.text

    # 查詢剛建立的報告 ID
    with Session(engine) as session:
        report = session.exec(
            select(Report).where(Report.inventory_year == test_year)
        ).first()
        assert report is not None
        report_id = report.id

    # 預覽頁面
    preview_resp = client.get(f"/reports/{report_id}/preview")
    assert preview_resp.status_code == 200
    assert "第三章 報告溫室氣體排放量" in preview_resp.text

    # 下載 PDF
    pdf_resp = client.get(f"/reports/{report_id}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers.get("content-type") == "application/pdf"
    assert len(pdf_resp.content) > 1000

    # 清理測試資料
    _cleanup_test_reports(test_year)


def test_sub_chapter_management(client):
    test_year = 2098
    _cleanup_test_reports(test_year)

    with patch("services.report_generator.generate_chapter", return_value="<p>AI 測試</p>"):
        response = client.post(
            "/reports/",
            data={
                "inventory_year": test_year,
                "base_year": test_year,
                "org_boundary_method": "控制權法",
            },
        )
    assert response.status_code == 200

    with Session(engine) as session:
        report = session.exec(
            select(Report).where(Report.inventory_year == test_year)
        ).first()
        report_id = report.id
        subs = session.exec(
            select(ReportSubChapter).where(ReportSubChapter.report_id == report_id)
        ).all()
        assert len(subs) > 0

    # 編輯頁包含小節
    edit_resp = client.get(f"/reports/{report_id}")
    assert edit_resp.status_code == 200
    assert "addSub" in edit_resp.text

    # 新增小節
    add_resp = client.post(
        f"/reports/{report_id}/sub-chapters",
        data={"chapter_no": 1, "title": "1.3 新增測試小節"},
    )
    assert add_resp.status_code == 200

    with Session(engine) as session:
        sub = session.exec(
            select(ReportSubChapter).where(
                ReportSubChapter.report_id == report_id,
                ReportSubChapter.chapter_no == 1,
                ReportSubChapter.sub_no == 3,
            )
        ).first()
        assert sub is not None
        sub_id = sub.id

    # 修改小節標題
    update_resp = client.put(
        f"/reports/{report_id}/sub-chapters/{sub_id}/title",
        data={"title": "1.3 已更新小節"},
    )
    assert update_resp.status_code == 200

    # 刪除小節
    del_resp = client.delete(f"/reports/{report_id}/sub-chapters/{sub_id}")
    assert del_resp.status_code == 200

    with Session(engine) as session:
        sub = session.get(ReportSubChapter, sub_id)
        assert sub is None

    _cleanup_test_reports(test_year)


def test_operational_boundary_table(client):
    test_year = 2097
    _cleanup_test_reports(test_year)

    with Session(engine) as session:
        existing = session.exec(
            select(Device).where(Device.name.like("[TEST]%"))
        ).all()
        for d in existing:
            session.delete(d)
        session.commit()

        devices_data = [
            Device(name="[TEST]廚房瓦斯", category="固定燃燒", emission_type="固定燃燒", location="", factor_ref_code="F0001", gas_type="CO2", unit=""),
            Device(name="[TEST]公務車", category="移動燃燒", emission_type="移動燃燒", location="", factor_ref_code="F0002", gas_type="CO2,CH4,N2O", unit=""),
            Device(name="[TEST]冷氣機", category="逸散排放", emission_type="逸散排放", location="", factor_ref_code="GG1835", gas_type="", unit="公斤", refrigerant_code="GG1835", equipment_category="4091"),
            Device(name="[TEST]外購電力", category="能源間接排放", emission_type="能源間接排放", location="", factor_ref_code="ELECTRICITY", gas_type="CO2", unit="", scope="scope2"),
        ]
        for d in devices_data:
            session.add(d)
        session.commit()

    response = client.post(
        "/reports/",
        data={
            "inventory_year": test_year,
            "base_year": test_year,
            "org_boundary_method": "控制權法",
        },
    )
    assert response.status_code == 200

    with Session(engine) as session:
        report = session.exec(
            select(Report).where(Report.inventory_year == test_year)
        ).first()
        report_id = report.id

    preview_resp = client.get(f"/reports/{report_id}/preview")
    assert preview_resp.status_code == 200
    html = preview_resp.text

    assert "第二章 盤查邊界設定" in html
    assert "2.2 營運邊界" in html
    assert "個溫室氣體排放源" in html
    assert "部用能設備" in html
    assert "CO₂" in html
    assert "CH₄" in html
    assert "N₂O" in html
    assert "HFCs" in html

    _cleanup_test_reports(test_year)
    with Session(engine) as session:
        existing = session.exec(
            select(Device).where(Device.name.like("[TEST]%"))
        ).all()
        for d in existing:
            session.delete(d)
        session.commit()
