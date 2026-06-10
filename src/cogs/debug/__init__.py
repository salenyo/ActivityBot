from __future__ import annotations

import disnake
from disnake.ext import commands


class DebugCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(name="debug-error", description="[DEV] Тест DM error logger")
    async def debug_error(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        raise RuntimeError("Тестовая ошибка для проверки DM error logger")


def setup(bot: commands.Bot) -> None:
    bot.add_cog(DebugCog(bot))
