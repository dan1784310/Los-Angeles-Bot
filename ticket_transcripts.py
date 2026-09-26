"""
Ticket transcript generation and Components V2 delivery helpers.

Transcript metadata is rendered in a Discord component card. The attached
transcript file contains only the channel's message history.
"""

import html
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import discord


@dataclass
class TranscriptBundle:
    """A message-only transcript file plus the metadata shown in its card."""

    file_bytes: bytes
    filename: str
    ticket_number: int
    guild_name: str
    channel_name: str
    channel_mention: str
    channel_id: int
    generated_at: datetime
    message_count: int
    creator_id: Optional[int] = None
    closed_by: Optional[discord.abc.User] = None

    @property
    def ticket_name(self) -> str:
        return f"ticket-{self.ticket_number:04d}"

    def create_file(self) -> discord.File:
        """Create a fresh attachment for delivery or fallback sending."""
        return discord.File(
            io.BytesIO(self.file_bytes),
            filename=self.filename,
        )


async def _fetch_messages(channel: discord.TextChannel) -> List[discord.Message]:
    return [
        message
        async for message in channel.history(limit=None, oldest_first=True)
    ]


def _format_message_lines(messages: List[discord.Message]) -> List[str]:
    """Format only message records; ticket metadata is never written here."""
    lines: List[str] = []

    for message in messages:
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{message.author} ({message.author.id})"
        content = message.content or "[No text content]"

        if message.attachments:
            filenames = ", ".join(
                attachment.filename for attachment in message.attachments
            )
            content += f"\n[Attachments: {filenames}]"

        if message.embeds:
            content += f"\n[Embeds: {len(message.embeds)} embed(s)]"

        lines.append(f"[{timestamp}] {author}")
        lines.append(content)
        lines.append("-" * 40)
        lines.append("")

    if not lines:
        lines.append("[No messages were sent in this ticket.]")

    return lines


def _get_ticket_record(channel: discord.TextChannel) -> Optional[dict]:
    from ticket_database import db

    return db.get_ticket_by_channel(channel.id)


async def create_transcript(
    channel: discord.TextChannel,
    closed_by: Optional[discord.abc.User] = None,
) -> TranscriptBundle:
    """Create a message-only transcript and the metadata needed for its card."""
    messages = await _fetch_messages(channel)

    ticket = _get_ticket_record(channel)
    ticket_number = int(ticket.get("ticket_number", 0)) if ticket else 0
    ticket_name = f"ticket-{ticket_number:04d}"
    generated_at = datetime.now(timezone.utc)
    file_lines = _format_message_lines(messages)
    file_bytes = "\n".join(file_lines).encode("utf-8")
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    filename = f"transcript_{ticket_name}_messages_{timestamp}.txt"

    return TranscriptBundle(
        file_bytes=file_bytes,
        filename=filename,
        ticket_number=ticket_number,
        guild_name=getattr(channel.guild, "name", "Unknown server"),
        channel_name=channel.name,
        channel_mention=channel.mention,
        channel_id=channel.id,
        generated_at=generated_at,
        message_count=len(messages),
        creator_id=int(ticket["user_id"]) if ticket and ticket.get("user_id") else None,
        closed_by=closed_by,
    )


def build_transcript_card(
    bundle: TranscriptBundle,
) -> tuple[discord.ui.LayoutView, discord.File]:
    """Build a Components V2 card with metadata above the file component."""
    attachment = bundle.create_file()
    generated_timestamp = int(bundle.generated_at.timestamp())

    info_lines = [
        f"**Server:** {bundle.guild_name}",
    ]
    if bundle.creator_id is not None:
        info_lines.append(f"**Created By:** <@{bundle.creator_id}>")
    info_lines.extend([
        f"**Generated:** <t:{generated_timestamp}:F>",
        f"**Messages:** {bundle.message_count}",
    ])
    if bundle.closed_by is not None:
        info_lines.append(f"**Closed By:** {bundle.closed_by.mention}")

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(37, 37, 41)
    )
    container.add_item(
        discord.ui.TextDisplay(
            f"# Ticket Transcript\n"
            f"Complete message history for `{bundle.ticket_name}`."
        )
    )
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("\n".join(info_lines)))
    container.add_item(discord.ui.Separator())
    container.add_item(
        discord.ui.TextDisplay(
            "**Message File**\n"
            "The attachment below contains only the ticket messages."
        )
    )
    container.add_item(discord.ui.File(attachment))
    view.add_item(container)

    return view, attachment


def build_transcript_embed(bundle: TranscriptBundle) -> discord.Embed:
    """Build a classic embed fallback for clients without Components V2."""
    generated_timestamp = int(bundle.generated_at.timestamp())
    embed = discord.Embed(
        title=f"Ticket Transcript • {bundle.ticket_name}",
        color=discord.Color.from_rgb(37, 37, 41),
    )
    embed.add_field(name="Server", value=bundle.guild_name, inline=True)
    embed.add_field(name="Messages", value=str(bundle.message_count), inline=True)
    if bundle.creator_id is not None:
        embed.add_field(name="Created By", value=f"<@{bundle.creator_id}>")
    if bundle.closed_by is not None:
        embed.add_field(name="Closed By", value=bundle.closed_by.mention)
    embed.add_field(
        name="Generated",
        value=f"<t:{generated_timestamp}:F>",
    )
    embed.set_footer(text="The attached file contains only the ticket messages.")
    return embed


async def send_transcript(
    destination,
    bundle: TranscriptBundle,
    ephemeral: bool = False,
):
    """Send a transcript card, falling back to a classic embed if needed."""
    view, attachment = build_transcript_card(bundle)
    kwargs = {"view": view, "file": attachment}
    if ephemeral:
        kwargs["ephemeral"] = True

    try:
        return await destination.send(**kwargs)
    except discord.HTTPException as component_error:
        print(
            "[TRANSCRIPT] Components V2 delivery failed; using embed fallback: "
            f"{component_error}"
        )

    fallback_attachment = bundle.create_file()
    kwargs = {
        "embed": build_transcript_embed(bundle),
        "file": fallback_attachment,
    }
    if ephemeral:
        kwargs["ephemeral"] = True
    return await destination.send(**kwargs)


async def create_html_transcript(
    channel: discord.TextChannel,
    closed_by: Optional[discord.abc.User] = None,
) -> discord.File:
    """
    Legacy HTML transcript kept for compatibility.

    Like the text transcript, the file contains only message records; ticket
    metadata is intentionally excluded.
    """
    del closed_by
    messages = await _fetch_messages(channel)
    message_blocks = []

    for message in messages:
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author_name = html.escape(str(message.author))
        content = html.escape(message.content or "[No text content]")
        content = content.replace("\n", "<br>")

        attachments_html = ""
        if message.attachments:
            links = "".join(
                f"<a href='{html.escape(attachment.url, quote=True)}'>"
                f"{html.escape(attachment.filename)}</a><br>"
                for attachment in message.attachments
            )
            attachments_html = f"<div class='attachment'>{links}</div>"

        message_blocks.append(
            "<div class='message'>"
            f"<div class='author'>{author_name}</div>"
            f"<div class='timestamp'>{timestamp}</div>"
            f"<div class='content'>{content}</div>"
            f"{attachments_html}"
            "</div>"
        )

    if not message_blocks:
        message_blocks.append(
            "<div class='message'>[No messages were sent in this ticket.]</div>"
        )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Ticket Messages</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #36393f;
            color: #dcddde;
        }}
        .message {{
            background-color: #40444b;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
        }}
        .timestamp {{ color: #72767d; font-size: 12px; }}
        .author {{ color: #ffffff; font-weight: bold; }}
        .content {{ margin-top: 5px; }}
        .attachment {{ color: #00b0f4; margin-top: 8px; }}
    </style>
</head>
<body>
{''.join(message_blocks)}
</body>
</html>"""

    html_file = io.BytesIO(html_content.encode("utf-8"))
    html_file.seek(0)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return discord.File(
        html_file,
        filename=f"transcript_messages_{timestamp}.html",
    )
