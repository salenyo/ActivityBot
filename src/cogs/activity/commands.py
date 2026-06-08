from __future__ import annotations

from datetime import datetime, timedelta, timezone

from disnake import ApplicationCommandInteraction, Member
from disnake.ext.commands import AutoShardedBot, Cog, Param, slash_command
from disnake.ext import tasks

from hydra_shared.logging import get_logger

from .containers import (
    build_contest_ended_container,
    build_contest_started_container,
    build_error_container,
    build_stats_container,
)

log = get_logger(__name__)

UTC = timezone.utc

_CONTEST_DURATIONS = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}


def _has_contest_perm(cfg, member: Member) -> bool:
    roles = set(cfg.activity_contest_role_ids or [])
    return any(r.id in roles for r in member.roles) or member.id in (cfg.owner_ids or [])


class ActivityCommands(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self._check_contests.start()

    def cog_unload(self):
        self._check_contests.cancel()

    @slash_command(name="activity", description="Активность в голосовых каналах")
    async def activity(self, inter: ApplicationCommandInteraction):
        pass

    @activity.sub_command(name="stats", description="Показать статистику активности")
    async def activity_stats(self, inter: ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        guild_id = inter.guild_id
        now = datetime.now(UTC)

        contest = await self.bot.db.activity.get_active_contest(guild_id)

        if contest:
            from_dt = datetime.fromisoformat(contest["started_at"])
            to_dt = datetime.fromisoformat(contest["ends_at"])
            if from_dt.tzinfo is None:
                from_dt = from_dt.replace(tzinfo=UTC)
            if to_dt.tzinfo is None:
                to_dt = to_dt.replace(tzinfo=UTC)
            to_dt = min(to_dt, now)
        else:
            from_dt = now - timedelta(days=7)
            to_dt = now

        entries = await self.bot.db.activity.get_leaderboard(
            guild_id=guild_id, from_dt=from_dt, to_dt=to_dt, limit=10,
        )
        user_data = await self.bot.db.activity.get_user_total(
            guild_id=guild_id, user_id=inter.author.id, from_dt=from_dt, to_dt=to_dt,
        )
        user_total = user_data.get("total_seconds", 0) if user_data else 0

        container = build_stats_container(
            entries=entries,
            contest=contest,
            user_id=inter.author.id,
            user_total=user_total,
            accent=cfg.embed_color,
        )
        await inter.edit_original_message(components=[container])

    @activity.sub_command(name="contest", description="Запустить конкурс активности")
    async def activity_contest(
        self,
        inter: ApplicationCommandInteraction,
        type: str = Param(description="Длительность конкурса", choices=["day", "week", "month"]),
    ):
        if not isinstance(inter.author, Member):
            return await inter.response.send_message("Только на сервере.", ephemeral=True)

        cfg = await self.bot.get_cfg()
        if not _has_contest_perm(cfg, inter.author):
            return await inter.response.send_message(
                "У вас недостаточно прав для запуска конкурса.", ephemeral=True
            )

        await inter.response.defer(ephemeral=True)
        now = datetime.now(UTC)
        ends_at = now + _CONTEST_DURATIONS[type]

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

    @tasks.loop(minutes=30)
    async def _check_contests(self):
        guild_id = self.bot.settings.primary_guild_id
        if guild_id is None:
            return
        try:
            contest = await self.bot.db.activity.get_active_contest(guild_id)
            if not contest:
                return

            ends_at = datetime.fromisoformat(contest["ends_at"])
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=UTC)
            if datetime.now(UTC) < ends_at:
                return

            await self._announce_winner(contest)
            await self.bot.db.activity.end_contest(contest["id"])
        except Exception as e:
            log.error("contest_check_failed", error=str(e))

    @_check_contests.before_loop
    async def _before_check(self):
        await self.bot.wait_until_ready()

    async def _announce_winner(self, contest: dict) -> None:
        cfg = await self.bot.get_cfg()
        if cfg.activity_results_channel_id is None:
            return

        guild = self.bot.get_guild(self.bot.settings.primary_guild_id)
        if guild is None:
            return
        channel = guild.get_channel(cfg.activity_results_channel_id)
        if channel is None:
            return

        from_dt = datetime.fromisoformat(contest["started_at"])
        ends_at = datetime.fromisoformat(contest["ends_at"])
        if from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=UTC)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=UTC)

        entries = await self.bot.db.activity.get_leaderboard(
            guild_id=guild.id, from_dt=from_dt, to_dt=ends_at, limit=5,
        )
        container = build_contest_ended_container(contest, entries, guild, cfg.embed_color)
        await channel.send(components=[container])
        log.info("contest_winner_announced", contest_id=contest["id"])
