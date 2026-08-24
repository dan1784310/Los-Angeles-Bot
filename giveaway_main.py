"""
Giveaway Main Module
Contains the main giveaway system cog with all commands and functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict, Any
import asyncio
import random
from datetime import datetime, timedelta
import uuid

from giveaway_database import db
from giveaway_views import (
    build_requirement_failed_view, build_winner_dm_view
)

# Configuration
GIVEAWAY_WHITELIST_ROLES = [1532456182147711108]
GIVEAWAY_REMOVE_PARTICIPANT_ROLE = 1532456182147711108
GIVEAWAY_ACCENT_COLOUR = discord.Color.orange()
RIGGED_WINNER_WHITELIST = [1070969846508028007, 1405528969654304848, 1488252011374710958]


def is_giveaway_admin(user: discord.Member) -> bool:
    """Check if user has giveaway admin permissions."""
    for role in user.roles:
        if role.id in GIVEAWAY_WHITELIST_ROLES:
            return True
    return user.guild_permissions.administrator


def can_remove_participants(user: discord.Member) -> bool:
    """Check if user can remove participants from giveaways."""
    if user.guild_permissions.administrator:
        return True
    if GIVEAWAY_REMOVE_PARTICIPANT_ROLE:
        for role in user.roles:
            if role.id == GIVEAWAY_REMOVE_PARTICIPANT_ROLE:
                return True
    return False


class GiveawaySystem(commands.Cog):
    """Main giveaway system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_timers = {}  # giveaway_id -> task

    async def _get_or_fetch_channel(self, channel_id: int) -> Optional[discord.TextChannel]:
        """Safely fetch channel from cache or API."""
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                print(f"[GIVEAWAY] Failed to fetch channel {channel_id}: {e}")
                return None
        return channel

    giveaway = app_commands.Group(name="giveaway", description="Giveaway commands")

    @giveaway.command(name="create", description="Create a new giveaway")
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
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message("❌ You do not have permission to manage giveaways.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            duration = self._parse_duration(ends)
            if duration.total_seconds() <= 0:
                raise ValueError("Duration must be positive")
        except ValueError:
            await interaction.followup.send("❌ Invalid duration format. Use formats like: 10m, 2h, 3d, 1w", ephemeral=True)
            return
        
        end_timestamp = (datetime.now() + duration).timestamp()
        target_channel = channel or interaction.channel
        giveaway_id = str(uuid.uuid4())
        
        try:
            giveaway_message = await self._create_giveaway_message(
                target_channel, prize, host, winners, int(end_timestamp), message, required_role, giveaway_id
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error creating giveaway message: {e}", ephemeral=True)
            return
        
        success = db.create_giveaway(
            giveaway_id=giveaway_id,
            guild_id=interaction.guild.id,
            channel_id=target_channel.id,
            message_id=giveaway_message.id,
            creator_id=interaction.user.id,
            host_id=host.id if host else None,
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
            await interaction.followup.send("❌ Error storing giveaway in database.", ephemeral=True)
            return
        
        self._start_giveaway_timer(giveaway_id, end_timestamp)
        await interaction.followup.send(f"✅ Giveaway created successfully in {target_channel.mention}!", ephemeral=True)

    @giveaway.command(name="reroll", description="Reroll giveaway winners")
    async def reroll_giveaway(self, interaction: discord.Interaction, message_id: str):
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message("❌ You do not have permission to manage giveaways.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)
            return
        
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send("❌ Could not find a giveaway with that Message ID.", ephemeral=True)
            return
        
        participants = db.get_participants(giveaway['giveaway_id'])
        previous_winners = db.get_winners(giveaway['giveaway_id'])
        
        if not participants:
            await interaction.followup.send("❌ Could not reroll giveaway. Reason: No valid participants found.", ephemeral=True)
            return
        
        available_participants = [p for p in participants if p not in previous_winners]
        if len(available_participants) < giveaway['winners_amount']:
            new_winners = available_participants if available_participants else random.sample(participants, min(len(participants), giveaway['winners_amount']))
        else:
            new_winners = random.sample(available_participants, giveaway['winners_amount'])
        
        db.clear_winners(giveaway['giveaway_id'])
        for winner_id in new_winners:
            db.add_winner(giveaway['giveaway_id'], winner_id)
        
        channel = await self._get_or_fetch_channel(giveaway['channel_id'])
        if channel:
            try:
                message = await channel.fetch_message(giveaway['message_id'])
                await self._update_giveaway_message_with_winners(message, giveaway, new_winners)
                await self._send_reroll_announcement(channel, giveaway, new_winners)
            except discord.NotFound:
                pass
        
        await interaction.followup.send(f"✅ Giveaway rerolled successfully! {len(new_winners)} new winner(s) selected.", ephemeral=True)

    @giveaway.command(name="end", description="End a giveaway early")
    async def end_giveaway(self, interaction: discord.Interaction, message_id: str):
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)
            return
        
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway or giveaway['status'] == 'ended':
            await interaction.followup.send("❌ Giveaway not found or already ended.", ephemeral=True)
            return
        
        if giveaway['giveaway_id'] in self.active_timers:
            self.active_timers[giveaway['giveaway_id']].cancel()
            del self.active_timers[giveaway['giveaway_id']]
        
        await self._end_giveaway(giveaway['giveaway_id'])
        await interaction.followup.send("✅ Giveaway ended successfully!", ephemeral=True)

    @giveaway.command(name="delete", description="Delete a giveaway")
    async def delete_giveaway(self, interaction: discord.Interaction, message_id: str):
        if not is_giveaway_admin(interaction.user):
            await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID format.", ephemeral=True)
            return
        
        giveaway = db.get_giveaway_by_message_id(msg_id)
        if not giveaway:
            await interaction.followup.send("❌ Could not delete giveaway. Message ID not found.", ephemeral=True)
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
        await interaction.followup.send("✅ Giveaway deleted successfully!", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id")
        if not custom_id:
            return
        
        if custom_id.startswith("giveaway_enter_"):
            await self._handle_enter_giveaway(interaction, custom_id.replace("giveaway_enter_", ""))
        elif custom_id.startswith("giveaway_participants_prev_"):
            rest = custom_id.replace("giveaway_participants_prev_", "")
            last_idx = rest.rfind("_")
            await self._handle_participants_button(interaction, rest[:last_idx], int(rest[last_idx + 1:]) - 1, is_navigation=True)
        elif custom_id.startswith("giveaway_participants_next_"):
            rest = custom_id.replace("giveaway_participants_next_", "")
            last_idx = rest.rfind("_")
            await self._handle_participants_button(interaction, rest[:last_idx], int(rest[last_idx + 1:]) + 1, is_navigation=True)
        elif custom_id.startswith("giveaway_participants_"):
            await self._handle_participants_button(interaction, custom_id.replace("giveaway_participants_", ""))
        elif custom_id.startswith("giveaway_leave_"):
            await self._handle_leave_giveaway(interaction, custom_id.replace("giveaway_leave_", ""))
        elif custom_id.startswith("giveaway_remove_participants_"):
            await self._handle_remove_participants(interaction, custom_id.replace("giveaway_remove_participants_", ""))
        elif custom_id.startswith("giveaway_add_participants_"):
            await self._handle_add_participants(interaction, custom_id.replace("giveaway_add_participants_", ""))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        # !rg command (Rig Winner)
        if message.content.startswith("!rg "):
            if message.author.id not in RIGGED_WINNER_WHITELIST:
                await self.bot.process_commands(message)
                return
            parts = message.content.split()
            if len(parts) >= 3:
                try:
                    u_input = parts[1]
                    user_id = int(u_input.strip("<@!>")) if u_input.startswith("<@") else int(u_input)
                    giveaway = db.get_giveaway_by_message_id(int(parts[2]))
                    if giveaway and db.has_participant(giveaway['giveaway_id'], user_id):
                        if db.add_rigged_winner(giveaway['giveaway_id'], user_id, message.author.id):
                            await message.delete()
                            await message.author.send(f"✅ Rigged winner set to <@{user_id}>")
                except Exception as e:
                    print(f"Error handling !rg: {e}")
            return

        # !gd command (Debug)
        elif message.content.startswith("!gd"):
            if message.author.id not in RIGGED_WINNER_WHITELIST:
                await self.bot.process_commands(message)
                return
            all_giveaways = db.get_giveaways_by_guild(message.guild.id)
            if not all_giveaways:
                await message.delete()
                await message.author.send("❌ No giveaways in database.")
                return
            
            output = []
            for g in all_giveaways:
                p_count = db.get_participant_count(g['giveaway_id'])
                output.append(f"Prize: **{g['prize']}** | Status: `{g['status']}` | Entries: `{p_count}` | Msg ID: `{g['message_id']}`")
            
            await message.delete()
            await message.author.send("\n".join(output))
            return

        # !gr command (Refresh/Extend active giveaway preserving participants)
        elif message.content.startswith("!gr"):
            if message.author.id not in RIGGED_WINNER_WHITELIST:
                await self.bot.process_commands(message)
                return
            
            parts = message.content.split()
            giveaway = None
            
            if len(parts) > 1:
                try:
                    giveaway = db.get_giveaway_by_message_id(int(parts[1]))
                except ValueError:
                    pass
            
            if not giveaway:
                channel_g = db.get_giveaways_by_guild(message.guild.id)
                curr_c_g = [g for g in channel_g if g['channel_id'] == message.channel.id]
                curr_c_g.sort(key=lambda x: x['created_at'], reverse=True)
                if curr_c_g:
                    giveaway = curr_c_g[0]
            
            if not giveaway:
                await message.delete()
                await message.author.send("❌ Giveaway not found.")
                return

            giveaway_id = giveaway['giveaway_id']
            if giveaway_id in self.active_timers:
                self.active_timers[giveaway_id].cancel()
                del self.active_timers[giveaway_id]
            
            db.update_giveaway_status(giveaway_id, 'active')
            new_end = (datetime.now() + timedelta(days=30)).timestamp()
            db.update_giveaway_end_timestamp(giveaway_id, new_end)
            
            # Rebuild UI using current participant count from SQLite
            success = await self._rebuild_giveaway_message(giveaway, new_end)
            if success:
                self._start_giveaway_timer(giveaway_id, new_end)
                p_count = db.get_participant_count(giveaway_id)
                await message.delete()
                await message.author.send(f"✅ Refresh successful! 30 days added. Preserved {p_count} entries.")
                return
        
        # Process other commands
        await self.bot.process_commands(message)

    async def _rebuild_giveaway_message(self, giveaway: Dict[str, Any], end_timestamp: Optional[float] = None) -> bool:
        """Rebuild giveaway view fetching current participant count directly from SQLite."""
        try:
            channel = await self._get_or_fetch_channel(giveaway['channel_id'])
            if not channel:
                return False
            
            message = await channel.fetch_message(giveaway['message_id'])
            final_end_timestamp = end_timestamp if end_timestamp else float(giveaway['end_timestamp'])
            
            # CRITICAL FIX: Dynamically load exact participant count from DB instead of resetting
            entry_count = db.get_participant_count(giveaway['giveaway_id'])
            
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(accent_colour=GIVEAWAY_ACCENT_COLOUR)
            
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
            return True
            
        except Exception as e:
            print(f"[GIVEAWAY REBUILD] Error rebuilding message {giveaway['giveaway_id']}: {e}")
            return False

    def _parse_duration(self, duration_str: str) -> timedelta:
        duration_str = duration_str.lower().strip()
        if duration_str.endswith('m'): return timedelta(minutes=int(duration_str[:-1]))
        if duration_str.endswith('h'): return timedelta(hours=int(duration_str[:-1]))
        if duration_str.endswith('d'): return timedelta(days=int(duration_str[:-1]))
        if duration_str.endswith('w'): return timedelta(weeks=int(duration_str[:-1]))
        raise ValueError("Invalid duration format")

    async def _create_giveaway_message(self, channel, prize, host, winners, end_timestamp, message, required_role, giveaway_id) -> discord.Message:
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=GIVEAWAY_ACCENT_COLOUR)
        
        container.add_item(discord.ui.TextDisplay(f"## {prize}"))
        container.add_item(discord.ui.Separator())
        
        if host:
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
        button_row.add_item(discord.ui.Button(label="🎉 Enter", style=discord.ButtonStyle.green, custom_id=f"giveaway_enter_{giveaway_id}"))
        button_row.add_item(discord.ui.Button(label="Participants", style=discord.ButtonStyle.secondary, custom_id=f"giveaway_participants_{giveaway_id}"))
        
        container.add_item(button_row)
        view.add_item(container)
        return await channel.send(view=view)

    async def _update_giveaway_entry_count(self, message_id: int):
        giveaway = db.get_giveaway_by_message_id(message_id)
        if giveaway:
            await self._rebuild_giveaway_message(giveaway)

    async def _handle_enter_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway or giveaway['status'] != 'active':
            await interaction.response.send_message("❌ Giveaway inactive or does not exist.", ephemeral=True)
            return
        
        if db.has_participant(giveaway_id, interaction.user.id):
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
            container.add_item(discord.ui.TextDisplay("You have already entered this giveaway."))
            container.add_item(discord.ui.Separator())
            
            button_row = discord.ui.ActionRow()
            button_row.add_item(discord.ui.Button(label="Leave Giveaway", style=discord.ButtonStyle.danger, custom_id=f"giveaway_leave_{giveaway_id}"))
            container.add_item(button_row)
            view.add_item(container)
            await interaction.response.send_message(view=view, ephemeral=True)
            return

        if giveaway['required_role_id']:
            req_role = interaction.guild.get_role(giveaway['required_role_id'])
            bypass = False
            if giveaway['requirement_bypass_role_id']:
                b_role = interaction.guild.get_role(giveaway['requirement_bypass_role_id'])
                if b_role and b_role in interaction.user.roles:
                    bypass = True
            
            if not bypass and (not req_role or req_role not in interaction.user.roles):
                await interaction.response.send_message(
                    view=build_requirement_failed_view(f"• You must have the {req_role.mention if req_role else 'required role'}."),
                    ephemeral=True
                )
                return

        db.add_participant(giveaway_id, interaction.user.id)
        await self._update_giveaway_entry_count(giveaway['message_id'])
        await interaction.response.send_message("✅ You have successfully entered this giveaway!", ephemeral=True)

    async def _handle_participants_button(self, interaction: discord.Interaction, giveaway_id: str, page: int = 1, is_navigation: bool = False):
        giveaway = db.get_giveaway(giveaway_id)
        if not giveaway:
            msg = "❌ This giveaway no longer exists."
            await interaction.response.edit_message(content=msg, view=None) if is_navigation else await interaction.response.send_message(msg, ephemeral=True)
            return
        
        participants = db.get_participants(giveaway_id)
        if not participants:
            msg = "No one has entered this giveaway yet."
            await interaction.response.edit_message(content=msg, view=None) if is_navigation else await interaction.response.send_message(msg, ephemeral=True)
            return
        
        per_page = 10
        total_pages = (len(participants) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        
        page_participants = participants[(page - 1) * per_page: page * per_page]
        mentions = [f"{(page - 1) * per_page + i + 1}. <@{pid}>" for i, pid in enumerate(page_participants)]
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        container.add_item(discord.ui.TextDisplay(f"Giveaway Participants (Page {page}/{total_pages})"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("\n".join(mentions)))
        
        if total_pages > 1:
            container.add_item(discord.ui.Separator())
            nav_row = discord.ui.ActionRow()
            nav_row.add_item(discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, custom_id=f"giveaway_participants_prev_{giveaway_id}_{page}", disabled=(page == 1)))
            nav_row.add_item(discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, custom_id=f"giveaway_participants_next_{giveaway_id}_{page}", disabled=(page == total_pages)))
            container.add_item(nav_row)
        
        if can_remove_participants(interaction.user):
            container.add_item(discord.ui.Separator())
            btn_row = discord.ui.ActionRow()
            btn_row.add_item(discord.ui.Button(label="Add Participants", style=discord.ButtonStyle.green, custom_id=f"giveaway_add_participants_{giveaway_id}"))
            btn_row.add_item(discord.ui.Button(label="Remove Participants", style=discord.ButtonStyle.danger, custom_id=f"giveaway_remove_participants_{giveaway_id}"))
            container.add_item(btn_row)
        
        view.add_item(container)
        await interaction.response.edit_message(view=view) if is_navigation else await interaction.response.send_message(view=view, ephemeral=True)

    async def _handle_leave_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        giveaway = db.get_giveaway(giveaway_id)
        if giveaway and db.has_participant(giveaway_id, interaction.user.id):
            db.remove_participant(giveaway_id, interaction.user.id)
            await self._update_giveaway_entry_count(giveaway['message_id'])
            await interaction.response.send_message("✅ You have left this giveaway.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You are not in this giveaway.", ephemeral=True)

    async def _handle_remove_participants(self, interaction: discord.Interaction, giveaway_id: str):
        if not can_remove_participants(interaction.user):
            await interaction.response.send_message("❌ Permission denied.", ephemeral=True)
            return
        
        participants = db.get_participants(giveaway_id)
        if not participants:
            await interaction.response.send_message("No participants to remove.", ephemeral=True)
            return
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        container.add_item(discord.ui.TextDisplay("Select participants to remove:"))
        
        user_select = discord.ui.UserSelect(placeholder="Select users...", min_values=1, max_values=min(len(participants), 25))

        async def select_callback(s_interaction: discord.Interaction):
            removed = 0
            for u in user_select.values:
                if db.remove_participant(giveaway_id, u.id):
                    removed += 1
            giveaway = db.get_giveaway(giveaway_id)
            if giveaway:
                await self._update_giveaway_entry_count(giveaway['message_id'])
            await s_interaction.response.send_message(f"✅ Removed {removed} participant(s).", ephemeral=True)

        user_select.callback = select_callback
        action_row = discord.ui.ActionRow()
        action_row.add_item(user_select)
        container.add_item(action_row)
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _handle_add_participants(self, interaction: discord.Interaction, giveaway_id: str):
        if not can_remove_participants(interaction.user):
            await interaction.response.send_message("❌ Permission denied.", ephemeral=True)
            return
        
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        container.add_item(discord.ui.TextDisplay("Select members to add:"))
        
        user_select = discord.ui.UserSelect(placeholder="Select users...", min_values=1, max_values=25)

        async def select_callback(s_interaction: discord.Interaction):
            added = 0
            for u in user_select.values:
                if not u.bot and db.add_participant(giveaway_id, u.id):
                    added += 1
            giveaway = db.get_giveaway(giveaway_id)
            if giveaway:
                await self._update_giveaway_entry_count(giveaway['message_id'])
            await s_interaction.response.send_message(f"✅ Added {added} participant(s).", ephemeral=True)

        user_select.callback = select_callback
        action_row = discord.ui.ActionRow()
        action_row.add_item(user_select)
        container.add_item(action_row)
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    def _start_giveaway_timer(self, giveaway_id: str, end_timestamp: float):
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
                print(f"[GIVEAWAY TIMER] Error: {e}")
        
        self.active_timers[giveaway_id] = asyncio.create_task(timer_task())

    async def _end_giveaway(self, giveaway_id: str):
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
        
        rigged_id = db.get_rigged_winner(giveaway_id)
        if rigged_id and rigged_id in participants:
            winners = [rigged_id]
            db.clear_rigged_winner(giveaway_id)
        else:
            winners = random.sample(participants, min(giveaway['winners_amount'], len(participants)))
        
        for w in winners:
            db.add_winner(giveaway_id, w)
        
        await self._update_giveaway_message_with_winners(message, giveaway, winners)
        await self._send_giveaway_announcement(channel, giveaway, winners, len(participants))

    async def _update_giveaway_message_with_winners(self, message: discord.Message, giveaway: dict, winners: List[int]):
        winner_mentions = [f"<@{w_id}>" for w_id in winners]
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=GIVEAWAY_ACCENT_COLOUR)
        container.add_item(discord.ui.TextDisplay("🎉 Giveaway Ended!"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"🎁 Prize: **{giveaway['prize']}**"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"🏆 Winners:\n" + "\n".join(winner_mentions)))
        view.add_item(container)
        await message.edit(view=view)

    async def _update_giveaway_message_no_winners(self, message: discord.Message):
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=GIVEAWAY_ACCENT_COLOUR)
        container.add_item(discord.ui.TextDisplay("❌ Giveaway Ended"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("No valid entries were found."))
        view.add_item(container)
        await message.edit(view=view)

    async def _send_giveaway_announcement(self, channel: discord.TextChannel, giveaway: dict, winners: List[int], total_entries: int):
        mentions = ", ".join([f"<@{w_id}>" for w_id in winners])
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        container.add_item(discord.ui.TextDisplay("Congratulations! 🎉"))
        container.add_item(discord.ui.TextDisplay(f"{mentions} won **{giveaway['prize']}**"))
        view.add_item(container)
        await channel.send(view=view)

    async def _send_reroll_announcement(self, channel: discord.TextChannel, giveaway: dict, winners: List[int]):
        mentions = ", ".join([f"<@{w_id}>" for w_id in winners])
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        container.add_item(discord.ui.TextDisplay(f"New winner for **{giveaway['prize']}**: {mentions}. Congrats! 🎉"))
        view.add_item(container)
        await channel.send(view=view)

    @commands.Cog.listener()
    async def on_ready(self):
        print("[GIVEAWAY STARTUP] Restoring giveaways from database...")
        all_giveaways = db.get_all_giveaways()
        for giveaway in all_giveaways:
            giveaway_id = giveaway['giveaway_id']
            end_timestamp = giveaway['end_timestamp']
            
            # Restores full message state including participants count from SQLite
            await self._rebuild_giveaway_message(giveaway)
            
            if giveaway['status'] == 'active':
                if datetime.now().timestamp() < end_timestamp:
                    self._start_giveaway_timer(giveaway_id, end_timestamp)
                else:
                    asyncio.create_task(self._end_giveaway(giveaway_id))
        print("[GIVEAWAY STARTUP] Restored successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawaySystem(bot))
