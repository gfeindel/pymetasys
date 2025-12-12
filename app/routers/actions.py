import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.dependencies import get_current_user, get_db, require_admin
from app.services.regex_utils import normalize_pattern

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("", response_model=list[schemas.ActionDefinitionOut])
def list_actions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.ActionDefinition)
    if current_user.role != models.UserRole.admin:
        query = query.filter(models.ActionDefinition.is_enabled == True)  # noqa: E712
    return query.order_by(models.ActionDefinition.name).all()


@router.get("/{action_id}", response_model=schemas.ActionDefinitionOut)
def get_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    action = db.query(models.ActionDefinition).filter(models.ActionDefinition.id == action_id).first()
    if not action or (not action.is_enabled and current_user.role != models.UserRole.admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return action


@router.post("", response_model=schemas.ActionDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_action(
    payload: schemas.ActionDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    existing = db.query(models.ActionDefinition).filter(models.ActionDefinition.slug == payload.slug).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")
    action = models.ActionDefinition(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        input_sequence=payload.input_sequence,
        result_regex=payload.result_regex,
        timeout_seconds=payload.timeout_seconds,
        is_enabled=payload.is_enabled,
        created_by_user_id=current_user.id,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.patch("/{action_id}", response_model=schemas.ActionDefinitionOut)
def update_action(
    action_id: int,
    payload: schemas.ActionDefinitionUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    action = db.query(models.ActionDefinition).filter(models.ActionDefinition.id == action_id).first()
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(action, field, value)

    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action(
    action_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    action = db.query(models.ActionDefinition).filter(models.ActionDefinition.id == action_id).first()
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    db.delete(action)
    db.commit()
    return


@router.post("/test-regex", response_model=schemas.RegexTestResponse)
def test_regex(
    payload: schemas.RegexTestRequest,
    _: models.User = Depends(require_admin),
):
    pattern = normalize_pattern(payload.regex)
    matches = re.findall(pattern, payload.sample_text, re.MULTILINE)
    groups: dict[str, str | None] = {}
    compiled = re.compile(pattern, re.MULTILINE)
    m = compiled.search(payload.sample_text)
    if m:
        groups = m.groupdict()
        if not groups and m.groups():
            groups = {"group1": m.group(1)}
    return schemas.RegexTestResponse(matches=[str(m) for m in matches], groups=groups)
