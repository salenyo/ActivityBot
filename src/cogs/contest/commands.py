from __future__ import annotations

import os
import random
from datetime import datetime, timezone

from disnake import (
    ApplicationCommandInteraction,
    File,
    Member,
    MessageInteraction,
    ModalInteraction,
)
from disnake.ext import tasks
from disnake.ext.commands import AutoShardedBot, Cog, slash_command
from disnake.ui import Modal, TextInput

from hydra_shared.logging import get_logger
from hydra_shared.ui import send_notify

from src.common import (
    CONTEST_DURATIONS,
    CONTEST_KIND_LABEL,
    duration_label,
    format_duration,
    has_contest_permission,
    medal,
    parse_contest_dates,
    parse_duration,
)

from .containers import (
    DUR_PREFIX,
    END_PREFIX,
    JOIN_PREFIX,
    KIND_PREFIX,
    MAIN_BUTTON,
    NEW_BUTTON,
    build_contest_announcement,
    build_contest_ended,
    build_contest_main,
    build_contest_overview,
    build_duration_picker,
    build_kind_picker,
)

log = get_logger(__name__)
UTC = timezone.utc
BANNER_FILENAME = "contest.png"
# Ключ Redis с таймстемпом захода в войс — совпадает с VoiceTracker (cogs/voice_tracker).
VOICE_KEY = "activity:voice:{user_id}"


class ContestCommands(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self._contest_watcher.start()

    def cog_unload(self):
        self._contest_watcher.cancel()

    # ── /contest ──────────────────────────────────────────────────────────────

    @slash_command(name="contest", description="Конкурсы активности")
    async def contest(self, inter: ApplicationCommandInteraction):
        if not isinstance(inter.author, Member):
            return await inter.response.send_message("Только на сервере.", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        contests = await self.bot.db.activity.get_active_contests(inter.guild_id)

        if has_contest_permission(cfg, inter.author):
            stats = await self._build_stats(contests)
            await inter.edit_original_message(
                components=[build_contest_main(stats, cfg.embed_color)]
            )
        else:
            stats = await self._build_stats(contests, viewer_id=inter.author.id)
            await inter.edit_original_message(
                components=[build_contest_overview(stats, cfg.embed_color)]
            )

    async def _build_stats(self, contests: list[dict], viewer_id: int | None = None) -> list[dict]:
        """Собирает по каждому активному конкурсу данные для контейнера обзора/управления."""
        stats: list[dict] = []
        for contest in contests:
            participants = await self.bot.db.activity.get_participants(contest["id"])
            stat = {
                "contest": contest,
                "participant_count": len(participants),
                "qualified_count": None,
                "personal": None,
            }
            if contest.get("kind") == "giveaway":
                qualified = await self.bot.db.activity.get_qualified_participants(contest["id"])
                stat["qualified_count"] = len(qualified)
                if viewer_id is not None:
                    if viewer_id in qualified:
                        stat["personal"] = "✅ Вы выполнили условие."
                    elif viewer_id in participants:
                        stat["personal"] = "⏳ Вы участвуете — наберите нужную активность в голосовых."
                    else:
                        stat["personal"] = "-# Нажмите «Участие» под анонсом, чтобы попасть в розыгрыш."
            elif viewer_id is not None:
                entries = await self.bot.db.activity.get_contest_leaderboard(contest["id"], limit=100)
                rank = next((e["rank"] for e in entries if e["user_id"] == viewer_id), None)
                if rank:
                    stat["personal"] = f"Ваша позиция: {medal(rank)}"
                elif viewer_id in participants:
                    stat["personal"] = "⏳ Вы участвуете — набирайте активность в голосовых."
                else:
                    stat["personal"] = "-# Нажмите «Участие» под анонсом, чтобы попасть в зачёт."
            stats.append(stat)
        return stats

    # ── Конструктор (кнопки) ─────────────────────────────────────────────────

    @Cog.listener("on_button_click")
    async def on_contest_button(self, inter: MessageInteraction):
        cid = inter.component.custom_id or ""
        if not cid.startswith("contest:") or cid.startswith(JOIN_PREFIX):
            return
        if not isinstance(inter.author, Member):
            return

        cfg = await self.bot.get_cfg()
        if not has_contest_permission(cfg, inter.author):
            return await inter.response.send_message("Нет доступа.", ephemeral=True)
        accent = cfg.embed_color

        if cid == NEW_BUTTON:
            await inter.response.edit_message(components=[build_kind_picker(accent)])

        elif cid == MAIN_BUTTON:
            contests = await self.bot.db.activity.get_active_contests(inter.guild_id)
            stats = await self._build_stats(contests)
            await inter.response.edit_message(components=[build_contest_main(stats, accent)])

        elif cid.startswith(KIND_PREFIX):
            kind = cid[len(KIND_PREFIX):]
            await inter.response.edit_message(components=[build_duration_picker(kind, accent)])

        elif cid.startswith(DUR_PREFIX):
            kind, _, contest_type = cid[len(DUR_PREFIX):].partition(":")
            await inter.response.send_modal(ContestCreateModal(self.bot, kind, contest_type, accent))

        elif cid.startswith(END_PREFIX):
            try:
                contest_id = int(cid[len(END_PREFIX):])
            except ValueError:
                return
            contest = await self.bot.db.activity.get_contest(contest_id)
            if not contest or not contest.get("is_active"):
                return await send_notify(inter, "Этот конкурс уже завершён.", is_error=True)
            await inter.response.defer(ephemeral=True)
            await self._finish_contest(contest, cfg)
            await send_notify(inter, "Конкурс завершён, победители объявлены.")

    # ── Кнопка участия ─────────────────────────────────────────────────────────

    @Cog.listener("on_button_click")
    async def on_join_button(self, inter: MessageInteraction):
        custom_id = inter.component.custom_id or ""
        if not custom_id.startswith(JOIN_PREFIX):
            return
        try:
            contest_id = int(custom_id[len(JOIN_PREFIX):])
        except ValueError:
            return

        contest = await self.bot.db.activity.get_contest(contest_id)
        if not contest or not contest.get("is_active"):
            return await send_notify(inter, "Этот конкурс уже завершён.", is_error=True)

        try:
            await self.bot.db.activity.add_participant(contest_id, inter.author.id)
        except Exception as e:
            log.error("contest_join_failed", contest_id=contest_id, error=str(e))
            return await send_notify(inter, "Не удалось записать участие.", is_error=True)

        secs = contest.get("min_voice_seconds")
        if contest.get("kind") == "giveaway" and secs:
            await send_notify(
                inter,
                f"Вы в розыгрыше! Наберите **{format_duration(secs)}** активности в голосовых — "
                f"при выполнении условия придёт уведомление в личные сообщения.",
            )
        else:
            await send_notify(
                inter, "Вы в списке участников конкурса! Набирайте активность в голосовых."
            )

    # ── Публикация с баннером ────────────────────────────────────────────────

    async def _post_with_banner(self, channel, builder, cfg):
        """Публикует контейнер в канал, добавляя баннер из ассетов, если он задан."""
        path = getattr(cfg, "activity_contest_banner_path", None)
        if path and os.path.exists(path):
            return await channel.send(
                components=[builder(BANNER_FILENAME)],
                file=File(path, filename=BANNER_FILENAME),
            )
        return await channel.send(components=[builder(None)])

    # ── Автозавершение и проверка условий ──────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _contest_watcher(self):
        guild_id = self.bot.primary_guild_id
        if guild_id is None:
            return
        try:
            contests = await self.bot.db.activity.get_active_contests(guild_id)
        except Exception as e:
            return log.error("contest_watcher_failed", error=str(e))

        cfg = None
        now = datetime.now(UTC)
        for contest in contests:
            try:
                _, ends_at = parse_contest_dates(contest)
                if now >= ends_at:
                    cfg = cfg or await self.bot.get_cfg()
                    await self._finish_contest(contest, cfg)
                elif contest.get("kind") == "giveaway":
                    await self._check_qualified(contest)
            except Exception as e:
                log.error("contest_tick_failed", contest_id=contest.get("id"), error=str(e))

    @_contest_watcher.before_loop
    async def _before_watcher(self):
        await self.bot.wait_until_ready()

    async def _voice_extra(self, contest: dict, until: datetime) -> dict[int, int]:
        """Доп. секунды живых (ещё не закрытых) голосовых сессий участников из Redis.

        В voice_sessions такие сессии появятся только после выхода из войса, поэтому их
        учитываем отдельно — как пересечение [join, until] с началом окна конкурса.
        """
        participants = await self.bot.db.activity.get_participants(contest["id"])
        if not participants:
            return {}
        started_at, _ = parse_contest_dates(contest)
        extra: dict[int, int] = {}
        for user_id in participants:
            try:
                joined_ts = await self.bot.redis.get(VOICE_KEY.format(user_id=user_id))
            except Exception:
                continue
            if not joined_ts:
                continue
            joined_at = datetime.fromtimestamp(int(joined_ts), UTC)
            overlap_start = max(joined_at, started_at)
            secs = int((until - overlap_start).total_seconds())
            if secs > 0:
                extra[user_id] = secs
        return extra

    async def _check_qualified(self, contest: dict) -> None:
        now = datetime.now(UTC)
        extra = await self._voice_extra(contest, now)
        result = await self.bot.db.activity.recompute_qualified(contest["id"], extra_seconds=extra)
        newly = result.get("newly_qualified") or []
        if not newly:
            return
        guild = self.bot.get_guild(self.bot.primary_guild_id)
        if guild is None:
            return
        prize = contest.get("prize")
        prize_line = f"\nПриз: **{prize}**" if prize else ""
        for user_id in newly:
            member = guild.get_member(user_id)
            if member is None:
                continue
            try:
                await member.send(
                    f"🎉 Вы выполнили условие розыгрыша на **{guild.name}**!{prize_line}\n"
                    f"Вы попадаете в финальную жеребьёвку победителей."
                )
            except Exception:
                log.info("contest_qualify_dm_failed", contest_id=contest["id"], user_id=user_id)

    async def _finish_contest(self, contest: dict, cfg) -> None:
        # Объявление в отдельном try: даже если публикация упадёт, конкурс всё равно
        # должен завершиться — иначе он навсегда останется активным.
        try:
            winners = contest.get("winners_count", 1)
            if contest.get("kind") == "giveaway":
                # Финальная сверка с учётом живых сессий, обрезанных по концу конкурса.
                _, ends_at = parse_contest_dates(contest)
                extra = await self._voice_extra(contest, ends_at)
                await self.bot.db.activity.recompute_qualified(contest["id"], extra_seconds=extra)
                qualified = await self.bot.db.activity.get_qualified_participants(contest["id"])
                chosen = random.sample(qualified, min(winners, len(qualified)))
                entries = [{"user_id": uid, "total_seconds": 0, "rank": i + 1} for i, uid in enumerate(chosen)]
            else:
                entries = await self.bot.db.activity.get_contest_leaderboard(contest["id"], limit=winners)
            await self._announce_winner(contest, entries, cfg)
        except Exception as e:
            log.error("contest_announce_failed", contest_id=contest["id"], error=str(e))
        await self.bot.db.activity.end_contest(contest["id"])
        log.info("contest_ended", contest_id=contest["id"])

    async def _announce_winner(self, contest: dict, entries: list[dict], cfg) -> None:
        guild = self.bot.get_guild(self.bot.primary_guild_id)
        if guild is None:
            return

        def builder(image_filename):
            return build_contest_ended(contest, entries, cfg.embed_color, image_filename)

        # Предпочтительно — опубликовать результат в канале конкурса и погасить кнопку
        # «Участие» в исходном анонсе (редактируем его без файла — баннер несёт свежее сообщение).
        channel_id = contest.get("channel_id")
        message_id = contest.get("message_id")
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                try:
                    await self._post_with_banner(channel, builder, cfg)
                    if message_id:
                        try:
                            await channel.get_partial_message(message_id).edit(
                                components=[builder(None)]
                            )
                        except Exception:
                            pass
                    return
                except Exception as e:
                    log.warning("contest_edit_announce_failed", contest_id=contest["id"], error=str(e))

        # Фолбэк — канал результатов из конфига.
        results_id = cfg.activity_results_channel_id
        if results_id is None:
            return log.warning("contest_results_channel_unset", contest_id=contest["id"])
        channel = guild.get_channel(results_id)
        if channel is None:
            return log.warning("contest_results_channel_not_found", channel_id=results_id)
        await self._post_with_banner(channel, builder, cfg)


class ContestCreateModal(Modal):
    def __init__(self, bot: AutoShardedBot, kind: str, contest_type: str, accent: int):
        self.bot = bot
        self.kind = kind
        self.contest_type = contest_type
        self.is_custom = contest_type == "custom"
        self.accent = accent
        components = [
            TextInput(label="Приз", custom_id="prize", placeholder="Что разыгрываем", max_length=200),
            TextInput(label="Сколько победителей", custom_id="winners", placeholder="1", value="1", max_length=2),
        ]
        if self.is_custom:
            components.append(
                TextInput(
                    label="Длительность",
                    custom_id="duration",
                    placeholder="например: 2д 3ч · 1 день 12 часов · 90 мин",
                    max_length=30,
                )
            )
        if kind == "giveaway":
            components.append(
                TextInput(
                    label="Мин. активность в голосовых (минуты)",
                    custom_id="min_minutes",
                    placeholder="60",
                    max_length=5,
                )
            )
        super().__init__(
            title=f"Новый конкурс · {CONTEST_KIND_LABEL.get(kind, kind)}",
            custom_id=f"contest_create:{kind}:{contest_type}",
            components=components,
        )

    async def callback(self, inter: ModalInteraction):
        await inter.response.defer(ephemeral=True)
        cog: ContestCommands = self.bot.get_cog("ContestCommands")

        prize = inter.text_values["prize"].strip() or None
        try:
            winners = int(inter.text_values["winners"].strip() or "1")
            if not 1 <= winners <= 20:
                raise ValueError
        except ValueError:
            return await send_notify(inter, "Число победителей должно быть от 1 до 20.", is_error=True)

        min_voice_seconds = None
        if self.kind == "giveaway":
            try:
                minutes = int(inter.text_values["min_minutes"].strip())
                if minutes <= 0:
                    raise ValueError
            except ValueError:
                return await send_notify(inter, "Минимальная активность должна быть числом минут больше 0.", is_error=True)
            min_voice_seconds = minutes * 60

        cfg = await self.bot.get_cfg()
        now = datetime.now(UTC)
        if self.is_custom:
            delta = parse_duration(inter.text_values["duration"])
            if delta is None:
                return await send_notify(
                    inter,
                    "Не понял длительность. Примеры: «2д 3ч», «1 день 12 часов», «90 мин» "
                    "(от 1 минуты до 365 дней).",
                    is_error=True,
                )
            ends_at = now + delta
            contest_type = duration_label(int(delta.total_seconds()))
        else:
            ends_at = now + CONTEST_DURATIONS[self.contest_type]
            contest_type = self.contest_type

        try:
            contest = await self.bot.db.activity.create_contest(
                guild_id=inter.guild_id,
                contest_type=contest_type,
                kind=self.kind,
                started_at=now,
                ends_at=ends_at,
                prize=prize,
                winners_count=winners,
                min_voice_seconds=min_voice_seconds,
            )
        except Exception as e:
            log.error("contest_create_failed", error=str(e))
            return await send_notify(inter, "Не удалось создать конкурс.", is_error=True)

        try:
            message = await cog._post_with_banner(
                inter.channel,
                lambda img: build_contest_announcement(contest, cfg.embed_color, img),
                cfg,
            )
            await self.bot.db.activity.set_contest_message(
                contest["id"], channel_id=message.channel.id, message_id=message.id
            )
        except Exception as e:
            log.error("contest_announce_post_failed", contest_id=contest["id"], error=str(e))
            return await send_notify(
                inter, "Конкурс создан, но не удалось опубликовать анонс в этом канале.", is_error=True
            )

        await send_notify(inter, "Конкурс создан и опубликован в этом канале.")
