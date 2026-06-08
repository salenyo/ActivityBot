from __future__ import annotations

from datetime import datetime, timedelta, timezone

from disnake import Member

UTC = timezone.utc

CONTEST_DURATIONS: dict[str, timedelta] = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}

CONTEST_TYPE_LABEL: dict[str, str] = {
    "day": "День",
    "week": "Неделя",
    "month": "Месяц",
}

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def medal(rank: int) -> str:
    return _MEDALS.get(rank, f"**{rank}.**")


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0мин"
    h, r = divmod(seconds, 3600)
    m = r // 60
    if h >= 24:
        d = h // 24
        h = h % 24
        return f"{d}д {h}ч {m}мин" if h else f"{d}д {m}мин"
    if h:
        return f"{h}ч {m}мин"
    return f"{m}мин"


def time_left(ends_at: datetime) -> str:
    now = datetime.now(UTC)
    delta = ends_at - now
    if delta.total_seconds() <= 0:
        return "завершён"
    total = int(delta.total_seconds())
    h, r = divmod(total, 3600)
    m = r // 60
    if h >= 24:
        d = h // 24
        return f"{d}д {h % 24}ч"
    if h:
        return f"{h}ч {m}мин"
    return f"{m}мин"


def parse_contest_dates(contest: dict) -> tuple[datetime, datetime]:
    from_dt = datetime.fromisoformat(contest["started_at"])
    to_dt = datetime.fromisoformat(contest["ends_at"])
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=UTC)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=UTC)
    return from_dt, to_dt


def has_contest_permission(cfg, member: Member) -> bool:
    roles = set(cfg.activity_contest_role_ids or [])
    return any(r.id in roles for r in member.roles) or member.id in (cfg.owner_ids or [])
