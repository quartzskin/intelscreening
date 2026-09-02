import csv
import io
import math
import random
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from backend.database import get_db, Question, Answer, TestResult
from backend.models import QuestionCreate, QuestionUpdate, QuestionOut, QuestionPublic, QuestionAnalytics, CSVImportResult
from backend.auth import require_admin, require_api_key

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/", response_model=list[QuestionOut])
def list_questions(
    category: str = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    q = db.query(Question)
    if active_only:
        q = q.filter(Question.active == True)
    if category:
        q = q.filter(Question.category == category)
    return q.order_by(Question.created_at.desc()).all()


@router.post("/", response_model=QuestionOut, status_code=201)
def create_question(
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    question = Question(**payload.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.put("/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    return question


@router.delete("/{question_id}", status_code=204)
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()


@router.get("/for-test", response_model=list[QuestionPublic])
def get_test_questions(
    count: int = 20,
    db: Session = Depends(get_db),
    _=Depends(require_api_key),
):
    questions = db.query(Question).filter(Question.active == True).all()
    if len(questions) < count:
        count = len(questions)
    return random.sample(questions, count)


@router.get("/analytics", response_model=list[QuestionAnalytics])
def get_analytics(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Per-question stats: correct rate, avg time, point-biserial discrimination."""
    rows = (
        db.query(Answer.question_id, Answer.is_correct, Answer.time_taken, TestResult.iq_score)
        .join(TestResult, Answer.result_id == TestResult.id)
        .all()
    )
    if not rows:
        return []

    q_data: dict[int, list] = defaultdict(list)
    for q_id, is_correct, time_taken, iq in rows:
        q_data[q_id].append((is_correct, time_taken, iq))

    questions = db.query(Question).filter(Question.id.in_(list(q_data.keys()))).all()
    q_map = {q.id: q for q in questions}

    result = []
    for q_id, data in q_data.items():
        q = q_map.get(q_id)
        if not q:
            continue
        total = len(data)
        correct = sum(1 for is_c, _, _ in data if is_c)
        avg_time = sum(t for _, t, _ in data) / total if total else 0.0
        disc = _point_biserial(data)
        result.append(QuestionAnalytics(
            question_id=q_id,
            text=q.text,
            category=q.category,
            difficulty=q.difficulty,
            total_attempts=total,
            correct_count=correct,
            correct_rate=round(correct / total * 100, 1) if total else 0.0,
            avg_time=round(avg_time, 1),
            discrimination=disc,
        ))

    return sorted(result, key=lambda x: x.total_attempts, reverse=True)


def _point_biserial(data: list) -> float:
    """Point-biserial correlation between item-correct and total IQ score."""
    n = len(data)
    if n < 5:
        return 0.0
    all_iq = [iq for _, _, iq in data]
    correct_iq = [iq for is_c, _, iq in data if is_c]
    if not correct_iq or len(correct_iq) == n:
        return 0.0
    mean_total = sum(all_iq) / n
    sd = math.sqrt(sum((x - mean_total) ** 2 for x in all_iq) / n)
    if sd < 0.001:
        return 0.0
    mean_correct = sum(correct_iq) / len(correct_iq)
    p = len(correct_iq) / n
    r = (mean_correct - mean_total) / sd * math.sqrt(p * (1 - p))
    return round(max(-1.0, min(1.0, r)), 3)


@router.post("/import", response_model=CSVImportResult)
async def import_csv(
    file: UploadFile = File(...),
    dry_run: bool = False,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """
    Import questions from a CSV file.
    Required columns: text, option_a, option_b, option_c, option_d, correct_answer
    Optional columns: difficulty (1-5), category

    With dry_run=true, validates and reports what would happen without writing.
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    required = {"text", "option_a", "option_b", "option_c", "option_d", "correct_answer"}

    added = 0
    skipped = 0
    errors = []
    seen_texts: set[str] = set()

    for i, row in enumerate(reader, start=2):
        missing = required - set(row.keys())
        if missing:
            errors.append(f"Row {i}: missing columns {missing}")
            skipped += 1
            continue

        answer = row["correct_answer"].strip().upper()
        if answer not in ("A", "B", "C", "D"):
            errors.append(f"Row {i}: correct_answer must be A/B/C/D, got '{answer}'")
            skipped += 1
            continue

        try:
            difficulty = int(row.get("difficulty", "3").strip())
            difficulty = max(1, min(5, difficulty))
        except ValueError:
            difficulty = 3

        text_val = row["text"].strip()
        if not text_val:
            errors.append(f"Row {i}: empty question text")
            skipped += 1
            continue

        if text_val in seen_texts:
            errors.append(f"Row {i}: duplicate of an earlier row in this file")
            skipped += 1
            continue

        exists = db.query(Question).filter(Question.text == text_val).first()
        if exists:
            errors.append(f"Row {i}: already exists in the question bank")
            skipped += 1
            continue

        seen_texts.add(text_val)

        if not dry_run:
            db.add(Question(
                text=text_val,
                option_a=row["option_a"].strip(),
                option_b=row["option_b"].strip(),
                option_c=row["option_c"].strip(),
                option_d=row["option_d"].strip(),
                correct_answer=answer,
                difficulty=difficulty,
                category=row.get("category", "general").strip() or "general",
            ))
        added += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return CSVImportResult(added=added, skipped=skipped, errors=errors[:20])
