from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

SQLALCHEMY_DATABASE_URL = "sqlite:///./screening.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    option_a = Column(String(512), nullable=False)
    option_b = Column(String(512), nullable=False)
    option_c = Column(String(512), nullable=False)
    option_d = Column(String(512), nullable=False)
    correct_answer = Column(String(1), nullable=False)
    difficulty = Column(Integer, default=3)
    category = Column(String(100), default="general")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True)
    discord_user_id = Column(String(32), nullable=False, index=True)
    discord_username = Column(String(100), nullable=False)
    raw_score = Column(Float, nullable=False)
    iq_score = Column(Integer, nullable=False)
    answers_correct = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    flagged = Column(Boolean, default=False)
    reviewed = Column(Boolean, default=False)
    percentile = Column(Integer, default=0)
    shamed = Column(Boolean, default=False)
    redeemed = Column(Boolean, default=False)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Answer(Base):
    """Stores individual question-level responses for per-question analytics."""
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, nullable=False, index=True)
    question_id = Column(Integer, nullable=False, index=True)
    answer = Column(String(1), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_taken = Column(Float, nullable=False, default=0.0)


class Config(Base):
    __tablename__ = "config"

    key = Column(String(100), primary_key=True)
    value = Column(String(512), nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DEFAULT_CONFIG = {
    "iq_threshold_min": "85",
    "iq_threshold_max": "160",
    "questions_per_test": "20",
    "time_per_question": "45",
    "failed_role_id": "",
    "passed_role_id": "",
    "test_channel_id": "",
    "results_channel_id": "",
    "allow_retest": "false",
    "retest_cooldown_hours": "24",
    "score_expires_days": "0",
    "flag_threshold_seconds": "4",
    "webhook_url": "",
    "shame_channel_id": "",
    "shame_role_id": "",
    "shame_nickname": "false",
    "audit_channel_id": "",
    "digest_channel_id": "",
    "digest_day": "sunday",
    "digest_hour": "12",
}


def init_db():
    Base.metadata.create_all(bind=engine)

    _safe_add_column("test_results", "flagged", "BOOLEAN DEFAULT 0")
    _safe_add_column("test_results", "percentile", "INTEGER DEFAULT 0")
    _safe_add_column("test_results", "reviewed", "BOOLEAN DEFAULT 0")
    _safe_add_column("test_results", "shamed", "BOOLEAN DEFAULT 0")
    _safe_add_column("test_results", "redeemed", "BOOLEAN DEFAULT 0")

    db = SessionLocal()
    try:
        for key, value in DEFAULT_CONFIG.items():
            existing = db.query(Config).filter(Config.key == key).first()
            if not existing:
                db.add(Config(key=key, value=value))
        db.commit()
    finally:
        db.close()


def _safe_add_column(table: str, column: str, definition: str):
    try:
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            conn.commit()
    except Exception:
        pass  # Column already exists
