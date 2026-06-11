from __future__ import annotations

from datetime import datetime, timezone

from disnake import ButtonStyle, Colour, MediaGalleryItem
from disnake.ui import ActionRow, Button, Container, MediaGallery, Separator, TextDisplay

from src.common import (
    CONTEST_KIND_LABEL,
    CONTEST_TYPE_LABEL,
    format_duration,
    medal,
    time_left,
)

UTC = timezone.utc

JOIN_PREFIX = "contest:join:"
NEW_BUTTON = "contest:new"
MAIN_BUTTON = "contest:main"
KIND_PREFIX = "contest:kind:"
DUR_PREFIX = "contest:dur:"
END_PREFIX = "contest:end:"


def _ends_at(contest: dict) -> datetime:
    dt = datetime.fromisoformat(contest["ends_at"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _kind(contest: dict) -> str:
    return contest.get("kind", "leaderboard")


def _is_giveaway(contest: dict) -> bool:
    return _kind(contest) == "giveaway"


def _prize_line(contest: dict) -> str:
    prize = contest.get("prize")
    return f"🎁 Приз: **{prize}**" if prize else "🎁 Приз разыгрывается среди участников."


def _condition_line(contest: dict) -> str | None:
    secs = contest.get("min_voice_seconds")
    if not _is_giveaway(contest) or not secs:
        return None
    return f"⏱️ Условие: набрать **{format_duration(secs)}** активности в голосовых каналах."


def _title(contest: dict, prefix: str) -> str:
    kind_label = CONTEST_KIND_LABEL.get(_kind(contest), "Конкурс")
    type_label = CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])
    return f"{prefix} {kind_label} · {type_label}"


def _media(image_filename: str | None) -> list:
    if not image_filename:
        return []
    return [MediaGallery(MediaGalleryItem(media=f"attachment://{image_filename}"))]


# ── Публичный анонс ──────────────────────────────────────────────────────────


def build_contest_announcement(contest: dict, accent: int, image_filename: str | None = None) -> Container:
    ts = int(_ends_at(contest).timestamp())
    winners = contest.get("winners_count", 1)

    if _is_giveaway(contest):
        winners_line = (
            "Победитель будет выбран случайно среди выполнивших условие."
            if winners <= 1
            else f"Случайно будут выбраны **{winners}** победителя среди выполнивших условие."
        )
    else:
        winners_line = (
            "Победитель определится по активности в голосовых каналах."
            if winners <= 1
            else f"Топ-**{winners}** по активности в голосовых каналах получат приз."
        )

    body = _prize_line(contest) + "\n"
    cond = _condition_line(contest)
    if cond:
        body += cond + "\n"
    body += (
        f"{winners_line}\n\n"
        f"Нажмите **«Участие»**, чтобы попасть в список участников.\n"
        f"Завершение: <t:{ts}:F> · <t:{ts}:R>"
    )

    return Container(
        TextDisplay(f"## 🏆 {_title(contest, 'Конкурс ·')}"),
        Separator(),
        *_media(image_filename),
        TextDisplay(body),
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


def build_contest_ended(contest: dict, entries: list[dict], accent: int, image_filename: str | None = None) -> Container:
    winners = contest.get("winners_count", 1)
    winner_entries = entries[:winners]
    giveaway = _is_giveaway(contest)

    if winner_entries:
        head = "Победитель 🎉" if len(winner_entries) == 1 else "Победители 🎉"
    else:
        head = "Победителей нет — никто не выполнил условие." if giveaway else \
            "Победителей нет — никто из участников не был активен."

    if giveaway:
        lines = [f"{medal(i + 1)} <@{e['user_id']}>" for i, e in enumerate(winner_entries)]
    else:
        lines = [
            f"{medal(e['rank'])} <@{e['user_id']}> — **{format_duration(e['total_seconds'])}**"
            for e in winner_entries
        ]
    board_text = "\n".join(lines)

    blocks = [
        TextDisplay(f"## 🏁 {_title(contest, 'Конкурс завершён ·')}"),
        Separator(),
        *_media(image_filename),
        TextDisplay(f"{_prize_line(contest)}\n{head}"),
    ]
    if board_text:
        blocks.append(Separator(divider=False))
        blocks.append(TextDisplay(board_text))
    return Container(*blocks, accent_colour=Colour(accent))


# ── Эфемерные вью (конструктор / обзор) ──────────────────────────────────────


def _stat_block(stat: dict) -> str:
    """Одна строка-блок описания активного конкурса для обзора/админ-вью."""
    contest = stat["contest"]
    ts = int(_ends_at(contest).timestamp())
    kind_label = CONTEST_KIND_LABEL.get(_kind(contest), "Конкурс")
    lines = [
        f"### {kind_label} · {CONTEST_TYPE_LABEL.get(contest['contest_type'], contest['contest_type'])}",
        _prize_line(contest),
    ]
    cond = _condition_line(contest)
    if cond:
        lines.append(cond)
    lines.append(
        f"Участников: **{stat['participant_count']}**"
        + (f" · Выполнили условие: **{stat['qualified_count']}**" if stat.get("qualified_count") is not None else "")
        + f" · Осталось: **{time_left(_ends_at(contest))}**"
    )
    lines.append(f"-# Завершение: <t:{ts}:R>")
    if stat.get("personal"):
        lines.append(stat["personal"])
    return "\n".join(lines)


def build_contest_overview(stats: list[dict], accent: int) -> Container:
    """Юзер-вью: список активных конкурсов со статистикой и личным статусом."""
    if not stats:
        return Container(
            TextDisplay("## 🏆 Конкурсы"),
            Separator(),
            TextDisplay("Сейчас нет активных конкурсов."),
            accent_colour=Colour(accent),
        )
    blocks = [TextDisplay("## 🏆 Активные конкурсы"), Separator()]
    for i, stat in enumerate(stats):
        if i:
            blocks.append(Separator())
        blocks.append(TextDisplay(_stat_block(stat)))
    return Container(*blocks, accent_colour=Colour(accent))


def build_contest_main(stats: list[dict], accent: int) -> Container:
    """Админ-вью: обзор активных конкурсов + конструктор и кнопки завершения."""
    blocks = [
        TextDisplay("## 🏆 Управление конкурсами"),
        Separator(),
    ]
    if stats:
        for i, stat in enumerate(stats):
            if i:
                blocks.append(Separator())
            blocks.append(TextDisplay(_stat_block(stat)))
            blocks.append(
                ActionRow(
                    Button(
                        label="Завершить",
                        emoji="🏁",
                        style=ButtonStyle.danger,
                        custom_id=f"{END_PREFIX}{stat['contest']['id']}",
                    )
                )
            )
        blocks.append(Separator())
    else:
        blocks.append(TextDisplay("Сейчас нет активных конкурсов."))
        blocks.append(Separator(divider=False))
    blocks.append(
        ActionRow(
            Button(
                label="Создать конкурс",
                emoji="➕",
                style=ButtonStyle.success,
                custom_id=NEW_BUTTON,
            )
        )
    )
    return Container(*blocks, accent_colour=Colour(accent))


def build_kind_picker(accent: int) -> Container:
    return Container(
        TextDisplay("## ➕ Новый конкурс\nВыберите тип конкурса."),
        Separator(),
        TextDisplay(
            f"**{CONTEST_KIND_LABEL['giveaway']}** — участники жмут «Участие», набирают минимальную "
            f"активность в голосовых, победители выбираются случайно среди выполнивших условие.\n"
            f"**{CONTEST_KIND_LABEL['leaderboard']}** — побеждают самые активные в голосовых каналах (топ)."
        ),
        Separator(divider=False),
        ActionRow(
            Button(
                label=CONTEST_KIND_LABEL["giveaway"],
                emoji="🎲",
                style=ButtonStyle.primary,
                custom_id=f"{KIND_PREFIX}giveaway",
            ),
            Button(
                label=CONTEST_KIND_LABEL["leaderboard"],
                emoji="📊",
                style=ButtonStyle.primary,
                custom_id=f"{KIND_PREFIX}leaderboard",
            ),
        ),
        ActionRow(
            Button(label="Назад", style=ButtonStyle.secondary, custom_id=MAIN_BUTTON),
        ),
        accent_colour=Colour(accent),
    )


def build_duration_picker(kind: str, accent: int) -> Container:
    kind_label = CONTEST_KIND_LABEL.get(kind, kind)
    return Container(
        TextDisplay(f"## ➕ Новый конкурс · {kind_label}\nВыберите длительность."),
        Separator(divider=False),
        ActionRow(
            Button(label="День", style=ButtonStyle.primary, custom_id=f"{DUR_PREFIX}{kind}:day"),
            Button(label="Неделя", style=ButtonStyle.primary, custom_id=f"{DUR_PREFIX}{kind}:week"),
            Button(label="Месяц", style=ButtonStyle.primary, custom_id=f"{DUR_PREFIX}{kind}:month"),
        ),
        ActionRow(
            Button(label="Назад", style=ButtonStyle.secondary, custom_id=NEW_BUTTON),
        ),
        accent_colour=Colour(accent),
    )
