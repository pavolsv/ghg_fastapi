from datetime import datetime
from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint


class EmissionFactor(SQLModel, table=True):
    code: str = Field(primary_key=True)
    gas_type: str = Field(primary_key=True)
    original_code: str = Field(index=True)
    emission_type: str = "固定燃燒"
    name: str
    factor_value: float
    unit: str
    year: int
    factor_source: Optional[str] = None
    calculation_method: Optional[str] = None
    lower_heating_value: Optional[float] = None
    lhv_unit: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)  # 自動遞增
    account: str
    password: str
    email: str

    # ORM relationships
    years: List["Year"] = Relationship(back_populates="account")
    companies: List["CompanyInfo"] = Relationship(back_populates="account")
    boundaries: List["Boundary"] = Relationship(back_populates="account")
    emission_sources: List["EmissionSource"] = Relationship(back_populates="account")
    activity_data: List["ActivityData"] = Relationship(back_populates="account")
    org_charts: List["OrgChart"] = Relationship(back_populates="account")


class CompanyInfo(SQLModel, table=True):
    tax_id: str = Field(default=None, primary_key=True)
    company_name: str
    address: str
    owner: str
    account_id: int = Field(foreign_key="account.id")

    telephone: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    URL: Optional[str] = None

    account: Optional[Account] = Relationship(back_populates="companies")


class OrgChart(SQLModel, table=True):
    """組織圖表主表"""
    __tablename__ = "org_chart"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    account_id: int = Field(foreign_key="account.id")

    account: Optional[Account] = Relationship(back_populates="org_charts")
    nodes: List["OrgNode"] = Relationship(back_populates="chart")


class OrgNode(SQLModel, table=True):
    """組織節點表"""
    __tablename__ = "org_node"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    duty: Optional[str] = Field(default=None)
    chart_id: int = Field(foreign_key="org_chart.id")
    parent_id: Optional[int] = Field(default=None, foreign_key="org_node.id")

    chart: Optional[OrgChart] = Relationship(back_populates="nodes")
    parent: Optional["OrgNode"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "OrgNode.id"}
    )
    children: List["OrgNode"] = Relationship(back_populates="parent")


class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str
    emission_type: str = Field(default="固定燃燒")
    location: str
    factor_ref_code: str
    gas_type: str
    unit: str
    device_number: Optional[str] = None
    device_code: Optional[str] = None
    quantity: int = 1

    # 冷媒設備專用欄位
    fill_amount: Optional[float] = None
    fill_unit: Optional[str] = None
    equipment_category: Optional[str] = None
    refrigerant_code: Optional[str] = None


class EmissionRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id")
    record_date: str
    activity_data: float
    total_co2e: float
    unit: Optional[str] = None
    data_source: Optional[str] = "manual"
    heat_value: Optional[float] = None
    lhv_unit: Optional[str] = None


class ETLStatus(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    etl_type: str = Field(index=True)
    last_fetch_time: Optional[datetime] = None
    last_fetch_result: str = ""
    fetched_count: int = 0
    source_url: Optional[str] = None


class DataChangeLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    module: str = Field(index=True)
    entity_name: str
    record_key: str
    action_type: str
    changed_by: str = Field(default="system")
    changed_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    change_details: str


class UtilityBill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bill_type: str = Field(index=True)
    bill_month: str = Field(index=True)
    period_start: str
    period_end: str
    usage_amount: float
    unit: str
    note: Optional[str] = None
    fuel_type: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class GWPReference(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    gas_name_zh: str = Field(index=True)
    gas_name_en: str = Field(index=True)
    formula: str = Field(index=True)
    gwp_value: float = 0.0
    version: str = "AR5"
    is_qualitative: bool = False
    note: Optional[str] = None


class Year(SQLModel, table=True):
    __tablename__ = "year"
    __table_args__ = (
        UniqueConstraint("year", "account_id"),
    )

    year_id: Optional[int] = Field(default=None, primary_key=True)
    year: int
    account_id: int = Field(foreign_key="account.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    account: Optional[Account] = Relationship(back_populates="years")
    boundaries: List["Boundary"] = Relationship(back_populates="year")
    emission_sources: List["EmissionSource"] = Relationship(back_populates="year")
    activity_data: List["ActivityData"] = Relationship(back_populates="year")


class Boundary(SQLModel, table=True):
    __tablename__ = "boundary"

    boundary_id: Optional[int] = Field(default=None, primary_key=True)
    boundary_name: str = Field(index=True)
    address: Optional[str] = None
    sort_order: Optional[int] = 0

    account_id: int = Field(foreign_key="account.id")
    year_id: int = Field(foreign_key="year.year_id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    account: Optional[Account] = Relationship(back_populates="boundaries")
    year: Optional[Year] = Relationship(back_populates="boundaries")
    emission_sources: List["EmissionSource"] = Relationship(back_populates="boundary")
    activity_data: List["ActivityData"] = Relationship(back_populates="boundary")


class EmissionSource(SQLModel, table=True):
    __tablename__ = "emission_source"
    __table_args__ = (
        UniqueConstraint("boundary_id", "source_number", name="uq_source_number_per_boundary"),
        UniqueConstraint("account_id", "year_id", "source_id", name="uq_source_global"),
    )

    source_id: Optional[int] = Field(default=None, primary_key=True)
    source_number: str = Field(index=True)
    source_name: str = Field(index=True)
    scope: str = Field(index=True)
    emission_type: str
    material: str
    quantity: int = 1
    sort_order: Optional[int] = 0

    account_id: int = Field(foreign_key="account.id")
    year_id: int = Field(foreign_key="year.year_id")
    boundary_id: int = Field(foreign_key="boundary.boundary_id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    account: Optional[Account] = Relationship(back_populates="emission_sources")
    year: Optional[Year] = Relationship(back_populates="emission_sources")
    boundary: Optional[Boundary] = Relationship(back_populates="emission_sources")
    activity_data: Optional["ActivityData"] = Relationship(back_populates="emission_source")


class ActivityData(SQLModel, table=True):
    __tablename__ = "activity_data"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_activity_data_per_source"),
        UniqueConstraint("account_id", "year_id", "source_id", name="uq_activity_global"),
    )

    data_id: Optional[int] = Field(default=None, primary_key=True)
    year_value: float = Field(ge=0)
    unit: str

    source_id: int = Field(foreign_key="emission_source.source_id", unique=True)
    account_id: int = Field(foreign_key="account.id")
    year_id: int = Field(foreign_key="year.year_id")
    boundary_id: int = Field(foreign_key="boundary.boundary_id")

    data_source: Optional[str] = "manual"
    lower_heating_value: Optional[float] = None
    lhv_unit: Optional[str] = None
    remark: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    account: Optional[Account] = Relationship(back_populates="activity_data")
    year: Optional[Year] = Relationship(back_populates="activity_data")
    boundary: Optional[Boundary] = Relationship(back_populates="activity_data")
    emission_source: Optional[EmissionSource] = Relationship(back_populates="activity_data")

class OilPrice(SQLModel, table=True):

    id: Optional[int] = Field(default=None, primary_key=True)

    publish_date: datetime = Field(index=True, unique=True, description="油價公布日期")

    price_92: float = Field(default=0.0, description="92無鉛汽油")
    price_95: float = Field(default=0.0, description="95無鉛汽油")
    price_98: float = Field(default=0.0, description="98無鉛汽油")
    price_diesel: float = Field(default=0.0, description="超級柴油")

    source_url: Optional[str] = Field(default="https://www.cpc.com.tw/historyprice.aspx?n=2890")

    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppendixReference(SQLModel, table=True):
    __tablename__ = "appendix_reference"
    __table_args__ = (
        UniqueConstraint("appendix_type", "code", name="uq_appendix_type_code"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    appendix_type: str = Field(index=True)
    seq: Optional[int] = None
    code: str = Field(index=True)
    name: str = Field(index=True)
    source_sheet: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
