from disnake.ext.commands import AutoShardedBot

from .commands import ContestCommands


def setup(bot: AutoShardedBot) -> None:
    bot.add_cog(ContestCommands(bot))
