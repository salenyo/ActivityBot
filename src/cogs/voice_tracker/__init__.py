from __future__ import annotations

from datetime import datetime, timezone

from disnake import CategoryChannel, Member, VoiceState
from disnake.ext.commands import AutoShardedBot, Cog

from hydra_shared.logging import get_logger

log = get_logger(__name__)

UTC = timezone.utc
MIN_SESSION_SECONDS = 30
_KEY = "activity:voice:{user_id}"


class VoiceTracker(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def cog_load(self):
        self.bot.loop.create_task(self._sync_on_ready())

    async def _sync_on_ready(self):
        await self.bot.wait_until_ready()
        await self._sync_active_members()

    def _redis_key(self, user_id: int) -> str:
        return _KEY.format(user_id=user_id)

    def _is_tracked(self, channel, cfg) -> bool:
        if cfg.activity_tracked_category_id is None:
            return False
        if channel.category_id != cfg.activity_tracked_category_id:
            return False
        if channel.id in (cfg.activity_excluded_channel_ids or []):
            return False
        return True

    async def _handle_join(self, member: Member, channel) -> None:
        key = self._redis_key(member.id)
        existing = await self.bot.redis.get(key)
        if not existing:
            ts = str(int(datetime.now(UTC).timestamp()))
            await self.bot.redis.set(key, ts)
            log.debug("voice_join_tracked", user_id=member.id, channel_id=channel.id)

    async def _handle_leave(self, member: Member, channel) -> None:
        key = self._redis_key(member.id)
        joined_ts = await self.bot.redis.get(key)
        if joined_ts is None:
            return
        await self.bot.redis.delete(key)

        joined_at = datetime.fromtimestamp(int(joined_ts), UTC)
        left_at = datetime.now(UTC)
        duration = int((left_at - joined_at).total_seconds())

        if duration < MIN_SESSION_SECONDS:
            return

        try:
            await self.bot.db.activity.add_session(
                user_id=member.id,
                channel_id=channel.id,
                guild_id=member.guild.id,
                joined_at=joined_at,
                left_at=left_at,
                duration_seconds=duration,
            )
            log.debug("voice_session_saved", user_id=member.id, duration=duration)
        except Exception as e:
            log.error("voice_session_save_failed", user_id=member.id, error=str(e))

    async def _sync_active_members(self) -> None:
        try:
            cfg = await self.bot.get_cfg()
        except Exception:
            return
        if cfg.activity_tracked_category_id is None:
            return

        guild = self.bot.get_guild(self.bot.primary_guild_id)
        if guild is None:
            return

        category = guild.get_channel(cfg.activity_tracked_category_id)
        if not isinstance(category, CategoryChannel):
            return

        now_ts = str(int(datetime.now(UTC).timestamp()))
        excluded = set(cfg.activity_excluded_channel_ids or [])
        for channel in category.voice_channels:
            if channel.id in excluded:
                continue
            for member in channel.members:
                if member.bot:
                    continue
                key = self._redis_key(member.id)
                if not await self.bot.redis.exists(key):
                    await self.bot.redis.set(key, now_ts)

        log.info("voice_tracker_synced")

    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState):
        if member.bot:
            return

        try:
            cfg = await self.bot.get_cfg()
        except Exception:
            return

        if before.channel and self._is_tracked(before.channel, cfg):
            await self._handle_leave(member, before.channel)

        if after.channel and self._is_tracked(after.channel, cfg):
            await self._handle_join(member, after.channel)


def setup(bot: AutoShardedBot) -> None:
    bot.add_cog(VoiceTracker(bot))
