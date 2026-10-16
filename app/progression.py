from datetime import datetime, timezone

from app.models import BotSetting


async def _get(session, key: str, default: str = "0") -> str:
    row = await session.get(BotSetting, key)
    return row.value if row else default


async def _set(session, key: str, value: str) -> None:
    row = await session.get(BotSetting, key)
    if row is None:
        session.add(BotSetting(key=key, value=value))
    else:
        row.value = value


async def record_match_progress(session, user_id: int, won: bool) -> None:
    """Update daily missions and the current monthly season without schema changes."""
    day = datetime.now(timezone.utc).date().isoformat()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    for suffix in (f"daily:{day}:games", f"season:{month}:games"):
        key = f"u:{user_id}:{suffix}"
        await _set(session, key, str(int(await _get(session, key)) + 1))
    if won:
        for suffix in (f"daily:{day}:wins", f"season:{month}:wins"):
            key = f"u:{user_id}:{suffix}"
            await _set(session, key, str(int(await _get(session, key)) + 1))
