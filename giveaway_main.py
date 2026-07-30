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

GIVEAWAY_WHITELIST_ROLES = [
    1532456182147711108
]

GIVEAWAY_REMOVE_PARTICIPANT_ROLE = 1532456182147711108  # Set to role ID (int) to allow removing participants


def is_giveaway_admin(user: discord.Member) -> bool:
    """Check if user has giveaway admin permissions."""
    for role in user.roles:
        if role.id in GIVEAWAY_WHITELIST_ROLES:
            return True
    
    if user.guild_permissions.administrator:
        return True
    
    return False


def can_remove_participants(user: discord.Member) -> bool:
    """Check if user can remove participants from giveaways."""
    if user.guild_permissions.administrator:
        return True
    
    if GIVEAWAY_REMOVE_PARTICIPANT_ROLE:
        for role in user.roles:
            if role.id == GIVEAWAY_REMOVE_PARTICIPANT_ROLE:
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
    # GIVEAWAY COMMAND GROUP
    # ==========================================
    
    giveaway = app_commands.Group(name="giveaway", description="Giveaway commands")

    @giveaway.command(name="create", description="Create a new giveaway")
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
        
        # Always defer initial response as ephemeral to avoid command hanging
        await interaction.response.defer(ephemeral=True)
        
        # Parse duration
        try:
            duration = self._parse_duration(ends)
            if duration.total_seconds() <= 0:
                raise ValueError("Duration must be positive")
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid duration format. Use formats like: 10m, 2h, 3d, 1w",
                ephemeral=True
            )
            return
        
        # Calculate end timestamp
        end_timestamp = (datetime.now() + duration).timestamp()
        
        # Determine channel and host
        target_channel = channel or interaction.channel
        target_host = host  # Only use provided host, don't default
        
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
            host_id=target_host.id if target_host else None,
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
            try:
                await giveaway_message.delete()
            except Exception:
                pass
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
    
    @giveaway.command(name="reroll", description="Reroll giveaway winners")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def reroll_giveaway(self, interaction: discord.Interaction, message_id: str):
        """Reroll giveaway winners."""
        
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid message ID format.",
                ephemeral=True
            )
            return
        
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send(
                "❌ Could not find a giveaway with that Message ID.",
                ephemeral=True
            )
            return
        
        participants = db.get_participants(giveaway['giveaway_id'])
        previous_winners = db.get_winners(giveaway['giveaway_id'])
        
        if not participants:
            await interaction.followup.send(
                "❌ Could not reroll giveaway. Reason: No valid participants found.",
                ephemeral=True
            )
            return
        
        available_participants = [p for p in participants if p not in previous_winners]
        
        if len(available_participants) < giveaway['winners_amount']:
            new_winners = available_participants if available_participants else random.sample(participants, min(len(participants), giveaway['winners_amount']))
        else:
            new_winners = random.sample(available_participants, giveaway['winners_amount'])
        
        if not new_winners:
            await interaction.followup.send(
                "❌ Could not reroll giveaway. Reason: No valid participants found.",
                ephemeral=True
            )
            return
        
        db.clear_winners(giveaway['giveaway_id'])
        for winner_id in new_winners:
            db.add_winner(giveaway['giveaway_id'], winner_id)
        
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
        
        await self._update_giveaway_message_with_winners(message, giveaway, new_winners)
        
        # Send reroll announcement
        await self._send_reroll_announcement(channel, giveaway, new_winners)
        
        if giveaway['winner_role_id']:
            await self._give_winner_role(channel.guild, new_winners, giveaway['winner_role_id'])
        
        if giveaway['winner_dm_message']:
            await self._dm_winners(new_winners, giveaway['prize'], giveaway['winner_dm_message'])
        
        await interaction.followup.send(
            f"✅ Giveaway rerolled successfully! {len(new_winners)} new winner(s) selected.",
            ephemeral=True
        )
    
    # ==========================================
    # GIVEAWAY END COMMAND
    # ==========================================
    
    @giveaway.command(name="end", description="End a giveaway early")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def end_giveaway(self, interaction: discord.Interaction, message_id: str):
        """End a giveaway early."""
        
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid message ID format.",
                ephemeral=True
            )
            return
        
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send(
                "❌ Could not find a giveaway with that Message ID.",
                ephemeral=True
            )
            return
        
        if giveaway['status'] == 'ended':
            await interaction.followup.send(
                "❌ This giveaway has already ended.",
                ephemeral=True
            )
            return
        
        if giveaway['giveaway_id'] in self.active_timers:
            self.active_timers[giveaway['giveaway_id']].cancel()
            del self.active_timers[giveaway['giveaway_id']]
        
        await self._end_giveaway(giveaway['giveaway_id'])
        
        await interaction.followup.send(
            "✅ Giveaway ended successfully!",
            ephemeral=True
        )
    
    # ==========================================
    # GIVEAWAY DELETE COMMAND
    # ==========================================
    
    @giveaway.command(name="delete", description="Delete a giveaway")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def delete_giveaway(self, interaction: discord.Interaction, message_id: str):
        """Delete a giveaway."""
        
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to manage giveaways.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid message ID format.",
                ephemeral=True
            )
            return
        
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send(
                "❌ Could not delete giveaway. Message ID not found.",
                ephemeral=True
            )
            return
        
        if giveaway['giveaway_id'] in self.active_timers:
            self.active_timers[giveaway['giveaway_id']].cancel()
            del self.active_timers[giveaway['giveaway_id']]
        
        try:
            channel = self.bot.get_channel(giveaway['channel_id'])
            if channel:
                message = await channel.fetch_message(giveaway['message_id'])
                await message.delete()
        except Exception:
            pass
        
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
        
        if custom_id.startswith("giveaway_enter_"):
            giveaway_id = custom_id.replace("giveaway_enter_", "")
            await self._handle_enter_giveaway(interaction, giveaway_id)
        elif custom_id.startswith("giveaway_participants_"):
            giveaway_id = custom_id.replace("giveaway_participants_", "")
            await self._handle_participants_button(interaction, giveaway_id)
        elif custom_id.startswith("giveaway_leave_"):
            giveaway_id = custom_id.replace("giveaway_leave_", "")
            await self._handle_leave_giveaway(interaction, giveaway_id)
        elif custom_id.startswith("giveaway_remove_participants_"):
            giveaway_id = custom_id.replace("giveaway_remove_participants_", "")
            await self._handle_remove_participants(interaction, giveaway_id)
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string to timedelta."""
        duration_str = duration_str.lower().strip()
        
        if duration_str.endswith('m'):
            return timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('h'):
            return timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            return timedelta(days=int(duration_str[:-1]))
        elif duration_str.endswith('w'):
            return timedelta(weeks=int(duration_str[:-1]))
        else:
            raise ValueError("Invalid duration format")
    
    async def _create_giveaway_message(
        self,
        channel: discord.TextChannel,
        prize: str,
        host: Optional[discord.Member],
        winners: int,
        end_timestamp: int,
        message: Optional[str],
        required_role: Optional[discord.Role],
        giveaway_id: str
    ) -> discord.Message:
        """Create the Components V2 giveaway message."""
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay(f"## {prize}"))
        container.add_item(discord.ui.Separator())
        
        if host is not None:
            container.add_item(discord.ui.TextDisplay(f"Hosted by {host.mention}"))
        
        container.add_item(discord.ui.TextDisplay(f"🏆 Winners: {winners}"))
        container.add_item(discord.ui.TextDisplay(f"⏰ Ends: <t:{end_timestamp}:R>"))
        
        if message:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(message))
        
        if required_role:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(f"📋 Requirement: {required_role.mention}"))
        
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("🎟️ Entries: 0"))
        container.add_item(discord.ui.Separator())
        
        button_row = discord.ui.ActionRow()
        button_row.add_item(
            discord.ui.Button(
                label="🎉 Enter",
                style=discord.ButtonStyle.green,
                custom_id=f"giveaway_enter_{giveaway_id}"
            )
        )
        button_row.add_item(
            discord.ui.Button(
                label="Participants",
                style=discord.ButtonStyle.secondary,
                custom_id=f"giveaway_participants_{giveaway_id}"
            )
        )
        container.add_item(button_row)
        view.add_item(container)
        
        return await channel.send(view=view)
    
    async def _update_giveaway_entry_count(self, message_id: int):
        """Update the entry count in the giveaway message."""
        try:
            giveaway = db.get_giveaway_by_message_id(message_id)
            if not giveaway:
                return
            
            channel = self.bot.get_channel(giveaway['channel_id'])
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            participants = db.get_participants(giveaway['giveaway_id'])
            entry_count = len(participants)
            
            # Rebuild the message with updated entry count
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(
                accent_colour=discord.Color.from_rgb(37, 37, 41)
            )
            
            container.add_item(discord.ui.TextDisplay(f"## {giveaway['prize']}"))
            container.add_item(discord.ui.Separator())
            
            if giveaway['host_id']:
                container.add_item(discord.ui.TextDisplay(f"Hosted by <@{giveaway['host_id']}>"))
            
            container.add_item(discord.ui.TextDisplay(f"🏆 Winners: {giveaway['winners_amount']}"))
            container.add_item(discord.ui.TextDisplay(f"⏰ Ends: <t:{int(float(giveaway['end_timestamp']))}:R>"))
            
            if giveaway['giveaway_message']:
                container.add_item(discord.ui.Separator())
                container.add_item(discord.ui.TextDisplay(giveaway['giveaway_message']))
            
            if giveaway['required_role_id']:
                container.add_item(discord.ui.Separator())
                container.add_item(discord.ui.TextDisplay(f"📋 Requirement: <@&{giveaway['required_role_id']}>"))
            
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(f"🎟️ Entries: {entry_count}"))
            container.add_item(discord.ui.Separator())
            
            button_row = discord.ui.ActionRow()
            button_row.add_item(
                discord.ui.Button(
                    label="🎉 Enter",
                    style=discord.ButtonStyle.green,
                    custom_id=f"giveaway_enter_{giveaway['giveaway_id']}"
                )
            )
            button_row.add_item(
                discord.ui.Button(
                    label="Participants",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"giveaway_participants_{giveaway['giveaway_id']}"
                )
            )
            container.add_item(button_row)
            
            view.add_item(container)
            
            await message.edit(view=view)
        except Exception as e:
            print(f"Error updating entry count: {e}")

    async def _handle_enter_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle the enter giveaway button click."""
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message(
                "❌ This giveaway no longer exists.",
                ephemeral=True
            )
            return
        
        if giveaway['status'] != 'active':
            await interaction.response.send_message(
                "❌ This giveaway has ended.",
                ephemeral=True
            )
            return
        
        if db.has_participant(giveaway_id, interaction.user.id):
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(
                accent_colour=discord.Color.from_rgb(37, 37, 41)
            )
            
            container.add_item(discord.ui.TextDisplay("You have already entered this giveaway."))
            container.add_item(discord.ui.Separator())
            
            button_row = discord.ui.ActionRow()
            button_row.add_item(
                discord.ui.Button(
                    label="Leave Giveaway",
                    style=discord.ButtonStyle.danger,
                    custom_id=f"giveaway_leave_{giveaway_id}"
                )
            )
            container.add_item(button_row)
            
            view.add_item(container)
            
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
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
        
        db.add_participant(giveaway_id, interaction.user.id)
        
        await self._update_giveaway_entry_count(giveaway['message_id'])
        
        await interaction.response.send_message(
            "✅ You have successfully entered this giveaway!",
            ephemeral=True
        )

    async def _handle_participants_button(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle the participants button click."""
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message(
                "❌ This giveaway no longer exists.",
                ephemeral=True
            )
            return
        
        participants = db.get_participants(giveaway_id)
        
        if not participants:
            await interaction.response.send_message(
                "No one has entered this giveaway yet.",
                ephemeral=True
            )
            return
        
        participant_mentions = []
        for participant_id in participants:
            member = interaction.guild.get_member(participant_id)
            if member:
                participant_mentions.append(f"{member.mention} ({member.name})")
            else:
                participant_mentions.append(f"<@{participant_id}> (Left server)")
        
        participants_text = "\n".join(participant_mentions)
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay(f"Giveaway Participants ({len(participants)})"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(participants_text))
        
        # Add remove participant button if user has permission
        if can_remove_participants(interaction.user):
            container.add_item(discord.ui.Separator())
            button_row = discord.ui.ActionRow()
            button_row.add_item(
                discord.ui.Button(
                    label="Remove Participants",
                    style=discord.ButtonStyle.danger,
                    custom_id=f"giveaway_remove_participants_{giveaway_id}"
                )
            )
            container.add_item(button_row)
        
        view.add_item(container)
        
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _handle_leave_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle the leave giveaway button click."""
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message(
                "❌ This giveaway no longer exists.",
                ephemeral=True
            )
            return
        
        if giveaway['status'] != 'active':
            await interaction.response.send_message(
                "❌ This giveaway has ended.",
                ephemeral=True
            )
            return
        
        if not db.has_participant(giveaway_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You are not in this giveaway.",
                ephemeral=True
            )
            return
        
        db.remove_participant(giveaway_id, interaction.user.id)
        
        await self._update_giveaway_entry_count(giveaway['message_id'])
        
        await interaction.response.send_message(
            "✅ You have left this giveaway.",
            ephemeral=True
        )

    async def _handle_remove_participants(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle the remove participants button click."""
        if not can_remove_participants(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to remove participants.",
                ephemeral=True
            )
            return
        
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway:
            await interaction.response.send_message(
                "❌ This giveaway no longer exists.",
                ephemeral=True
            )
            return
        
        participants = db.get_participants(giveaway_id)
        
        if not participants:
            await interaction.response.send_message(
                "No participants to remove.",
                ephemeral=True
            )
            return
        
        # Create select options for participants
        select_options = []
        for participant_id in participants:
            member = interaction.guild.get_member(participant_id)
            if member:
                label = f"{member.name} ({member.id})"
                value = str(participant_id)
                select_options.append(
                    discord.SelectOption(label=label, value=value)
                )
        
        if not select_options:
            await interaction.response.send_message(
                "No valid participants to remove.",
                ephemeral=True
            )
            return
        
        # Create view with select menu
        class RemoveParticipantsView(discord.ui.View):
            def __init__(self, giveaway_id: str, cog):
                super().__init__(timeout=None)
                self.giveaway_id = giveaway_id
                self.cog = cog
            
            @discord.ui.select(
                placeholder="Select participants to remove...",
                min_values=1,
                max_values=len(select_options),
                options=select_options[:25]  # Discord limit is 25
            )
            async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
                selected_ids = [int(value) for value in select.values]
                
                for user_id in selected_ids:
                    db.remove_participant(self.giveaway_id, user_id)
                
                await self.cog._update_giveaway_entry_count(giveaway['message_id'])
                
                await interaction.response.edit_message(
                    content=f"✅ Removed {len(selected_ids)} participant(s) from the giveaway.",
                    view=None
                )
        
        view = RemoveParticipantsView(giveaway_id, self)
        
        await interaction.response.edit_message(
            content="Select participants to remove:",
            view=view
        )

    def _start_giveaway_timer(self, giveaway_id: str, end_timestamp: float):
        """Start a timer for the giveaway."""
        delay = end_timestamp - datetime.now().timestamp()
        print(f"[GIVEAWAY TIMER] Starting timer for {giveaway_id}, delay: {delay} seconds")
        
        if delay <= 0:
            print(f"[GIVEAWAY TIMER] Delay is <= 0, ending immediately")
            asyncio.create_task(self._end_giveaway(giveaway_id))
            return
        
        async def timer_task():
            try:
                print(f"[GIVEAWAY TIMER] Sleeping for {delay} seconds...")
                await asyncio.sleep(delay)
                print(f"[GIVEAWAY TIMER] Timer finished, ending giveaway {giveaway_id}")
                await self._end_giveaway(giveaway_id)
            except asyncio.CancelledError:
                print(f"[GIVEAWAY TIMER] Timer cancelled for {giveaway_id}")
            except Exception as e:
                print(f"[GIVEAWAY TIMER] Error in giveaway timer: {e}")
                import traceback
                traceback.print_exc()
        
        task = asyncio.create_task(timer_task())
        self.active_timers[giveaway_id] = task
        print(f"[GIVEAWAY TIMER] Timer task created and stored for {giveaway_id}")

    async def _end_giveaway(self, giveaway_id: str):
        """End a giveaway and select winners."""
        print(f"[GIVEAWAY END] Ending giveaway {giveaway_id}")
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway or giveaway['status'] == 'ended':
            print(f"[GIVEAWAY END] Giveaway not found or already ended")
            return
        
        print(f"[GIVEAWAY END] Updating status to 'ended'")
        db.update_giveaway_status(giveaway_id, 'ended')
        
        if giveaway_id in self.active_timers:
            del self.active_timers[giveaway_id]
        
        participants = db.get_participants(giveaway_id)
        print(f"[GIVEAWAY END] Found {len(participants)} participants")
        channel = self.bot.get_channel(giveaway['channel_id'])
        if not channel:
            print(f"[GIVEAWAY END] Could not find channel")
            return
        
        try:
            message = await channel.fetch_message(giveaway['message_id'])
        except discord.NotFound:
            print(f"[GIVEAWAY END] Could not find message")
            return
        
        if not participants:
            print(f"[GIVEAWAY END] No participants, updating message")
            await self._update_giveaway_message_no_winners(message)
            return
        
        winners_amount = min(giveaway['winners_amount'], len(participants))
        winners = random.sample(participants, winners_amount)
        print(f"[GIVEAWAY END] Selected {len(winners)} winners: {winners}")
        
        for winner_id in winners:
            db.add_winner(giveaway_id, winner_id)
        
        print(f"[GIVEAWAY END] Updating message with winners")
        await self._update_giveaway_message_with_winners(message, giveaway, winners)
        
        print(f"[GIVEAWAY END] Sending announcement message")
        await self._send_giveaway_announcement(channel, giveaway, winners, len(participants))
        
        if giveaway['winner_role_id']:
            print(f"[GIVEAWAY END] Giving winner role")
            await self._give_winner_role(channel.guild, winners, giveaway['winner_role_id'])
        
        if giveaway['winner_dm_message']:
            print(f"[GIVEAWAY END] DMing winners")
            await self._dm_winners(winners, giveaway['prize'], giveaway['winner_dm_message'])
        
        print(f"[GIVEAWAY END] Giveaway ended successfully")

    async def _update_giveaway_message_with_winners(
        self,
        message: discord.Message,
        giveaway: dict,
        winners: List[int]
    ):
        """Update the giveaway message with winners using Components V2."""
        winner_mentions = [f"<@{w_id}>" for w_id in winners]
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay("🎉 Giveaway Ended!"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"🎁 Prize: {giveaway['prize']}"))
        container.add_item(discord.ui.Separator())
        
        winners_text = "\n".join(winner_mentions)
        container.add_item(discord.ui.TextDisplay(f"🏆 Winners: {winners_text}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("Congratulations! 🎉"))
        
        view.add_item(container)
        
        await message.edit(view=view)

    async def _update_giveaway_message_no_winners(self, message: discord.Message):
        """Update the giveaway message when no winners using Components V2."""
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay("❌ Giveaway Ended"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("No valid entries were found."))
        
        view.add_item(container)
        
        await message.edit(view=view)

    async def _give_winner_role(self, guild: discord.Guild, winner_ids: List[int], role_id: int):
        role = guild.get_role(role_id)
        if not role:
            return
        
        for winner_id in winner_ids:
            try:
                member = guild.get_member(winner_id)
                if member:
                    await member.add_roles(role)
            except Exception as e:
                print(f"Error giving winner role: {e}")

    async def _dm_winners(self, winner_ids: List[int], prize: str, dm_message: str):
        for winner_id in winner_ids:
            try:
                user = self.bot.get_user(winner_id)
                if user:
                    await user.send(
                        view=build_winner_dm_view(prize, dm_message)
                    )
            except Exception as e:
                print(f"Error DMing winner {winner_id}: {e}")

    async def _send_giveaway_announcement(
        self,
        channel: discord.TextChannel,
        giveaway: dict,
        winners: List[int],
        total_entries: int
    ):
        """Send a separate announcement message when giveaway ends."""
        winner_mentions = [f"<@{w_id}>" for w_id in winners]
        winners_text = ", ".join(winner_mentions)
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay("Congratulations! 🎉"))
        container.add_item(discord.ui.TextDisplay(f"{winners_text} won **{giveaway['prize']}**"))
        
        view.add_item(container)
        
        await channel.send(view=view)

    async def _send_reroll_announcement(
        self,
        channel: discord.TextChannel,
        giveaway: dict,
        winners: List[int]
    ):
        """Send a reroll announcement message."""
        winner_mentions = [f"<@{w_id}>" for w_id in winners]
        winners_text = ", ".join(winner_mentions)
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay(f"The new winner for the giveaway of **{giveaway['prize']}** is {winners_text}. Congrats! 🎉"))
        
        view.add_item(container)
        
        await channel.send(view=view)

    @commands.Cog.listener()
    async def on_ready(self):
        """Restore active giveaways on startup."""
        active_giveaways = db.get_active_giveaways()
        for giveaway in active_giveaways:
            giveaway_id = giveaway['giveaway_id']
            end_timestamp = giveaway['end_timestamp']
            
            if datetime.now().timestamp() >= end_timestamp:
                asyncio.create_task(self._end_giveaway(giveaway_id))
            else:
                self._start_giveaway_timer(giveaway_id, end_timestamp)


async def setup(bot: commands.Bot):
    """Setup the giveaway cog."""
    await bot.add_cog(GiveawaySystem(bot))
