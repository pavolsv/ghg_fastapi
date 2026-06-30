from datetime import datetime
from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship, UniqueConstraint


class EmissionFactor604(SQLModel, table=True):
    __tablename__ = "emission_factor_604"

    code: str = Field(primary_key=True)
    original_code: str = Field(index=True)
    gas_type: str
    emission_type: str
    name: str
    factor_value: float
    unit: str
    year: Optional[int] = Field(default=None, index=True)


class FactorCodeMap(SQLModel, table=True):
    __tablename__ = "factor_code_map"

    code: str = Field(primary_key=True)
    fuel_name_zh: str = Field(index=True)
    emission_type: str = "固定燃燒"


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)  # 自動遞增
    account: str
    password: str
    email: str
    inventory_year: Optional[int] = Field(default=None, index=True)

    # ORM relationships
    companies: List["CompanyInfo"] = Relationship(back_populates="account")
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
    scope: str = Field(default="scope1")

    # 冷媒設備專用欄位
    fill_amount: Optional[float] = None
    fill_unit: Optional[str] = None
    equipment_category: Optional[str] = None
    refrigerant_code: Optional[str] = None

    # 加入 account_id 欄位
    account_id: int = Field(foreign_key="account.id", index=True)


class EmissionRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id")
    record_date: str
    activity_data: float
    total_co2e: float
    unit: Optional[str] = None
    data_source: Optional[str] = "manual"

    # 新計算方式明細與追溯欄位
    co2: Optional[float] = None
    ch4: Optional[float] = None
    n2o: Optional[float] = None
    factor_year: Optional[int] = None
    gwp_version: str = Field(default="AR5")
    activity_unit: Optional[str] = None
    factor_source: Optional[str] = None
    calculation_version: str = Field(default="v2")
    target_year: Optional[int] = None


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
    target_year: Optional[int] = None
    target_usage: Optional[float] = None
    device_id: Optional[int] = Field(default=None, foreign_key="device.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # 加入 account_id 欄位
    account_id: int = Field(foreign_key="account.id", index=True)  


class GasRecord(SQLModel, table=True):
    """加油紀錄：每一筆對應到一台設備（Device）的某次加油"""
    __tablename__ = "gas_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)
    fuel_type: str = Field(index=True)  # "汽油" | "柴油"
    liters: float
    unit: str = "公升"
    record_date: str = Field(index=True)
    note: Optional[str] = None
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


class Report(SQLModel, table=True):
    __tablename__ = "report"

    id: Optional[int] = Field(default=None, primary_key=True)
    inventory_year: int = Field(index=True)
    base_year: int
    org_boundary_method: str = Field(default="控制權法")
    operational_boundary_note: Optional[str] = None
    status: str = Field(default="draft", index=True)  # draft / final
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    chapters: List["ReportChapter"] = Relationship(
        back_populates="report",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    sub_chapters: List["ReportSubChapter"] = Relationship(
        back_populates="report",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ReportChapter(SQLModel, table=True):
    __tablename__ = "report_chapter"
    __table_args__ = (
        UniqueConstraint("report_id", "chapter_no", name="uq_report_chapter_no"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="report.id", index=True)
    chapter_no: int  # 1 ~ 6
    title: str
    generated_content: Optional[str] = None
    edited_content: Optional[str] = None
    is_generated_by_llm: bool = Field(default=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    report: Optional[Report] = Relationship(back_populates="chapters")


class ReportSubChapter(SQLModel, table=True):
    __tablename__ = "report_sub_chapter"
    __table_args__ = (
        UniqueConstraint("report_id", "chapter_no", "sub_no", name="uq_report_sub_chapter_no"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="report.id", index=True)
    chapter_no: int  # 所屬大章編號 1~6
    sub_no: int  # 小節編號 1, 2, 3...
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    report: Optional[Report] = Relationship(back_populates="sub_chapters")

class OrgBoundary(SQLModel, table=True):
    __tablename__ = "org_boundary"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                                    # 邊界名稱（例如：台北總部、台中廠區）
    address: str                                 # 地址
    account_id: int = Field(foreign_key="account.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)



