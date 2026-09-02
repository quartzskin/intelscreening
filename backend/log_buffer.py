import asyncio
import threading
from collections import deque

_lock = threading.Lock()
_recent: deque = deque(maxlen=500)
_subscribers: list[asyncio.Queue] = []
_loop: asyncio.AbstractEventLoop | None = None


def init(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def push(line: str) -> None:
    with _lock:
        _recent.append(line)
        if _loop and not _loop.is_closed():
            for q in _subscribers:
                try:
                    _loop.call_soon_threadsafe(q.put_nowait, line)
                except RuntimeError:
                    pass


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def get_recent() -> list[str]:
    with _lock:
        return list(_recent)
