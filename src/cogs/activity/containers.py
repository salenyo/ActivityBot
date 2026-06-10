from __future__ import annotations

from disnake import Colour, SelectOption
from disnake.ui import ActionRow, Container, Separator, StringSelect, TextDisplay

from src.common import format_duration, medal

PERIOD_CUSTOM_ID = "activity_stats:period"

PERIOD_LABEL: dict[str, str] = {
    "day": "День",
    "week": "Неделя",
    "month": "Месяц",
    "all": "Всё время",
}


def _period_select(period: str, *, disabled: bool = False) -> ActionRow:
    return ActionRow(
        StringSelect(
            custom_id=PERIOD_CUSTOM_ID,
            placeholder=PERIOD_LABEL.get(period, "Неделя"),
            disabled=disabled,
            options=[
                SelectOption(label=label, value=value, default=(value == period))
                for value, label in PERIOD_LABEL.items()
            ],
        )
    )


def build_loading_container(period: str, accent: int) -> Container:
    label = PERIOD_LABEL.get(period, "Неделя")
    return Container(
        _period_select(period, disabled=True),
        TextDisplay(f"## 📊 Активность · {label}\n-# Загружаем данные..."),
        accent_colour=Colour(accent),
    )


def build_stats_container(
    entries: list[dict],
    period: str,
    user_id: int,
    user_total: int,
    accent: int,
) -> Container:
    label = PERIOD_LABEL.get(period, "Неделя")

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
        user_line = "Вы ещё не были активны в этом периоде."

    return Container(
        _period_select(period),
        TextDisplay(f"## 📊 Активность · {label}"),
        Separator(),
        TextDisplay(board_text),
        Separator(),
        TextDisplay(user_line),
        accent_colour=Colour(accent),
    )
