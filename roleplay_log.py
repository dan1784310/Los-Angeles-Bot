"""
Roleplay Log Module
Contains the /roleplay-log slash command for logging completed roleplay sessions.
"""

import discord
from discord import app_commands
from discord.ext import commands


# ==========================================
# CONFIGURATION
# ==========================================

# Anyone with this role, or a role positioned higher than it in the server's
# role hierarchy, can use /roleplay-log — no administrator permission
# required for that.
# TODO: replace with the actual role ID.
ROLEPLAY_LOG_ROLE_ID = 1539180003605086269

# Channel to automatically send roleplay log embeds to.
# TODO: replace with the actual channel ID.
ROLEPLAY_LOG_CHANNEL_ID = 1540428444599582834

TIME_CHOICES = [
    "30 mins",
    "45 mins",
    "1 hour",
    "1h 30 mins",
    "2 hours"
]


def _can_log_roleplay(interaction: discord.Interaction) -> bool:
    """Server owner, administrators, or anyone whose top role is at or above
    ROLEPLAY_LOG_ROLE_ID in the role hierarchy."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return True

    required_role = interaction.guild.get_role(ROLEPLAY_LOG_ROLE_ID)
    if not required_role:
        return False

    return interaction.user.top_role >= required_role


# ==========================================
# ROLEPLAY LOG COG
# ==========================================

class RoleplayLog(commands.Cog):
    """Slash command for logging completed roleplay sessions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="roleplay-log", description="Log a completed roleplay session")
    @app_commands.describe(
        user="The primary user involved in the roleplay",
        team_members="Other team members involved",
        time="How long the roleplay session lasted",
        type="The type of roleplay"
    )
    @app_commands.choices(time=[
        app_commands.Choice(name=choice, value=choice) for choice in TIME_CHOICES
    ])
    async def roleplay_log(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        team_members: str,
        time: app_commands.Choice[str],
        type: str
    ):
        """Log a completed roleplay session."""

        # Check permissions
        if not _can_log_roleplay(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        target_channel = interaction.guild.get_channel(ROLEPLAY_LOG_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send(
                "❌ Could not find the roleplay log channel.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Roleplay log",
            color=discord.Color.from_rgb(37, 37, 41),
            timestamp=discord.utils.utcnow()
        )

        # "logged by @user" line above the title, with the server's icon as
        # the small circular avatar next to it
        guild_icon_url = interaction.guild.icon.url if interaction.guild.icon else None
        embed.set_author(
            name=f"logged by @{interaction.user.display_name}",
            icon_url=guild_icon_url
        )

        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Team members", value=team_members, inline=False)
        embed.add_field(name="Time", value=time.value, inline=False)
        embed.add_field(name="Type", value=type, inline=False)

        try:
            await target_channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to send messages in the roleplay log channel.",
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error sending roleplay log: {e}",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"✅ Roleplay log sent to {target_channel.mention}!",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    """Setup the roleplay log cog."""
    await bot.add_cog(RoleplayLog(bot))
