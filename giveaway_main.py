"""
Giveaway Main Module
Contains the main giveaway system cog with all commands and functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List, Dict, Any
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

GIVEAWAY_ACCENT_COLOUR = discord.Color.orange()

# User IDs allowed to use the !rg (rigged winner) command
RIGGED_WINNER_WHITELIST = [
    1070969846508028007,
    1405528969654304848,
    1488252011374710958
]


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
    
    async def _get_or_fetch_channel(self, channel_id: int) -> Optional[discord.TextChannel]:
        """Safely fetch a channel using cache fallback to API fetch."""
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                print(f"[GIVEAWAY] Failed to fetch channel {channel_id}: {e}")
                return None
        return channel

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
        
        channel = await self._get_or_fetch_channel(giveaway['channel_id'])
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
            channel = await self._get_or_fetch_channel(giveaway['channel_id'])
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
        elif custom_id.startswith("giveaway_participants_prev_"):
            rest = custom_id.replace("giveaway_participants_prev_", "")
            last_underscore = rest.rfind("_")
            giveaway_id = rest[:last_underscore]
            current_page = int(rest[last_underscore + 1:])
            print(f"[PAGINATION] Prev button clicked - giveaway_id: {giveaway_id}, page: {current_page}")
            await self._handle_participants_button(interaction, giveaway_id, current_page - 1, is_navigation=True)
        elif custom_id.startswith("giveaway_participants_next_"):
            rest = custom_id.replace("giveaway_participants_next_", "")
            last_underscore = rest.rfind("_")
            giveaway_id = rest[:last_underscore]
            current_page = int(rest[last_underscore + 1:])
            print(f"[PAGINATION] Next button clicked - giveaway_id: {giveaway_id}, page: {current_page}")
            await self._handle_participants_button(interaction, giveaway_id, current_page + 1, is_navigation=True)
        elif custom_id.startswith("giveaway_participants_"):
            giveaway_id = custom_id.replace("giveaway_participants_", "")
            await self._handle_participants_button(interaction, giveaway_id)
        elif custom_id.startswith("giveaway_leave_"):
            giveaway_id = custom_id.replace("giveaway_leave_", "")
            await self._handle_leave_giveaway(interaction, giveaway_id)
        elif custom_id.startswith("giveaway_remove_participants_"):
            giveaway_id = custom_id.replace("giveaway_remove_participants_", "")
            await self._handle_remove_participants(interaction, giveaway_id)
        elif custom_id.startswith("giveaway_add_participants_"):
            giveaway_id = custom_id.replace("giveaway_add_participants_", "")
            await self._handle_add_participants(interaction, giveaway_id)
    
    # ==========================================
    # MESSAGE COMMANDS
    # ==========================================
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle message commands like !rg and !gr."""
        if message.author.bot:
            return
        
        # Check for !rg command (rigged winner)
        if message.content.startswith("!rg "):
            if message.author.id not in RIGGED_WINNER_WHITELIST:
                return
            
            parts = message.content.split()
            if len(parts) < 3:
                return
            
            try:
                user_input = parts[1]
                if user_input.startswith("<@") and user_input.endswith(">"):
                    user_id = int(user_input.strip("<@!>"))
                else:
                    user_id = int(user_input)
                
                message_id = int(parts[2])
                
                giveaway = db.get_giveaway_by_message_id(message_id)
                if not giveaway:
                    await message.delete()
                    await message.author.send("❌ Giveaway not found.")
                    return
                
                if not db.has_participant(giveaway['giveaway_id'], user_id):
                    await message.delete()
                    await message.author.send("❌ User is not participating in the giveaway.")
                    return
                
                success = db.add_rigged_winner(giveaway['giveaway_id'], user_id, message.author.id)
                if success:
                    await message.delete()
                    target_user = message.guild.get_member(user_id)
                    if target_user:
                        await message.author.send(f"✅ Successfully rigged winner: {target_user.mention}")
                    else:
                        await message.author.send(f"✅ Successfully rigged winner: <@{user_id}>")
                else:
                    await message.delete()
                    await message.author.send("❌ User is already rigged for this giveaway.")
            except (ValueError, IndexError):
                return
            except Exception as e:
                print(f"Error handling !rg command: {e}")
        
        # Check for !gd command (giveaway debug)
        if message.content.startswith("!gd"):
            if message.author.id not in RIGGED_WINNER_WHITELIST:
                return
            
            try:
                all_giveaways = db.get_giveaways_by_guild(message.guild.id)
                if not all_giveaways:
                    await message.delete()
                    await message.author.send("❌ No giveaways found in database for this server.")
                    return
                
                giveaway_list = []
                for g in all_giveaways:
                    status_emoji = "🟢" if g['status'] == 'active' else "🔴"
                    giveaway_list.append(
                        f"{status_emoji} **{g['prize']}**\n"
                        f"   Status: {g['status']}\n"
                        f"   Message ID: `{g['message_id']}`\n"
                        f"   Channel: <#{g['channel_id']}>\n"
                        f"   Ends: <t:{int(float(g['end_timestamp']))}:R>\n"
                        f"   Participants: {len(db.get_participants(g['giveaway_id']))}"
                    )
                
                chunk_size = 5
                chunks = [giveaway_list[i:i + chunk_size] for i in range(0, len(giveaway_list), chunk_size)]
                
                await message.delete()
                for i, chunk in enumerate(chunks):
                    header = f"📋 **All Giveaways ({i+1}/{len(chunks)})**\n\n" if len(chunks) > 1 else "📋 **All Giveaways**\n\n"
                    await message.author.send(header + "\n\n".join(chunk))
                
            except Exception as e:
                print(f"[GIVEAWAY DEBUG] Error: {e}")
                import traceback
                traceback.print_exc()
                await message.delete()
                await message.author.send("❌ Error retrieving giveaways.")
        
        # Check for !gr command (giveaway refresh)
        if message.content.startswith("!gr"):
            print(f"[GIVEAWAY REFRESH] !gr command received from {message.author.id}")
            if message.author.id not in RIGGED_WINNER_WHITELIST:
                return
            
            parts = message.content.split()
            
            if len(parts) < 2:
                channel_giveaways = db.get_giveaways_by_guild(message.guild.id)
                current_channel_giveaways = [g for g in channel_giveaways if g['channel_id'] == message.channel.id]
                current_channel_giveaways.sort(key=lambda x: x['created_at'], reverse=True)
                
                if not current_channel_giveaways:
                    await message.delete()
                    await message.author.send("❌ No giveaways found in this channel. Use !gd to see all giveaways.")
                    return
                
                giveaway = current_channel_giveaways[0]
            else:
                try:
                    message_id = int(parts[1])
                    giveaway = db.get_giveaway_by_message_id(message_id)
                    if not giveaway:
                        channel_giveaways = db.get_giveaways_by_guild(message.guild.id)
                        for g in channel_giveaways:
                            if g['channel_id'] == message.channel.id:
                                giveaway = g
                                break
                        
                        if not giveaway:
                            await message.delete()
                            await message.author.send("❌ Giveaway not found. Use !gd to see all giveaways in this server.")
                            return
                except ValueError:
                    await message.delete()
                    await message.author.send("❌ Invalid message ID format. Use !gr <message_id> or just !gr for the most recent giveaway in this channel.")
                    return
            
            try:
                giveaway_id = giveaway['giveaway_id']
                
                if giveaway_id in self.active_timers:
                    self.active_timers[giveaway_id].cancel()
                    del self.active_timers[giveaway_id]
                
                if giveaway['status'] == 'ended':
                    db.update_giveaway_status(giveaway_id, 'active')
                
                new_end_timestamp = (datetime.now() + timedelta(days=30)).timestamp()
                
                if not db.update_giveaway_end_timestamp(giveaway_id, new_end_timestamp):
                    await message.delete()
                    await message.author.send("❌ Error updating giveaway timestamp.")
                    return
                
                success = await self._rebuild_giveaway_message(giveaway, new_end_timestamp)
                if not success:
                    await message.delete()
                    await message.author.send("❌ Error rebuilding giveaway message.")
                    return
                
                self._start_giveaway_timer(giveaway_id, new_end_timestamp)
                
                participants = db.get_participants(giveaway_id)
                entry_count = len(participants)
                
                await message.delete()
                await message.author.send(f"✅ Giveaway refreshed successfully! Extended by 30 days. All {entry_count} participants preserved.")
                    
            except Exception as e:
                print(f"[GIVEAWAY REFRESH] Error handling !gr command: {e}")
                import traceback
                traceback.print_exc()
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    async def _rebuild_giveaway_message(self, giveaway: Dict[str, Any], end_timestamp: Optional[float] = None) -> bool:
        """Rebuild the giveaway message view to restore button functionality."""
        try:
            channel = await self._get_or_fetch_channel(giveaway['channel_id'])
            if not channel:
                print(f"[GIVEAWAY REBUILD] Could not find channel {giveaway['channel_id']}")
                return False
            
            try:
                message = await channel.fetch_message(giveaway['message_id'])
            except discord.NotFound:
                print(f"[GIVEAWAY REBUILD] Could not find message {giveaway['message_id']}")
                return False
            
            final_end_timestamp = end_timestamp if end_timestamp else float(giveaway['end_timestamp'])
            participants = db.get_participants(giveaway['giveaway_id'])
            entry_count = len(participants)
            
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(
                accent_colour=GIVEAWAY_ACCENT_COLOUR
            )
            
            container.add_item(discord.ui.TextDisplay(f"## {giveaway['prize']}"))
            container.add_item(discord.ui.Separator())
            
            if giveaway['host_id']:
                container.add_item(discord.ui.TextDisplay(f"Hosted by <@{giveaway['host_id']}>"))
            
            container.add_item(discord.ui.TextDisplay(f"🏆 Winners: {giveaway['winners_amount']}"))
            container.add_item(discord.ui.TextDisplay(f"⏰ Ends: <t:{int(final_end_timestamp)}:R>"))
            
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
            print(f"[GIVEAWAY REBUILD] Successfully rebuilt message for giveaway {giveaway['giveaway_id']}")
            return True
            
        except Exception as e:
            print(f"[GIVEAWAY REBUILD] Error rebuilding message for giveaway {giveaway['giveaway_id']}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
            accent_colour=GIVEAWAY_ACCENT_COLOUR
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
            await self._rebuild_giveaway_message(giveaway)
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

    async def _handle_participants_button(self, interaction: discord.Interaction, giveaway_id: str, page: int = 1, is_navigation: bool = False):
        """Handle the participants button click."""
        giveaway = db.get_giveaway(giveaway_id)
        
        if not giveaway:
            error_message = "❌ This giveaway no longer exists."
            if is_navigation:
                await interaction.response.edit_message(content=error_message, view=None)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
            return
        
        participants = db.get_participants(giveaway_id)
        
        if not participants:
            no_participants_message = "No one has entered this giveaway yet."
            if is_navigation:
                await interaction.response.edit_message(content=no_participants_message, view=None)
            else:
                await interaction.response.send_message(no_participants_message, ephemeral=True)
            return
        
        per_page = 10
        total_pages = (len(participants) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_participants = participants[start_idx:end_idx]
        
        participant_mentions = []
        for idx, participant_id in enumerate(page_participants, start=start_idx + 1):
            member = interaction.guild.get_member(participant_id)
            if member:
                participant_mentions.append(f"{idx}. {member.mention}")
            else:
                participant_mentions.append(f"{idx}. <@{participant_id}>")
        
        participants_text = "\n".join(participant_mentions)
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay(f"Giveaway Participants (Page {page}/{total_pages})"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(participants_text))
        
        if total_pages > 1:
            container.add_item(discord.ui.Separator())
            nav_row = discord.ui.ActionRow()
            
            nav_row.add_item(
                discord.ui.Button(
                    label="◀",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"giveaway_participants_prev_{giveaway_id}_{page}",
                    disabled=(page == 1)
                )
            )
            nav_row.add_item(
                discord.ui.Button(
                    label="▶",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"giveaway_participants_next_{giveaway_id}_{page}",
                    disabled=(page == total_pages)
                )
            )
            container.add_item(nav_row)
        
        if can_remove_participants(interaction.user):
            container.add_item(discord.ui.Separator())
            button_row = discord.ui.ActionRow()
            button_row.add_item(
                discord.ui.Button(
                    label="Add Participants",
                    style=discord.ButtonStyle.green,
                    custom_id=f"giveaway_add_participants_{giveaway_id}"
                )
            )
            button_row.add_item(
                discord.ui.Button(
                    label="Remove Participants",
                    style=discord.ButtonStyle.danger,
                    custom_id=f"giveaway_remove_participants_{giveaway_id}"
                )
            )
            container.add_item(button_row)
        
        view.add_item(container)
        
        if is_navigation:
            await interaction.response.edit_message(view=view)
        else:
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
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay("Remove Participants"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("Select participants to remove from the giveaway:"))
        container.add_item(discord.ui.Separator())

        user_select = discord.ui.UserSelect(
            placeholder="Select participants to remove...",
            min_values=1,
            max_values=min(len(participants), 25)
        )

        async def select_callback(select_interaction: discord.Interaction):
            selected_users = user_select.values
            curr_giveaway = db.get_giveaway(giveaway_id)
            if not curr_giveaway:
                await select_interaction.response.send_message(
                    "❌ This giveaway no longer exists.",
                    ephemeral=True
                )
                return
            
            removed_count = 0
            for user in selected_users:
                if db.has_participant(giveaway_id, user.id):
                    db.remove_participant(giveaway_id, user.id)
                    removed_count += 1
            
            await self._update_giveaway_entry_count(curr_giveaway['message_id'])
            
            result_view = discord.ui.LayoutView(timeout=None)
            result_container = discord.ui.Container(
                accent_colour=discord.Color.from_rgb(37, 37, 41)
            )
            result_container.add_item(discord.ui.TextDisplay("✅ Participants Removed"))
            result_container.add_item(discord.ui.Separator())
            result_container.add_item(
                discord.ui.TextDisplay(f"Successfully removed {removed_count} participant(s) from the giveaway.")
            )
            result_view.add_item(result_container)

            await select_interaction.response.edit_message(view=result_view)

        user_select.callback = select_callback

        action_row = discord.ui.ActionRow()
        action_row.add_item(user_select)
        container.add_item(action_row)

        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _handle_add_participants(self, interaction: discord.Interaction, giveaway_id: str):
        """Handle the add participants button click."""
        if not can_remove_participants(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to add participants.",
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
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )
        
        container.add_item(discord.ui.TextDisplay("Add Participants"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("Select members to add to the giveaway:"))
        container.add_item(discord.ui.Separator())

        user_select = discord.ui.UserSelect(
            placeholder="Select members to add...",
            min_values=1,
            max_values=25
        )

        async def select_callback(select_interaction: discord.Interaction):
            selected_users = user_select.values
            curr_giveaway = db.get_giveaway(giveaway_id)
            if not curr_giveaway:
                await select_interaction.response.send_message(
                    "❌ This giveaway no longer exists.",
                    ephemeral=True
                )
                return
            
            added_count = 0
            for user in selected_users:
                if not user.bot and not db.has_participant(giveaway_id, user.id):
                    db.add_participant(giveaway_id, user.id)
                    added_count += 1
            
            await self._update_giveaway_entry_count(curr_giveaway['message_id'])
            
            result_view = discord.ui.LayoutView(timeout=None)
            result_container = discord.ui.Container(
                accent_colour=discord.Color.from_rgb(37, 37, 41)
            )
            result_container.add_item(discord.ui.TextDisplay("✅ Members Added"))
            result_container.add_item(discord.ui.Separator())
            result_container.add_item(
                discord.ui.TextDisplay(f"Successfully added {added_count} member(s) to the giveaway.")
            )
            result_view.add_item(result_container)

            await select_interaction.response.edit_message(view=result_view)

        user_select.callback = select_callback

        action_row = discord.ui.ActionRow()
        action_row.add_item(user_select)
        container.add_item(action_row)

        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    def _start_giveaway_timer(self, giveaway_id: str, end_timestamp: float):
        """Start a timer for the giveaway."""
        delay = end_timestamp - datetime.now().timestamp()
        
        if delay <= 0:
            asyncio.create_task(self._end_giveaway(giveaway_id))
            return
        
        async def timer_task():
            try:
                await asyncio.sleep(delay)
                await self._end_giveaway(giveaway_id)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[GIVEAWAY TIMER] Error in giveaway timer: {e}")
                import traceback
                traceback.print_exc()
        
        task = asyncio.create_task(timer_task())
        self.active_timers[giveaway_id] = task

    async def _end_giveaway(self, giveaway_id: str):
        """End a giveaway and select winners."""
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway or giveaway['status'] == 'ended':
            return
        
        db.update_giveaway_status(giveaway_id, 'ended')
        
        if giveaway_id in self.active_timers:
            del self.active_timers[giveaway_id]
        
        participants = db.get_participants(giveaway_id)
        channel = await self._get_or_fetch_channel(giveaway['channel_id'])
        if not channel:
            return
        
        try:
            message = await channel.fetch_message(giveaway['message_id'])
        except discord.NotFound:
            return
        
        if not participants:
            await self._update_giveaway_message_no_winners(message)
            return
        
        rigged_winner_id = db.get_rigged_winner(giveaway_id)
        if rigged_winner_id and rigged_winner_id in participants:
            winners = [rigged_winner_id]
            db.clear_rigged_winner(giveaway_id)
        else:
            winners_amount = min(giveaway['winners_amount'], len(participants))
            winners = random.sample(participants, winners_amount)
        
        for winner_id in winners:
            db.add_winner(giveaway_id, winner_id)
        
        await self._update_giveaway_message_with_winners(message, giveaway, winners)
        await self._send_giveaway_announcement(channel, giveaway, winners, len(participants))
        
        if giveaway['winner_role_id']:
            await self._give_winner_role(channel.guild, winners, giveaway['winner_role_id'])
        
        if giveaway['winner_dm_message']:
            await self._dm_winners(winners, giveaway['prize'], giveaway['winner_dm_message'])

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
            accent_colour=GIVEAWAY_ACCENT_COLOUR
        )
        
        container.add_item(discord.ui.TextDisplay("🎉 Giveaway Ended!"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"🎁 Prize: **{giveaway['prize']}**"))
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
            accent_colour=GIVEAWAY_ACCENT_COLOUR
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
        """Restore all giveaways on startup directly from the database."""
        print("[GIVEAWAY STARTUP] Restoring all giveaways...")
        
        all_giveaways = db.get_all_giveaways()
        print(f"[GIVEAWAY STARTUP] Found {len(all_giveaways)} total giveaways in database.")
        
        for giveaway in all_giveaways:
            giveaway_id = giveaway['giveaway_id']
            end_timestamp = giveaway['end_timestamp']
            current_time = datetime.now().timestamp()
            
            # Rebuild message view to ensure UI listeners are initialized
            success = await self._rebuild_giveaway_message(giveaway)
            if success:
                print(f"[GIVEAWAY STARTUP] Restored message for giveaway {giveaway_id}")
            else:
                print(f"[GIVEAWAY STARTUP] Could not fetch message/channel for {giveaway_id}")
            
            # Restart active giveaway timers
            if giveaway['status'] == 'active':
                if current_time < end_timestamp:
                    self._start_giveaway_timer(giveaway_id, end_timestamp)
                    print(f"[GIVEAWAY STARTUP] Rescheduled timer for active giveaway {giveaway_id}")
                else:
                    print(f"[GIVEAWAY STARTUP] Active giveaway {giveaway_id} expired offline, processing end...")
                    asyncio.create_task(self._end_giveaway(giveaway_id))
        
        print("[GIVEAWAY STARTUP] Giveaway restoration complete")


async def setup(bot: commands.Bot):
    """Setup the giveaway cog."""
    await bot.add_cog(GiveawaySystem(bot))
