from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from audit_log import add_change_log
from database import engine
from model import OrgChart, OrgNode

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/org_chart", tags=["org_chart"])


def _get_current_user(request: Request) -> Optional[int]:
    return request.session.get("user")


def _load_org_charts(session: Session, user_id: int):
    statement = select(OrgChart).where(OrgChart.account_id == user_id).order_by(OrgChart.id)
    return session.exec(statement).all()


def _load_org_nodes(session: Session, chart_id: int):
    statement = select(OrgNode).where(OrgNode.chart_id == chart_id).order_by(OrgNode.id)
    return session.exec(statement).all()


def _find_chart_for_user(session: Session, user_id: int, chart_id: Optional[int]):
    if chart_id:
        chart = session.get(OrgChart, chart_id)
        if chart and chart.account_id == user_id:
            return chart
    return session.exec(select(OrgChart).where(OrgChart.account_id == user_id).order_by(OrgChart.id)).first()


def _serialize_chart(chart: OrgChart) -> dict:
    return {"id": chart.id, "name": chart.name}


def _serialize_node(node: OrgNode) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "duty": node.duty or "",
        "parent_id": node.parent_id,
    }


@router.get("/", response_class=HTMLResponse)
async def org_chart_page(
    request: Request,
    selected_chart_id: Optional[int] = None,
    edit_node_id: Optional[int] = None,
):
    user_id = _get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        charts = _load_org_charts(session, user_id)
        selected_chart = _find_chart_for_user(session, user_id, selected_chart_id)
        nodes = []
        edit_node = None
        parent_options = []

        if selected_chart:
            nodes = _load_org_nodes(session, selected_chart.id)
            parent_options = [node for node in nodes if node.id != edit_node_id]
            if edit_node_id:
                edit_node = next((node for node in nodes if node.id == edit_node_id), None)

        charts_data = [_serialize_chart(chart) for chart in charts]
        nodes_data = [_serialize_node(node) for node in nodes]
        parent_options_data = [
            {"id": node.id, "name": node.name} for node in parent_options
        ]
        parent_map = {node.id: node.name for node in nodes}

    return templates.TemplateResponse(
        "org_chart.html",
        {
            "request": request,
            "charts": charts,
            "charts_data": charts_data,
            "selected_chart": selected_chart,
            "nodes": nodes,
            "nodes_data": nodes_data,
            "parent_options": parent_options,
            "parent_options_data": parent_options_data,
            "parent_map": parent_map,
            "edit_node": edit_node,
        },
    )


@router.post("/chart")
async def save_chart(
    request: Request,
    chart_id: Optional[int] = Form(None),
    name: str = Form(...),
):
    user_id = _get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        if chart_id:
            chart = session.get(OrgChart, chart_id)
            if not chart or chart.account_id != user_id:
                return RedirectResponse(url=router.prefix + "/", status_code=303)
            chart.name = name.strip() or chart.name
            session.add(chart)
            action = "UPDATE"
        else:
            chart = OrgChart(name=name.strip(), account_id=user_id)
            session.add(chart)
            action = "CREATE"

        add_change_log(
            session=session,
            module="org_chart",
            entity_name="OrgChart",
            record_key=str(chart.id if chart_id else "new"),
            action_type=action,
            changed_by=str(user_id),
            change_details=f"name={name}",
        )
        session.commit()
        return RedirectResponse(
            url=f"{router.prefix}/?selected_chart_id={chart.id}",
            status_code=303,
        )


@router.post("/delete_chart")
async def delete_chart(request: Request, chart_id: int = Form(...)):
    user_id = _get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        chart = session.get(OrgChart, chart_id)
        if chart and chart.account_id == user_id:
            nodes = _load_org_nodes(session, chart.id)
            for node in nodes:
                session.delete(node)
            session.delete(chart)
            add_change_log(
                session=session,
                module="org_chart",
                entity_name="OrgChart",
                record_key=str(chart.id),
                action_type="DELETE",
                changed_by=str(user_id),
                change_details=f"chart_name={chart.name}",
            )
            session.commit()

    return RedirectResponse(url=router.prefix + "/", status_code=303)


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_required_int(value: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


@router.post("/node")
async def save_node(
    request: Request,
    chart_id: str = Form(...),
    node_id: Optional[str] = Form(None),
    name: str = Form(...),
    duty: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
):
    user_id = _get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    chart_id_int = _parse_required_int(chart_id)
    node_id_int = _parse_optional_int(node_id)
    parent_id_int = _parse_optional_int(parent_id)

    if chart_id_int is None:
        return RedirectResponse(url=router.prefix + "/", status_code=303)

    with Session(engine) as session:
        chart = session.get(OrgChart, chart_id_int)
        if not chart or chart.account_id != user_id:
            return RedirectResponse(url=router.prefix + "/", status_code=303)

        if node_id_int:
            node = session.get(OrgNode, node_id_int)
            if not node or node.chart_id != chart_id_int:
                return RedirectResponse(url=f"{router.prefix}/?selected_chart_id={chart_id_int}", status_code=303)
            node.name = name.strip() or node.name
            node.duty = duty.strip() if duty else None
            node.parent_id = parent_id_int
            action = "UPDATE"
        else:
            node = OrgNode(
                name=name.strip(),
                duty=duty.strip() if duty else None,
                chart_id=chart_id_int,
                parent_id=parent_id_int,
            )
            session.add(node)
            action = "CREATE"

        add_change_log(
            session=session,
            module="org_chart",
            entity_name="OrgNode",
            record_key=str(node.id if node_id_int else "new"),
            action_type=action,
            changed_by=str(user_id),
            change_details=f"chart_id={chart_id_int}, node_name={name}, parent_id={parent_id_int}",
        )
        session.commit()

    return RedirectResponse(url=f"{router.prefix}/?selected_chart_id={chart_id}", status_code=303)


@router.post("/node/delete")
async def delete_node(request: Request, chart_id: int = Form(...), node_id: int = Form(...)):
    user_id = _get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        node = session.get(OrgNode, node_id)
        if node and node.chart_id == chart_id:
            children = session.exec(select(OrgNode).where(OrgNode.parent_id == node.id)).all()
            for child in children:
                child.parent_id = None
                session.add(child)
            session.delete(node)
            add_change_log(
                session=session,
                module="org_chart",
                entity_name="OrgNode",
                record_key=str(node.id),
                action_type="DELETE",
                changed_by=str(user_id),
                change_details=f"chart_id={chart_id}, node_name={node.name}",
            )
            session.commit()

    return RedirectResponse(url=f"{router.prefix}/?selected_chart_id={chart_id}", status_code=303)


@router.post("/node/clear")
async def clear_nodes(request: Request, chart_id: int = Form(...)):
    user_id = _get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    with Session(engine) as session:
        chart = session.get(OrgChart, chart_id)
        if chart and chart.account_id == user_id:
            nodes = _load_org_nodes(session, chart_id)
            for node in nodes:
                session.delete(node)
            add_change_log(
                session=session,
                module="org_chart",
                entity_name="OrgNode",
                record_key=f"chart_id={chart_id}",
                action_type="DELETE",
                changed_by=str(user_id),
                change_details=f"cleared all nodes for chart={chart.name}",
            )
            session.commit()

    return RedirectResponse(url=f"{router.prefix}/?selected_chart_id={chart_id}", status_code=303)
