from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .deps import get_db
from .security import verify_password
from ..models import User

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/auth/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/groups", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
