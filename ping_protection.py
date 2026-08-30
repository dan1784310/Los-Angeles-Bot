"""
Ping Protection System
Monitors pings to protected roles and issues warnings/mutes.
"""

import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


# ==========================================
# CONFIGURATION
# ==========================================

PROTECTED_ROLE_ID = 1527055221098811433
WHITELISTED_ROLE_ID = 1543709338764582952
WARNINGS_BEFORE_TIMEOUT = 3
TIMEOUT_DURATION_MINUTES = 10


# ==========================================
# WARNING STORAGE
# ==========================================

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
    data["last_warning"] = datetime.now(timezone.utc)
    return data["warning_count"]


def reset_warnings(user_id: int):
    """Reset warnings for a user."""
    if user_id in _warnings:
        _warnings[user_id]["warning_count"] = 0
        _warnings[user_id]["last_warning"] = None


def get_ordinal_suffix(n: int) -> str:
    """Return correct ordinal suffix for warning messages (1st, 2nd, 3rd, 4th...)."""
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


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

        # Ensure author is a Member instance (has roles attribute)
        if not isinstance(message.author, discord.Member):
            return

        # Explicitly collect user role IDs as integers
        user_role_ids = [r.id for r in message.author.roles]
        
        # Whitelist Check
        if int(WHITELISTED_ROLE_ID) in user_role_ids:
            print(f"[PING PROTECTION] Ignored {message.author.display_name}: User possesses whitelisted role.")
            return

        # Fetch protected role
        protected_role = message.guild.get_role(int(PROTECTED_ROLE_ID))
        if not protected_role:
            return

        # Exclude author if their highest role is equal to or higher than protected role
        if message.author.top_role >= protected_role:
            return

        # Handle message reply exceptions (replying without pinging)
        if message.reference and message.reference.message_id:
            try:
                referenced_message = message.reference.cached_message or await message.channel.fetch_message(message.reference.message_id)
                if referenced_message and referenced_message.author.bot:
                    return
                if referenced_message and isinstance(referenced_message.author, discord.Member):
                    if protected_role in referenced_message.author.roles or referenced_message.author.top_role >= protected_role:
                        return
            except (discord.NotFound, discord.HTTPException):
                pass

        # Check direct user mentions
        for mention in message.mentions:
            if isinstance(mention, discord.Member):
                if protected_role in mention.roles or mention.top_role >= protected_role:
                    await self._handle_unauthorized_ping(message, mention)
                    return

        # Check role mentions
        for role_mention in message.role_mentions:
            if role_mention >= protected_role:
                await self._handle_unauthorized_ping(message, role_mention)
                return

    async def _handle_unauthorized_ping(self, message: discord.Message, pinged_target):
        """Handle an unauthorized ping."""
        user_id = message.author.id
        warning_count = add_warning(user_id)
        suffix = get_ordinal_suffix(warning_count)
        
        warning_msg = (
            f"{message.author.mention} You have been warned for pinging {pinged_target.mention}. "
            f"This is your {warning_count}{suffix} warning."
        )
        
        await message.reply(warning_msg)
        print(f"[PING PROTECTION] {message.author.display_name} warned for pinging {pinged_target.name} (Warning {warning_count})")
        
        if warning_count >= WARNINGS_BEFORE_TIMEOUT:
            await self._timeout_user(message.author, message.guild)

    async def _timeout_user(self, member: discord.Member, guild: discord.Guild):
        """Timeout a user for the specified duration."""
        try:
            timeout_duration = timedelta(minutes=TIMEOUT_DURATION_MINUTES)
            await member.timeout(timeout_duration, reason=f"Reached {WARNINGS_BEFORE_TIMEOUT} warnings for unauthorized pings")
            
            reset_warnings(member.id)
            print(f"[PING PROTECTION] Timed out {member.display_name} for {TIMEOUT_DURATION_MINUTES} minutes")
            
            await member.send(
                f"You have been timed out in {guild.name} for {TIMEOUT_DURATION_MINUTES} minutes due to reaching {WARNINGS_BEFORE_TIMEOUT} warnings for unauthorized pings. Your warnings have been reset."
            )
        except discord.Forbidden:
            print(f"[PING PROTECTION] Missing permissions to timeout {member.display_name}")
        except Exception as e:
            print(f"[PING PROTECTION] Failed to timeout user: {e}")


async def setup(bot: commands.Bot):
    """Setup the ping protection cog."""
    await bot.add_cog(PingProtection(bot))