import csv
import io
import math
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session
from backend.database import get_db, Question, TestResult, Answer, Config
from backend.models import TestSubmission, TestResultOut, StatsOut
from backend.auth import require_admin, require_api_key, verify_jwt_token

router = APIRouter(prefix="/results", tags=["results"])

GUESSING_PARAM = 0.25
THETA_BOUNDS = (-4.0, 4.0)
LOGISTIC_SD = math.pi / math.sqrt(3)
IQ_MEAN = 100
IQ_SD = 15
MAX_ITERATIONS = 50
CONVERGENCE_TOL = 1e-5


def difficulty_to_logit(difficulty: int) -> float:
    return -2.0 + (difficulty - 1) * 1.0


def p_correct(theta: float, b: float, c: float = GUESSING_PARAM) -> float:
    return c + (1.0 - c) / (1.0 + math.exp(-(theta - b)))


def estimate_theta(responses: list[tuple[bool, float]]) -> float:
    if not responses:
        return 0.0
    n_correct = sum(1 for correct, _ in responses if correct)
    if n_correct == 0:
        return THETA_BOUNDS[0]
    if n_correct == len(responses):
        return THETA_BOUNDS[1]

    theta = 0.0
    for _ in range(MAX_ITERATIONS):
        first_deriv = 0.0
        info = 0.0
        for is_correct, b in responses:
            c = GUESSING_PARAM
            p = p_correct(theta, b, c)
            p_star = (p - c) / (1.0 - c)
            q_star = 1.0 - p_star
            x = 1 if is_correct else 0
            numerator = (x - p) * (p - c)
            denominator = p * (1.0 - c)
            first_deriv += (numerator / denominator) * q_star
            info += ((p - c) ** 2 * p_star * q_star) / (p ** 2 * (1.0 - c) ** 2)

        if info < 1e-10:
            break
        delta = first_deriv / info
        theta += delta
        theta = max(THETA_BOUNDS[0], min(THETA_BOUNDS[1], theta))
        if abs(delta) < CONVERGENCE_TOL:
            break

    return theta


def theta_to_iq(theta: float) -> int:
    iq = IQ_MEAN + (IQ_SD / LOGISTIC_SD) * theta
    return int(round(max(40, min(160, iq))))


def wechsler_classification(iq: int) -> str:
    if iq >= 130: return "Very Superior"
    if iq >= 120: return "Superior"
    if iq >= 110: return "High Average"
    if iq >= 90:  return "Average"
    if iq >= 80:  return "Low Average"
    if iq >= 70:  return "Borderline"
    return "Extremely Low"


def score_test(answers: list, questions_map: dict, flag_threshold: float) -> tuple[float, int, int, str, bool]:
    """Returns (theta, iq_score, correct_count, classification, flagged)."""
    responses = []
    correct_count = 0
    times = []

    for answer in answers:
        q = questions_map.get(answer.question_id)
        if not q:
            continue
        b = difficulty_to_logit(q.difficulty)
        is_correct = answer.answer.upper() == q.correct_answer
        if is_correct:
            correct_count += 1
        responses.append((is_correct, b))
        times.append(answer.time_taken)

    if not responses:
        return 0.0, IQ_MEAN, 0, "Average", False

    theta = estimate_theta(responses)
    iq = theta_to_iq(theta)
    classification = wechsler_classification(iq)

    avg_time = sum(times) / len(times) if times else flag_threshold + 1
    flagged = avg_time < flag_threshold

    return round(theta, 4), iq, correct_count, classification, flagged


def compute_percentile(db: Session, iq_score: int, exclude_id: int = None) -> int:
    q = db.query(TestResult).filter(TestResult.iq_score < iq_score)
    if exclude_id:
        q = q.filter(TestResult.id != exclude_id)
    below = q.count()
    total_q = db.query(TestResult)
    if exclude_id:
        total_q = total_q.filter(TestResult.id != exclude_id)
    total = total_q.count()
    if total == 0:
        return 99
    return min(99, int(round(below / total * 100)))


def _fire_webhook(url: str, username: str, iq: int, passed: bool, flagged: bool) -> None:
    """Fires a Discord-format webhook embed. Runs in a background task."""
    if not url:
        return
    try:
        color = 0x3ddc84 if passed else 0xff6464
        if flagged:
            color = 0xf59e0b
        fields = [
            {"name": "Member", "value": username, "inline": True},
            {"name": "Score", "value": str(iq), "inline": True},
            {"name": "Verdict", "value": "PASSED" if passed else "FAILED", "inline": True},
        ]
        if flagged:
            fields.append({"name": "Flagged", "value": "Unusually fast responses detected", "inline": False})
        payload = {"embeds": [{"title": "Screening Result", "color": color, "fields": fields}]}
        with httpx.Client(timeout=5.0) as client:
            client.post(url, json=payload)
    except Exception:
        pass


@router.post("/submit", response_model=TestResultOut)
def submit_test(
    payload: TestSubmission,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    question_ids = [a.question_id for a in payload.answers]
    questions = db.query(Question).filter(Question.id.in_(question_ids)).all()
    questions_map = {q.id: q for q in questions}

    cfg = {row.key: row.value for row in db.query(Config).all()}
    threshold_min = int(cfg.get("iq_threshold_min", "85"))
    flag_threshold = float(cfg.get("flag_threshold_seconds", "4"))
    webhook_url = cfg.get("webhook_url", "").strip()

    theta, iq_score, correct_count, classification, flagged = score_test(
        payload.answers, questions_map, flag_threshold
    )
    passed = iq_score >= threshold_min

    result = TestResult(
        discord_user_id=payload.discord_user_id,
        discord_username=payload.discord_username,
        raw_score=theta,
        iq_score=iq_score,
        answers_correct=correct_count,
        total_questions=len(payload.answers),
        passed=passed,
        flagged=flagged,
        percentile=0,
    )
    db.add(result)
    db.flush()

    pct = compute_percentile(db, iq_score, exclude_id=result.id)
    result.percentile = pct
    db.commit()
    db.refresh(result)

    answer_records = []
    for a in payload.answers:
        q = questions_map.get(a.question_id)
        if q:
            answer_records.append(Answer(
                result_id=result.id,
                question_id=a.question_id,
                answer=a.answer.upper(),
                is_correct=a.answer.upper() == q.correct_answer,
                time_taken=a.time_taken,
            ))
    if answer_records:
        db.bulk_save_objects(answer_records)
        db.commit()

    if (not passed or flagged) and webhook_url:
        background_tasks.add_task(_fire_webhook, webhook_url, payload.discord_username, iq_score, passed, flagged)

    return result


def _compute_stats(db: Session) -> StatsOut:
    total = db.query(TestResult).count()
    passed = db.query(TestResult).filter(TestResult.passed == True).count()
    flagged = db.query(TestResult).filter(TestResult.flagged == True).count()
    avg_iq_row = db.query(func.avg(TestResult.iq_score)).scalar()
    avg_iq = round(float(avg_iq_row), 1) if avg_iq_row else 0.0
    return StatsOut(
        total=total,
        passed=passed,
        failed=total - passed,
        pass_rate=round(passed / total * 100, 1) if total else 0.0,
        avg_iq=avg_iq,
        flagged=flagged,
    )


@router.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db), _=Depends(require_api_key)):
    return _compute_stats(db)


@router.get("/stats/admin", response_model=StatsOut)
def get_stats_admin(db: Session = Depends(get_db), _=Depends(require_admin)):
    return _compute_stats(db)


@router.get("/leaderboard", response_model=list[TestResultOut])
def get_leaderboard(
    limit: int = 10,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    """Top N unique users by highest passing IQ score."""
    subq = (
        db.query(
            TestResult.discord_user_id,
            sqlfunc.max(TestResult.iq_score).label("max_iq"),
        )
        .filter(TestResult.passed == True)
        .group_by(TestResult.discord_user_id)
        .subquery()
    )
    return (
        db.query(TestResult)
        .join(subq, (TestResult.discord_user_id == subq.c.discord_user_id) &
              (TestResult.iq_score == subq.c.max_iq))
        .order_by(TestResult.iq_score.desc())
        .limit(limit)
        .all()
    )


@router.get("/leaderboard/worst", response_model=list[TestResultOut])
def get_worst_leaderboard(
    limit: int = 10,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    """Bottom N unique users by lowest failing IQ score — the Hall of Shame."""
    subq = (
        db.query(
            TestResult.discord_user_id,
            sqlfunc.min(TestResult.iq_score).label("min_iq"),
        )
        .filter(TestResult.passed == False)
        .group_by(TestResult.discord_user_id)
        .subquery()
    )
    return (
        db.query(TestResult)
        .join(subq, (TestResult.discord_user_id == subq.c.discord_user_id) &
              (TestResult.iq_score == subq.c.min_iq))
        .order_by(TestResult.iq_score.asc())
        .limit(limit)
        .all()
    )


@router.get("/worst-of-week", response_model=TestResultOut)
def get_worst_of_week(
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = (
        db.query(TestResult)
        .filter(TestResult.passed == False, TestResult.completed_at >= cutoff)
        .order_by(TestResult.iq_score.asc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="No failing results in the past week")
    return result


@router.patch("/{result_id}/shamed")
def mark_shamed(
    result_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    result = db.query(TestResult).filter(TestResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    result.shamed = True
    db.commit()
    return {"ok": True}


@router.get("/user/{discord_user_id}/needs-redemption")
def needs_redemption(
    discord_user_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    exists = (
        db.query(TestResult)
        .filter(
            TestResult.discord_user_id == discord_user_id,
            TestResult.shamed == True,
            TestResult.redeemed == False,
        )
        .first()
    )
    return {"needs_redemption": exists is not None}


@router.patch("/user/{discord_user_id}/redeem")
def mark_redeemed(
    discord_user_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    updated = (
        db.query(TestResult)
        .filter(TestResult.discord_user_id == discord_user_id, TestResult.shamed == True)
        .update({"redeemed": True}, synchronize_session=False)
    )
    db.commit()
    return {"updated": updated}


@router.delete("/user/{discord_user_id}")
def delete_user_results(
    discord_user_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    """Reset a member's test history — clears all results and answer records."""
    result_ids = [
        r.id for r in db.query(TestResult.id)
        .filter(TestResult.discord_user_id == discord_user_id).all()
    ]
    if result_ids:
        db.query(Answer).filter(Answer.result_id.in_(result_ids)).delete(synchronize_session=False)
    deleted = db.query(TestResult).filter(TestResult.discord_user_id == discord_user_id).delete()
    db.commit()
    return {"deleted": deleted}


@router.get("/flagged", response_model=list[TestResultOut])
def list_flagged(
    reviewed: bool = Query(False, description="Include already-reviewed results"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    q = db.query(TestResult).filter(TestResult.flagged == True)
    if not reviewed:
        q = q.filter(TestResult.reviewed == False)
    return q.order_by(TestResult.completed_at.desc()).all()


@router.patch("/{result_id}/review")
def mark_reviewed(
    result_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    result = db.query(TestResult).filter(TestResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    result.reviewed = True
    db.commit()
    return {"ok": True}


@router.get("/member", response_model=list[TestResultOut])
def search_member(
    q: str = Query(..., description="Discord user ID or username fragment"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    results = (
        db.query(TestResult)
        .filter(
            (TestResult.discord_user_id == q) |
            (TestResult.discord_username.ilike(f"%{q}%"))
        )
        .order_by(TestResult.completed_at.desc())
        .limit(50)
        .all()
    )
    return results


@router.get("/", response_model=list[TestResultOut])
def list_results(
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return (
        db.query(TestResult)
        .order_by(TestResult.completed_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/user/{discord_user_id}", response_model=list[TestResultOut])
def get_user_results(
    discord_user_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    return (
        db.query(TestResult)
        .filter(TestResult.discord_user_id == discord_user_id)
        .order_by(TestResult.completed_at.desc())
        .all()
    )


@router.get("/export")
def export_results_csv(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    verify_jwt_token(token)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "discord_user_id", "discord_username", "iq_score", "raw_score",
        "answers_correct", "total_questions", "passed", "flagged", "percentile",
        "completed_at",
    ])
    for r in db.query(TestResult).order_by(TestResult.completed_at.desc()).all():
        writer.writerow([
            r.id, r.discord_user_id, r.discord_username, r.iq_score, r.raw_score,
            r.answers_correct, r.total_questions, r.passed, r.flagged, r.percentile,
            r.completed_at.isoformat(),
        ])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=screening_results.csv"},
    )


@router.get("/user/{discord_user_id}/latest", response_model=TestResultOut)
def get_latest_result(
    discord_user_id: str,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    result = (
        db.query(TestResult)
        .filter(TestResult.discord_user_id == discord_user_id)
        .order_by(TestResult.completed_at.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="No test results found for this user")
    return result
