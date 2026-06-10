from __future__ import annotations

import asyncio

from hydra_shared.bot_base import HydraBot, run_bot
from hydra_shared.config import ServiceSettings
from hydra_shared.core_client import fetch_primary_guild_id
from hydra_shared.events.topics import CORE_CONFIG_CHANGED
from hydra_shared.logging import configure_logging, get_logger

from src.data import ActivityConfig

SERVICE_NAME = "activity-bot"
COGS = [
    "src.cogs.voice_tracker",
    "src.cogs.activity",
    "src.cogs.debug",
]


class ActivityBot(HydraBot):
    def __init__(self, settings: ServiceSettings, *, primary_guild_id: int | None = None):
        super().__init__(settings, primary_guild_id=primary_guild_id)
        self._guild_cfg: ActivityConfig | None = None
        self._rewarm_task: asyncio.Task | None = None
        self.logger = get_logger(SERVICE_NAME)

    async def get_cfg(self) -> ActivityConfig:
        gid = self.primary_guild_id
        if gid is None:
            return ActivityConfig(guild_id=0)
        raw = await self.core.get_guild_config(gid)
        cfg = ActivityConfig.model_validate(raw.model_dump())
        self._guild_cfg = cfg
        return cfg

    async def on_ready(self):
        await super().on_ready()
        try:
            await self.get_cfg()
        except Exception as e:
            self.logger.warning("guild_config_prefetch_failed", error=str(e))
        self._rewarm_task = asyncio.create_task(self._rewarm_on_invalidation())

    async def _rewarm_on_invalidation(self):
        async for payload in self.bus.subscribe(CORE_CONFIG_CHANGED):
            if int(payload.get("guild_id", 0)) == self.primary_guild_id:
                try:
                    cfg = await self.get_cfg()
                    await self._apply_status(cfg)
                    self.logger.info("config_rewarmed")
                except Exception as e:
                    self.logger.warning("config_rewarm_failed", error=str(e))

    async def close(self):
        if self._rewarm_task:
            self._rewarm_task.cancel()
        await super().close()


async def run() -> None:
    settings = ServiceSettings(service_name=SERVICE_NAME)
    configure_logging(SERVICE_NAME, settings.log_level)
    log = get_logger(SERVICE_NAME)

    if not settings.discord_token:
        log.error("missing_discord_token")
        return

    primary_guild_id = await fetch_primary_guild_id(settings.core_url)
    if primary_guild_id is None:
        log.warning("primary_guild_unresolved", core_url=settings.core_url)

    bot = ActivityBot(settings, primary_guild_id=primary_guild_id)
    bot.error_handler.install(bot)
    for cog in COGS:
        bot.load_extension(cog)

    log.info("starting", service=SERVICE_NAME, cogs=COGS)
    await bot.start(settings.discord_token)
