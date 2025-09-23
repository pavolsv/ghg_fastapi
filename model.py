from typing import Optional,  List
from sqlmodel import SQLModel, Field, Relationship


class gwp_list(SQLModel, table=True):
    product_code: str = Field(primary_key=True)
    chemical_name: str = Field(default="")
    gwp: float | None = Field(default=None)
    status: str | None = Field(default=None)


class Utility(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    utility_name: str
    utility_unit: str

    records: List["UtilityRecord"] = Relationship(back_populates="utility")
    factors: List["UtilityFactor"] = Relationship(back_populates="utility")


class UtilityRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    utility_id: Optional[int] = Field(default=None, foreign_key="utility.id")

    utility_record_year: int
    utility_record_month: int
    utility_record_start: str
    utility_record_end: str
    utility_record_value: float

    utility: Optional[Utility] = Relationship(back_populates="records")


class UtilityFactor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    utility_id: Optional[int] = Field(default=None, foreign_key="utility.id")

    utility_factor_year: int
    utility_factor_value: float
    utility_factor_unit: str
    utility_factor_source: str

    utility: Optional[Utility] = Relationship(back_populates="factors")
