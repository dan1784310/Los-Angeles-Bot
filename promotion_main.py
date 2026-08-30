"""
Promotion System Module
Contains the promotion slash command and card display functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional


# ==========================================
# CONFIGURATION
# ==========================================

# Anyone with this role, or a role positioned higher than it in the server's
# role hierarchy, can use /promote — no administrator permission
# required for that.
PROMOTION_ROLE_ID = 1539201630161993728

# Channel to automatically send promotion embeds to
PROMOTION_CHANNEL_ID = 1526898908272263209


def _can_issue_promotion(interaction: discord.Interaction) -> bool:
    """Server owner, administrators, or anyone whose top role is at or above
    PROMOTION_ROLE_ID in the role hierarchy."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return True

    required_role = interaction.guild.get_role(PROMOTION_ROLE_ID)
    if not required_role:
        return False

    return interaction.user.top_role >= required_role


# ==========================================
# PROMOTION COG
# ==========================================

class PromotionSystem(commands.Cog):
    """Main promotion system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    # ==========================================
    # PROMOTION COMMAND
    # ==========================================
    
    @app_commands.command(name="promote", description="Promote a staff member to a new rank")
    @app_commands.describe(
        user="The user to promote",
        rank="The rank to assign to the user",
        reason="The reason for the promotion",
        notes="Additional notes for the promotion (optional)"
    )
    async def promote(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        rank: str,
        reason: str,
        notes: Optional[str] = None
    ):
        """Promote a staff member to a new rank."""
        
        # Check permissions
        if not _can_issue_promotion(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to issue promotions.",
                ephemeral=True
            )
            return
        
        # Defer response
        await interaction.response.defer(ephemeral=True)
        
        # Set default notes if not provided
        final_notes = notes if notes else "N/A"
        
        # Get the target channel
        target_channel = interaction.guild.get_channel(PROMOTION_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send(
                "❌ Could not find the promotion channel.",
                ephemeral=True
            )
            return
        
        # Try to find and assign the role
        role_assigned = False
        assigned_role = None
        
        # Search for role by name (case-insensitive)
        print(f"[PROMOTION] Searching for role: '{rank}'")
        print(f"[PROMOTION] Available roles: {[role.name for role in interaction.guild.roles]}")
        
        for role in interaction.guild.roles:
            if role.name.lower() == rank.lower():
                try:
                    await user.add_roles(role)
                    role_assigned = True
                    assigned_role = role
                    print(f"[PROMOTION] Assigned role '{role.name}' (ID: {role.id}) to {user.display_name}")
                    break
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"❌ I don't have permission to assign the role '{role.name}'.",
                        ephemeral=True
                    )
                    return
                except Exception as e:
                    print(f"[PROMOTION] Error assigning role: {e}")
                    await interaction.followup.send(
                        f"❌ Error assigning role: {e}",
                        ephemeral=True
                    )
                    return
        
        if not role_assigned:
            print(f"[PROMOTION] Could not find role matching '{rank}'")
            await interaction.followup.send(
                f"⚠️ Could not find a role matching '{rank}'. Available roles: {', '.join([r.name for r in interaction.guild.roles[:10]])}...",
                ephemeral=True
            )
        
        # Create promotion card
        try:
            await self._create_promotion_card(
                target_channel,
                interaction.user,  # promoter
                user,  # recipient
                rank,
                reason,
                final_notes
            )
            
            role_status = f" and assigned the role {assigned_role.mention}" if role_assigned else ""
            await interaction.followup.send(
                f"✅ Promotion issued successfully to {user.mention}{role_status}!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating promotion card: {e}")
            await interaction.followup.send(
                f"❌ Error creating promotion card: {e}",
                ephemeral=True
            )
    
    async def _create_promotion_card(
        self,
        channel: discord.TextChannel,
        promoter: discord.Member,
        recipient: discord.Member,
        rank: str,
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
            name=f"Signed, {promoter.display_name}",
            icon_url=promoter.display_avatar.url
        )
        
        # Thumbnail pins the recipient profile picture to the top right
        embed.set_thumbnail(url=recipient.display_avatar.url)
        
        # Format N/A with backticks for the inline box style
        formatted_notes = f"`{notes}`" if notes == "N/A" else notes
        
        # Build description with bold bullet points and single-line spacing
        description = f"- **User:** {recipient.mention}\n"
        description += f"- **Updated Rank:** {rank}\n"
        description += f"- **Reason:** {reason}\n"
        description += f"- **Notes:** {formatted_notes}"
        
        embed.description = description
        
        await channel.send(content=f"{recipient.mention}", embed=embed)


async def setup(bot: commands.Bot):
    """Setup the promotion cog."""
    await bot.add_cog(PromotionSystem(bot))
