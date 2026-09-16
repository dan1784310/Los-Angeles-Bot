"""
Ticket Panel Module
Handles the creation and display of ticket panels.

Uses Discord's Components V2 (LayoutView / Container / TextDisplay /
MediaGallery / Separator) instead of a classic Embed, matching the style
already used for the announcement cards in bot.py.
"""

import discord
from typing import Dict, List, Any, Optional
from ticket_views import build_ticket_panel_view


def _collect_texts(source: Dict[str, Any]) -> List[Optional[str]]:
    return [source.get(f'text{i}') for i in range(1, 6)]


def create_ticket_panel(session: Dict[str, Any], categories: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a ticket panel (Components V2) from an in-progress setup session.
    
    Args:
        session: Setup session data containing panel configuration
        categories: List of ticket categories from database
    
    Returns:
        Dictionary with a 'view' key (a discord.ui.LayoutView)
    """
    
    view = build_ticket_panel_view(
        categories,
        lambda interaction, category_id: None,  # Will be handled by ticket_creation
        banner_url=session.get('banner_url'),
        texts=_collect_texts(session),
        bottom_banner_url=session.get('bottom_banner_url')
    )
    
    return {'view': view}


def create_panel_from_db(guild_id: int, db) -> Optional[Dict[str, Any]]:
    """
    Create a ticket panel (Components V2) from database settings.
    
    Args:
        guild_id: The guild ID
        db: Database instance
    
    Returns:
        Dictionary with a 'view' key, or None if not configured
    """
    
    settings = db.get_guild_settings(guild_id)
    if not settings:
        return None
    
    categories = db.get_ticket_categories(guild_id)
    if not categories:
        return None
    
    # Import here to avoid circular dependency - callback will be set by ticket_creation cog
    view = build_ticket_panel_view(
        categories,
        lambda interaction, category_id: None,  # Callback will be set by ticket_creation cog
        banner_url=settings.get('banner_url'),
        texts=_collect_texts(settings),
        bottom_banner_url=settings.get('bottom_banner_url')
    )
    
    return {'view': view}


async def update_panel(guild: discord.Guild, db) -> bool:
    """
    Re-attach a working ticket panel in the configured channel.

    This rebuilds the panel's view with a *live* category-select
    callback and either edits the existing panel message in place or
    sends a new one. Meant to be called on bot startup for every guild
    with ticket settings configured, since a plain (non-persistent)
    view's callback only exists in memory for as long as the bot
    process that sent it keeps running — after a restart, an old panel
    message still looks fine but its dropdown silently does nothing
    until it's re-attached like this.

    Args:
        guild: The guild object
        db: Database instance

    Returns:
        True if successful, False otherwise
    """

    settings = db.get_guild_settings(guild.id)
    if not settings:
        return False

    panel_channel = guild.get_channel(settings['panel_channel_id'])
    if not panel_channel:
        return False

    categories = db.get_ticket_categories(guild.id)
    if not categories:
        return False

    # Import here to avoid circular imports, and to make sure we wire
    # up the REAL category-select handler rather than a placeholder.
    from ticket_creation import on_category_select

    view = build_ticket_panel_view(
        categories,
        lambda i, cid: on_category_select(i, cid, guild.id, db),
        banner_url=settings.get('banner_url'),
        texts=_collect_texts(settings),
        bottom_banner_url=settings.get('bottom_banner_url')
    )

    # Get existing message
    existing_message_id = db.get_panel_message(guild.id)
    if existing_message_id:
        try:
            existing_message = await panel_channel.fetch_message(existing_message_id)
            # Clear any old content/embeds explicitly — a Components V2
            # message can't mix content/embeds with the new layout components.
            await existing_message.edit(content=None, embeds=[], view=view)
            return True
        except:
            pass
    
    # Send new message if no existing one
    message = await panel_channel.send(view=view)
    db.save_panel_message(guild.id, message.id)
    return True


async def delete_panel(guild: discord.Guild, db) -> bool:
    """
    Delete the ticket panel from the configured channel.
    
    Args:
        guild: The guild object
        db: Database instance
    
    Returns:
        True if successful, False otherwise
    """
    
    settings = db.get_guild_settings(guild.id)
    if not settings:
        return False
    
    panel_channel = guild.get_channel(settings['panel_channel_id'])
    if not panel_channel:
        return False
    
    # Get existing message
    existing_message_id = db.get_panel_message(guild.id)
    if existing_message_id:
        try:
            existing_message = await panel_channel.fetch_message(existing_message_id)
            await existing_message.delete()
            db.clear_panel_message(guild.id)
            return True
        except:
            pass
    
    return False
