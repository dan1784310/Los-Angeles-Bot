"""
Infraction System Module
Contains the infraction slash command and card display functionality.
Also contains promotion system.
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

PROMOTION_CHANNEL_ID = 1526898908272263209  # Channel to send promotions to
INFRACTION_CHANNEL_ID = 1526898975704350822  # Channel to send infractions to


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
        notes="Additional notes for the infraction"
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
        notes: Optional[str] = None
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
        
        # Get the infraction channel
        infraction_channel = interaction.guild.get_channel(INFRACTION_CHANNEL_ID)
        if not infraction_channel:
            await interaction.followup.send(
                "❌ Could not find the infraction channel.",
                ephemeral=True
            )
            return
        
        # Create infraction card
        try:
            await self._create_infraction_card(
                infraction_channel,
                interaction.user,  # issuer
                staff,  # recipient
                action,
                reason,
                final_notes,
                expiration_timestamp
            )
            
            await interaction.followup.send(
                f"✅ Infraction issued successfully to {staff.mention}!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating infraction card: {e}")
            await interaction.followup.send(
                f"❌ Error creating infraction card: {e}",
                ephemeral=True
            )
    
    # ==========================================
    # PROMOTION COMMAND
    # ==========================================
    
    @app_commands.command(name="promote", description="Promote a staff member")
    @app_commands.describe(
        user="The user to promote",
        updated_rank="The new role to assign",
        reason="The reason for the promotion",
        notes="Additional notes (optional)"
    )
    async def promote(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        updated_rank: discord.Role,
        reason: str,
        notes: Optional[str] = None
    ):
        """Promote a staff member."""
        
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to promote members.",
                ephemeral=True
            )
            return
        
        # Defer response
        await interaction.response.defer(ephemeral=True)
        
        # Set default notes if not provided
        final_notes = notes if notes else "N/A"
        
        # Get the promotion channel
        promotion_channel = interaction.guild.get_channel(PROMOTION_CHANNEL_ID)
        if not promotion_channel:
            await interaction.followup.send(
                "❌ Could not find the promotion channel.",
                ephemeral=True
            )
            return
        
        # Create promotion card
        try:
            await self._create_promotion_card(
                promotion_channel,
                interaction.user,  # issuer
                user,  # promoted user
                updated_rank,
                reason,
                final_notes
            )
            
            await interaction.followup.send(
                f"✅ Promotion sent for {user.mention} to {updated_rank.mention}!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating promotion card: {e}")
            await interaction.followup.send(
                f"❌ Error creating promotion card: {e}",
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
        """Create the infraction card matching the exact image layout."""
        
        # Create embed with dark charcoal accent
        embed = discord.Embed(
            title="Staff Consequences & Discipline",
            color=discord.Color.from_rgb(37, 37, 41)
        )
        
        # Author field creates the exact small pfp circle next to the sign-off text
        embed.set_author(
            name=f"Signed, {issuer.display_name}",
            icon_url=issuer.display_avatar.url
        )
        
        # Thumbnail pins the recipient profile picture to the top right
        embed.set_thumbnail(url=recipient.display_avatar.url)
        
        # Format N/A with backticks for the inline box style
        formatted_notes = f"`{notes}`" if notes == "N/A" else notes
        
        # Build description with bold bullet points and extra spacing
        description = f"• **Staff Member:** {recipient.mention}\n\n"
        description += f"• **Action:** {action}\n\n"
        description += f"• **Reason:** {reason}\n\n"
        
        if expiration_timestamp:
            expiration_text = f"<t:{int(expiration_timestamp)}:R>"
            description += f"• **Expiration:** {expiration_text}\n\n"
            
        description += f"• **Notes:** {formatted_notes}"
        
        embed.description = description
        
        await channel.send(embed=embed)
    
    async def _create_promotion_card(
        self,
        channel: discord.TextChannel,
        issuer: discord.Member,
        promoted_user: discord.Member,
        new_role: discord.Role,
        reason: str,
        notes: str
    ):
        """Create the promotion card matching the exact infraction layout."""
        
        # Create embed with dark charcoal accent
        embed = discord.Embed(
            title="Staff Promotion",
            color=discord.Color.from_rgb(37, 37, 41)
        )
        
        # Author field creates the exact small pfp circle next to the sign-off text
        embed.set_author(
            name=f"Signed, {issuer.display_name}",
            icon_url=issuer.display_avatar.url
        )
        
        # Thumbnail pins the promoted user profile picture to the top right
        embed.set_thumbnail(url=promoted_user.display_avatar.url)
        
        # Format N/A with backticks for the inline box style
        formatted_notes = f"`{notes}`" if notes == "N/A" else notes
        
        # Build description with bold bullet points and extra spacing
        description = f"• **User:** {promoted_user.mention}\n\n"
        description += f"• **Updated Rank:** {new_role.mention}\n\n"
        description += f"• **Reason:** {reason}\n\n"
        description += f"• **Notes:** {formatted_notes}"
        
        embed.description = description
        
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    """Setup the infraction cog."""
    await bot.add_cog(InfractionSystem(bot))