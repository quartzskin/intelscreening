import asyncio
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from backend import log_buffer
from backend.auth import JWT_SECRET, JWT_ALGORITHM

router = APIRouter(prefix="/logs", tags=["logs"])


def _verify_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return bool(payload.get("sub"))
    except JWTError:
        return False


@router.get("/recent")
def get_recent_logs(token: str = Query(...)):
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return log_buffer.get_recent()


@router.get("/stream")
async def stream_logs(token: str = Query(...)):
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")

    q = log_buffer.subscribe()

    async def event_generator():
        try:
            for line in log_buffer.get_recent():
                yield f"data: {line}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {line}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            log_buffer.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
