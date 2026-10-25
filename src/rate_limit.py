import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request

load_dotenv()

LOCAL_FILE = Path(__file__).resolve().parent.parent / "data" / "blocked_ips.json"
_redis_client = None


# ---------- helpers ----------

def _on_vercel() -> bool:
    return bool(os.getenv("VERCEL"))


def _disabled() -> bool:
    return os.getenv("DISABLE_RATE_LIMIT") == "1" and not _on_vercel()


def _redis():
    """Returns a Redis client if Upstash env vars exist, else None."""
    global _redis_client
    url = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_REST_API_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("KV_REST_API_TOKEN")
    if not url or not token:
        if _on_vercel():
            raise RuntimeError(
                "Upstash Redis env vars are missing on Vercel. "
                "Connect an Upstash Redis database to this project."
            )
        return None
    if _redis_client is None:
        from upstash_redis import Redis
        _redis_client = Redis(url=url, token=token)
    return _redis_client


def _key(ip: str) -> str:
    return f"blocked_ip:{ip}"


def _local_load() -> set:
    try:
        data = json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def _local_save(ips: set) -> None:
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(sorted(ips)), encoding="utf-8")


# ---------- public functions ----------

def normalize_ip(request: Request) -> str:
    # Vercel sets these headers itself, so users cannot fake them there
    for header in ("x-vercel-forwarded-for", "x-real-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def is_ip_blocked(request: Request) -> bool:
    if _disabled():
        return False
    ip = normalize_ip(request)
    r = _redis()
    if r:
        return bool(r.exists(_key(ip)))
    return ip in _local_load()


def block_ip(request: Request) -> bool:
    """Blocks the IP. Returns True if newly blocked, False if already blocked."""
    if _disabled():
        return True
    ip = normalize_ip(request)
    r = _redis()
    if r:
        # NX = only set if it doesn't exist yet (atomic, no race)
        return bool(r.set(_key(ip), "1", nx=True))
    blocked = _local_load()
    if ip in blocked:
        return False
    blocked.add(ip)
    _local_save(blocked)
    return True


def unblock_ip(request: Request) -> None:
    """Gives the try back (used when generation fails)."""
    if _disabled():
        return
    ip = normalize_ip(request)
    r = _redis()
    if r:
        r.delete(_key(ip))
        return
    blocked = _local_load()
    blocked.discard(ip)
    _local_save(blocked)