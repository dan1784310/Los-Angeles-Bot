"""
Ping Protection System
Monitors pings to protected roles and issues warnings/mutes.
"""

import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Dict, Optional


# ==========================================
# CONFIGURATION
# ==========================================

# Role ID that is protected from being pinged by lower roles
PROTECTED_ROLE_ID = 1527055221098811433

# Mute role ID (you'll need to set this to your actual mute role)
MUTE_ROLE_ID = None  # TODO: Set this to your mute role ID

# Number of warnings before mute
WARNINGS_BEFORE_MUTE = 3

# Mute duration
MUTE_DURATION_MINUTES = 10


# ==========================================
# WARNING STORAGE
# ==========================================

# Stores warning counts: {user_id: {warning_count: int, last_warning: datetime}}
_warnings: Dict[int, Dict] = {}


def get_warnings(user_id: int) -> Dict:
    """Get or create warning data for a user."""
    if user_id not in _warnings:
        _warnings[user_id] = {
            "warning_count": 0,
            "last_warning": None
        }
    return _warnings[user_id]


def add_warning(user_id: int) -> int:
    """Add a warning and return the new count."""
    data = get_warnings(user_id)
    data["warning_count"] += 1
    data["last_warning"] = datetime.now()
    return data["warning_count"]


def reset_warnings(user_id: int):
    """Reset warnings for a user."""
    if user_id in _warnings:
        _warnings[user_id]["warning_count"] = 0
        _warnings[user_id]["last_warning"] = None


# ==========================================
# PING PROTECTION COG
# ==========================================

class PingProtection(commands.Cog):
    """Ping protection system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mute_tasks: Dict[int, asyncio.Task] = {}
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages for unauthorized pings."""
        
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return
        
        # Get the protected role
        protected_role = message.guild.get_role(PROTECTED_ROLE_ID)
        if not protected_role:
            return
        
        # Check if author has permission to ping (role at or above protected role)
        author_top_role = message.author.top_role if isinstance(message.author, discord.Member) else None
        if author_top_role and author_top_role >= protected_role:
            return  # User has permission to ping
        
        # Check if message contains a ping to the protected role or anyone higher
        for mention in message.mentions:
            if isinstance(mention, discord.Member):
                # Check if the mentioned user has the protected role or higher
                if protected_role in mention.roles or mention.top_role >= protected_role:
                    await self._handle_unauthorized_ping(message, mention)
                    return
        
        # Check for role mentions
        for role_mention in message.role_mentions:
            if role_mention >= protected_role:
                await self._handle_unauthorized_ping(message, role_mention)
                return
    
    async def _handle_unauthorized_ping(self, message: discord.Message, pinged_target):
        """Handle an unauthorized ping."""
        
        user_id = message.author.id
        warning_count = add_warning(user_id)
        
        # Send warning message
        warning_msg = (
            f"{message.author.mention} You have been warned for pinging {pinged_target.mention}. "
            f"This is your {warning_count}{'st' if warning_count == 1 else 'nd' if warning_count == 2 else 'rd' if warning_count == 3 else 'th'} warning."
        )
        
        await message.reply(warning_msg)
        
        print(f"[PING PROTECTION] {message.author.display_name} warned for pinging {pinged_target.name} (Warning {warning_count})")
        
        # Check if user should be muted
        if warning_count >= WARNINGS_BEFORE_MUTE:
            await self._mute_user(message.author, message.guild)
    
    async def _mute_user(self, member: discord.Member, guild: discord.Guild):
        """Mute a user for the specified duration."""
        
        if not MUTE_ROLE_ID:
            print("[PING PROTECTION] MUTE_ROLE_ID not set, cannot mute user")
            await member.send("⚠️ You have reached the warning limit, but no mute role is configured.")
            return
        
        mute_role = guild.get_role(MUTE_ROLE_ID)
        if not mute_role:
            print(f"[PING PROTECTION] Could not find mute role with ID {MUTE_ROLE_ID}")
            await member.send("⚠️ You have reached the warning limit, but the mute role could not be found.")
            return
        
        try:
            # Add mute role
            await member.add_roles(mute_role)
            print(f"[PING PROTECTION] Muted {member.display_name} for {MUTE_DURATION_MINUTES} minutes")
            
            # Notify the user
            await member.send(
                f"🔇 You have been muted for {MUTE_DURATION_MINUTES} minutes due to reaching {WARNINGS_BEFORE_MUTE} warnings for unauthorized pings."
            )
            
            # Schedule unmute
            self._schedule_unmute(member, guild, mute_role)
            
        except discord.Forbidden:
            print(f"[PING PROTECTION] No permission to mute {member.display_name}")
            await member.send("⚠️ You have reached the warning limit, but I do not have permission to mute you.")
        except Exception as e:
            print(f"[PING PROTECTION] Error muting user: {e}")
    
    async def _schedule_unmute(self, member: discord.Member, guild: discord.Guild, mute_role: discord.Role):
        """Schedule an unmute task."""
        
        async def unmute_task():
            try:
                await asyncio.sleep(MUTE_DURATION_MINUTES * 60)
                
                # Check if user is still in guild
                member_check = guild.get_member(member.id)
                if member_check and mute_role in member_check.roles:
                    await member_check.remove_roles(mute_role)
                    print(f"[PING PROTECTION] Unmuted {member_check.display_name}")
                    await member_check.send("🔊 You have been unmuted.")
                
                # Clean up task
                if member.id in self._mute_tasks:
                    del self._mute_tasks[member.id]
                    
            except Exception as e:
                print(f"[PING PROTECTION] Error in unmute task: {e}")
        
        # Create and store the task
        import asyncio
        task = asyncio.create_task(unmute_task())
        self._mute_tasks[member.id] = task


async def setup(bot: commands.Bot):
    """Setup the ping protection cog."""
    await bot.add_cog(PingProtection(bot))
