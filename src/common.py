from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from disnake import Member

from hydra_shared.decorators.permissions import has_role_access

UTC = timezone.utc

MAX_CONTEST_SECONDS = 365 * 86400  # верхняя граница произвольной длительности конкурса

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

CONTEST_KIND_LABEL: dict[str, str] = {
    "leaderboard": "Топ по активности",
    "giveaway": "Розыгрыш",
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


def _unit_seconds(unit: str) -> int | None:
    u = unit.lower()
    # Порядок важен: «мес»/«нед» проверяем до «м» (минут), иначе перехватит минутами.
    if u in {"w", "week", "weeks"} or u.startswith("нед"):
        return 7 * 86400
    if u in {"mo", "mon", "month", "months"} or u.startswith("мес"):
        return 30 * 86400
    if u in {"d", "day", "days"} or u == "д" or u.startswith(("дн", "день", "дня", "дней", "сут", "су")):
        return 86400
    if u in {"h", "hr", "hrs", "hour", "hours"} or u.startswith(("час", "ч")):
        return 3600
    if u in {"m", "min", "mins", "minute", "minutes"} or u.startswith(("мин", "м")):
        return 60
    return None


def parse_duration(text: str) -> timedelta | None:
    """Парсит произвольную длительность вида «2д 3ч», «1 день 12 часов», «90 мин».

    Возвращает None, если ничего не распознано или результат вне диапазона
    (1 минута … MAX_CONTEST_SECONDS).
    """
    total = 0
    matched = False
    for num, unit in re.findall(r"(\d+)\s*([a-zA-Zа-яА-Я]+)", text):
        mult = _unit_seconds(unit)
        if mult is None:
            continue
        total += int(num) * mult
        matched = True
    if not matched or not (60 <= total <= MAX_CONTEST_SECONDS):
        return None
    return timedelta(seconds=total)


def duration_label(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append(f"{d}д")
    if h:
        parts.append(f"{h}ч")
    if m:
        parts.append(f"{m}мин")
    return " ".join(parts) or "0мин"


def parse_contest_dates(contest: dict) -> tuple[datetime, datetime]:
    from_dt = datetime.fromisoformat(contest["started_at"])
    to_dt = datetime.fromisoformat(contest["ends_at"])
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=UTC)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=UTC)
    return from_dt, to_dt


def has_contest_permission(cfg, member: Member) -> bool:
    # Общая ролевая проверка из ядра: админ/владелец ИЛИ роль из конфига.
    return has_role_access(cfg, member, "activity_contest_role_ids")
