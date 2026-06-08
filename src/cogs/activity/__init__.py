from disnake.ext.commands import AutoShardedBot

from .commands import ActivityCommands


def setup(bot: AutoShardedBot) -> None:
    bot.add_cog(ActivityCommands(bot))
