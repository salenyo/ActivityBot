from __future__ import annotations

from hydra_shared.bot_base import ConfiguredBot, run_bot

from src.data import ActivityConfig

SERVICE_NAME = "activity-bot"
COGS = [
    "src.cogs.voice_tracker",
    "src.cogs.activity",
    "src.cogs.contest",
    "src.cogs.debug",
]


class ActivityBot(ConfiguredBot):
    config_cls = ActivityConfig


async def run() -> None:
    await run_bot(SERVICE_NAME, COGS, ActivityBot)
