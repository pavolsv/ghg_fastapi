from fastapi import Request, HTTPException
from database import get_session

def get_current_user(request: Request):
    user_id = request.session.get("user")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登入")
    return user_id