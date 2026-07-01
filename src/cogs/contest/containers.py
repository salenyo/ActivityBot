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
SPONSOR_PREFIX = "contest:sponsor:"




def _ends_at(contest: dict) -> datetime:
    dt = datetime.fromisoformat(contest["ends_at"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _kind(contest: dict) -> str:
    return contest.get("kind", "leaderboard")


def _is_giveaway(contest: dict) -> bool:
    return _kind(contest) == "giveaway"


def _kind_label(contest: dict) -> str:
    return CONTEST_KIND_LABEL.get(_kind(contest), "Конкурс")


def _type_label(contest: dict) -> str:
    return CONTEST_TYPE_LABEL.get(contest["contest_type"], contest["contest_type"])


def _media(image_media: str | None) -> list:
    """image_media — готовая строка media (URL или attachment://имя) из hydra_shared.ui.media_ref."""
    if not image_media:
        return []
    return [MediaGallery(MediaGalleryItem(media=image_media))]


def _desc_md(desc: str) -> str:
    """Описание заголовком ### - крупнее и контрастнее обычного текста, не сливается с фоном."""
    return "\n".join(f"### {ln}" if ln.strip() else ln for ln in desc.splitlines())


def _sponsor_button(contest: dict, txt: dict | None = None) -> Button | None:
    url = contest.get("sponsor_url")
    if not url:
        return None
    label = (txt or {}).get("sponsor_button", "Спонсор")
    return Button(label=label, style=ButtonStyle.link, url=url)


def _winners_line(contest: dict, txt: dict | None = None) -> str:
    a = (txt or {}).get("announce", {})
    n = contest.get("winners_count", 1)
    if _is_giveaway(contest):
        who = a.get("winners_giveaway_who", "случайный выбор среди выполнивших условие")
        head = (
            a.get("winners_giveaway_one", "1 победитель") if n <= 1
            else a.get("winners_giveaway_many", "{n} победителей").format(n=n)
        )
        return f"{head} · {who}"
    return (
        a.get("winners_leaderboard_one", "топ-1 по активности") if n <= 1
        else a.get("winners_leaderboard_many", "топ-{n} по активности").format(n=n)
    )


def _fields(contest: dict, txt: dict | None = None) -> str:
    """Компактный блок "ключ - значение" для анонса."""
    a = (txt or {}).get("announce", {})
    prize = contest.get("prize")
    if prize:
        lines = [a.get("prize", "**Приз** — {prize}").format(prize=prize)]
    else:
        lines = [a.get("prize_none", "**Приз** — разыгрывается среди участников")]
    secs = contest.get("min_voice_seconds")
    if _is_giveaway(contest) and secs:
        lines.append(a.get("condition", "**Условие** — {duration} в голосовых").format(
            duration=format_duration(secs)))
    lines.append(a.get("awards", "**Награды** — {winners}").format(winners=_winners_line(contest, txt)))
    return "\n".join(lines)




def build_contest_announcement(
    contest: dict, accent: int, image_media: str | None = None, txt: dict | None = None
) -> Container:
    a = (txt or {}).get("announce", {})
    ts = int(_ends_at(contest).timestamp())
    desc = contest.get("description")
    blocks = [
        TextDisplay(f"## {_kind_label(contest)}"),
        TextDisplay(f"-# {_type_label(contest)}  ·  завершение <t:{ts}:R>"),
        Separator(),
        *_media(image_media),
    ]
    if desc:
        blocks.append(TextDisplay(_desc_md(desc)))
        blocks.append(Separator(divider=False))
    blocks.append(TextDisplay(_fields(contest, txt)))
    blocks.append(Separator(divider=False))
    blocks.append(TextDisplay(a.get("join_hint", "-# Нажмите «Участие», чтобы вступить в конкурс.")))
    blocks.append(
        ActionRow(
            Button(label=a.get("join_button", "Участие"), style=ButtonStyle.success,
                   custom_id=f"{JOIN_PREFIX}{contest['id']}"),
            *([b] if (b := _sponsor_button(contest, txt)) else []),
        )
    )
    return Container(*blocks, accent_colour=Colour(accent))


def build_contest_ended(
    contest: dict, entries: list[dict], accent: int,
    image_media: str | None = None, txt: dict | None = None,
) -> Container:
    r = (txt or {}).get("results", {})
    winners = contest.get("winners_count", 1)
    winner_entries = entries[:winners]
    giveaway = _is_giveaway(contest)

    if not winner_entries:
        head = r.get("none_giveaway", "Победителей нет — никто не выполнил условие.") if giveaway \
            else r.get("none_leaderboard", "Победителей нет — участники не набрали активности.")
    elif len(winner_entries) == 1:
        head = r.get("winner_one", "Победитель")
    else:
        head = r.get("winner_many", "Победители")

    if giveaway:
        lines = [f"{medal(i + 1)} <@{e['user_id']}>" for i, e in enumerate(winner_entries)]
    else:
        lines = [
            f"{medal(e['rank'])} <@{e['user_id']}> · {format_duration(e['total_seconds'])}"
            for e in winner_entries
        ]

    prize = contest.get("prize")
    desc = contest.get("description")
    blocks = [
        TextDisplay(r.get("title", "## Итоги · {kind}").format(kind=_kind_label(contest))),
        TextDisplay(f"-# {_type_label(contest)}"),
        Separator(),
        *_media(image_media),
    ]
    if desc:
        blocks.append(TextDisplay(_desc_md(desc)))
        blocks.append(Separator(divider=False))
    if prize:
        blocks.append(TextDisplay(r.get("prize", "**Приз** — {prize}").format(prize=prize)))
    blocks.append(TextDisplay(f"**{head}**" if winner_entries else head))
    if lines:
        blocks.append(TextDisplay("\n".join(lines)))
    sponsor = _sponsor_button(contest, txt)
    if sponsor:
        blocks.append(Separator(divider=False))
        blocks.append(ActionRow(sponsor))
    return Container(*blocks, accent_colour=Colour(accent))




def _stat_block(stat: dict) -> str:
    contest = stat["contest"]
    ts = int(_ends_at(contest).timestamp())
    lines = [f"### {_kind_label(contest)} · {_type_label(contest)}"]

    prize = contest.get("prize")
    if prize:
        lines.append(f"**Приз** — {prize}")
    secs = contest.get("min_voice_seconds")
    if _is_giveaway(contest) and secs:
        lines.append(f"**Условие** — {format_duration(secs)} в голосовых")

    counts = f"**{stat['participant_count']}** участников"
    if stat.get("qualified_count") is not None:
        counts += f" · **{stat['qualified_count']}** выполнили условие"
    counts += f" · осталось **{time_left(_ends_at(contest))}**"
    lines.append(counts)
    lines.append(f"-# завершение <t:{ts}:R>")
    if stat.get("personal"):
        lines.append(stat["personal"])
    return "\n".join(lines)


def build_contest_overview(stats: list[dict], accent: int) -> Container:
    if not stats:
        return Container(
            TextDisplay("## Конкурсы"),
            TextDisplay("-# Сейчас нет активных конкурсов."),
            accent_colour=Colour(accent),
        )
    blocks: list = [TextDisplay("## Активные конкурсы"), Separator()]
    for i, stat in enumerate(stats):
        if i:
            blocks.append(Separator())
        blocks.append(TextDisplay(_stat_block(stat)))
    return Container(*blocks, accent_colour=Colour(accent))


def build_contest_main(stats: list[dict], accent: int) -> Container:
    blocks: list = [
        TextDisplay("## Управление конкурсами"),
        TextDisplay("-# Создавайте конкурсы и управляйте активными."),
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
                        style=ButtonStyle.danger,
                        custom_id=f"{END_PREFIX}{stat['contest']['id']}",
                    )
                )
            )
        blocks.append(Separator())
    else:
        blocks.append(TextDisplay("-# Сейчас нет активных конкурсов."))
    blocks.append(ActionRow(Button(label="Создать конкурс", style=ButtonStyle.success, custom_id=NEW_BUTTON)))
    return Container(*blocks, accent_colour=Colour(accent))


def build_kind_picker(accent: int) -> Container:
    return Container(
        TextDisplay("## Новый конкурс"),
        TextDisplay("-# Шаг 1 — выберите тип."),
        Separator(),
        TextDisplay(
            f"**{CONTEST_KIND_LABEL['giveaway']}**\n"
            "-# Участники вступают и набирают минимальную активность в голосовых. "
            "Победители выбираются случайно среди выполнивших условие.\n\n"
            f"**{CONTEST_KIND_LABEL['leaderboard']}**\n"
            "-# Побеждают самые активные в голосовых каналах (топ)."
        ),
        Separator(divider=False),
        ActionRow(
            Button(label=CONTEST_KIND_LABEL["giveaway"], style=ButtonStyle.primary, custom_id=f"{KIND_PREFIX}giveaway"),
            Button(label=CONTEST_KIND_LABEL["leaderboard"], style=ButtonStyle.primary, custom_id=f"{KIND_PREFIX}leaderboard"),
        ),
        ActionRow(Button(label="Назад", style=ButtonStyle.secondary, custom_id=MAIN_BUTTON)),
        accent_colour=Colour(accent),
    )


def build_duration_picker(kind: str, accent: int) -> Container:
    return Container(
        TextDisplay(f"## Новый конкурс · {CONTEST_KIND_LABEL.get(kind, kind)}"),
        TextDisplay("-# Шаг 2 — длительность. «Другое» — задать свою."),
        Separator(divider=False),
        ActionRow(
            Button(label="День", style=ButtonStyle.primary, custom_id=f"{DUR_PREFIX}{kind}:day"),
            Button(label="Неделя", style=ButtonStyle.primary, custom_id=f"{DUR_PREFIX}{kind}:week"),
            Button(label="Месяц", style=ButtonStyle.primary, custom_id=f"{DUR_PREFIX}{kind}:month"),
            Button(label="Другое", style=ButtonStyle.secondary, custom_id=f"{DUR_PREFIX}{kind}:custom"),
        ),
        ActionRow(Button(label="Назад", style=ButtonStyle.secondary, custom_id=NEW_BUTTON)),
        accent_colour=Colour(accent),
    )


def build_qualify_dm(contest: dict, guild_name: str, accent: int) -> Container:
    """ЛС участнику giveaway: условие выполнено."""
    blocks: list = [
        TextDisplay("## Условие выполнено"),
        TextDisplay(f"-# {guild_name} · {_kind_label(contest)}"),
        Separator(divider=False),
        TextDisplay("Вы выполнили условие розыгрыша и попадаете в финальную жеребьёвку победителей."),
    ]
    prize = contest.get("prize")
    if prize:
        blocks.append(TextDisplay(f"**Приз** — {prize}"))
    return Container(*blocks, accent_colour=Colour(accent))


def build_winner_dm(contest: dict, guild_name: str, accent: int) -> Container:
    """ЛС победителю при завершении конкурса."""
    blocks: list = [
        TextDisplay("## Поздравляем — вы победили!"),
        TextDisplay(f"-# {guild_name} · {_kind_label(contest)}"),
        Separator(divider=False),
        TextDisplay("Вы вошли в число победителей конкурса. Администрация свяжется по поводу приза."),
    ]
    prize = contest.get("prize")
    if prize:
        blocks.append(TextDisplay(f"**Приз** — {prize}"))
    sponsor = _sponsor_button(contest)
    if sponsor:
        blocks.append(Separator(divider=False))
        blocks.append(ActionRow(sponsor))
    return Container(*blocks, accent_colour=Colour(accent))


def build_contest_created(contest: dict, accent: int) -> Container:
    return Container(
        TextDisplay("## Конкурс создан"),
        TextDisplay("-# Анонс опубликован в этом канале."),
        Separator(divider=False),
        TextDisplay("Можно добавить спонсора — кнопка-ссылка появится рядом с «Участие»."),
        ActionRow(
            Button(
                label="Добавить спонсора",
                style=ButtonStyle.secondary,
                custom_id=f"{SPONSOR_PREFIX}{contest['id']}",
            )
        ),
        accent_colour=Colour(accent),
    )
