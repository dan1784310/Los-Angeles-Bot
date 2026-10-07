"""
/media  -  AZSRP media team submission + quality-check workflow.

Requires: discord.py >= 2.4  (uses DynamicItem so buttons survive bot restarts, no database)

Load it in your bot:
    await bot.load_extension("media_cog")      # file named media_cog.py
Then sync commands once:
    await bot.tree.sync()
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# ----------------------------- CONFIG ---------------------------------------
PICTURE_QC_CHANNEL_ID = 1550105388022636604   # channel for picture submissions
VIDEO_QC_CHANNEL_ID = 1550105442385141790     # channel for video files + links
ACCEPTOR_ROLE_ID = 1556820767034056794        # "Media Acceptors" role ID
ACCEPTOR_ROLE_NAME = "Media Acceptors"        # only used if ACCEPTOR_ROLE_ID is 0
MEDIA_TEAM_ROLE_ID = 1550098439503880243      # only this role can run /media
# -----------------------------------------------------------------------------

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

# Message IDs already accepted/denied, guards double-clicks.
# Capped so it cannot grow without bound during a long uptime.
_decided: set[int] = set()
_DECIDED_MAX = 10_000


def get_acceptor_role(guild: discord.Guild) -> Optional[discord.Role]:
    if ACCEPTOR_ROLE_ID:
        return guild.get_role(ACCEPTOR_ROLE_ID)
    return discord.utils.get(guild.roles, name=ACCEPTOR_ROLE_NAME)


def classify(att: discord.Attachment) -> Optional[str]:
    """Return 'image', 'video', or None for unsupported file types."""
    ctype = (att.content_type or "").lower()
    ext = os.path.splitext(att.filename.lower())[1]
    if ctype.startswith("image/") or ext in IMAGE_EXT:
        return "image"
    if ctype.startswith("video/") or ext in VIDEO_EXT:
        return "video"
    return None


class DecisionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"media:(?P<action>accept|deny):(?P<uid>\d+)",
):
    """Accept / Deny button. Submitter ID lives in the custom_id, so it survives restarts."""

    def __init__(self, action: str, uid: int) -> None:
        accept = action == "accept"
        super().__init__(
            discord.ui.Button(
                label="Accept" if accept else "Deny",
                style=discord.ButtonStyle.success if accept else discord.ButtonStyle.danger,
                custom_id=f"media:{action}:{uid}",
            )
        )
        self.action = action
        self.uid = uid

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ) -> "DecisionButton":
        return cls(match["action"], int(match["uid"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        role = get_acceptor_role(interaction.guild) if interaction.guild else None
        member = interaction.user
        if role is None or not isinstance(member, discord.Member) or role not in member.roles:
            await interaction.response.send_message(
                "Only Media Acceptors can accept or deny submissions.", ephemeral=True
            )
            return False
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        msg = interaction.message
        if msg is None or msg.id in _decided:
            await interaction.response.send_message(
                "This submission was already decided.", ephemeral=True
            )
            return
        _decided.add(msg.id)
        if len(_decided) > _DECIDED_MAX:
            _decided.clear()

        accepted = self.action == "accept"
        status = (
            f"\u2705 **Accepted by {interaction.user.name}**"
            if accepted
            else f"\u274c **Denied by {interaction.user.name}**"
        )

        # Replace the buttons with the status line. Suppress mentions so the
        # original submitter tag in the body is not re-announced.
        try:
            await interaction.response.edit_message(
                content=f"{msg.content}\n\n{status}",
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as e:
            print(f"[MEDIA] Could not update the decision message: {e}")

        # Mirror the status on the parent message in the QC channel
        channel = interaction.channel
        if isinstance(channel, discord.Thread) and channel.parent is not None:
            try:
                parent_msg = await channel.parent.fetch_message(channel.id)
                await parent_msg.edit(
                    content=f"{parent_msg.content}\n{status}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass

        # Ping the submitter with the decision
        word = "accepted" if accepted else "denied"
        try:
            await channel.send(
                f"<@{self.uid}> your media submission was **{word}** by {interaction.user.name}.",
                allowed_mentions=discord.AllowedMentions(
                    users=[discord.Object(id=self.uid)]
                ),
            )
        except discord.HTTPException as e:
            print(f"[MEDIA] Could not notify the submitter: {e}")


class MediaCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(DecisionButton)

    @app_commands.command(
        name="media",
        description="Submit media to the quality check queue",
    )
    @app_commands.describe(
        file="Photo or video file",
        link="Link to social media content (TikTok, YouTube, Instagram, etc.)",
    )
    @app_commands.guild_only()
    async def media(
        self,
        interaction: discord.Interaction,
        file: Optional[discord.Attachment] = None,
        link: Optional[str] = None,
    ) -> None:
        guild = interaction.guild
        assert guild is not None

        # --- permission: media team only ---
        if MEDIA_TEAM_ROLE_ID:
            member = interaction.user
            if (
                not isinstance(member, discord.Member)
                or not any(r.id == MEDIA_TEAM_ROLE_ID for r in member.roles)
            ):
                await interaction.response.send_message(
                    "Only the media team can use this command.", ephemeral=True
                )
                return

        # --- validate: at least one of file / link ---
        link = link.strip() if link else None
        if not file and not link:
            await interaction.response.send_message(
                "Provide a **file**, a **link**, or both.", ephemeral=True
            )
            return
        if link and not URL_RE.match(link):
            await interaction.response.send_message(
                "That link doesn't look valid. It must start with `http://` or `https://`.",
                ephemeral=True,
            )
            return

        kind: Optional[str] = None
        if file:
            kind = classify(file)
            if kind is None:
                await interaction.response.send_message(
                    "Unsupported file type. Upload a picture or a video.", ephemeral=True
                )
                return
            if file.size > guild.filesize_limit:
                limit_mb = guild.filesize_limit // (1024 * 1024)
                await interaction.response.send_message(
                    f"File is too large for this server ({limit_mb} MB limit). "
                    "Upload it to a site and use the **link** option.",
                    ephemeral=True,
                )
                return

        # --- routing: links and videos -> video channel, pictures -> picture channel ---
        to_video = bool(link) or kind == "video"
        channel_id = VIDEO_QC_CHANNEL_ID if to_video else PICTURE_QC_CHANNEL_ID
        qc_channel = guild.get_channel(channel_id)
        if not isinstance(qc_channel, discord.TextChannel):
            await interaction.response.send_message(
                "QC channel isn't configured correctly. Tell an admin.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        role = get_acceptor_role(guild)
        if role is None:
            await interaction.followup.send(
                f"Couldn't find the **{ACCEPTOR_ROLE_NAME}** role, so nobody "
                "can review submissions. Tell an admin.",
                ephemeral=True,
            )
            return

        ping = role.mention
        label = "Video / Link" if to_video else "Picture"
        uid = interaction.user.id

        # Re-upload the file now (interaction attachment URLs expire)
        files = [await file.to_file()] if file else []

        parent = await qc_channel.send(
            f"{ping} New **{label}** submission from "
            f"{interaction.user.mention} \u2014 review in the thread.",
            allowed_mentions=discord.AllowedMentions(roles=[role], users=False),
        )
        thread = await parent.create_thread(
            name=f"{label} - {interaction.user.name}"[:100],
            auto_archive_duration=1440,
        )

        body = f"**Submitted by:** {interaction.user.mention}"
        if link:
            body += f"\n{link}"

        view = discord.ui.View(timeout=None)
        view.add_item(DecisionButton("accept", uid))
        view.add_item(DecisionButton("deny", uid))

        await thread.send(
            body,
            files=files,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        await interaction.followup.send(
            f"Submitted for review: {thread.mention}", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MediaCog(bot))
