import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from audit_log import add_change_log
from model import ReportDraft, ReportSnapshot
from routers.result import (
    _build_docx_report,
    _build_report_snapshot,
    _generate_report_payload,
    _normalize_report_payload,
    _validate_report_payload,
)


REPORT_SECTIONS: list[dict[str, str]] = [
    {"id": "company_basic_info", "title": "一、公司基本資料"},
    {"id": "boundary_setting", "title": "二、盤查邊界設定"},
    {"id": "source_identification", "title": "三、排放源鑑別"},
    {"id": "emission_calculation", "title": "四、排放量計算"},
    {"id": "other_regulatory_items", "title": "五、其他主管機關規定事項"},
    {"id": "appendix", "title": "六、附錄與佐證資料"},
]


def get_report_section_definitions() -> list[dict[str, str]]:
    return [dict(item) for item in REPORT_SECTIONS]


def _blank_sections_payload() -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for item in REPORT_SECTIONS:
        payload[item["id"]] = {
            "title": item["title"],
            "content": "",
            "citations": [],
            "updated_at": None,
            "source": "manual",
        }
    return payload


def _parse_json_payload(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def create_report_draft(session: Session, account_id: int | None, created_by: str) -> ReportDraft:
    snapshot = _build_report_snapshot(session)

    snapshot_id = str(uuid4())
    snapshot_row = ReportSnapshot(
        snapshot_id=snapshot_id,
        account_id=account_id,
        inventory_year=int(snapshot.get("inventory_year") or 0) or None,
        snapshot_payload=json.dumps(snapshot, ensure_ascii=False),
        created_by=created_by,
    )
    session.add(snapshot_row)

    draft_id = str(uuid4())
    draft_row = ReportDraft(
        draft_id=draft_id,
        snapshot_id=snapshot_id,
        account_id=account_id,
        sections_payload=json.dumps(_blank_sections_payload(), ensure_ascii=False),
        created_by=created_by,
    )
    session.add(draft_row)

    add_change_log(
        session=session,
        module="report_editor",
        entity_name="ReportDraft",
        record_key=draft_id,
        action_type="CREATE",
        changed_by=created_by,
        change_details=f"create_draft snapshot_id={snapshot_id}",
    )
    session.commit()
    session.refresh(draft_row)
    return draft_row


def get_report_draft(session: Session, draft_id: str, account_id: int | None) -> tuple[ReportDraft, dict[str, Any]]:
    draft = session.get(ReportDraft, draft_id)
    if not draft:
        raise ValueError("找不到報告草稿")
    if account_id is not None and draft.account_id not in (None, account_id):
        raise PermissionError("沒有存取此報告草稿的權限")

    snapshot = session.get(ReportSnapshot, draft.snapshot_id)
    if not snapshot:
        raise ValueError("找不到報告快照")

    snapshot_payload = _parse_json_payload(snapshot.snapshot_payload, {})
    return draft, snapshot_payload


def list_report_drafts(session: Session, account_id: int | None) -> list[dict[str, Any]]:
    statement = select(ReportDraft).order_by(
        ReportDraft.updated_at.desc(),
        ReportDraft.created_at.desc(),
    )
    if account_id is not None:
        statement = statement.where(ReportDraft.account_id == account_id)

    drafts = session.exec(statement).all()
    total_sections = len(REPORT_SECTIONS)
    summaries: list[dict[str, Any]] = []

    for draft in drafts:
        snapshot = session.get(ReportSnapshot, draft.snapshot_id)
        snapshot_payload = _parse_json_payload(snapshot.snapshot_payload if snapshot else None, {})
        sections = _parse_json_payload(draft.sections_payload, _blank_sections_payload())
        completed_sections = sum(
            1
            for section in sections.values()
            if isinstance(section, dict) and str(section.get("content") or "").strip()
        )

        summaries.append(
            {
                "draft_id": draft.draft_id,
                "title": draft.title,
                "status": draft.status,
                "inventory_year": snapshot_payload.get("inventory_year"),
                "snapshot_generated_at": snapshot_payload.get("generated_at"),
                "created_at": draft.created_at.isoformat(timespec="seconds") if draft.created_at else None,
                "updated_at": draft.updated_at.isoformat(timespec="seconds") if draft.updated_at else None,
                "completed_sections": completed_sections,
                "total_sections": total_sections,
            }
        )

    return summaries


def update_report_section(
    session: Session,
    draft: ReportDraft,
    section_id: str,
    content: str,
    changed_by: str,
    source: str = "manual",
    citations: list[dict[str, Any]] | None = None,
) -> ReportDraft:
    sections = _parse_json_payload(draft.sections_payload, _blank_sections_payload())
    if section_id not in sections:
        raise ValueError("不支援的章節")

    section = sections[section_id]
    section["content"] = content.strip()
    section["citations"] = citations or []
    section["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    section["source"] = source

    draft.sections_payload = json.dumps(sections, ensure_ascii=False)
    draft.updated_at = datetime.utcnow()
    session.add(draft)

    add_change_log(
        session=session,
        module="report_editor",
        entity_name="ReportDraftSection",
        record_key=f"{draft.draft_id}:{section_id}",
        action_type="UPDATE",
        changed_by=changed_by,
        change_details=f"source={source}, content_length={len(content or '')}",
    )

    session.commit()
    session.refresh(draft)
    return draft


def generate_section_content(
    session: Session,
    draft: ReportDraft,
    snapshot_payload: dict[str, Any],
    section_id: str,
    changed_by: str,
) -> dict[str, Any]:
    if section_id not in {item["id"] for item in REPORT_SECTIONS}:
        raise ValueError("不支援的章節")

    payload = _generate_report_payload(snapshot_payload)
    normalized = _normalize_report_payload(payload, snapshot_payload)
    _validate_report_payload(normalized, snapshot_payload)

    section_map = normalized.get("compliance_template_sections", {})
    section_lines = section_map.get(section_id)

    # appendix is manual-first; provide deterministic fallback
    if section_id == "appendix":
        section_lines = section_lines or [
            "佐證資料建議：保留量測報告、採購/能源帳單、設備台帳與年度彙整表。",
            "若有第三方查證文件，請附上查證範圍與日期。",
        ]

    if not isinstance(section_lines, list):
        section_lines = ["資料缺口：此章節目前無可用內容。"]

    section_content = "\n".join(str(item).strip() for item in section_lines if str(item).strip())

    citations_raw = normalized.get("citations", [])
    citations = []
    for item in citations_raw:
        if isinstance(item, dict):
            citations.append(
                {
                    "metric": str(item.get("metric", "")).strip(),
                    "source_path": str(item.get("source_path", "")).strip(),
                    "value": item.get("value"),
                }
            )

    updated_draft = update_report_section(
        session=session,
        draft=draft,
        section_id=section_id,
        content=section_content,
        changed_by=changed_by,
        source="ai",
        citations=citations,
    )

    sections = _parse_json_payload(updated_draft.sections_payload, _blank_sections_payload())
    return sections.get(section_id, {})


def insert_section_data(
    session: Session,
    draft: ReportDraft,
    snapshot_payload: dict[str, Any],
    section_id: str,
    changed_by: str,
) -> dict[str, Any]:
    if section_id not in {item["id"] for item in REPORT_SECTIONS}:
        raise ValueError("不支援的章節")

    summary = snapshot_payload.get("summary", {})
    company = snapshot_payload.get("company_summary", {})
    boundary = snapshot_payload.get("boundary_summary", {})

    if section_id == "company_basic_info":
        lines = [
            f"事業名稱：{company.get('company_name') or '-'}",
            f"統一編號：{company.get('tax_id') or '-'}",
            f"地址：{company.get('address') or '-'}",
            f"負責人：{company.get('owner') or '-'}",
        ]
    elif section_id == "boundary_setting":
        lines = [
            f"盤查邊界數量：{boundary.get('boundary_count', 0)}",
            f"排放源數量：{boundary.get('source_count', 0)}",
            f"活動數據覆蓋率：{boundary.get('activity_coverage_rate', 0)}%",
        ]
    elif section_id == "emission_calculation":
        lines = [
            f"總排放量：{summary.get('total_co2e', 0)} kg CO2e",
            f"排放紀錄筆數：{summary.get('record_count', 0)}",
            f"設備數量：{summary.get('device_count', 0)}",
        ]
    elif section_id == "appendix":
        lines = [
            "附錄A：活動數據來源與原始憑證清單",
            "附錄B：排放係數與熱值參數來源",
            "附錄C：計算過程摘要與查核重點",
        ]
    else:
        lines = ["資料插入完成，請依需要補充敘述內容。"]

    section_content = "\n".join(lines)
    updated_draft = update_report_section(
        session=session,
        draft=draft,
        section_id=section_id,
        content=section_content,
        changed_by=changed_by,
        source="system",
        citations=[],
    )
    sections = _parse_json_payload(updated_draft.sections_payload, _blank_sections_payload())
    return sections.get(section_id, {})


def export_report_draft(session: Session, draft: ReportDraft, snapshot_payload: dict[str, Any]) -> Path:
    sections = _parse_json_payload(draft.sections_payload, _blank_sections_payload())

    compliance_sections: dict[str, list[str]] = {}
    for key in [
        "company_basic_info",
        "boundary_setting",
        "source_identification",
        "emission_calculation",
        "other_regulatory_items",
    ]:
        content = str(sections.get(key, {}).get("content", "")).strip()
        if content:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            compliance_sections[key] = lines if lines else ["資料缺口：尚未填寫。"]
        else:
            compliance_sections[key] = ["資料缺口：尚未填寫。"]

    appendix_content = str(sections.get("appendix", {}).get("content", "")).strip()

    payload = {
        "executive_summary": "本報告採分章草稿模式，由系統數據與人工補充內容逐步完成。",
        "compliance_template_sections": compliance_sections,
        "current_state_findings": [
            "本文件由『計算 > 報告』頁面逐章產出。",
            f"草稿編號：{draft.draft_id}",
        ],
        "reduction_actions": [
            {
                "title": "持續補齊資料缺口",
                "detail": "請在章節中補齊尚未填寫項目，並保留佐證文件。",
                "expected_impact": "提升查證完整性與追溯性。",
            }
        ],
        "assumptions": ["引用數值以草稿建立時快照資料為準。"],
        "data_gaps": ["請於正式送審前完成所有章節複核。"],
        "citations": [],
    }

    if appendix_content:
        payload["current_state_findings"].append(f"附錄摘要：{appendix_content}")

    file_path = _build_docx_report(payload, snapshot_payload, draft.draft_id)
    draft.status = "exported"
    draft.exported_file_path = str(file_path)
    draft.updated_at = datetime.utcnow()
    session.add(draft)
    session.commit()
    return file_path
