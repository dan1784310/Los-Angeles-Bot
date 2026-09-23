"""
Invite Tracking Module
Tracks who invited whom into the server, recovers historical joins for
current members on first startup, and exposes /invites and
/invite-leaderboard commands.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from invite_database import db

MEMBER_SEARCH_PAGE_SIZE = 100
MEMBER_SEARCH_SORT_NEWEST = 1

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
        self.backfill_task: Optional[asyncio.Task] = None

    def cog_unload(self):
        if self.backfill_task and not self.backfill_task.done():
            self.backfill_task.cancel()

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
        self._schedule_historical_backfill()

    def _schedule_historical_backfill(self) -> None:
        if self.backfill_task and not self.backfill_task.done():
            return
        self.backfill_task = asyncio.create_task(
            self.backfill_existing_history(),
            name="discord-invite-history-backfill",
        )

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
                member.joined_at.timestamp() if member.joined_at else None,
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

    @staticmethod
    def _historical_invite_record(
        entry: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        member_data = entry.get("member") or {}
        user_data = member_data.get("user") or {}
        inviter_id = entry.get("inviter_id")
        invited_id = user_data.get("id")

        if inviter_id is None or invited_id is None or user_data.get("bot"):
            return None

        joined_at = None
        joined_at_ms = None
        joined_at_value = member_data.get("joined_at")
        if joined_at_value:
            try:
                parsed_joined_at = datetime.fromisoformat(
                    joined_at_value.replace("Z", "+00:00")
                )
                joined_at = parsed_joined_at.timestamp()
                joined_at_ms = int(joined_at * 1000)
            except (TypeError, ValueError):
                pass

        join_source_type = entry.get("join_source_type")
        if join_source_type is not None:
            join_source_type = int(join_source_type)

        return {
            "inviter_id": int(inviter_id),
            "invited_id": int(invited_id),
            "invite_code": entry.get("source_invite_code"),
            "join_source_type": join_source_type,
            "join_source_application_id": entry.get(
                "join_source_application_id"
            ),
            "join_source_channel_id": entry.get("join_source_channel_id"),
            "joined_at": joined_at,
            "joined_at_ms": joined_at_ms,
        }

    async def _fetch_member_search_page(
        self,
        guild_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        # This is the same bot-accessible member index used by Discord's
        # Members page. It is not part of the public API documentation.
        route = discord.http.Route(
            "POST",
            "/guilds/{guild_id}/members-search",
            guild_id=guild_id,
            metadata="invite-history-backfill",
        )

        for attempt in range(5):
            # discord.py 2.7 returns the decoded response body directly.
            data = await self.bot.http.request(route, json=payload)

            if not isinstance(data, dict):
                raise RuntimeError(
                    "Discord returned an invalid member search response."
                )

            # A 202 indexing response contains retry_after but no members.
            if "members" not in data and "retry_after" in data:
                retry_after = min(
                    max(float(data.get("retry_after", 1)), 0.1),
                    15,
                )
                await asyncio.sleep(retry_after)
                continue

            return data

        raise RuntimeError(
            "Discord is still indexing member data after five retries."
        )

    async def _backfill_guild_history(self, guild: discord.Guild) -> bool:
        if guild.me is None:
            return False

        permissions = guild.me.guild_permissions
        can_search_members = any(
            (
                permissions.administrator,
                permissions.manage_guild,
                permissions.ban_members,
                permissions.kick_members,
                permissions.moderate_members,
                permissions.manage_roles,
                permissions.manage_nicknames,
            )
        )
        if not can_search_members:
            print(
                f"[INVITE] Historical backfill skipped for guild "
                f"{guild.id}: the bot lacks member-management permissions."
            )
            return False

        payload: Dict[str, Any] = {
            "or_query": {},
            "and_query": {},
            "limit": MEMBER_SEARCH_PAGE_SIZE,
            "sort": MEMBER_SEARCH_SORT_NEWEST,
        }
        after = None
        seen_cursors = set()
        processed_members = 0
        imported_records = 0

        print(
            f"[INVITE] Recovering historical joins for guild {guild.id}..."
        )

        while True:
            if after is not None:
                payload["after"] = after

            data = await self._fetch_member_search_page(guild.id, payload)
            members = data.get("members") or []
            records = [
                record
                for entry in members
                if (
                    record := self._historical_invite_record(entry)
                ) is not None
            ]

            if records:
                saved_count = await asyncio.to_thread(
                    db.backfill_invites,
                    guild.id,
                    records,
                )
                if saved_count == 0:
                    print(
                        f"[INVITE] Historical backfill could not save "
                        f"a page for guild {guild.id}; it will retry later."
                    )
                    return False
                imported_records += saved_count

            processed_members += len(members)
            total_result_count = data.get("total_result_count")
            if (
                not members
                or len(members) < MEMBER_SEARCH_PAGE_SIZE
                or (
                    total_result_count is not None
                    and processed_members >= int(total_result_count)
                )
            ):
                break

            cursor_member = None
            cursor_user = None
            for candidate in reversed(members):
                candidate_member = candidate.get("member") or {}
                candidate_user = candidate_member.get("user") or {}
                if candidate_member.get("joined_at") and candidate_user.get(
                    "id"
                ) is not None:
                    cursor_member = candidate_member
                    cursor_user = candidate_user
                    break
            if cursor_member is None or cursor_user is None:
                break

            parsed_joined_at = datetime.fromisoformat(
                cursor_member["joined_at"].replace("Z", "+00:00")
            )
            next_cursor = {
                "guild_joined_at": int(parsed_joined_at.timestamp() * 1000),
                "user_id": str(cursor_user["id"]),
            }
            cursor_key = (
                next_cursor["guild_joined_at"],
                next_cursor["user_id"],
            )
            if cursor_key in seen_cursors:
                break
            seen_cursors.add(cursor_key)
            after = next_cursor

            # Avoid bursts when recovering a large member list.
            await asyncio.sleep(0.2)

        marked_complete = await asyncio.to_thread(
            db.mark_backfill_complete,
            guild.id,
            imported_records,
        )
        if marked_complete:
            print(
                f"[INVITE] Historical backfill complete for guild {guild.id}: "
                f"checked {processed_members} current members and recovered "
                f"{imported_records} attributed invite records."
            )
        return marked_complete

    async def backfill_existing_history(self) -> None:
        for guild in list(self.bot.guilds):
            try:
                already_complete = await asyncio.to_thread(
                    db.is_backfill_complete,
                    guild.id,
                )
                if already_complete:
                    continue

                await self._backfill_guild_history(guild)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(
                    f"[INVITE] Historical backfill failed for guild "
                    f"{guild.id}: {e}. Live invite tracking is still active."
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
