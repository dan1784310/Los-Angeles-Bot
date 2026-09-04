"""
Moderation Main Module
Contains all moderation commands with permission checks and logging.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime, timedelta

from moderation_database import db

# Configuration - Set the role ID that can use moderation commands
MODERATION_ROLE_ID = 1527053931304321130  # Change this to your desired role ID


def has_moderation_role(user: discord.Member) -> bool:
    """Check if user has the moderation role or higher."""
    if user.guild_permissions.administrator:
        return True
    
    # Check if user has the moderation role or a higher role
    mod_role = user.guild.get_role(MODERATION_ROLE_ID)
    if mod_role and mod_role in user.roles:
        return True
    
    # Check if user has any role higher than the moderation role
    if mod_role:
        for role in user.roles:
            if role.position > mod_role.position:
                return True
    
    return False


def can_moderate(moderator: discord.Member, target: discord.Member) -> bool:
    """Check if moderator can manage the target (respects role hierarchy)."""
    if moderator.guild_permissions.administrator:
        return True
    
    # Check if target is higher in hierarchy
    if target.top_role.position >= moderator.top_role.position:
        return False
    
    return True


class WarningsPaginationView(discord.ui.LayoutView):
    """Pagination view for warnings list."""
    
    def __init__(self, warnings_list, user, guild):
        super().__init__(timeout=None)
        self.warnings_list = warnings_list
        self.user = user
        self.guild = guild
        self.current_page = 0
        self.per_page = 5
        self.total_pages = (len(warnings_list) + self.per_page - 1) // self.per_page
        self.container = None
        self.nav_container = None
        self.update_view()
    
    def update_view(self):
        # Remove existing items
        for item in self.children[:]:
            self.remove_item(item)
        
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        
        warning_text = "warning" if len(self.warnings_list) == 1 else "warnings"
        container.add_item(discord.ui.TextDisplay(f"**{self.user.mention} has {len(self.warnings_list)} {warning_text}:**"))
        container.add_item(discord.ui.Separator())
        
        start_idx = self.current_page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.warnings_list))
        
        for i in range(start_idx, end_idx):
            warning = self.warnings_list[i]
            moderator = self.guild.get_member(warning['moderator_id'])
            mod_mention = moderator.mention if moderator else f"<@{warning['moderator_id']}>"
            reason = warning['reason'] or "No reason provided"
            
            try:
                timestamp = int(warning['created_at'])
                time_str = f"<t:{timestamp}:R>"
            except:
                time_str = "Unknown time"
            
            container.add_item(discord.ui.TextDisplay(f"{i + 1}. {reason} - by {mod_mention} - {time_str}"))
        
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"Page {self.current_page + 1}/{self.total_pages}"))
        
        self.add_item(container)
        self.container = container
        
        # Add navigation buttons
        nav_container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        
        left_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="◀️")
        left_button.disabled = self.current_page == 0
        left_button.callback = self.go_left
        nav_container.add_item(left_button)
        
        right_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="▶️")
        right_button.disabled = self.current_page >= self.total_pages - 1
        right_button.callback = self.go_right
        nav_container.add_item(right_button)
        
        self.add_item(nav_container)
        self.nav_container = nav_container
    
    async def go_left(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_view()
            await interaction.response.edit_message(view=self)
    
    async def go_right(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_view()
            await interaction.response.edit_message(view=self)


class ModlogsPaginationView(discord.ui.LayoutView):
    """Pagination view for modlogs list."""
    
    def __init__(self, logs_list, user, guild):
        super().__init__(timeout=None)
        self.logs_list = logs_list
        self.user = user
        self.guild = guild
        self.current_page = 0
        self.per_page = 5
        self.total_pages = (len(logs_list) + self.per_page - 1) // self.per_page
        self.container = None
        self.nav_container = None
        self.update_view()
    
    def update_view(self):
        # Remove existing items
        for item in self.children[:]:
            self.remove_item(item)
        
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        
        container.add_item(discord.ui.TextDisplay(f"**Moderation history for {self.user.mention}:**"))
        container.add_item(discord.ui.Separator())
        
        start_idx = self.current_page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.logs_list))
        
        for i in range(start_idx, end_idx):
            log = self.logs_list[i]
            moderator = self.guild.get_member(log['moderator_id'])
            mod_mention = moderator.mention if moderator else f"<@{log['moderator_id']}>"
            action = log['action_type']
            reason = log['reason'] or "No reason"
            details = log['details'] or ""
            
            try:
                timestamp = int(log['created_at'])
                time_str = f"<t:{timestamp}:F>"
            except:
                time_str = "Unknown time"
            
            container.add_item(discord.ui.TextDisplay(f"**{action}** - {reason} {details}"))
            container.add_item(discord.ui.TextDisplay(f"By: {mod_mention} | {time_str}"))
            container.add_item(discord.ui.Separator())
        
        container.add_item(discord.ui.TextDisplay(f"Page {self.current_page + 1}/{self.total_pages}"))
        
        self.add_item(container)
        self.container = container
        
        # Add navigation buttons
        nav_container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
        
        left_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="◀️")
        left_button.disabled = self.current_page == 0
        left_button.callback = self.go_left
        nav_container.add_item(left_button)
        
        right_button = discord.ui.Button(style=discord.ButtonStyle.secondary, emoji="▶️")
        right_button.disabled = self.current_page >= self.total_pages - 1
        right_button.callback = self.go_right
        nav_container.add_item(right_button)
        
        self.add_item(nav_container)
        self.nav_container = nav_container
    
    async def go_left(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_view()
            await interaction.response.edit_message(view=self)
    
    async def go_right(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_view()
            await interaction.response.edit_message(view=self)


class ModerationSystem(commands.Cog):
    """Main moderation system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Log manual bans to moderation database."""
        try:
            # Get the audit log entry to find who performed the ban
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    # Log the ban
                    moderator_id = entry.user.id if entry.user else guild.me.id
                    reason = entry.reason or "No reason provided"
                    db.add_modlog(guild.id, user.id, moderator_id, "BAN", reason)
                    break
        except Exception as e:
            print(f"[MOD LOGS] Error logging manual ban: {e}")
    
    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Log manual unbans to moderation database."""
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    moderator_id = entry.user.id if entry.user else guild.me.id
                    db.add_modlog(guild.id, user.id, moderator_id, "UNBAN", None)
                    break
        except Exception as e:
            print(f"[MOD LOGS] Error logging manual unban: {e}")
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Log manual nickname changes and timeouts."""
        try:
            # Check for nickname change
            if before.nick != after.nick:
                async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id:
                        changes = entry.changes.before.get('nick') if entry.changes else None
                        if changes is not None:
                            moderator_id = entry.user.id if entry.user else after.guild.me.id
                            db.add_modlog(after.guild.id, after.id, moderator_id, "NICKNAME", f"Changed to: {after.nick}")
                            break
            
            # Check for timeout change
            if before.timed_out != after.timed_out:
                if after.timed_out:
                    # User was timed out
                    async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target.id == after.id:
                            if entry.changes and 'communication_disabled_until' in entry.changes.after:
                                moderator_id = entry.user.id if entry.user else after.guild.me.id
                                reason = entry.reason or "No reason provided"
                                db.add_modlog(after.guild.id, after.id, moderator_id, "TIMEOUT", reason)
                                break
                else:
                    # User timeout was removed
                    async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target.id == after.id:
                            if entry.changes and 'communication_disabled_until' in entry.changes.before:
                                moderator_id = entry.user.id if entry.user else after.guild.me.id
                                db.add_modlog(after.guild.id, after.id, moderator_id, "UNTIMEOUT", None)
                                break
        except Exception as e:
            print(f"[MOD LOGS] Error logging manual member update: {e}")
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Log manual voice mutes/unmutes."""
        try:
            if before.mute != after.mute:
                if after.mute:
                    # User was muted
                    async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target.id == member.id:
                            if entry.changes and 'mute' in entry.changes.after:
                                moderator_id = entry.user.id if entry.user else member.guild.me.id
                                db.add_modlog(member.guild.id, member.id, moderator_id, "MUTE", None)
                                break
                else:
                    # User was unmuted
                    async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                        if entry.target.id == member.id:
                            if entry.changes and 'mute' in entry.changes.before:
                                moderator_id = entry.user.id if entry.user else member.guild.me.id
                                db.add_modlog(member.guild.id, member.id, moderator_id, "UNMUTE", None)
                                break
        except Exception as e:
            print(f"[MOD LOGS] Error logging manual voice state update: {e}")
    
    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string like '1s', '1m', '1h', '1d', '1w'."""
        duration_str = duration_str.lower().strip()
        if duration_str.endswith('s'):
            return timedelta(seconds=int(duration_str[:-1]))
        if duration_str.endswith('m'):
            return timedelta(minutes=int(duration_str[:-1]))
        if duration_str.endswith('h'):
            return timedelta(hours=int(duration_str[:-1]))
        if duration_str.endswith('d'):
            return timedelta(days=int(duration_str[:-1]))
        if duration_str.endswith('w'):
            return timedelta(weeks=int(duration_str[:-1]))
        raise ValueError("Invalid duration format")
    
    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.describe(user="The member to kick", reason="The reason for kicking")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ You don't have the Kick Members permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await user.kick(reason=reason)
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "KICK", reason)
            await interaction.followup.send(f"✅ Successfully kicked {user.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to kick user: {e}", ephemeral=True)
    
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(user="The member to timeout", duration="Duration (e.g., 1s, 1m, 1h, 1d, 1w)", reason="The reason for timeout")
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: Optional[str] = None):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ You don't have the Moderate Members permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            td = self._parse_duration(duration)
            until = discord.utils.utcnow() + td
            await user.timeout(until, reason=reason)
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "TIMEOUT", reason, f"Duration: {duration}")
            await interaction.followup.send(f"✅ Successfully timed out {user.mention} for {duration}!", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Invalid duration format. Use formats like: 10s, 10m, 2h, 3d, 1w", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to timeout user: {e}", ephemeral=True)
    
    @app_commands.command(name="untimeout", description="Remove timeout from a member")
    @app_commands.describe(user="The member to untimeout")
    async def untimeout(self, interaction: discord.Interaction, user: discord.Member):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ You don't have the Moderate Members permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await user.timeout(None, reason="Timeout removed")
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "UNTIMEOUT", None)
            await interaction.followup.send(f"✅ Successfully removed timeout from {user.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to remove timeout: {e}", ephemeral=True)
    
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(user="The member to warn", reason="The reason for warning")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            db.add_warning(interaction.guild.id, user.id, interaction.user.id, reason)
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "WARN", reason)
            
            # Send warning message to the user
            warn_message = f"{user.mention}, you have been warned for the following reason: {reason}"
            
            await interaction.followup.send(f"✅ Successfully warned {user.mention}!", ephemeral=True)
            await interaction.channel.send(warn_message)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to warn user: {e}", ephemeral=True)
    
    @app_commands.command(name="warnings", description="Show a member's warnings")
    @app_commands.describe(user="The member to check warnings for")
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            warning_count = db.get_warning_count(interaction.guild.id, user.id)
            warnings_list = db.get_warnings(interaction.guild.id, user.id)
            
            if warning_count == 0:
                view = discord.ui.LayoutView(timeout=None)
                container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
                container.add_item(discord.ui.TextDisplay(f"ℹ️ {user.mention} has no warnings."))
                view.add_item(container)
                await interaction.followup.send(view=view, ephemeral=True)
                return
            
            view = WarningsPaginationView(warnings_list, user, interaction.guild)
            await interaction.followup.send(view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to retrieve warnings: {e}", ephemeral=True)
    
    @app_commands.command(name="slowmode", description="Enable slowmode in the channel")
    @app_commands.describe(duration="Duration (e.g., 1s, 1m, 1h, 1d, 1w)")
    async def slowmode(self, interaction: discord.Interaction, duration: str):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You don't have the Manage Channels permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            td = self._parse_duration(duration)
            seconds = int(td.total_seconds())
            
            if seconds > 21600:  # Discord max is 6 hours
                await interaction.followup.send("❌ Duration cannot exceed 6 hours.", ephemeral=True)
                return
            
            await interaction.channel.edit(slowmode_delay=seconds)
            await interaction.followup.send(f"✅ Slowmode enabled for {duration}!", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Invalid duration format. Use formats like: 10s, 10m, 2h, 3d, 1w", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to set slowmode: {e}", ephemeral=True)
    
    @app_commands.command(name="lock", description="Lock the current channel")
    async def lock(self, interaction: discord.Interaction):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You don't have the Manage Channels permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Store lock in database
            db.set_channel_lock(interaction.guild.id, interaction.channel.id)
            
            # Deny @everyone permission to send messages
            everyone_role = interaction.guild.default_role
            overwrite = interaction.channel.overwrites_for(everyone_role)
            overwrite.send_messages = False
            await interaction.channel.set_permissions(everyone_role, overwrite=overwrite)
            
            await interaction.followup.send("✅ Channel locked!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to lock channel: {e}", ephemeral=True)
    
    @app_commands.command(name="unlock", description="Unlock the current channel")
    async def unlock(self, interaction: discord.Interaction):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You don't have the Manage Channels permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Remove lock from database
            db.remove_channel_lock(interaction.guild.id, interaction.channel.id)
            
            # Allow @everyone to send messages
            everyone_role = interaction.guild.default_role
            overwrite = interaction.channel.overwrites_for(everyone_role)
            overwrite.send_messages = None
            await interaction.channel.set_permissions(everyone_role, overwrite=overwrite)
            
            await interaction.followup.send("✅ Channel unlocked!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to unlock channel: {e}", ephemeral=True)
    
    @app_commands.command(name="nickname", description="Change a member's nickname")
    @app_commands.describe(user="The member to rename", name="The new nickname")
    async def nickname(self, interaction: discord.Interaction, user: discord.Member, name: str):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.manage_nicknames:
            await interaction.response.send_message("❌ You don't have the Manage Nicknames permission.", ephemeral=True)
            return
        
        if len(name) > 32:
            await interaction.response.send_message("❌ Nickname cannot exceed 32 characters.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await user.edit(nick=name)
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "NICKNAME", f"Changed to: {name}")
            await interaction.followup.send(f"✅ Successfully changed {user.mention}'s nickname to {name}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to change nickname: {e}", ephemeral=True)
    
    @app_commands.command(name="modlogs", description="Show a member's moderation history")
    @app_commands.describe(user="The member to check modlogs for")
    async def modlogs(self, interaction: discord.Interaction, user: discord.Member):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            logs = db.get_modlogs(interaction.guild.id, user.id)
            
            if not logs:
                view = discord.ui.LayoutView(timeout=None)
                container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
                container.add_item(discord.ui.TextDisplay(f"ℹ️ {user.mention} has no moderation history."))
                view.add_item(container)
                await interaction.followup.send(view=view, ephemeral=True)
                return
            
            view = ModlogsPaginationView(logs, user, interaction.guild)
            await interaction.followup.send(view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to retrieve modlogs: {e}", ephemeral=True)
    
    @app_commands.command(name="mute", description="Mute a member in voice channel")
    @app_commands.describe(user="The member to mute")
    async def mute(self, interaction: discord.Interaction, user: discord.Member):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.mute_members:
            await interaction.response.send_message("❌ You don't have the Mute Members permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await user.edit(mute=True)
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "MUTE", None)
            await interaction.followup.send(f"✅ Successfully muted {user.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to mute user: {e}", ephemeral=True)
    
    @app_commands.command(name="unmute", description="Unmute a member in voice channel")
    @app_commands.describe(user="The member to unmute")
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        if not has_moderation_role(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        if not can_moderate(interaction.user, user):
            await interaction.response.send_message("❌ You cannot moderate this user (role hierarchy).", ephemeral=True)
            return
        
        if not interaction.user.guild_permissions.mute_members:
            await interaction.response.send_message("❌ You don't have the Mute Members permission.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            await user.edit(mute=False)
            db.add_modlog(interaction.guild.id, user.id, interaction.user.id, "UNMUTE", None)
            await interaction.followup.send(f"✅ Successfully unmuted {user.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to unmute user: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationSystem(bot))
