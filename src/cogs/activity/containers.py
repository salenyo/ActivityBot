from __future__ import annotations

from datetime import datetime, timezone

from disnake import Colour
from disnake.ui import Container, Separator, TextDisplay

from .utils import CONTEST_TYPE_LABEL, format_duration, medal, time_left

REJECT_COLOUR = 0xED4245
UTC = timezone.utc


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
        type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
        header = f"## 🏆 Конкурс активности · {type_label}"
        sub = f"Осталось: **{time_left(ends_at)}**"
    else:
        header = "## 📊 Активность за 7 дней"
        sub = "Нет активного конкурса · статистика за последние 7 дней"

    lines = [
        f"{medal(e['rank'])} <@{e['user_id']}> — **{format_duration(e['total_seconds'])}**"
        for e in entries
    ]
    board_text = "\n".join(lines) if lines else "*Нет данных за этот период*"

    user_rank = next((e["rank"] for e in entries if e["user_id"] == user_id), None)
    if user_rank:
        user_line = f"Ваша позиция: {medal(user_rank)} — **{format_duration(user_total)}**"
    elif user_total:
        user_line = f"Ваш результат: **{format_duration(user_total)}** (за пределами топ-10)"
    else:
        user_line = "Вы ещё не участвовали в этом периоде."

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
    type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
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
    accent: int,
) -> Container:
    type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    lines = [
        f"{medal(e['rank'])} <@{e['user_id']}> — **{format_duration(e['total_seconds'])}**"
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
