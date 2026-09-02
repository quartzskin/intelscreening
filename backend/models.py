from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class QuestionCreate(BaseModel):
    text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str
    difficulty: int = 3
    category: str = "general"

    @field_validator("correct_answer")
    @classmethod
    def validate_answer(cls, v):
        if v.upper() not in ("A", "B", "C", "D"):
            raise ValueError("correct_answer must be A, B, C, or D")
        return v.upper()

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v):
        if v < 1 or v > 5:
            raise ValueError("difficulty must be 1-5")
        return v


class QuestionUpdate(BaseModel):
    text: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    correct_answer: Optional[str] = None
    difficulty: Optional[int] = None
    category: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("correct_answer")
    @classmethod
    def validate_answer(cls, v):
        if v is not None and v.upper() not in ("A", "B", "C", "D"):
            raise ValueError("correct_answer must be A, B, C, or D")
        return v.upper() if v else v

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError("difficulty must be 1-5")
        return v


class QuestionOut(BaseModel):
    id: int
    text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str
    difficulty: int
    category: str
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionPublic(BaseModel):
    id: int
    text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    difficulty: int
    category: str

    class Config:
        from_attributes = True


class QuestionAnalytics(BaseModel):
    question_id: int
    text: str
    category: str
    difficulty: int
    total_attempts: int
    correct_count: int
    correct_rate: float
    avg_time: float
    discrimination: float


class SubmitAnswer(BaseModel):
    question_id: int
    answer: str
    time_taken: float


class TestSubmission(BaseModel):
    discord_user_id: str
    discord_username: str
    answers: list[SubmitAnswer]


class TestResultOut(BaseModel):
    id: int
    discord_user_id: str
    discord_username: str
    raw_score: float
    iq_score: int
    answers_correct: int
    total_questions: int
    passed: bool
    flagged: bool = False
    reviewed: bool = False
    percentile: int = 0
    shamed: bool = False
    redeemed: bool = False
    completed_at: datetime

    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_iq: float
    flagged: int


class ConfigUpdate(BaseModel):
    values: dict[str, str]


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CSVImportResult(BaseModel):
    added: int
    skipped: int
    errors: list[str]
