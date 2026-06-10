from __future__ import annotations

from datetime import datetime, timedelta, timezone

from disnake import ApplicationCommandInteraction, MessageInteraction
from disnake.ext.commands import AutoShardedBot, Cog, slash_command

from hydra_shared.logging import get_logger

from .containers import (
    PERIOD_CUSTOM_ID,
    build_loading_container,
    build_stats_container,
)

log = get_logger(__name__)
UTC = timezone.utc

_PERIOD_DELTA: dict[str, timedelta | None] = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "all": None,
}
_ALL_TIME_START = datetime(2020, 1, 1, tzinfo=UTC)


def _period_window(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    delta = _PERIOD_DELTA.get(period)
    from_dt = _ALL_TIME_START if delta is None else now - delta
    return from_dt, now


class ActivityCommands(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @slash_command(name="activity", description="Активность в голосовых каналах")
    async def activity(self, inter: ApplicationCommandInteraction):
        pass

    @activity.sub_command(name="stats", description="Показать статистику голосовой активности")
    async def activity_stats(self, inter: ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        cfg = await self.bot.get_cfg()
        container = await self._build_stats(inter.guild_id, inter.author.id, "week", cfg.embed_color)
        await inter.edit_original_message(components=[container])

    @Cog.listener("on_dropdown")
    async def on_period_select(self, inter: MessageInteraction):
        if inter.component.custom_id != PERIOD_CUSTOM_ID:
            return
        period = inter.values[0]
        cfg = await self.bot.get_cfg()
        await inter.response.edit_message(
            components=[build_loading_container(period, cfg.embed_color)]
        )
        container = await self._build_stats(inter.guild_id, inter.author.id, period, cfg.embed_color)
        await inter.edit_original_response(components=[container])

    async def _build_stats(self, guild_id: int, user_id: int, period: str, accent: int):
        from_dt, to_dt = _period_window(period)
        entries = await self.bot.db.activity.get_leaderboard(
            guild_id=guild_id, from_dt=from_dt, to_dt=to_dt, limit=10,
        )
        user_data = await self.bot.db.activity.get_user_total(
            guild_id=guild_id, user_id=user_id, from_dt=from_dt, to_dt=to_dt,
        )
        user_total = (user_data or {}).get("total_seconds", 0)
        return build_stats_container(
            entries=entries,
            period=period,
            user_id=user_id,
            user_total=user_total,
            accent=accent,
        )
