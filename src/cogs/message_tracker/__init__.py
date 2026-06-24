"""Пишет метаданные каждого сообщения гильдии (автор, канал, дата) для подсчёта активности; содержимое не сохраняем."""
from __future__ import annotations

import disnake
from disnake.ext.commands import AutoShardedBot, Cog

from hydra_shared.logging import get_logger

log = get_logger(__name__)


class MessageTracker(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot or message.guild is None:
            return
        try:
            await self.bot.db.activity.add_message(
                user_id=message.author.id,
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                sent_at=message.created_at,
            )
        except Exception as e:  # noqa: BLE001 — учёт сообщений не должен влиять на бота
            log.debug("message_log_failed", user_id=message.author.id, error=str(e))


def setup(bot: AutoShardedBot) -> None:
    bot.add_cog(MessageTracker(bot))
