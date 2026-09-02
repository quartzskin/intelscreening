from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db, Config
from backend.models import ConfigUpdate
from backend.auth import require_admin, require_api_key

router = APIRouter(prefix="/config", tags=["config"])

ALLOWED_KEYS = {
    "iq_threshold_min",
    "iq_threshold_max",
    "questions_per_test",
    "time_per_question",
    "failed_role_id",
    "passed_role_id",
    "test_channel_id",
    "results_channel_id",
    "allow_retest",
    "retest_cooldown_hours",
    "score_expires_days",
    "flag_threshold_seconds",
    "webhook_url",
    "shame_channel_id",
    "shame_role_id",
    "shame_nickname",
    "audit_channel_id",
    "digest_channel_id",
    "digest_day",
    "digest_hour",
}


@router.get("/")
def get_config(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    rows = db.query(Config).all()
    return {row.key: row.value for row in rows}


@router.get("/public")
def get_public_config(
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    """Bot-facing: returns all config values."""
    rows = db.query(Config).all()
    return {row.key: row.value for row in rows}


def _apply_config_update(payload: ConfigUpdate, db: Session) -> dict:
    updated = {}
    for key, value in payload.values.items():
        if key not in ALLOWED_KEYS:
            continue
        row = db.query(Config).filter(Config.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Config(key=key, value=value))
        updated[key] = value
    db.commit()
    return updated


@router.patch("/")
def update_config(
    payload: ConfigUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return {"updated": _apply_config_update(payload, db)}


@router.patch("/bot")
def update_config_bot(
    payload: ConfigUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    """Bot-facing config writes, e.g. role/channel pickers set via slash command."""
    return {"updated": _apply_config_update(payload, db)}
