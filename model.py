from sqlmodel import SQLModel, Field

# not in use 08/13
class GWP(SQLModel, table=True):
    gwp_id: int | None = Field(default=None, primary_key=True)
    gwp_name: str = Field(index=True)
    gwp_value: float = Field(default=0.0)


class FUEL(SQLModel, table=True):
    fuel_id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    CO2: float = Field(default=0.0)
    CH4: float = Field(default=0.0)
    N2O: float = Field(default=0.0)

class gwp_list(SQLModel, table=True):
    product_code: str = Field(primary_key=True)
    chemical_name: str = Field(default="")
    gwp: float | None = Field(default=None)
    status: str | None = Field(default=None)