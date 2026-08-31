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

# Anyone with this role, or a role positioned higher than it in the server's
# role hierarchy, can use /infraction issue — no administrator permission
# required for that.
INFRACTION_ROLE_ID = 1539201630161993728

# Channel to automatically send infraction embeds to
INFRACTION_CHANNEL_ID = 1526898975704350822

# Role ID required to use the Void button
VOID_ROLE_ID = 1527051014992040106


def _can_issue_infraction(interaction: discord.Interaction) -> bool:
    """Server owner, administrators, or anyone whose top role is at or above
    INFRACTION_ROLE_ID in the role hierarchy."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return True

    required_role = interaction.guild.get_role(INFRACTION_ROLE_ID)
    if not required_role:
        return False

    return interaction.user.top_role >= required_role


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
        if not _can_issue_infraction(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to issue infractions.",
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
        
        # Get the target channel
        target_channel = interaction.guild.get_channel(INFRACTION_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send(
                "❌ Could not find the infraction channel.",
                ephemeral=True
            )
            return
        
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
        
        # Build description with bold bullet points and single-line spacing
        description = f"• **Staff Member:** {recipient.mention}\n"
        description += f"• **Action:** {action}\n"
        description += f"• **Reason:** {reason}\n"
        
        if expiration_timestamp:
            expiration_text = f"<t:{int(expiration_timestamp)}:R>"
            description += f"• **Expiration:** {expiration_text}\n"
            
        description += f"• **Notes:** {formatted_notes}"
        
        embed.description = description
        
        # Store embed data for void functionality
        class VoidView(discord.ui.View):
            def __init__(self, original_embed):
                super().__init__()
                self.original_embed = original_embed
            
            @discord.ui.button(label="Void", style=discord.ButtonStyle.danger, emoji="🔴")
            async def void_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Check permissions
                void_role = interaction.guild.get_role(VOID_ROLE_ID)
                if not void_role or interaction.user.top_role < void_role:
                    await interaction.response.send_message("You don't have permission to use this button.", ephemeral=True)
                    return
                
                # Update embed
                self.original_embed.title = f"Voided by {interaction.user.display_name}"
                self.original_embed.color = discord.Color.red()
                
                # Disable button and update message
                button.disabled = True
                button.label = "Voided"
                
                await interaction.response.edit_message(embed=self.original_embed, view=self)
        
        # Send message with view
        message = await channel.send(content=f"{recipient.mention}", embed=embed, view=VoidView(embed))
    
    @commands.command(name="m")
    @commands.has_permissions(administrator=True)
    async def message_command(self, ctx: commands.Context, *, message: str):
        """Send a message as the bot (direct send, not a reply)."""
        await ctx.send(message)
        await ctx.message.delete()


async def setup(bot: commands.Bot):
    """Setup the infraction cog."""
    await bot.add_cog(InfractionSystem(bot))