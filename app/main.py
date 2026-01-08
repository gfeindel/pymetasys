from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth.deps import get_current_user, require_admin, get_db
from .auth.routes import router as auth_router
from .auth.security import hash_password
from .config import settings
from .db import init_db
from .jobs.queue import create_job
from .logging_config import configure_logging
from .models import (
    Group,
    Job,
    JOB_COMMAND_POINT,
    JOB_READ_GROUP,
    Point,
    ROLE_ADMIN,
    User,
)

configure_logging()
init_db()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret_key)
app.include_router(auth_router)

templates = Jinja2Templates(directory="app/templates")

@app.get("/")
async def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/groups", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/groups")
async def groups_list(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    groups = db.query(Group).order_by(Group.group_number.asc()).all()
    return templates.TemplateResponse("groups.html", {"request": request, "user": user, "groups": groups})

@app.get("/groups/{group_id}")
async def group_detail(group_id: int, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404)
    points = db.query(Point).filter(Point.group_id == group.id).order_by(Point.point_number.asc()).all()
    return templates.TemplateResponse(
        "group_detail.html",
        {"request": request, "user": user, "group": group, "points": points},
    )

@app.post("/groups/{group_id}/refresh")
async def refresh_group(group_id: int, request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404)
    job = create_job(
        db,
        created_by_user_id=user.id,
        job_type=JOB_READ_GROUP,
        payload={"group_id": group.id, "group_number": group.group_number},
    )
    return RedirectResponse(f"/groups/{group_id}?job_id={job.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/points/{point_id}/command")
async def command_point(
    point_id: int,
    request: Request,
    user=Depends(get_current_user),
    db=Depends(get_db),
    command_type: str = Form(...),
    command_value: str = Form(...),
):
    point = db.query(Point).filter(Point.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404)
    if point.read_only:
        raise HTTPException(status_code=403)
    if point.allowed_operations and "command" not in point.allowed_operations:
        raise HTTPException(status_code=403)
    group = db.query(Group).filter(Group.id == point.group_id).first()
    if not group:
        raise HTTPException(status_code=404)
    job = create_job(
        db,
        created_by_user_id=user.id,
        job_type=JOB_COMMAND_POINT,
        payload={
            "group_id": group.id,
            "group_number": group.group_number,
            "point_id": point.id,
            "point_number": point.point_number,
            "command_type": command_type,
            "command_value": command_value,
        },
    )
    return RedirectResponse(f"/groups/{group.id}?job_id={job.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/jobs/{job_id}")
async def job_status(job_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404)
    return JSONResponse(
        {
            "id": job.id,
            "status": job.status,
            "result": job.result_json,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
    )

@app.get("/admin/users")
async def admin_users(request: Request, user=Depends(require_admin), db=Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin/users.html", {"request": request, "user": user, "users": users})

@app.get("/admin/users/new")
async def admin_user_new(request: Request, user=Depends(require_admin)):
    return templates.TemplateResponse("admin/user_edit.html", {"request": request, "user": user, "form": {}})

@app.post("/admin/users/new")
async def admin_user_create(
    request: Request,
    user=Depends(require_admin),
    db=Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
):
    new_user = User(email=email, password_hash=hash_password(password), role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/users/{user_id}/edit")
async def admin_user_edit(user_id: int, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    edit_user = db.query(User).filter(User.id == user_id).first()
    if not edit_user:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/user_edit.html", {"request": request, "user": user, "form": edit_user})

@app.post("/admin/users/{user_id}/edit")
async def admin_user_update(
    user_id: int,
    request: Request,
    user=Depends(require_admin),
    db=Depends(get_db),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(""),
):
    edit_user = db.query(User).filter(User.id == user_id).first()
    if not edit_user:
        raise HTTPException(status_code=404)
    edit_user.email = email
    edit_user.role = role
    if password:
        edit_user.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/users/{user_id}/delete")
async def admin_user_delete(user_id: int, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    delete_user = db.query(User).filter(User.id == user_id).first()
    if delete_user:
        db.delete(delete_user)
        db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/groups")
async def admin_groups(request: Request, user=Depends(require_admin), db=Depends(get_db)):
    groups = db.query(Group).order_by(Group.group_number.asc()).all()
    return templates.TemplateResponse("admin/groups.html", {"request": request, "user": user, "groups": groups})

@app.get("/admin/groups/new")
async def admin_group_new(request: Request, user=Depends(require_admin)):
    return templates.TemplateResponse("admin/group_edit.html", {"request": request, "user": user, "form": {}})

@app.post("/admin/groups/new")
async def admin_group_create(
    request: Request,
    user=Depends(require_admin),
    db=Depends(get_db),
    group_number: int = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    building: str = Form(""),
    floor: str = Form(""),
):
    group = Group(
        group_number=group_number,
        name=name,
        description=description,
        building=building,
        floor=floor,
    )
    db.add(group)
    db.commit()
    return RedirectResponse("/admin/groups", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/groups/{group_id}/edit")
async def admin_group_edit(group_id: int, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    edit_group = db.query(Group).filter(Group.id == group_id).first()
    if not edit_group:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/group_edit.html", {"request": request, "user": user, "form": edit_group})

@app.post("/admin/groups/{group_id}/edit")
async def admin_group_update(
    group_id: int,
    request: Request,
    user=Depends(require_admin),
    db=Depends(get_db),
    group_number: int = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    building: str = Form(""),
    floor: str = Form(""),
):
    edit_group = db.query(Group).filter(Group.id == group_id).first()
    if not edit_group:
        raise HTTPException(status_code=404)
    edit_group.group_number = group_number
    edit_group.name = name
    edit_group.description = description
    edit_group.building = building
    edit_group.floor = floor
    db.commit()
    return RedirectResponse("/admin/groups", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/groups/{group_id}/delete")
async def admin_group_delete(group_id: int, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    delete_group = db.query(Group).filter(Group.id == group_id).first()
    if delete_group:
        db.delete(delete_group)
        db.commit()
    return RedirectResponse("/admin/groups", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/points")
async def admin_points(request: Request, user=Depends(require_admin), db=Depends(get_db)):
    points = db.query(Point).order_by(Point.group_id.asc(), Point.point_number.asc()).all()
    groups = db.query(Group).order_by(Group.group_number.asc()).all()
    return templates.TemplateResponse(
        "admin/points.html",
        {"request": request, "user": user, "points": points, "groups": groups},
    )

@app.get("/admin/points/new")
async def admin_point_new(request: Request, user=Depends(require_admin), db=Depends(get_db)):
    groups = db.query(Group).order_by(Group.group_number.asc()).all()
    return templates.TemplateResponse(
        "admin/point_edit.html",
        {"request": request, "user": user, "form": {}, "groups": groups},
    )

@app.post("/admin/points/new")
async def admin_point_create(
    request: Request,
    user=Depends(require_admin),
    db=Depends(get_db),
    point_number: int = Form(...),
    name: str = Form(...),
    group_id: int = Form(...),
    point_type: str = Form(""),
    unit: str = Form(""),
    read_only: bool = Form(False),
    allowed_operations: str = Form(""),
):
    allowed = None
    if allowed_operations.strip():
        allowed = [item.strip() for item in allowed_operations.split(",") if item.strip()]
    point = Point(
        point_number=point_number,
        name=name,
        group_id=group_id,
        point_type=point_type,
        unit=unit,
        read_only=read_only,
        allowed_operations=allowed,
    )
    db.add(point)
    db.commit()
    return RedirectResponse("/admin/points", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/points/{point_id}/edit")
async def admin_point_edit(point_id: int, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    edit_point = db.query(Point).filter(Point.id == point_id).first()
    if not edit_point:
        raise HTTPException(status_code=404)
    groups = db.query(Group).order_by(Group.group_number.asc()).all()
    return templates.TemplateResponse(
        "admin/point_edit.html",
        {"request": request, "user": user, "form": edit_point, "groups": groups},
    )

@app.post("/admin/points/{point_id}/edit")
async def admin_point_update(
    point_id: int,
    request: Request,
    user=Depends(require_admin),
    db=Depends(get_db),
    point_number: int = Form(...),
    name: str = Form(...),
    group_id: int = Form(...),
    point_type: str = Form(""),
    unit: str = Form(""),
    read_only: bool = Form(False),
    allowed_operations: str = Form(""),
):
    edit_point = db.query(Point).filter(Point.id == point_id).first()
    if not edit_point:
        raise HTTPException(status_code=404)
    allowed = None
    if allowed_operations.strip():
        allowed = [item.strip() for item in allowed_operations.split(",") if item.strip()]
    edit_point.point_number = point_number
    edit_point.name = name
    edit_point.group_id = group_id
    edit_point.point_type = point_type
    edit_point.unit = unit
    edit_point.read_only = read_only
    edit_point.allowed_operations = allowed
    db.commit()
    return RedirectResponse("/admin/points", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/points/{point_id}/delete")
async def admin_point_delete(point_id: int, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    delete_point = db.query(Point).filter(Point.id == point_id).first()
    if delete_point:
        db.delete(delete_point)
        db.commit()
    return RedirectResponse("/admin/points", status_code=status.HTTP_303_SEE_OTHER)
