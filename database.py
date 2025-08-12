from sqlmodel import create_engine, Session, SQLModel

db = "sqlite:///database.db"
engine = create_engine(db, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
