"""
Giveaway Views Module
Contains all UI components for the giveaway system.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Callable
import random


# ==========================================
# GIVEAWAY ENTRY BUTTON
# ==========================================

class EnterGiveawayButton(discord.ui.Button):
    """Button for entering a giveaway."""
    
    def __init__(self, giveaway_id: str, on_enter_callback: Optional[Callable] = None):
        super().__init__(
            label="🎉 Enter Giveaway",
            style=discord.ButtonStyle.green,
            custom_id=f"giveaway_enter_{giveaway_id}"
        )
        self.giveaway_id = giveaway_id
        self.on_enter_callback = on_enter_callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.on_enter_callback:
            await self.on_enter_callback(interaction, self.giveaway_id)


# ==========================================
# GIVEAWAY VIEW (PERSISTENT)
# ==========================================

class GiveawayView(discord.ui.View):
    """Persistent view for giveaway interactions."""
    
    def __init__(self, giveaway_id: str, on_enter_callback: Optional[Callable] = None):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.add_item(EnterGiveawayButton(giveaway_id, on_enter_callback))


# ==========================================
# ENDED GIVEAWAY VIEW
# ==========================================

class EndedGiveawayView(discord.ui.View):
    """View for ended giveaways (disabled button)."""
    
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="🎉 Giveaway Ended",
                style=discord.ButtonStyle.gray,
                disabled=True,
                custom_id="giveaway_ended"
            )
        )


# ==========================================
# ENTRY CONFIRMATION EMBED
# ==========================================

def build_entry_confirmation_embed(prize: str, winners: int, end_timestamp: int) -> discord.Embed:
    """Build an embed for entry confirmation."""
    embed = discord.Embed(
        title="✅ Successfully Entered!",
        description="You have successfully entered this giveaway!",
        color=discord.Color.green()
    )
    embed.add_field(name="🎁 Prize", value=prize, inline=True)
    embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
    embed.add_field(name="⏰ Ends", value=f"<t:{end_timestamp}:R>", inline=True)
    embed.set_footer(text="Good luck! 🍀")
    return embed


# ==========================================
# ALREADY ENTERED EMBED
# ==========================================

def build_already_entered_embed() -> discord.Embed:
    """Build an embed for already entered message."""
    embed = discord.Embed(
        title="ℹ️ Already Entered",
        description="You're already participating in this giveaway.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Good luck! 🍀")
    return embed


# ==========================================
# REQUIREMENT FAILED EMBED
# ==========================================

def build_requirement_failed_embed(reason: str) -> discord.Embed:
    """Build an embed for requirement failure."""
    embed = discord.Embed(
        title="❌ Cannot Enter",
        description="You can't enter this giveaway.",
        color=discord.Color.red()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    return embed


# ==========================================
# WINNER DM EMBED
# ==========================================

def build_winner_dm_embed(prize: str, custom_message: Optional[str] = None) -> discord.Embed:
    """Build an embed for winner DM."""
    embed = discord.Embed(
        title="🎉 Congratulations!",
        description=f"You won:\n{prize}",
        color=discord.Color.purple()
    )
    if custom_message:
        embed.add_field(name="Message", value=custom_message, inline=False)
    return embed
