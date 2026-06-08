from disnake import ApplicationCommandInteraction
from disnake.ext.commands import AutoShardedBot, Cog, CommandError

from hydra_shared.logging import get_logger

log = get_logger(__name__)


class ErrorLogger(Cog):
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @Cog.listener()
    async def on_slash_command_error(self, inter: ApplicationCommandInteraction, error: CommandError):
        log.error("slash_command_error", command=inter.application_command.name, error=str(error))
        try:
            await inter.response.send_message(
                "Произошла ошибка при выполнении команды.", ephemeral=True
            )
        except Exception:
            pass


def setup(bot: AutoShardedBot) -> None:
    bot.add_cog(ErrorLogger(bot))
