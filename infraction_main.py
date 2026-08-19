"""
Infraction System Module
Contains the infraction slash command and card display functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime, timedelta


# ==========================================
# CONFIGURATION
# ==========================================

INFRACTION_ACTIONS = [
    "Activity Notice",
    "Verbal Warning", 
    "Warning",
    "Strike",
    "Demotion",
    "Termination",
    "Staff Blacklist",
    "Under Investigation",
    "Suspension"
]


# ==========================================
# INFRACTION COG
# ==========================================

class InfractionSystem(commands.Cog):
    """Main infraction system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    # ==========================================
    # INFRACTION COMMAND GROUP
    # ==========================================
    
    infraction = app_commands.Group(name="infraction", description="Infraction commands")
    
    @infraction.command(name="issue", description="Issue an infraction to a staff member")
    @app_commands.describe(
        staff="The staff member to issue the infraction to",
        action="The type of infraction action",
        reason="The reason for the infraction",
        expiration="Expiration time (e.g., 10m, 10h, 10d, 10w)",
        notes="Additional notes for the infraction",
        channel="Channel to send the infraction to"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Activity Notice", value="Activity Notice"),
        app_commands.Choice(name="Verbal Warning", value="Verbal Warning"),
        app_commands.Choice(name="Warning", value="Warning"),
        app_commands.Choice(name="Strike", value="Strike"),
        app_commands.Choice(name="Demotion", value="Demotion"),
        app_commands.Choice(name="Termination", value="Termination"),
        app_commands.Choice(name="Staff Blacklist", value="Staff Blacklist"),
        app_commands.Choice(name="Under Investigation", value="Under Investigation"),
        app_commands.Choice(name="Suspension", value="Suspension")
    ])
    async def issue_infraction(
        self,
        interaction: discord.Interaction,
        staff: discord.Member,
        action: str,
        reason: str,
        expiration: Optional[str] = None,
        notes: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None
    ):
        """Issue an infraction to a staff member."""
        
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to issue infractions.",
                ephemeral=True
            )
            return
        
        # Defer response
        await interaction.response.defer(ephemeral=True)
        
        # Validate action
        if action not in INFRACTION_ACTIONS:
            await interaction.followup.send(
                f"❌ Invalid action. Valid actions: {', '.join(INFRACTION_ACTIONS)}",
                ephemeral=True
            )
            return
        
        # Parse expiration if provided
        expiration_timestamp = None
        if expiration:
            try:
                expiration_timestamp = self._parse_expiration(expiration)
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid expiration format. Use formats like: 10m, 10h, 10d, 10w",
                    ephemeral=True
                )
                return
        
        # Set default notes if not provided
        final_notes = notes if notes else "N/A"
        
        # Determine target channel
        target_channel = channel or interaction.channel
        
        # Create infraction card
        try:
            await self._create_infraction_card(
                target_channel,
                interaction.user,  # issuer
                staff,  # recipient
                action,
                reason,
                final_notes,
                expiration_timestamp
            )
            
            await interaction.followup.send(
                f"✅ Infraction issued successfully to {staff.mention} in {target_channel.mention}!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating infraction card: {e}")
            await interaction.followup.send(
                f"❌ Error creating infraction card: {e}",
                ephemeral=True
            )
    
    def _parse_expiration(self, expiration_str: str) -> float:
        """Parse expiration string to timestamp."""
        expiration_str = expiration_str.lower().strip()
        
        if expiration_str.endswith('m'):
            return (datetime.now() + timedelta(minutes=int(expiration_str[:-1]))).timestamp()
        elif expiration_str.endswith('h'):
            return (datetime.now() + timedelta(hours=int(expiration_str[:-1]))).timestamp()
        elif expiration_str.endswith('d'):
            return (datetime.now() + timedelta(days=int(expiration_str[:-1]))).timestamp()
        elif expiration_str.endswith('w'):
            return (datetime.now() + timedelta(weeks=int(expiration_str[:-1]))).timestamp()
        else:
            raise ValueError("Invalid expiration format")
    
    async def _create_infraction_card(
        self,
        channel: discord.TextChannel,
        issuer: discord.Member,
        recipient: discord.Member,
        action: str,
        reason: str,
        notes: str,
        expiration_timestamp: Optional[float] = None
    ):
        """Create the infraction card using Components V2 layout."""
        
        # Format N/A with backticks for the box style unless custom notes were provided
        formatted_notes = f"`{notes}`" if notes == "N/A" else notes

        # Header / Author line
        content = f"Signed, {issuer.display_name}\n\n"
        content += "### Staff Consequences & Discipline\n\n"

        # Bullet points with bold labels
        content += f"• **Staff Member:** {recipient.mention}\n"
        content += f"• **Action:** {action}\n"
        content += f"• **Reason:** {reason}\n"

        if expiration_timestamp:
            expiration_text = f"<t:{int(expiration_timestamp)}:R>"
            content += f"• **Expiration:** {expiration_text}\n"

        content += f"• **Notes:** {formatted_notes}"

        # Build Components V2 view
        view = discord.ui.LayoutView(timeout=None)
        
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )

        # Main text section with user avatar thumbnail on the right
        section = discord.ui.Section(
            discord.ui.TextDisplay(content),
            accessory=discord.ui.Thumbnail(media=recipient.display_avatar.url) if recipient.display_avatar else None
        )

        container.add_item(section)
        view.add_item(container)

        await channel.send(view=view)


async def setup(bot: commands.Bot):
    """Setup the infraction cog."""
    await bot.add_cog(InfractionSystem(bot))