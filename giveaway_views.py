"""
Giveaway Views Module
Contains all Components V2 UI components for the giveaway system.
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
# ENTRY CONFIRMATION VIEW (COMPONENTS V2)
# ==========================================

def build_entry_confirmation_view(prize: str, winners: int, end_timestamp: int) -> discord.ui.LayoutView:
    """Build a Components V2 view for entry confirmation."""
    view = discord.ui.LayoutView(timeout=None)
    
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(34, 197, 94)
    )
    
    # Success header
    container.add_item(
        discord.ui.TextDisplay(
            "✅ You have successfully entered this giveaway!"
        )
    )
    
    container.add_item(discord.ui.Separator())
    
    # Prize info
    container.add_item(
        discord.ui.TextDisplay(
            f"🎁 {prize}"
        )
    )
    
    # Winners info
    container.add_item(
        discord.ui.TextDisplay(
            f"🏆 Winners: {winners}"
        )
    )
    
    # End time
    container.add_item(
        discord.ui.TextDisplay(
            f"⏰ Ends: <t:{end_timestamp}:R>"
        )
    )
    
    container.add_item(discord.ui.Separator())
    
    # Footer
    container.add_item(
        discord.ui.TextDisplay(
            "Good luck! 🍀"
        )
    )
    
    view.add_item(container)
    
    return view


# ==========================================
# ALREADY ENTERED VIEW (COMPONENTS V2)
# ==========================================

def build_already_entered_view() -> discord.ui.LayoutView:
    """Build a Components V2 view for already entered message."""
    view = discord.ui.LayoutView(timeout=None)
    
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(59, 130, 246)
    )
    
    container.add_item(
        discord.ui.TextDisplay(
            "ℹ️ You're already participating in this giveaway."
        )
    )
    
    container.add_item(discord.ui.Separator())
    
    container.add_item(
        discord.ui.TextDisplay(
            "Good luck! 🍀"
        )
    )
    
    view.add_item(container)
    
    return view


# ==========================================
# REQUIREMENT FAILED VIEW (COMPONENTS V2)
# ==========================================

def build_requirement_failed_view(reason: str) -> discord.ui.LayoutView:
    """Build a Components V2 view for requirement failure."""
    view = discord.ui.LayoutView(timeout=None)
    
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(239, 68, 68)
    )
    
    container.add_item(
        discord.ui.TextDisplay(
            "❌ You can't enter this giveaway."
        )
    )
    
    container.add_item(discord.ui.Separator())
    
    container.add_item(
        discord.ui.TextDisplay(
            f"Reason:\n{reason}"
        )
    )
    
    view.add_item(container)
    
    return view


# ==========================================
# WINNER DM VIEW (COMPONENTS V2)
# ==========================================

def build_winner_dm_view(prize: str, custom_message: Optional[str] = None) -> discord.ui.LayoutView:
    """Build a Components V2 view for winner DM."""
    view = discord.ui.LayoutView(timeout=None)
    
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(168, 85, 247)
    )
    
    container.add_item(
        discord.ui.TextDisplay(
            "🎉 Congratulations!"
        )
    )
    
    container.add_item(discord.ui.Separator())
    
    container.add_item(
        discord.ui.TextDisplay(
            f"You won:\n{prize}"
        )
    )
    
    if custom_message:
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                custom_message
            )
        )
    
    view.add_item(container)
    
    return view
