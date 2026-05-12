from sqlmodel import Session

from model import DataChangeLog


def add_change_log(
    session: Session,
    module: str,
    entity_name: str,
    record_key: str,
    action_type: str,
    changed_by: str,
    change_details: str,
):
    session.add(
        DataChangeLog(
            module=module,
            entity_name=entity_name,
            record_key=record_key,
            action_type=action_type,
            changed_by=changed_by,
            change_details=change_details,
        )
    )
