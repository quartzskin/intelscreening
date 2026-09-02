import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from bot import api_client

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {GUILD_ID}")
    else:
        await bot.tree.sync()
        print("Slash commands synced globally (may take up to 1 hour)")


@bot.event
async def on_member_join(member: discord.Member):
    try:
        cfg = await api_client.get_config()
    except Exception:
        return
    test_channel_id = cfg.get("test_channel_id", "").strip()
    if test_channel_id:
        channel = member.guild.get_channel(int(test_channel_id))
        if channel:
            try:
                await channel.send(
                    f"Welcome {member.mention}! Please use **/test** to complete the intelligence screening "
                    f"to gain full access to the server."
                )
            except discord.Forbidden:
                pass


async def load_cogs():
    await bot.load_extension("bot.cogs.test")
    await bot.load_extension("bot.cogs.admin")


async def main():
    async with bot:
        await load_cogs()
        try:
            await bot.start(DISCORD_TOKEN)
        finally:
            await api_client.close_client()


if __name__ == "__main__":
    asyncio.run(main())
