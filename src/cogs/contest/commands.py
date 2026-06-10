from __future__ import annotations

from datetime import datetime, timezone

from disnake import ApplicationCommandInteraction, Member, MessageInteraction
from disnake.ext import tasks
from disnake.ext.commands import AutoShardedBot, Cog, Param, slash_command

from hydra_shared.logging import get_logger
from hydra_shared.ui import send_notify

from src.common import (
    CONTEST_DURATIONS,
    has_contest_permission,
    parse_contest_dates,
)

from .containers import (
    JOIN_PREFIX,
    build_contest_announcement,
    build_contest_ended,
    build_contest_stats,
)

log = get_logger(__name__)
UTC = timezone.utc


class ContestCommands(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self._contest_watcher.start()

    def cog_unload(self):
        self._contest_watcher.cancel()

    # ── Commands ─────────────────────────────────────────────────────────────

    @slash_command(name="contest", description="Конкурсы активности")
    async def contest(self, inter: ApplicationCommandInteraction):
        pass

    @contest.sub_command(name="start", description="Запустить конкурс активности с призом")
    async def contest_start(
        self,
        inter: ApplicationCommandInteraction,
        type: str = Param(description="Длительность конкурса", choices=["day", "week", "month"]),
        prize: str = Param(description="Приз конкурса"),
        winners: int = Param(default=1, description="Сколько победителей", ge=1, le=20),
    ):
        if not isinstance(inter.author, Member):
            return await inter.response.send_message("Только на сервере.", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        if not has_contest_permission(cfg, inter.author):
            return await send_notify(
                inter, "У вас недостаточно прав для запуска конкурса.", is_error=True
            )

        now = datetime.now(UTC)
        ends_at = now + CONTEST_DURATIONS[type]

        try:
            contest = await self.bot.db.activity.create_contest(
                guild_id=inter.guild_id,
                contest_type=type,
                started_at=now,
                ends_at=ends_at,
                prize=prize,
                winners_count=winners,
            )
        except Exception as e:
            log.error("contest_create_failed", error=str(e))
            return await send_notify(inter, "Не удалось запустить конкурс.", is_error=True)

        try:
            message = await inter.channel.send(
                components=[build_contest_announcement(contest, cfg.embed_color)]
            )
            await self.bot.db.activity.set_contest_message(
                contest["id"], channel_id=message.channel.id, message_id=message.id
            )
        except Exception as e:
            log.error("contest_announce_post_failed", contest_id=contest["id"], error=str(e))
            return await send_notify(
                inter,
                "Конкурс создан, но не удалось опубликовать анонс в этом канале.",
                is_error=True,
            )

        await send_notify(inter, "Конкурс запущен и опубликован в этом канале.")

    @contest.sub_command(name="stats", description="Статус текущего конкурса")
    async def contest_stats(self, inter: ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        contest = await self.bot.db.activity.get_active_contest(inter.guild_id)
        if not contest:
            return await send_notify(inter, "Сейчас нет активного конкурса.", is_error=True)

        participants = await self.bot.db.activity.get_participants(contest["id"])
        entries = await self.bot.db.activity.get_contest_leaderboard(contest["id"], limit=10)
        await inter.edit_original_message(
            components=[build_contest_stats(
                contest=contest,
                entries=entries,
                participant_count=len(participants),
                user_id=inter.author.id,
                accent=cfg.embed_color,
            )]
        )

    @contest.sub_command(name="end", description="Завершить текущий конкурс досрочно")
    async def contest_end(self, inter: ApplicationCommandInteraction):
        if not isinstance(inter.author, Member):
            return await inter.response.send_message("Только на сервере.", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        if not has_contest_permission(cfg, inter.author):
            return await send_notify(
                inter, "У вас недостаточно прав для завершения конкурса.", is_error=True
            )

        contest = await self.bot.db.activity.get_active_contest(inter.guild_id)
        if not contest:
            return await send_notify(inter, "Сейчас нет активного конкурса.", is_error=True)

        await self._finish_contest(contest, cfg)
        await send_notify(inter, "Конкурс завершён, победители объявлены.")

    # ── Participation button ───────────────────────────────────────────────

    @Cog.listener("on_button_click")
    async def on_join_button(self, inter: MessageInteraction):
        custom_id = inter.component.custom_id or ""
        if not custom_id.startswith(JOIN_PREFIX):
            return
        try:
            contest_id = int(custom_id[len(JOIN_PREFIX):])
        except ValueError:
            return

        contest = await self.bot.db.activity.get_active_contest(inter.guild_id)
        if not contest or contest["id"] != contest_id:
            return await send_notify(inter, "Этот конкурс уже завершён.", is_error=True)

        try:
            await self.bot.db.activity.add_participant(contest_id, inter.author.id)
        except Exception as e:
            log.error("contest_join_failed", contest_id=contest_id, error=str(e))
            return await send_notify(inter, "Не удалось записать участие.", is_error=True)

        await send_notify(inter, "Вы в списке участников конкурса! Набирайте активность в голосовых.")

    # ── Auto-completion watcher ──────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _contest_watcher(self):
        guild_id = self.bot.primary_guild_id
        if guild_id is None:
            return
        try:
            contest = await self.bot.db.activity.get_active_contest(guild_id)
            if not contest:
                return
            _, ends_at = parse_contest_dates(contest)
            if datetime.now(UTC) < ends_at:
                return
            cfg = await self.bot.get_cfg()
            await self._finish_contest(contest, cfg)
        except Exception as e:
            log.error("contest_watcher_failed", error=str(e))

    @_contest_watcher.before_loop
    async def _before_watcher(self):
        await self.bot.wait_until_ready()

    async def _finish_contest(self, contest: dict, cfg) -> None:
        # Объявление в отдельном try: даже если публикация упадёт, конкурс всё равно
        # должен завершиться — иначе он навсегда останется активным.
        try:
            winners = contest.get("winners_count", 1)
            entries = await self.bot.db.activity.get_contest_leaderboard(
                contest["id"], limit=winners,
            )
            await self._announce_winner(contest, entries, cfg)
        except Exception as e:
            log.error("contest_announce_failed", contest_id=contest["id"], error=str(e))
        await self.bot.db.activity.end_contest(contest["id"])
        log.info("contest_ended", contest_id=contest["id"])

    async def _announce_winner(self, contest: dict, entries: list[dict], cfg) -> None:
        container = build_contest_ended(contest, entries, cfg.embed_color)
        guild = self.bot.get_guild(self.bot.primary_guild_id)
        if guild is None:
            return

        # Предпочтительно — опубликовать результат в канале конкурса и погасить кнопку
        # «Участие» в исходном анонсе (редактируем его на тот же контейнер).
        channel_id = contest.get("channel_id")
        message_id = contest.get("message_id")
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                try:
                    await channel.send(components=[container])
                    if message_id:
                        try:
                            await channel.get_partial_message(message_id).edit(components=[container])
                        except Exception:
                            pass
                    return
                except Exception as e:
                    log.warning("contest_edit_announce_failed", contest_id=contest["id"], error=str(e))

        # Фолбэк — канал результатов из конфига.
        results_id = cfg.activity_results_channel_id
        if results_id is None:
            log.warning("contest_results_channel_unset", contest_id=contest["id"])
            return
        channel = guild.get_channel(results_id)
        if channel is None:
            log.warning("contest_results_channel_not_found", channel_id=results_id)
            return
        await channel.send(components=[container])
