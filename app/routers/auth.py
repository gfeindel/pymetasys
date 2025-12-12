from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import get_settings
from app.database import Base, engine
from app.dependencies import get_db, get_current_user
from app.security import verify_password, get_password_hash, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token_expires = timedelta(minutes=get_settings().access_token_expire_minutes)
    token = create_access_token({"user_id": user.id, "role": user.role.value}, access_token_expires)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Using explicit db query to ensure fresh data
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/bootstrap-admin", response_model=schemas.UserOut)
def bootstrap_admin(db: Session = Depends(get_db)):
    """
    Creates an initial admin user if none exist.
    Controlled via ADMIN_EMAIL and ADMIN_PASSWORD env vars.
    """
    settings = get_settings()
    if not settings.admin_bootstrap_email or not settings.admin_bootstrap_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bootstrap not configured")

    admin_exists = db.query(models.User).filter(models.User.role == models.UserRole.admin).first()
    if admin_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin already exists")

    hashed = get_password_hash(settings.admin_bootstrap_password)
    user = models.User(email=settings.admin_bootstrap_email, password_hash=hashed, role=models.UserRole.admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
