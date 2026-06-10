from __future__ import annotations

from datetime import datetime, timezone

from disnake import ButtonStyle, Colour
from disnake.ui import ActionRow, Button, Container, Separator, TextDisplay

from src.common import CONTEST_TYPE_LABEL, format_duration, medal, time_left

UTC = timezone.utc
JOIN_PREFIX = "contest:join:"


def _ends_at(contest: dict) -> datetime:
    dt = datetime.fromisoformat(contest["ends_at"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _prize_line(contest: dict) -> str:
    prize = contest.get("prize")
    return f"🎁 Приз: **{prize}**" if prize else "🎁 Приз разыгрывается среди участников."


def build_contest_announcement(contest: dict, accent: int) -> Container:
    type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    ts = int(_ends_at(contest).timestamp())
    winners = contest.get("winners_count", 1)
    winners_line = (
        "Победитель определится по активности в голосовых каналах."
        if winners <= 1
        else f"Топ-**{winners}** по активности в голосовых каналах получат приз."
    )
    return Container(
        TextDisplay(f"## 🏆 Конкурс активности · {type_label}"),
        Separator(),
        TextDisplay(
            f"{_prize_line(contest)}\n"
            f"{winners_line}\n\n"
            f"Нажмите **«Участие»**, чтобы попасть в список участников.\n"
            f"Завершение: <t:{ts}:F> · <t:{ts}:R>"
        ),
        Separator(divider=False),
        ActionRow(
            Button(
                label="Участие",
                emoji="🎟️",
                style=ButtonStyle.green,
                custom_id=f"{JOIN_PREFIX}{contest['id']}",
            )
        ),
        accent_colour=Colour(accent),
    )


def build_contest_stats(
    contest: dict,
    entries: list[dict],
    participant_count: int,
    user_id: int,
    accent: int,
) -> Container:
    type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    ts = int(_ends_at(contest).timestamp())

    lines = [
        f"{medal(e['rank'])} <@{e['user_id']}> — **{format_duration(e['total_seconds'])}**"
        for e in entries
    ]
    board_text = "\n".join(lines) if lines else "*Пока никто из участников не набрал времени*"

    user_rank = next((e["rank"] for e in entries if e["user_id"] == user_id), None)
    if user_rank:
        user_line = f"Ваша позиция: {medal(user_rank)}"
    else:
        user_line = "-# Нажмите «Участие» под анонсом конкурса, чтобы попасть в зачёт."

    return Container(
        TextDisplay(f"## 🏆 Конкурс активности · {type_label}"),
        Separator(),
        TextDisplay(
            f"{_prize_line(contest)}\n"
            f"Участников: **{participant_count}** · Осталось: **{time_left(_ends_at(contest))}**\n"
            f"-# Завершение: <t:{ts}:R>"
        ),
        Separator(),
        TextDisplay(f"### Текущий зачёт участников\n{board_text}"),
        Separator(divider=False),
        TextDisplay(user_line),
        accent_colour=Colour(accent),
    )


def build_contest_ended(contest: dict, entries: list[dict], accent: int) -> Container:
    type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    winners = contest.get("winners_count", 1)
    winner_entries = entries[:winners]

    if winner_entries:
        if len(winner_entries) == 1:
            head = f"Победитель: <@{winner_entries[0]['user_id']}> 🎉"
        else:
            head = "Победители 🎉"
    else:
        head = "Победителей нет — никто из участников не был активен."

    lines = [
        f"{medal(e['rank'])} <@{e['user_id']}> — **{format_duration(e['total_seconds'])}**"
        for e in winner_entries
    ]
    board_text = "\n".join(lines)

    blocks = [
        TextDisplay(f"## 🏁 Конкурс завершён · {type_label}"),
        Separator(),
        TextDisplay(f"{_prize_line(contest)}\n{head}"),
    ]
    if board_text:
        blocks.append(Separator(divider=False))
        blocks.append(TextDisplay(board_text))
    return Container(*blocks, accent_colour=Colour(accent))
