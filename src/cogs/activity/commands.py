from __future__ import annotations

from datetime import datetime, timezone

from disnake import ApplicationCommandInteraction, Member
from disnake.ext import tasks
from disnake.ext.commands import AutoShardedBot, Cog, Param, slash_command

from hydra_shared.logging import get_logger

from .containers import (
    build_contest_ended_container,
    build_contest_started_container,
    build_error_container,
    build_stats_container,
)
from .utils import (
    CONTEST_DURATIONS,
    has_contest_permission,
    parse_contest_dates,
)

log = get_logger(__name__)
UTC = timezone.utc


class ActivityCommands(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self._contest_watcher.start()

    def cog_unload(self):
        self._contest_watcher.cancel()

    # ── Commands ─────────────────────────────────────────────────────────────

    @slash_command(name="activity", description="Активность в голосовых каналах")
    async def activity(self, inter: ApplicationCommandInteraction):
        pass

    @activity.sub_command(name="stats", description="Показать статистику голосовой активности")
    async def activity_stats(self, inter: ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        guild_id = inter.guild_id
        now = datetime.now(UTC)

        contest = await self.bot.db.activity.get_active_contest(guild_id)

        if contest:
            from_dt, to_dt = parse_contest_dates(contest)
            to_dt = min(to_dt, now)
        else:
            from datetime import timedelta
            from_dt = now - timedelta(days=7)
            to_dt = now

        entries = await self.bot.db.activity.get_leaderboard(
            guild_id=guild_id, from_dt=from_dt, to_dt=to_dt, limit=10,
        )
        user_data = await self.bot.db.activity.get_user_total(
            guild_id=guild_id, user_id=inter.author.id, from_dt=from_dt, to_dt=to_dt,
        )
        user_total = (user_data or {}).get("total_seconds", 0)

        await inter.edit_original_message(
            components=[build_stats_container(
                entries=entries,
                contest=contest,
                user_id=inter.author.id,
                user_total=user_total,
                accent=cfg.embed_color,
            )]
        )

    @activity.sub_command(name="contest", description="Запустить конкурс активности")
    async def activity_contest(
        self,
        inter: ApplicationCommandInteraction,
        type: str = Param(
            description="Длительность конкурса",
            choices=["day", "week", "month"],
        ),
    ):
        if not isinstance(inter.author, Member):
            return await inter.response.send_message("Только на сервере.", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        if not has_contest_permission(cfg, inter.author):
            return await inter.edit_original_message(
                components=[build_error_container("У вас недостаточно прав для запуска конкурса.")]
            )

        now = datetime.now(UTC)
        ends_at = now + CONTEST_DURATIONS[type]

        try:
            contest = await self.bot.db.activity.create_contest(
                guild_id=inter.guild_id,
                contest_type=type,
                started_at=now,
                ends_at=ends_at,
            )
        except Exception as e:
            log.error("contest_create_failed", error=str(e))
            return await inter.edit_original_message(
                components=[build_error_container("Не удалось запустить конкурс.")]
            )

        await inter.edit_original_message(
            components=[build_contest_started_container(contest, cfg.embed_color)]
        )

    # ── Auto-completion watcher ───────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _contest_watcher(self):
        guild_id = self.bot.primary_guild_id
        if guild_id is None:
            log.warning("contest_watcher_no_guild")
            return
        try:
            contest = await self.bot.db.activity.get_active_contest(guild_id)
            if not contest:
                return
            _, ends_at = parse_contest_dates(contest)
            if datetime.now(UTC) < ends_at:
                return

            # Объявление в отдельном try: даже если отправка упадёт (нет прав,
            # канал не найден и т.п.), конкурс всё равно должен завершиться —
            # иначе он навсегда останется активным и будет висеть в /activity stats.
            try:
                await self._announce_winner(contest)
            except Exception as e:
                log.error(
                    "contest_announce_failed",
                    contest_id=contest["id"],
                    error=str(e),
                )

            await self.bot.db.activity.end_contest(contest["id"])
            log.info("contest_ended", contest_id=contest["id"])
        except Exception as e:
            log.error("contest_watcher_failed", error=str(e))

    @_contest_watcher.before_loop
    async def _before_watcher(self):
        await self.bot.wait_until_ready()

    async def _announce_winner(self, contest: dict) -> None:
        cfg = await self.bot.get_cfg()
        if cfg.activity_results_channel_id is None:
            log.warning("contest_results_channel_unset", contest_id=contest["id"])
            return
        guild = self.bot.get_guild(self.bot.primary_guild_id)
        if guild is None:
            log.warning("contest_guild_unavailable", guild_id=self.bot.primary_guild_id)
            return
        channel = guild.get_channel(cfg.activity_results_channel_id)
        if channel is None:
            log.warning(
                "contest_results_channel_not_found",
                channel_id=cfg.activity_results_channel_id,
            )
            return

        from_dt, ends_at = parse_contest_dates(contest)
        entries = await self.bot.db.activity.get_leaderboard(
            guild_id=guild.id, from_dt=from_dt, to_dt=ends_at, limit=5,
        )
        await channel.send(
            components=[build_contest_ended_container(contest, entries, cfg.embed_color)]
        )
        log.info("contest_winner_announced", contest_id=contest["id"])
