"""
Ticket Creation Module
Handles ticket creation from dropdown selection and channel management.
"""

import discord
from discord.ext import commands
from typing import Optional, List
import asyncio

from ticket_database import db
from ticket_views import TicketManagementView, AddUserModal, RemoveUserModal


async def on_category_select(interaction: discord.Interaction, category_id: str, guild_id: int, db_instance):
    """
    Handle category selection from dropdown.
    
    Args:
        interaction: The interaction object
        category_id: The selected category ID as string
        guild_id: The guild ID
        db_instance: Database instance
    """
    
    await interaction.response.defer()
    
    # Get guild settings
    settings = db_instance.get_guild_settings(guild_id)
    if not settings:
        await interaction.followup.send("❌ Ticket system not configured.", ephemeral=True)
        return

    # Check blacklist — members with a blacklisted role can't open tickets
    blacklisted_role_ids = settings.get('blacklisted_roles', [])
    if blacklisted_role_ids and isinstance(interaction.user, discord.Member):
        member_role_ids = {role.id for role in interaction.user.roles}
        if member_role_ids.intersection(blacklisted_role_ids):
            await interaction.followup.send(
                "❌ You are blacklisted from opening a ticket!",
                ephemeral=True
            )
            return
    
    # Check for duplicate tickets
    user_open_tickets = db_instance.get_user_open_tickets(guild_id, interaction.user.id)
    if user_open_tickets:
        await interaction.followup.send(
            f"❌ You already have an open ticket. Please close it before creating a new one.",
            ephemeral=True
        )
        return
    
    # Get category info
    category_id_int = int(category_id)
    categories = db_instance.get_ticket_categories(guild_id)
    category = next((cat for cat in categories if cat['id'] == category_id_int), None)
    
    if not category:
        await interaction.followup.send("❌ Category not found.", ephemeral=True)
        return
    
    # Get ticket number
    ticket_number = settings.get('ticket_counter', 0) + 1
    
    # Create ticket channel
    try:
        ticket_channel = await create_ticket_channel(
            interaction.guild,
            interaction.user,
            settings,
            ticket_number
        )
        
        # Save ticket to database
        db_instance.create_ticket(
            guild_id,
            ticket_channel.id,
            interaction.user.id,
            category_id_int,
            ticket_number
        )
        
        # Send category embed in ticket channel
        await send_ticket_welcome(
            ticket_channel,
            interaction.user,
            category,
            ticket_number
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


async def create_ticket_channel(guild: discord.Guild, user: discord.Member, 
                                settings: dict, ticket_number: int) -> discord.TextChannel:
    """
    Create a ticket channel with proper permissions.
    
    Args:
        guild: The guild object
        user: The user creating the ticket
        settings: Guild settings from database
        ticket_number: The ticket number
    
    Returns:
        The created ticket channel
    """
    
    # Get category
    category = guild.get_channel(settings['ticket_category_id'])
    
    # Build permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    # Add support roles
    support_role_ids = settings.get('support_roles', [])
    for role_id in support_role_ids:
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
    channel_name = f"ticket-{ticket_number:04d}"
    ticket_channel = await guild.create_text_channel(
        channel_name,
        overwrites=overwrites,
        category=category
    )
    
    return ticket_channel


async def send_ticket_welcome(channel: discord.TextChannel, user: discord.Member, 
                            category: dict, ticket_number: int):
    """
    Send the welcome message in a new ticket channel.
    
    Args:
        channel: The ticket channel
        user: The user who created the ticket
        category: The category information
        ticket_number: The ticket number
    """
    
    # Create embed
    embed = discord.Embed(
        title=category.get('title', category['name']),
        description=category.get('description', ''),
        color=discord.Color.from_rgb(37, 37, 41)
    )
    
    embed.add_field(name="Ticket Number", value=f"#{ticket_number:04d}", inline=True)
    embed.add_field(name="Created By", value=user.mention, inline=True)
    embed.add_field(name="Category", value=category['name'], inline=True)
    
    # Create management view
    view = TicketManagementView(
        channel.id,
        on_close=lambda i: close_ticket(i, channel.id),
        on_claim=lambda i: claim_ticket(i, channel.id, user),
        on_add_user=lambda i: add_user_to_ticket(i, channel.id),
        on_remove_user=lambda i: remove_user_from_ticket(i, channel.id),
        on_transcript=lambda i: generate_transcript(i, channel.id)
    )
    
    await channel.send(content=f"{user.mention}", embed=embed, view=view)


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
    
    await asyncio.sleep(3)
    
    # Delete channel
    channel = interaction.guild.get_channel(channel_id)
    if channel:
        await channel.delete()
    
    # Delete from database
    db.delete_ticket(channel_id)


async def claim_ticket(interaction: discord.Interaction, channel_id: int, creator: discord.Member):
    """
    Claim a ticket (add claimant to the channel).
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
        creator: The ticket creator
    """
    
    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
        return
    
    # Add claimant to channel
    overwrites = channel.overwrites_for(interaction.user)
    overwrites.read_messages = True
    overwrites.send_messages = True
    await channel.set_permissions(interaction.user, overwrite=overwrites)
    
    await interaction.response.send_message(
        f"🎯 Ticket claimed by {interaction.user.mention}",
        ephemeral=False
    )


async def add_user_to_ticket(interaction: discord.Interaction, channel_id: int):
    """
    Add a user to a ticket channel.
    
    Args:
        interaction: The interaction object
        channel_id: The ticket channel ID
    """
    
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
