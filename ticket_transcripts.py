"""
Ticket Transcripts Module
Handles transcript generation for ticket channels.
"""

import discord
from typing import List
import io
import datetime
from datetime import timezone


async def create_transcript(channel: discord.TextChannel) -> discord.File:
    """
    Create a transcript of all messages in a ticket channel.
    
    Args:
        channel: The ticket channel to transcribe
    
    Returns:
        A discord.File containing the transcript
    """
    
    # Fetch all messages
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        messages.append(message)
    
    # Build transcript content
    transcript_lines = []
    
    # Header
    transcript_lines.append("=" * 50)
    transcript_lines.append(f"TRANSCRIPT - {channel.name}")
    transcript_lines.append(f"Guild: {channel.guild.name}")
    transcript_lines.append(f"Channel ID: {channel.id}")
    transcript_lines.append(f"Generated: {datetime.datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    transcript_lines.append("=" * 50)
    transcript_lines.append("")
    
    # Messages
    for message in messages:
        # Timestamp
        timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Author
        author = f"{message.author} ({message.author.id})"
        
        # Content
        content = message.content or ""
        
        # Add attachments info
        if message.attachments:
            content += "\n[Attachments: " + ", ".join(a.filename for a in message.attachments) + "]"
        
        # Add embeds info
        if message.embeds:
            content += "\n[Embeds: " + str(len(message.embeds)) + " embed(s)]"
        
        # Format message
        transcript_lines.append(f"[{timestamp}] {author}:")
        transcript_lines.append(content)
        transcript_lines.append("-" * 30)
        transcript_lines.append("")
    
    # Footer
    transcript_lines.append("=" * 50)
    transcript_lines.append("End of Transcript")
    transcript_lines.append("=" * 50)
    
    # Create file
    transcript_content = "\n".join(transcript_lines)
    transcript_file = io.BytesIO(transcript_content.encode('utf-8'))
    transcript_file.seek(0)
    
    return discord.File(
        transcript_file,
        filename=f"transcript_{channel.name}_{datetime.datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt"
    )


async def create_html_transcript(channel: discord.TextChannel) -> discord.File:
    """
    Create an HTML transcript of all messages in a ticket channel.
    
    Args:
        channel: The ticket channel to transcribe
    
    Returns:
        A discord.File containing the HTML transcript
    """
    
    # Fetch all messages
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        messages.append(message)
    
    # Build HTML content
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Transcript - {channel.name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #36393f;
            color: #dcddde;
        }}
        .header {{
            background-color: #202225;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .message {{
            background-color: #40444b;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
        }}
        .timestamp {{
            color: #72767d;
            font-size: 12px;
        }}
        .author {{
            color: #ffffff;
            font-weight: bold;
        }}
        .content {{
            margin-top: 5px;
            white-space: pre-wrap;
        }}
        .attachment {{
            color: #00b0f4;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Transcript - {channel.name}</h1>
        <p>Guild: {channel.guild.name}</p>
        <p>Channel ID: {channel.id}</p>
        <p>Generated: {datetime.datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
    </div>
"""
    
    # Messages
    for message in messages:
        # Timestamp
        timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Author
        author_name = message.author.display_name
        author_color = str(message.author.color) if message.author.color else "#ffffff"
        
        # Avatar
        avatar_url = message.author.display_avatar.url if message.author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        
        # Content
        content = message.content or ""
        
        # Format content (basic Discord markdown to HTML)
        content = content.replace("**", "<strong>").replace("**", "</strong>")
        content = content.replace("*", "<em>").replace("*", "</em>")
        content = content.replace("~~", "<del>").replace("~~", "</del>")
        content = content.replace("`", "<code>").replace("`", "</code>")
        
        # Add attachments
        attachments_html = ""
        if message.attachments:
            attachments_html = "<div class='attachment'>"
            for attachment in message.attachments:
                attachments_html += f"<a href='{attachment.url}'>{attachment.filename}</a><br>"
            attachments_html += "</div>"
        
        # Add message
        html_content += f"""
    <div class="message">
        <img src="{avatar_url}" width="40" height="40" style="border-radius: 50%; float: left; margin-right: 10px;">
        <div>
            <span class="author" style="color: {author_color}">{author_name}</span>
            <span class="timestamp">{timestamp}</span>
        </div>
        <div class="content">{content}</div>
        {attachments_html}
    </div>
"""
    
    # Footer
    html_content += """
</body>
</html>
"""
    
    # Create file
    html_file = io.BytesIO(html_content.encode('utf-8'))
    html_file.seek(0)
    
    return discord.File(
        html_file,
        filename=f"transcript_{channel.name}_{datetime.datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.html"
    )
