from fastapi import Request, HTTPException
from sqlmodel import Session, create_engine

DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as session:
        yield session

def get_current_user(request: Request):
    user_id = request.session.get("user")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登入")
    return user_id
