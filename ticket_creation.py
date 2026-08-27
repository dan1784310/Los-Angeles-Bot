"""
Ticket Creation Module
Handles ticket creation from dropdown selection and channel management.
"""

import discord
from discord.ext import commands
from typing import Optional, List
import asyncio

from ticket_database import db
from ticket_views import (
    AddUserModal, RemoveUserModal, TicketIssueModal,
    build_ticket_management_view
)

# Only members with this role may claim tickets or add/remove users on a ticket.
TICKET_MANAGER_ROLE_ID = 1527374021572956291

# The live, auto-updating transcript for every open ticket is posted (and
# kept edited in place) here.
TRANSCRIPT_LOG_CHANNEL_ID = 1529155819239768164


def _has_ticket_manager_role(interaction: discord.Interaction) -> bool:
    """Check whether the interacting member has the ticket manager role."""

    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    return any(role.id == TICKET_MANAGER_ROLE_ID for role in user.roles)


async def _reject_missing_role(interaction: discord.Interaction):
    """Send the standard ephemeral error for missing the ticket manager role."""

    await interaction.response.send_message(
        "❌ You don't have permission to do that.",
        ephemeral=True
    )


async def on_category_select(interaction: discord.Interaction, category_id: str, guild_id: int, db_instance):
    """
    Handle category selection from dropdown.

    Runs the pre-flight checks (config present, not blacklisted, no
    duplicate ticket, category exists) and, if they all pass, opens a
    modal asking the user to describe their issue. The actual ticket
    channel isn't created until that modal is submitted — see
    create_ticket_from_issue.
    
    Args:
        interaction: The interaction object
        category_id: The selected category ID as string
        guild_id: The guild ID
        db_instance: Database instance
    """
    
    # Get guild settings
    settings = db_instance.get_guild_settings(guild_id)
    if not settings:
        await interaction.response.send_message("❌ Ticket system not configured.", ephemeral=True)
        return

    # Check blacklist — members with a blacklisted role can't open tickets
    blacklisted_role_ids = settings.get('blacklisted_roles', [])
    if blacklisted_role_ids and isinstance(interaction.user, discord.Member):
        member_role_ids = {role.id for role in interaction.user.roles}
        if member_role_ids.intersection(blacklisted_role_ids):
            await interaction.response.send_message(
                "❌ You are blacklisted from opening a ticket!",
                ephemeral=True
            )
            return
    
    # Check for duplicate tickets
    user_open_tickets = db_instance.get_user_open_tickets(guild_id, interaction.user.id)
    if user_open_tickets:
        await interaction.response.send_message(
            f"❌ You already have an open ticket. Please close it before creating a new one.",
            ephemeral=True
        )
        return
    
    # Get category info
    category_id_int = int(category_id)
    categories = db_instance.get_ticket_categories(guild_id)
    category = next((cat for cat in categories if cat['id'] == category_id_int), None)
    
    if not category:
        await interaction.response.send_message("❌ Category not found.", ephemeral=True)
        return

    # Ask the user to describe their issue before the ticket is created
    await interaction.response.send_modal(
        TicketIssueModal(
            lambda modal_interaction, issue_text: create_ticket_from_issue(
                modal_interaction, guild_id, db_instance, settings, category_id_int, category, issue_text
            )
        )
    )


async def create_ticket_from_issue(interaction: discord.Interaction, guild_id: int, db_instance,
                                    settings: dict, category_id_int: int, category: dict, issue_text: str):
    """
    Create the ticket channel once the user has submitted the "What seems
    to be the issue?" modal.

    Args:
        interaction: The modal submission interaction
        guild_id: The guild ID
        db_instance: Database instance
        settings: Guild settings fetched during category selection
        category_id_int: The selected category ID
        category: The category info
        issue_text: What the user wrote in the modal
    """

    await interaction.response.defer(ephemeral=True)

    # Get ticket number
    ticket_number = settings.get('ticket_counter', 0) + 1

    # Create ticket channel
    try:
        ticket_channel = await create_ticket_channel(
            interaction.guild,
            interaction.user,
            settings,
            ticket_number,
            ticket_category_info=category
        )
        
        # Save ticket to database
        db_instance.create_ticket(
            guild_id,
            ticket_channel.id,
            interaction.user.id,
            category_id_int,
            ticket_number,
            issue_text
        )
        
        # Send category embed in ticket channel
        await send_ticket_welcome(
            ticket_channel,
            interaction.user,
            category,
            ticket_number,
            issue_text
        )
        
        await interaction.followup.send(
            f"✅ Ticket created: {ticket_channel.mention}",
            ephemeral=True
        )
        
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ The bot doesn't have permission to create channels. Please contact an administrator.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error creating ticket: {str(e)}",
            ephemeral=True
        )


def _build_ping_line(user_mention: str, category: dict) -> str:
    """Build the mention line for a ticket — always pings the user, plus
    whichever role(s) are configured for that specific category."""
    role_ids = category.get('ping_role_ids') or []
    role_mentions = [f"<@&{role_id}>" for role_id in role_ids]
    return ", ".join([user_mention] + role_mentions)


async def create_ticket_channel(guild: discord.Guild, user: discord.Member, 
                                settings: dict, ticket_number: int,
                                ticket_category_info: Optional[dict] = None) -> discord.TextChannel:
    """
    Create a ticket channel with proper permissions.
    
    Args:
        guild: The guild object
        user: The user creating the ticket
        settings: Guild settings from database
        ticket_number: The ticket number
        ticket_category_info: The selected ticket category's info (name, title,
            description, ping_role_ids, visible_role_ids). Used to decide which
            roles can see this channel — falls back to the guild's global
            support roles if the category doesn't specify its own.
    
    Returns:
        The created ticket channel
    """
    
    # Discord channel category (the folder) tickets get created under
    channel_category = guild.get_channel(settings['ticket_category_id'])
    
    # Build permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    # Which roles can see this ticket: this category's own visibility roles
    # if it has any configured, otherwise fall back to the guild's global
    # support roles (so categories that haven't set anything keep working
    # exactly like before).
    visible_role_ids = None
    if ticket_category_info:
        visible_role_ids = ticket_category_info.get('visible_role_ids')
    if not visible_role_ids:
        visible_role_ids = settings.get('support_roles', [])

    for role_id in visible_role_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    # Add administrator roles — utils.get(..., permissions=X) does an exact
    # equality match against the whole permission set, so it will basically
    # never match a real admin role (which usually has other bits set too).
    # Check the .administrator flag on each role instead, and add all of them.
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    # Create channel
    channel_name = "🔴unclaimed"
    ticket_channel = await guild.create_text_channel(
        channel_name,
        overwrites=overwrites,
        category=channel_category
    )
    
    return ticket_channel


async def send_ticket_welcome(channel: discord.TextChannel, user: discord.Member, 
                            category: dict, ticket_number: int, issue_text: Optional[str] = None):
    """
    Send the welcome message in a new ticket channel.

    A single Components V2 message: mentions on top, then the
    configured category text (## title), a separator, the user's
    inquiry (bold), a separator, ticket info, a separator, and the
    management buttons.
    
    Args:
        channel: The ticket channel
        user: The user who created the ticket
        category: The category information
        ticket_number: The ticket number
        issue_text: What the user described in the "What seems to be the
            issue?" modal, if any.
    """

    accent_color = discord.Color.from_rgb(37, 37, 41)

    management_view = build_ticket_management_view(
        config_title=category.get('title', category['name']),
        config_description=category.get('description', ''),
        issue_text=issue_text,
        ticket_number=ticket_number,
        creator_mention=user.mention,
        category_name=category['name'],
        on_close=lambda i: close_ticket(i, channel.id),
        on_claim=lambda i: claim_ticket(i, channel.id, user),
        on_add_user=lambda i: add_user_to_ticket(i, channel.id),
        on_remove_user=lambda i: remove_user_from_ticket(i, channel.id),
        on_transcript=lambda i: generate_transcript(i, channel.id),
        accent_colour=accent_color,
        mention_line=_build_ping_line(user.mention, category)
    )

    await channel.send(view=management_view)


async def close_ticket(interaction: discord.Interaction, channel_id: int):
    """
    Close a ticket channel.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
    """
    
    await interaction.response.send_message("🔒 Closing ticket in 3 seconds...", ephemeral=True)
    
    # Update database
    db.close_ticket(channel_id)
    
    channel = interaction.guild.get_channel(channel_id)

    # Post the transcript (channel still exists at this point)
    if channel:
        await post_ticket_transcript(channel)
    
    await asyncio.sleep(3)
    
    # Delete channel
    if channel:
        await channel.delete()
    
    # Delete from database
    db.delete_ticket(channel_id)


async def _rebuild_management_view(interaction: discord.Interaction, channel_id: int, claimed: bool) -> Optional[discord.ui.LayoutView]:
    """
    Rebuild the ticket's management view from stored data, in either
    the claimed or unclaimed state. Used to edit the public message in
    place when someone claims/unclaims.
    """

    ticket = db.get_ticket_by_channel(channel_id)
    if not ticket:
        return None

    categories = db.get_ticket_categories(ticket['guild_id'])
    category = next((c for c in categories if c['id'] == ticket['category_id']), None)
    if not category:
        return None

    creator = interaction.guild.get_member(ticket['user_id'])
    if not creator:
        try:
            creator = await interaction.guild.fetch_member(ticket['user_id'])
        except discord.NotFound:
            creator = None
    creator_mention = creator.mention if creator else f"<@{ticket['user_id']}>"

    claimant_mention = None
    if claimed and ticket.get('claimed_by'):
        claimant = interaction.guild.get_member(ticket['claimed_by'])
        claimant_mention = claimant.mention if claimant else f"<@{ticket['claimed_by']}>"

    accent_color = discord.Color.from_rgb(37, 37, 41)

    return build_ticket_management_view(
        config_title=category.get('title', category['name']),
        config_description=category.get('description', ''),
        issue_text=ticket.get('issue_text'),
        ticket_number=ticket['ticket_number'],
        creator_mention=creator_mention,
        category_name=category['name'],
        on_close=lambda i: close_ticket(i, channel_id),
        on_claim=lambda i: claim_ticket(i, channel_id, creator),
        on_unclaim=lambda i: unclaim_ticket(i, channel_id),
        claimed=claimed,
        claimant_mention=claimant_mention,
        on_add_user=lambda i: add_user_to_ticket(i, channel_id),
        on_remove_user=lambda i: remove_user_from_ticket(i, channel_id),
        on_transcript=lambda i: generate_transcript(i, channel_id),
        accent_colour=accent_color,
        mention_line=_build_ping_line(creator_mention, category)
    )


async def claim_ticket(interaction: discord.Interaction, channel_id: int, creator: discord.Member):
    """
    Claim a ticket. The bot edits the public ticket message itself,
    swapping the Claim button for Unclaim — visible to everyone. Only
    the claimant is allowed to click Unclaim afterward.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
        creator: The ticket creator
    """
    
    if not _has_ticket_manager_role(interaction):
        await _reject_missing_role(interaction)
        return

    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
        return

    ticket = db.get_ticket_by_channel(channel_id)
    claimed_by = ticket.get('claimed_by') if ticket else None

    if claimed_by:
        await interaction.response.send_message(
            f"❌ This ticket has already been claimed by <@{claimed_by}>.",
            ephemeral=True
        )
        return
    
    # Add claimant to channel
    overwrites = channel.overwrites_for(interaction.user)
    overwrites.read_messages = True
    overwrites.send_messages = True
    await channel.set_permissions(interaction.user, overwrite=overwrites)

    db.set_ticket_claim(channel_id, interaction.user.id)

    # Auto-rename channel to show claimed status
    username_part = interaction.user.display_name[:5].lower()
    new_name = f"🟢claimed-{username_part}"
    try:
        await channel.edit(name=new_name)
        print(f"[TICKET RENAME] Claimed: {channel.name} -> {new_name}")
    except Exception as e:
        print(f"[TICKET RENAME ERROR] Failed to rename on claim: {e}")

    # Edit the actual public message — the button becomes Unclaim for everyone
    new_view = await _rebuild_management_view(interaction, channel_id, claimed=True)
    if new_view:
        await interaction.response.edit_message(view=new_view)
    else:
        await interaction.response.defer()

    # Public announcement
    await interaction.followup.send(
        f"🎯 Ticket claimed by {interaction.user.mention}",
        ephemeral=False
    )


async def unclaim_ticket(interaction: discord.Interaction, channel_id: int):
    """
    Unclaim a ticket. Only the current claimant can do this — anyone
    else clicking the (now public) Unclaim button gets turned away.
    Edits the public message back to showing Claim.

    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
    """

    ticket = db.get_ticket_by_channel(channel_id)
    claimed_by = ticket.get('claimed_by') if ticket else None

    if claimed_by != interaction.user.id:
        if claimed_by:
            message = f"❌ Only <@{claimed_by}> (who claimed this ticket) can unclaim it."
        else:
            message = "❌ This ticket isn't currently claimed."
        await interaction.response.send_message(message, ephemeral=True)
        return

    db.set_ticket_claim(channel_id, None)

    channel = interaction.guild.get_channel(channel_id)
    if channel:
        await channel.set_permissions(interaction.user, overwrite=None)

    # Auto-rename channel to show unclaimed status
    new_name = "🔴unclaimed"
    try:
        await channel.edit(name=new_name)
        print(f"[TICKET RENAME] Unclaimed: {channel.name} -> {new_name}")
    except Exception as e:
        print(f"[TICKET RENAME ERROR] Failed to rename on unclaim: {e}")

    # Edit the actual public message back to showing Claim
    new_view = await _rebuild_management_view(interaction, channel_id, claimed=False)
    if new_view:
        await interaction.response.edit_message(view=new_view)
    else:
        await interaction.response.defer()

    # Public announcement
    await interaction.followup.send(
        f"🔓 Ticket unclaimed by {interaction.user.mention}",
        ephemeral=False
    )


async def add_user_to_ticket(interaction: discord.Interaction, channel_id: int):
    """
    Add a user to a ticket channel.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
    """
    
    if not _has_ticket_manager_role(interaction):
        await _reject_missing_role(interaction)
        return

    await interaction.response.send_modal(
        AddUserModal(lambda i, user_id: on_add_user_submit(i, channel_id, user_id))
    )


async def on_add_user_submit(interaction: discord.Interaction, channel_id: int, user_id: int):
    """
    Handle add user submission.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
        user_id: The user ID to add
    """
    
    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
        return
    
    try:
        user = await interaction.guild.fetch_member(user_id)
        
        # Add user to channel
        overwrites = channel.overwrites_for(user)
        overwrites.read_messages = True
        overwrites.send_messages = True
        await channel.set_permissions(user, overwrite=overwrites)
        
        await interaction.response.send_message(
            f"✅ Added {user.mention} to the ticket.",
            ephemeral=False
        )
        
    except discord.NotFound:
        await interaction.response.send_message("❌ User not found.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error adding user: {str(e)}", ephemeral=True)


async def remove_user_from_ticket(interaction: discord.Interaction, channel_id: int):
    """
    Remove a user from a ticket channel.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
    """
    
    if not _has_ticket_manager_role(interaction):
        await _reject_missing_role(interaction)
        return

    await interaction.response.send_modal(
        RemoveUserModal(lambda i, user_id: on_remove_user_submit(i, channel_id, user_id))
    )


async def on_remove_user_submit(interaction: discord.Interaction, channel_id: int, user_id: int):
    """
    Handle remove user submission.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
        user_id: The user ID to remove
    """
    
    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
        return
    
    try:
        user = await interaction.guild.fetch_member(user_id)
        
        # Remove user from channel
        await channel.set_permissions(user, overwrite=None)
        
        await interaction.response.send_message(
            f"✅ Removed {user.mention} from the ticket.",
            ephemeral=False
        )
        
    except discord.NotFound:
        await interaction.response.send_message("❌ User not found.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error removing user: {str(e)}", ephemeral=True)


async def post_ticket_transcript(channel: discord.TextChannel):
    """
    Generate the ticket's transcript and post it to TRANSCRIPT_LOG_CHANNEL_ID.
    Called once, when the ticket is closed.
    """

    log_channel = channel.guild.get_channel(TRANSCRIPT_LOG_CHANNEL_ID)
    if not log_channel:
        print(f"Transcript log channel {TRANSCRIPT_LOG_CHANNEL_ID} not found.")
        return

    from ticket_transcripts import create_transcript

    try:
        transcript_file = await create_transcript(channel)
        await log_channel.send(
            f"📄 Transcript generated for {channel.mention}",
            file=transcript_file
        )
    except Exception as e:
        print(f"Error posting transcript for channel {channel.id}: {e}")


async def generate_transcript(interaction: discord.Interaction, channel_id: int):
    """
    Generate a transcript of the ticket.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
    """
    
    await interaction.response.defer(ephemeral=True)
    
    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.followup.send("❌ Ticket channel not found.", ephemeral=True)
        return
    
    # Import transcript generator
    from ticket_transcripts import create_transcript
    
    try:
        transcript_file = await create_transcript(channel)
        
        await interaction.followup.send(
            f"📄 Transcript generated for {channel.mention}",
            file=transcript_file,
            ephemeral=True
        )
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Error generating transcript: {str(e)}",
            ephemeral=True
        )


class TicketCreation(commands.Cog):
    """Cog for handling ticket creation and management."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._setup_panel_callbacks()
    
    def _setup_panel_callbacks(self):
        """Setup dropdown callbacks for existing panels."""
        from ticket_panel import create_panel_from_db
        from ticket_views import TicketPanelView
        
        # This will be called when panels are created/updated
        # The callback will be set dynamically when the panel is sent
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions for ticket management."""
        
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id")
        if not custom_id:
            return
        
        # Handle close ticket button
        if custom_id == "close_ticket":
            await close_ticket(interaction, interaction.channel_id)
        
        # Handle claim ticket button
        elif custom_id == "claim_ticket":
            ticket = db.get_ticket_by_channel(interaction.channel_id)
            if ticket:
                creator = await interaction.guild.fetch_member(ticket['user_id'])
                await claim_ticket(interaction, interaction.channel_id, creator)

        # Handle unclaim ticket button
        elif custom_id == "unclaim_ticket":
            await unclaim_ticket(interaction, interaction.channel_id)
        
        # Handle add user button
        elif custom_id == "add_user":
            await add_user_to_ticket(interaction, interaction.channel_id)
        
        # Handle remove user button
        elif custom_id == "remove_user":
            await remove_user_from_ticket(interaction, interaction.channel_id)
        
        # Handle transcript button
        elif custom_id == "transcript":
            await generate_transcript(interaction, interaction.channel_id)


async def setup(bot: commands.Bot):
    """Setup the ticket creation cog."""
    await bot.add_cog(TicketCreation(bot))
