import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

from backend.database import init_db
from backend.auth import authenticate_admin, create_access_token, require_admin
from backend.models import LoginRequest, TokenResponse
from backend.routers import questions, results, config
from backend.routers import logs as logs_router
from backend import log_buffer

load_dotenv()

_SUPPRESS_PATHS = ("/api/health", "/api/logs/stream", "/favicon.ico")

_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")


class _AccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not any(p in record.getMessage() for p in _SUPPRESS_PATHS)


class _LogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_buffer.push(_fmt.format(record))
        except Exception:
            pass


_log_handler = _LogHandler()
_log_handler.setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    loop = asyncio.get_running_loop()
    log_buffer.init(loop)
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addFilter(_AccessFilter())
    access_logger.addHandler(_log_handler)
    for name in ("uvicorn.error", "fastapi", "sqlalchemy"):
        logging.getLogger(name).addHandler(_log_handler)
    log_buffer.push(_fmt.format(logging.makeLogRecord({
        "levelname": "INFO", "name": "startup",
        "msg": "Intelligence Screening backend ready",
    })))
    yield


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Intelligence Screening API",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(questions.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(logs_router.router, prefix="/api")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health", include_in_schema=False)
def health():
    return {"ok": True}


@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest):
    if not authenticate_admin(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": payload.username})
    return TokenResponse(access_token=token)


@app.get("/api/auth/verify")
def verify_token(_=Depends(require_admin)):
    return {"ok": True}


@app.get("/", include_in_schema=False)
@app.get("/{path:path}", include_in_schema=False)
def serve_ui(path: str = ""):
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
