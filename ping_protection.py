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

# Whitelisted role ID - users with this role are exempt from ping protection
WHITELISTED_ROLE_ID = 1543709338764582952

# Number of warnings before timeout
WARNINGS_BEFORE_TIMEOUT = 3

# Timeout duration
TIMEOUT_DURATION_MINUTES = 10


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
    
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages for unauthorized pings."""
        
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return
        
        # Check if user has whitelisted role (exempt from ping protection)
        user_role_ids = [role.id for role in message.author.roles]
        print(f"[PING PROTECTION] User {message.author.display_name} roles: {user_role_ids}")
        print(f"[PING PROTECTION] Whitelisted role ID: {WHITELISTED_ROLE_ID}")
        if WHITELISTED_ROLE_ID in user_role_ids:
            print(f"[PING PROTECTION] User {message.author.display_name} is whitelisted, skipping ping check")
            return
        
        # Get the protected role
        protected_role = message.guild.get_role(PROTECTED_ROLE_ID)
        if not protected_role:
            return
        
        # Ignore if replying to a bot message or a protected user
        if message.reference and message.reference.message_id:
            try:
                referenced_message = await message.channel.fetch_message(message.reference.message_id)
                if referenced_message.author.bot:
                    return
                # Check if replying to a protected user
                if isinstance(referenced_message.author, discord.Member):
                    if protected_role in referenced_message.author.roles or referenced_message.author.top_role >= protected_role:
                        return
            except:
                pass
        
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
        
        # Check if user should be timed out
        if warning_count >= WARNINGS_BEFORE_TIMEOUT:
            await self._timeout_user(message.author, message.guild)
    
    async def _timeout_user(self, member: discord.Member, guild: discord.Guild):
        """Timeout a user for the specified duration."""
        
        try:
            # Calculate timeout duration
            timeout_duration = timedelta(minutes=TIMEOUT_DURATION_MINUTES)
            
            # Apply timeout
            await member.timeout(timeout_duration, reason=f"Reached {WARNINGS_BEFORE_TIMEOUT} warnings for unauthorized pings")
            print(f"[PING PROTECTION] Timed out {member.display_name} for {TIMEOUT_DURATION_MINUTES} minutes")
            
            # Reset warnings immediately
            reset_warnings(member.id)
            print(f"[PING PROTECTION] Reset warnings for {member.display_name} (timeout applied)")
            
            # Notify the user
            await member.send(
                f"You have been timed out for {TIMEOUT_DURATION_MINUTES} minutes due to reaching {WARNINGS_BEFORE_TIMEOUT} warnings for unauthorized pings. Your warnings have been reset."
            )
            
        except discord.Forbidden:
            print(f"[PING PROTECTION] No permission to timeout {member.display_name}")
            await member.send("You have reached the warning limit, but I do not have permission to timeout you.")
        except Exception as e:
            print(f"[PING PROTECTION] Error timing out user: {e}")


async def setup(bot: commands.Bot):
    """Setup the ping protection cog."""
    await bot.add_cog(PingProtection(bot))
