import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")

_client: httpx.AsyncClient | None = None


def _headers() -> dict:
    return {"X-API-Key": API_SECRET_KEY, "Content-Type": "application/json"}


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


async def fetch_test_questions(count: int) -> list[dict]:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/questions/for-test",
        headers=_headers(),
        params={"count": count},
    )
    resp.raise_for_status()
    return resp.json()


async def submit_test(discord_user_id: str, discord_username: str, answers: list[dict]) -> dict:
    client = await get_client()
    payload = {
        "discord_user_id": discord_user_id,
        "discord_username": discord_username,
        "answers": answers,
    }
    resp = await client.post(
        f"{BACKEND_URL}/api/results/submit",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


async def get_user_latest_result(discord_user_id: str) -> dict | None:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/user/{discord_user_id}/latest",
        headers=_headers(),
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def get_user_all_results(discord_user_id: str) -> list[dict]:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/user/{discord_user_id}",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def delete_user_results(discord_user_id: str) -> int:
    client = await get_client()
    resp = await client.delete(
        f"{BACKEND_URL}/api/results/user/{discord_user_id}",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json().get("deleted", 0)


async def get_leaderboard(limit: int = 10) -> list[dict]:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/leaderboard",
        headers=_headers(),
        params={"limit": limit},
    )
    resp.raise_for_status()
    return resp.json()


_config_cache: dict = {}
_config_cache_ts: float = 0.0
CONFIG_CACHE_TTL = 60.0  # seconds


async def get_config(force: bool = False) -> dict:
    global _config_cache, _config_cache_ts
    if not force and _config_cache and (time.monotonic() - _config_cache_ts) < CONFIG_CACHE_TTL:
        return _config_cache
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/config/public",
        headers=_headers(),
    )
    resp.raise_for_status()
    _config_cache = resp.json()
    _config_cache_ts = time.monotonic()
    return _config_cache


def invalidate_config_cache():
    global _config_cache_ts
    _config_cache_ts = 0.0


async def update_config(values: dict) -> dict:
    client = await get_client()
    resp = await client.patch(
        f"{BACKEND_URL}/api/config/bot",
        headers=_headers(),
        json={"values": values},
    )
    resp.raise_for_status()
    invalidate_config_cache()
    return resp.json()


async def get_stats() -> dict:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/stats",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def get_worst_leaderboard(limit: int = 10) -> list[dict]:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/leaderboard/worst",
        headers=_headers(),
        params={"limit": limit},
    )
    resp.raise_for_status()
    return resp.json()


async def get_worst_of_week() -> dict | None:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/worst-of-week",
        headers=_headers(),
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def mark_shamed(result_id: int) -> None:
    client = await get_client()
    resp = await client.patch(
        f"{BACKEND_URL}/api/results/{result_id}/shamed",
        headers=_headers(),
    )
    resp.raise_for_status()


async def needs_redemption(discord_user_id: str) -> bool:
    client = await get_client()
    resp = await client.get(
        f"{BACKEND_URL}/api/results/user/{discord_user_id}/needs-redemption",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json().get("needs_redemption", False)


async def mark_redeemed(discord_user_id: str) -> None:
    client = await get_client()
    resp = await client.patch(
        f"{BACKEND_URL}/api/results/user/{discord_user_id}/redeem",
        headers=_headers(),
    )
    resp.raise_for_status()
