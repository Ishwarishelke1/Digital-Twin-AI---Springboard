"""
core/rate_limit.py — Rate limiting for brute-force-sensitive endpoints (auth).

Uses an in-memory, per-process counter (slowapi's default storage) — this is a known
limitation: limits reset on process restart and aren't shared across multiple uvicorn
workers. Acceptable for now since the app runs as a single process; if that changes,
swap the storage backend for Redis (slowapi supports this via `storage_uri=`) without
touching any call site — every usage goes through this shared `limiter` instance.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
