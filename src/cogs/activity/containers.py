from __future__ import annotations

from datetime import datetime, timezone

from disnake import ButtonStyle, Colour
from disnake.ui import ActionRow, Button, Container, Separator, TextDisplay

REJECT_COLOUR = 0xED4245
UTC = timezone.utc

_TYPE_LABEL = {"day": "День", "week": "Неделя", "month": "Месяц"}
_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _medal(rank: int) -> str:
    return _MEDALS.get(rank, f"**{rank}.**")


def _fmt(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m = r // 60
    if h:
        return f"{h}ч {m}мин"
    return f"{m}мин"


def _time_left(ends_at: datetime) -> str:
    delta = ends_at - datetime.now(UTC)
    if delta.total_seconds() <= 0:
        return "завершён"
    total = int(delta.total_seconds())
    h, r = divmod(total, 3600)
    m = r // 60
    if h >= 24:
        return f"{h // 24}д {h % 24}ч"
    if h:
        return f"{h}ч {m}мин"
    return f"{m}мин"


def build_stats_container(
    entries: list[dict],
    contest: dict | None,
    user_id: int,
    user_total: int,
    accent: int,
) -> Container:
    if contest:
        ends_at = datetime.fromisoformat(contest["ends_at"])
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=UTC)
        type_label = _TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
        header = f"## 🏆 Конкурс активности · {type_label}"
        sub = f"Осталось: **{_time_left(ends_at)}**"
    else:
        header = "## 📊 Активность за 7 дней"
        sub = "Нет активного конкурса"

    lines = [f"{_medal(e['rank'])} <@{e['user_id']}> — **{_fmt(e['total_seconds'])}**" for e in entries]
    board_text = "\n".join(lines) if lines else "*Нет данных*"

    user_rank = next((e["rank"] for e in entries if e["user_id"] == user_id), None)
    user_line = (
        f"Ваша позиция: {_medal(user_rank)} — **{_fmt(user_total)}**"
        if user_rank
        else f"Ваш результат: **{_fmt(user_total)}**" if user_total else "Вы ещё не участвовали в этом периоде."
    )

    return Container(
        TextDisplay(header),
        Separator(),
        TextDisplay(sub),
        Separator(divider=False),
        TextDisplay(board_text),
        Separator(),
        TextDisplay(user_line),
        accent_colour=Colour(accent),
    )


def build_contest_started_container(contest: dict, accent: int) -> Container:
    type_label = _TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    ends_at = datetime.fromisoformat(contest["ends_at"])
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=UTC)
    ts = int(ends_at.timestamp())
    return Container(
        TextDisplay(f"## 🏆 Конкурс запущен · {type_label}"),
        Separator(),
        TextDisplay(
            f"Отслеживается время в голосовых каналах.\n"
            f"Конкурс завершится: <t:{ts}:F> · <t:{ts}:R>"
        ),
        accent_colour=Colour(accent),
    )


def build_contest_ended_container(
    contest: dict,
    entries: list[dict],
    guild,
    accent: int,
) -> Container:
    type_label = _TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    lines = [
        f"{_medal(e['rank'])} <@{e['user_id']}> — **{_fmt(e['total_seconds'])}**"
        for e in entries
    ]
    board_text = "\n".join(lines) if lines else "*Нет участников*"
    winner_text = f"Победитель: <@{entries[0]['user_id']}> 🎉" if entries else "Победителя нет."

    return Container(
        TextDisplay(f"## 🏁 Конкурс завершён · {type_label}"),
        Separator(),
        TextDisplay(winner_text),
        Separator(divider=False),
        TextDisplay(board_text),
        accent_colour=Colour(accent),
    )


def build_error_container(text: str) -> Container:
    return Container(
        TextDisplay("## ❌ Ошибка"),
        Separator(),
        TextDisplay(text),
        accent_colour=Colour(REJECT_COLOUR),
    )
