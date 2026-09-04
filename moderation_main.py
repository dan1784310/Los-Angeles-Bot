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


class ModerationSystem(commands.Cog):
    """Main moderation system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
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
            
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
            
            if warning_count == 0:
                container.add_item(discord.ui.TextDisplay(f"ℹ️ {user.mention} has no warnings."))
            else:
                container.add_item(discord.ui.TextDisplay(f"**{user.mention} has {warning_count} warning(s):**"))
                container.add_item(discord.ui.Separator())
                
                for i, warning in enumerate(warnings_list[:10], 1):
                    moderator = interaction.guild.get_member(warning['moderator_id'])
                    mod_mention = moderator.mention if moderator else f"<@{warning['moderator_id']}>"
                    reason = warning['reason'] or "No reason provided"
                    
                    # Convert timestamp to Discord timestamp
                    try:
                        timestamp = int(warning['created_at'])
                        time_str = f"<t:{timestamp}:R>"
                    except:
                        time_str = "Unknown time"
                    
                    container.add_item(discord.ui.TextDisplay(f"{i}. {reason} - by {mod_mention} - {time_str}"))
                
                if len(warnings_list) > 10:
                    container.add_item(discord.ui.Separator())
                    container.add_item(discord.ui.TextDisplay(f"... and {len(warnings_list) - 10} more warning(s)."))
            
            view.add_item(container)
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
            
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))
            
            if not logs:
                container.add_item(discord.ui.TextDisplay(f"ℹ️ {user.mention} has no moderation history."))
            else:
                container.add_item(discord.ui.TextDisplay(f"**Moderation history for {user.mention}:**"))
                container.add_item(discord.ui.Separator())
                
                for log in logs[:20]:
                    moderator = interaction.guild.get_member(log['moderator_id'])
                    mod_mention = moderator.mention if moderator else f"<@{log['moderator_id']}>"
                    action = log['action_type']
                    reason = log['reason'] or "No reason"
                    details = log['details'] or ""
                    
                    # Convert timestamp to Discord timestamp
                    try:
                        timestamp = int(log['created_at'])
                        time_str = f"<t:{timestamp}:F>"
                    except:
                        time_str = "Unknown time"
                    
                    container.add_item(discord.ui.TextDisplay(f"**{action}** - {reason} {details}"))
                    container.add_item(discord.ui.TextDisplay(f"By: {mod_mention} | {time_str}"))
                    container.add_item(discord.ui.Separator())
                
                if len(logs) > 20:
                    container.add_item(discord.ui.TextDisplay(f"... and {len(logs) - 20} more action(s)."))
            
            view.add_item(container)
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
