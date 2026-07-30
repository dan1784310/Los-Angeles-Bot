"""
Giveaway Main Module
Contains the main giveaway system cog with all commands and functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List
import asyncio
import random
from datetime import datetime, timedelta
import uuid

from giveaway_database import db
from giveaway_views import (
    GiveawayView, EndedGiveawayView,
    build_entry_confirmation_view, build_already_entered_view,
    build_requirement_failed_view, build_winner_dm_view
)


# ==========================================
# CONFIGURATION
# ==========================================

# Role IDs that are whitelisted to use giveaway commands
# Add your role IDs here
GIVEAWAY_WHITELIST_ROLES = [
    # Example: 123456789012345678
]


def is_giveaway_admin(user: discord.Member) -> bool:
    """Check if user has giveaway admin permissions."""
    # Check if user has any whitelisted role
    for role in user.roles:
        if role.id in GIVEAWAY_WHITELIST_ROLES:
            return True
    
    # Check if user has Manage Server permission
    if user.guild_permissions.manage_guild:
        return True
    
    return False


# ==========================================
# GIVEAWAY COG
# ==========================================

class GiveawaySystem(commands.Cog):
    """Main giveaway system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_timers = {}  # giveaway_id -> task
    
    # ==========================================
    # GIVEAWAY CREATE COMMAND
    # ==========================================
    
    @app_commands.command(name="giveaway_create", description="Create a new giveaway")
    @app_commands.describe(
        prize="The prize for the giveaway",
        ends="Duration (e.g., 10m, 2h, 3d, 1w)",
        winners="Number of winners",
        host="The user hosting the giveaway",
        channel="Channel to post the giveaway in",
        message="Custom message for the giveaway",
        winner_role="Role to give to winners",
        winner_dm="Message to DM winners",
        required_role="Role required to enter",
        bypass_role="Role that bypasses requirements"
    )
    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        prize: str,
        ends: str,
        winners: int,
        host: Optional[discord.Member] = None,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
        winner_role: Optional[discord.Role] = None,
        winner_dm: Optional[str] = None,
        required_role: Optional[discord.Role] = None,
        bypass_role: Optional[discord.Role] = None
    ):
        """Create a new giveaway."""
        
        # Check permissions
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Parse duration
        try:
            duration = self._parse_duration(ends)
            if duration <= 0:
                raise ValueError("Duration must be positive")
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Invalid duration format. Use formats like: 10m, 2h, 3d, 1w",
                ephemeral=True
            )
            return
        
        # Calculate end timestamp
        end_timestamp = (datetime.now() + duration).timestamp()
        
        # Determine channel
        target_channel = channel or interaction.channel
        
        # Determine host
        target_host = host or interaction.user
        
        # Generate giveaway ID
        giveaway_id = str(uuid.uuid4())
        
        # Create giveaway message
        try:
            giveaway_message = await self._create_giveaway_message(
                target_channel,
                prize,
                target_host,
                winners,
                int(end_timestamp),
                message,
                required_role,
                giveaway_id
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error creating giveaway message: {e}",
                ephemeral=True
            )
            return
        
        # Store in database
        success = db.create_giveaway(
            giveaway_id=giveaway_id,
            guild_id=interaction.guild.id,
            channel_id=target_channel.id,
            message_id=giveaway_message.id,
            creator_id=interaction.user.id,
            host_id=target_host.id,
            prize=prize,
            winners_amount=winners,
            end_timestamp=end_timestamp,
            giveaway_message=message,
            winner_role_id=winner_role.id if winner_role else None,
            winner_dm_message=winner_dm,
            required_role_id=required_role.id if required_role else None,
            requirement_bypass_role_id=bypass_role.id if bypass_role else None
        )
        
        if not success:
            await giveaway_message.delete()
            await interaction.followup.send(
                "❌ Error storing giveaway in database.",
                ephemeral=True
            )
            return
        
        # Start timer
        self._start_giveaway_timer(giveaway_id, end_timestamp)
        
        await interaction.followup.send(
            f"✅ Giveaway created successfully in {target_channel.mention}!",
            ephemeral=True
        )
    
    # ==========================================
    # GIVEAWAY REROLL COMMAND
    # ==========================================
    
    @app_commands.command(name="giveaway_reroll", description="Reroll giveaway winners")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def reroll_giveaway(self, interaction: discord.Interaction, message_id: str):
        """Reroll giveaway winners."""
        
        # Check permissions
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Parse message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid message ID format.",
                ephemeral=True
            )
            return
        
        # Get giveaway
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send(
                "❌ Could not find a giveaway with that Message ID.\nPlease provide the Message ID of a valid giveaway.",
                ephemeral=True
            )
            return
        
        # Get participants
        participants = db.get_participants(giveaway['giveaway_id'])
        previous_winners = db.get_winners(giveaway['giveaway_id'])
        
        if not participants:
            await interaction.followup.send(
                "❌ Could not reroll giveaway.\nReason: No valid participants found.",
                ephemeral=True
            )
            return
        
        # Select new winners (avoid previous winners if possible)
        available_participants = [p for p in participants if p not in previous_winners]
        
        if len(available_participants) < giveaway['winners_amount']:
            # Not enough unique participants, use all available
            new_winners = available_participants
        else:
            new_winners = random.sample(available_participants, giveaway['winners_amount'])
        
        if not new_winners:
            await interaction.followup.send(
                "❌ Could not reroll giveaway.\nReason: No valid participants found.",
                ephemeral=True
            )
            return
        
        # Clear previous winners and add new ones
        db.clear_winners(giveaway['giveaway_id'])
        for winner_id in new_winners:
            db.add_winner(giveaway['giveaway_id'], winner_id)
        
        # Get channel and message
        channel = self.bot.get_channel(giveaway['channel_id'])
        if not channel:
            await interaction.followup.send(
                "❌ Could not find the giveaway channel.",
                ephemeral=True
            )
            return
        
        try:
            message = await channel.fetch_message(giveaway['message_id'])
        except discord.NotFound:
            await interaction.followup.send(
                "❌ Could not find the giveaway message.",
                ephemeral=True
            )
            return
        
        # Update message with new winners
        await self._update_giveaway_message_with_winners(message, giveaway, new_winners)
        
        # Give winner role if configured
        if giveaway['winner_role_id']:
            await self._give_winner_role(channel.guild, new_winners, giveaway['winner_role_id'])
        
        # DM winners if configured
        if giveaway['winner_dm_message']:
            await self._dm_winners(new_winners, giveaway['prize'], giveaway['winner_dm_message'])
        
        await interaction.followup.send(
            f"✅ Giveaway rerolled successfully! {len(new_winners)} new winner(s) selected.",
            ephemeral=True
        )
    
    # ==========================================
    # GIVEAWAY END COMMAND
    # ==========================================
    
    @app_commands.command(name="giveaway_end", description="End a giveaway early")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def end_giveaway(self, interaction: discord.Interaction, message_id: str):
        """End a giveaway early."""
        
        # Check permissions
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Parse message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid message ID format.",
                ephemeral=True
            )
            return
        
        # Get giveaway
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send(
                "❌ Could not find a giveaway with that Message ID.\nPlease provide the Message ID of a valid giveaway.",
                ephemeral=True
            )
            return
        
        # Check if already ended
        if giveaway['status'] == 'ended':
            await interaction.followup.send(
                "❌ This giveaway has already ended.",
                ephemeral=True
            )
            return
        
        # Cancel timer if running
        if giveaway['giveaway_id'] in self.active_timers:
            self.active_timers[giveaway['giveaway_id']].cancel()
            del self.active_timers[giveaway['giveaway_id']]
        
        # End the giveaway
        await self._end_giveaway(giveaway['giveaway_id'])
        
        await interaction.followup.send(
            "✅ Giveaway ended successfully!",
            ephemeral=True
        )
    
    # ==========================================
    # GIVEAWAY DELETE COMMAND
    # ==========================================
    
    @app_commands.command(name="giveaway_delete", description="Delete a giveaway")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def delete_giveaway(self, interaction: discord.Interaction, message_id: str):
        """Delete a giveaway."""
        
        # Check permissions
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Parse message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid message ID format.",
                ephemeral=True
            )
            return
        
        # Get giveaway
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send(
                "❌ Could not delete giveaway.\nThe provided Message ID is not linked to a giveaway.",
                ephemeral=True
            )
            return
        
        # Cancel timer if running
        if giveaway['giveaway_id'] in self.active_timers:
            self.active_timers[giveaway['giveaway_id']].cancel()
            del self.active_timers[giveaway['giveaway_id']]
        
        # Delete message if possible
        try:
            channel = self.bot.get_channel(giveaway['channel_id'])
            if channel:
                message = await channel.fetch_message(giveaway['message_id'])
                await message.delete()
        except Exception:
            pass  # Message might already be deleted
        
        # Delete from database
        db.delete_giveaway(giveaway['giveaway_id'])
        
        await interaction.followup.send(
            "✅ Giveaway deleted successfully!",
            ephemeral=True
        )
    
    # ==========================================
    # BUTTON HANDLER
    # ==========================================
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions."""
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id")
        if not custom_id:
            return
        
        # Handle enter giveaway button
        if custom_id.startswith("giveaway_enter_"):
            giveaway_id = custom_id.replace("giveaway_enter_", "")
            await self._handle_enter_giveaway(interaction, giveaway_id)
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string to timedelta."""
        duration_str = duration_str.lower().strip()
        
        if duration_str.endswith('m'):
            minutes = int(duration_str[:-1])
            return timedelta(minutes=minutes)
        elif duration_str.endswith('h'):
            hours = int(duration_str[:-1])
            return timedelta(hours=hours)
        elif duration_str.endswith('d'):
            days = int(duration_str[:-1])
            return timedelta(days=days)
        elif duration_str.endswith('w'):
            weeks = int(duration_str[:-1])
            return timedelta(weeks=weeks)
        else:
            raise ValueError("Invalid duration format")
    
    async def _create_giveaway_message(
        self,
        channel: discord.TextChannel,
        prize: str,
        host: discord.Member,
        winners: int,
        end_timestamp: int,
        message: Optional[str],
        required_role: Optional[discord.Role],
        giveaway_id: str
    ) -> discord.Message:
        """Create the Components V2 giveaway message."""
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(139, 92, 246)
        )
        
        # Prize (main title)
        container.add_item(
            discord.ui.TextDisplay(f"🎉 {prize}")
        )
        
        container.add_item(discord.ui.Separator())
        
        # Host
        container.add_item(
            discord.ui.TextDisplay(f"Hosted by {host.mention}")
        )
        
        # Winners
        container.add_item(
            discord.ui.TextDisplay(f"🏆 Winners: {winners}")
        )
        
        # End time
        container.add_item(
            discord.ui.TextDisplay(f"⏰ Ends: <t:{end_timestamp}:R>")
        )
        
        # Custom message if provided
        if message:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(message)
            )
        
        # Requirements if provided
        if required_role:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.TextDisplay(f"📋 Requirement: {required_role.mention}")
            )
        
        container.add_item(discord.ui.Separator())
        
        # Entry count
        container.add_item(
            discord.ui.TextDisplay("🎟️ Entries: 0")
        )
        
        container.add_item(discord.ui.Separator())
        
        # Enter button with actual giveaway ID
        button_row = discord.ui.ActionRow()
        button_row.add_item(
            discord.ui.Button(
                label="🎉 Enter Giveaway",
                style=discord.ButtonStyle.green,
                custom_id=f"giveaway_enter_{giveaway_id}"
            )
        )
        container.add_item(button_row)
        
        view.add_item(container)
        
        message = await channel.send(view=view)
        return message
    
    async def _update_giveaway_entry_count(self, message_id: int, count: int):
        """Update the entry count in the giveaway message."""
        try:
            channel = self.bot.get_channel(
                db.get_giveaway_by_message_id(message_id)['channel_id']
            )
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            # Note: Components V2 messages can't be easily edited to update just text
            # For now, we'll skip this or implement a full message rebuild
        except Exception as e:
            print(f"Error updating entry count: {e}")
    
    async def _handle_enter_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle the enter giveaway button click."""
        
        # Get giveaway
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message(
                "❌ This giveaway no longer exists.",
                ephemeral=True
            )
            return
        
        # Check if giveaway is active
        if giveaway['status'] != 'active':
            await interaction.response.send_message(
                "❌ This giveaway has ended.",
                ephemeral=True
            )
            return
        
        # Check if already entered
        if db.has_participant(giveaway_id, interaction.user.id):
            await interaction.response.send_message(
                view=build_already_entered_view(),
                ephemeral=True
            )
            return
        
        # Check requirements
        if giveaway['required_role_id']:
            required_role = interaction.guild.get_role(giveaway['required_role_id'])
            has_bypass = False
            
            if giveaway['requirement_bypass_role_id']:
                bypass_role = interaction.guild.get_role(giveaway['requirement_bypass_role_id'])
                if bypass_role and bypass_role in interaction.user.roles:
                    has_bypass = True
            
            if not has_bypass and (not required_role or required_role not in interaction.user.roles):
                await interaction.response.send_message(
                    view=build_requirement_failed_view(
                        f"• You must have the {required_role.mention if required_role else 'required role'}."
                    ),
                    ephemeral=True
                )
                return
        
        # Add participant
        db.add_participant(giveaway_id, interaction.user.id)
        
        # Send confirmation
        await interaction.response.send_message(
            view=build_entry_confirmation_view(
                giveaway['prize'],
                giveaway['winners_amount'],
                int(giveaway['end_timestamp'])
            ),
            ephemeral=True
        )
        
        # Update entry count (would need to rebuild message in V2)
        # For now, we'll skip this to avoid complexity
    
    def _start_giveaway_timer(self, giveaway_id: str, end_timestamp: float):
        """Start a timer for the giveaway."""
        delay = end_timestamp - datetime.now().timestamp()
        
        if delay <= 0:
            # Already ended
            asyncio.create_task(self._end_giveaway(giveaway_id))
            return
        
        async def timer_task():
            try:
                await asyncio.sleep(delay)
                await self._end_giveaway(giveaway_id)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Error in giveaway timer: {e}")
        
        task = asyncio.create_task(timer_task())
        self.active_timers[giveaway_id] = task
    
    async def _end_giveaway(self, giveaway_id: str):
        """End a giveaway and select winners."""
        
        # Get giveaway
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway or giveaway['status'] == 'ended':
            return
        
        # Update status
        db.update_giveaway_status(giveaway_id, 'ended')
        
        # Remove from active timers
        if giveaway_id in self.active_timers:
            del self.active_timers[giveaway_id]
        
        # Get participants
        participants = db.get_participants(giveaway_id)
        
        # Get channel and message
        channel = self.bot.get_channel(giveaway['channel_id'])
        if not channel:
            print(f"Could not find channel for giveaway {giveaway_id}")
            return
        
        try:
            message = await channel.fetch_message(giveaway['message_id'])
        except discord.NotFound:
            print(f"Could not find message for giveaway {giveaway_id}")
            return
        
        # Select winners
        if not participants:
            # No participants
            await self._update_giveaway_message_no_winners(message)
            return
        
        winners_amount = min(giveaway['winners_amount'], len(participants))
        winners = random.sample(participants, winners_amount)
        
        # Store winners
        for winner_id in winners:
            db.add_winner(giveaway_id, winner_id)
        
        # Update message with winners
        await self._update_giveaway_message_with_winners(message, giveaway, winners)
        
        # Give winner role if configured
        if giveaway['winner_role_id']:
            await self._give_winner_role(channel.guild, winners, giveaway['winner_role_id'])
        
        # DM winners if configured
        if giveaway['winner_dm_message']:
            await self._dm_winners(winners, giveaway['prize'], giveaway['winner_dm_message'])
    
    async def _update_giveaway_message_with_winners(
        self,
        message: discord.Message,
        giveaway: dict,
        winners: List[int]
    ):
        """Update the giveaway message with winners."""
        
        # Get winner mentions
        winner_mentions = []
        for winner_id in winners:
            member = message.guild.get_member(winner_id)
            if member:
                winner_mentions.append(member.mention)
            else:
                winner_mentions.append(f"<@{winner_id}>")
        
        # Build new message
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(34, 197, 94)
        )
        
        container.add_item(
            discord.ui.TextDisplay("🎉 Giveaway Ended!")
        )
        
        container.add_item(discord.ui.Separator())
        
        container.add_item(
            discord.ui.TextDisplay(f"🎁 Prize:\n{giveaway['prize']}")
        )
        
        container.add_item(discord.ui.Separator())
        
        winners_text = "\n".join(winner_mentions)
        container.add_item(
            discord.ui.TextDisplay(f"🏆 Winners:\n{winners_text}")
        )
        
        container.add_item(discord.ui.Separator())
        
        container.add_item(
            discord.ui.TextDisplay("Congratulations! 🎉")
        )
        
        view.add_item(container)
        
        await message.edit(view=view)
    
    async def _update_giveaway_message_no_winners(self, message: discord.Message):
        """Update the giveaway message when no winners."""
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(239, 68, 68)
        )
        
        container.add_item(
            discord.ui.TextDisplay("❌ Giveaway Ended")
        )
        
        container.add_item(discord.ui.Separator())
        
        container.add_item(
            discord.ui.TextDisplay("No valid entries were found.")
        )
        
        view.add_item(container)
        
        await message.edit(view=view)
    
    async def _give_winner_role(self, guild: discord.Guild, winner_ids: List[int], role_id: int):
        """Give winner role to winners."""
        role = guild.get_role(role_id)
        if not role:
            print(f"Could not find winner role {role_id}")
            return
        
        for winner_id in winner_ids:
            try:
                member = guild.get_member(winner_id)
                if member:
                    await member.add_roles(role)
            except Exception as e:
                print(f"Error giving winner role to {winner_id}: {e}")
    
    async def _dm_winners(self, winner_ids: List[int], prize: str, dm_message: str):
        """DM winners."""
        for winner_id in winner_ids:
            try:
                user = self.bot.get_user(winner_id)
                if user:
                    await user.send(
                        view=build_winner_dm_view(prize, dm_message)
                    )
            except Exception as e:
                print(f"Error DMing winner {winner_id}: {e}")
    
    # ==========================================
    # STARTUP RESTORATION
    # ==========================================
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Restore active giveaways on startup."""
        print("Restoring active giveaways...")
        
        active_giveaways = db.get_active_giveaways()
        
        for giveaway in active_giveaways:
            giveaway_id = giveaway['giveaway_id']
            end_timestamp = giveaway['end_timestamp']
            
            # Check if already ended
            if datetime.now().timestamp() >= end_timestamp:
                # End it
                asyncio.create_task(self._end_giveaway(giveaway_id))
            else:
                # Start timer
                self._start_giveaway_timer(giveaway_id, end_timestamp)
        
        print(f"Restored {len(active_giveaways)} active giveaways.")


# ==========================================
# SETUP FUNCTION
# ==========================================

async def setup(bot: commands.Bot):
    """Setup the giveaway cog."""
    await bot.add_cog(GiveawaySystem(bot))
