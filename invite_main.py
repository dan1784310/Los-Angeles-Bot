"""
Invite Tracking Module
Tracks who invited whom into the server and exposes /invites and
/invite-leaderboard commands.
"""

import asyncio
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from invite_database import db

# ============================================================
# PAGINATION VIEW
# ============================================================


class InviteLeaderboardView(discord.ui.View):
    """Pagination view for the invite leaderboard, 10 entries per page."""

    def __init__(
        self,
        entries: List[Dict[str, Any]],
        guild: discord.Guild,
    ):
        super().__init__(timeout=180)
        self.entries = entries
        self.guild = guild
        self.current_page = 0
        self.per_page = 10
        self.total_pages = max(
            1,
            (len(entries) + self.per_page - 1) // self.per_page,
        )
        self.update_buttons()

    def update_buttons(self) -> None:
        self.left_button.disabled = self.current_page == 0
        self.right_button.disabled = self.current_page >= self.total_pages - 1

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🏆 Invite Leaderboard",
            color=discord.Color.from_rgb(37, 37, 41)
        )

        if not self.entries:
            embed.description = "No invites have been tracked yet."
            embed.set_footer(text="Page 1/1")
            return embed

        start_idx = self.current_page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.entries))

        lines = []
        for idx in range(start_idx, end_idx):
            entry = self.entries[idx]
            member = self.guild.get_member(entry["_id"])
            mention = member.mention if member else f"<@{entry['_id']}>"
            lines.append(
                f"**{idx + 1}.** {mention} — **{entry['total']}** total "
                f"(**{entry['active']}** active, **{entry['left']}** left)"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="invite_lb_left")
    async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="invite_lb_right")
    async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ============================================================
# INVITE TRACKING COG
# ============================================================


class InviteSystem(commands.Cog):
    """Tracks invites and provides invite stats/leaderboard commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> {invite_code: uses}
        self.invite_cache: Dict[int, Dict[str, int]] = {}
        # Prevent simultaneous joins from reading the same invite-use snapshot.
        self.guild_locks: Dict[int, asyncio.Lock] = {}

    async def _cache_guild_invites(self, guild: discord.Guild) -> bool:
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {
                invite.code: invite.uses or 0
                for invite in invites
            }
            return True
        except discord.Forbidden:
            self.invite_cache.pop(guild.id, None)
            print(
                f"[INVITE] Missing permissions to fetch invites for "
                f"guild {guild.id}. Grant Manage Guild and restart the bot."
            )
        except Exception as e:
            self.invite_cache.pop(guild.id, None)
            print(f"[INVITE] Error caching invites for guild {guild.id}: {e}")

        return False

    async def initialize_invites(self) -> None:
        for guild in self.bot.guilds:
            await self._cache_guild_invites(guild)
        print("[INVITE] Invite cache built for all guilds.")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.initialize_invites()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        self.invite_cache.pop(guild.id, None)
        self.guild_locks.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None:
            return
        self.invite_cache.setdefault(invite.guild.id, {})[
            invite.code
        ] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None:
            return
        guild_invites = self.invite_cache.get(invite.guild.id)
        if guild_invites is not None:
            guild_invites.pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        guild = member.guild
        guild_lock = self.guild_locks.setdefault(guild.id, asyncio.Lock())

        async with guild_lock:
            before = self.invite_cache.get(guild.id)
            if before is None:
                # Establish a baseline only. Without the pre-join snapshot, the
                # invite cannot be identified safely and must not be guessed.
                await self._cache_guild_invites(guild)
                return

            try:
                after_invites = await guild.invites()
            except discord.Forbidden:
                self.invite_cache.pop(guild.id, None)
                print(
                    f"[INVITE] Missing permissions to fetch invites for "
                    f"guild {guild.id}. Grant Manage Guild and restart the bot."
                )
                return
            except Exception as e:
                self.invite_cache.pop(guild.id, None)
                print(
                    f"[INVITE] Error fetching invites on member join "
                    f"for guild {guild.id}: {e}"
                )
                return

            after = {
                invite.code: invite.uses or 0
                for invite in after_invites
            }
            self.invite_cache[guild.id] = after

            used_invites = [
                invite
                for invite in after_invites
                if (invite.uses or 0) > before.get(invite.code, 0)
            ]
            used_invite = max(
                used_invites,
                key=lambda invite: (invite.uses or 0)
                - before.get(invite.code, 0),
                default=None,
            )

            if not used_invite or not used_invite.inviter:
                print(
                    f"[INVITE] Could not determine who invited {member} "
                    f"(vanity URL or unknown invite)."
                )
                return

            recorded = await asyncio.to_thread(
                db.add_invite,
                guild.id,
                used_invite.inviter.id,
                member.id,
                used_invite.code,
            )
            if recorded:
                print(
                    f"[INVITE] {member} was invited by "
                    f"{used_invite.inviter} using code {used_invite.code}"
                )
            else:
                print(f"[INVITE] Failed to save the invite for {member}.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        await asyncio.to_thread(
            db.mark_left,
            member.guild.id,
            member.id,
        )

    # ============================================================
    # COMMANDS
    # ============================================================

    @app_commands.command(
        name="invites",
        description="Shows invite statistics of a user.",
    )
    @app_commands.describe(
        user="The user to check invite statistics for (defaults to you)",
    )
    async def invites(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True,
            )
            return

        target = user or interaction.user
        await interaction.response.defer(ephemeral=True)

        try:
            stats = await asyncio.to_thread(
                db.get_invite_stats,
                interaction.guild.id,
                target.id,
            )

            embed = discord.Embed(
                title=f"📨 Invite Stats for {target.display_name}",
                color=discord.Color.from_rgb(37, 37, 41),
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(
                name="Total Invites",
                value=str(stats["total"]),
                inline=True,
            )
            embed.add_field(
                name="Active Invites",
                value=str(stats["active"]),
                inline=True,
            )
            embed.add_field(
                name="Left Invites",
                value=str(stats["left"]),
                inline=True,
            )
            embed.set_footer(
                text="Total includes active and past invitees.",
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[INVITE] Error retrieving invite stats: {e}")
            await interaction.followup.send(
                "❌ Failed to retrieve invite statistics.",
                ephemeral=True,
            )

    @app_commands.command(
        name="invite-leaderboard",
        description="Shows the leaderboard for most invites.",
    )
    async def invite_leaderboard(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            entries = await asyncio.to_thread(
                db.get_leaderboard,
                interaction.guild.id,
            )
            view = InviteLeaderboardView(entries, interaction.guild)
            await interaction.followup.send(
                embed=view.build_embed(),
                view=view,
                ephemeral=True,
            )
        except Exception as e:
            print(f"[INVITE] Error retrieving invite leaderboard: {e}")
            await interaction.followup.send(
                "❌ Failed to retrieve the invite leaderboard.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    existing_cog = bot.get_cog("InviteSystem")
    if isinstance(existing_cog, InviteSystem):
        invite_system = existing_cog
    else:
        invite_system = InviteSystem(bot)
        await bot.add_cog(invite_system)

    # Cogs are loaded from bot.py's ready handler, so the Cog's own ready
    # listener is registered too late to receive the first ready event.
    if bot.is_ready():
        await invite_system.initialize_invites()
