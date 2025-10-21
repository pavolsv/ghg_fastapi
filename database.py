from sqlmodel import create_engine, Session, SQLModel, select
from model import Utility, Account



db = "sqlite:///database.db"
engine = create_engine(db, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        statement = select(Utility).where(Utility.id.in_([0, 1])) # type: ignore
        existing_utilities = session.exec(statement).all()
        
        if not existing_utilities:
            electricity = Utility(id=0, utility_name="電", utility_unit="kWh")
            water = Utility(id=1, utility_name="水", utility_unit="m³")
            
            session.add(electricity)
            session.add(water)
            session.commit()
            print("預設成功")
def get_session():
    with Session(engine) as session:
        yield session
