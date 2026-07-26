"""
Ticket Views Module
Contains all UI components (modals, buttons, dropdowns) for the ticket system.
"""

import discord
from discord import ui
from discord.ext import commands
from typing import Optional, List, Dict, Any, Callable


# ==========================================
# STEP 1: Ticket Configuration Modal
# ==========================================

class TicketConfigModal(ui.Modal, title='Ticket Configuration'):
    """Modal for configuring basic ticket settings."""
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction)


# ==========================================
# STEP 2: Panel Designer Modals
# ==========================================

class BannerURLModal(ui.Modal, title='Banner Image'):
    """Modal for banner image URL."""
    
    banner_url = ui.TextInput(
        label='Banner Image URL',
        placeholder='https://example.com/banner.png',
        required=False,
        style=discord.TextStyle.short
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.banner_url.value)


class TextBlockModal(ui.Modal, title='Text Block'):
    """Modal for text blocks."""
    
    text = ui.TextInput(
        label='Text Content',
        placeholder='Enter your text here (Markdown supported)',
        style=discord.TextStyle.paragraph,
        required=False
    )
    
    def __init__(self, block_number: int, on_submit: Callable):
        super().__init__()
        self.block_number = block_number
        self.on_submit_callback = on_submit
        self.text.label = f'Text {block_number}'
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.block_number, self.text.value)


class CategoryInputModal(ui.Modal, title='Add Ticket Category'):
    """Modal for adding a single ticket category."""
    
    category_name = ui.TextInput(
        label='Category Name',
        placeholder='e.g., General Questions',
        style=discord.TextStyle.short,
        required=True
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.category_name.value)


class BottomBannerModal(ui.Modal, title='Bottom Banner Image'):
    """Modal for bottom banner image URL."""
    
    banner_url = ui.TextInput(
        label='Bottom Banner Image URL',
        placeholder='https://example.com/bottom-banner.png',
        required=False,
        style=discord.TextStyle.short
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.banner_url.value)


# ==========================================
# STEP 3: Category Configuration Modal
# ==========================================

class CategoryConfigModal(ui.Modal):
    """Fixed Category Config Modal"""
    title_input = ui.TextInput(
        label='Embed Title',
        placeholder='e.g., General Questions',
        style=discord.TextStyle.short,
        required=True
    )
    
    description_input = ui.TextInput(
        label='Embed Description',
        placeholder='e.g., Please describe your question in detail...',
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    def __init__(self, category_name: str, on_submit: Callable):
        super().__init__(title=f"Configure: {category_name}")
        self.category_name = category_name
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(
            interaction, 
            self.category_name, 
            self.title_input.value, 
            self.description_input.value
        )


# ==========================================
# Navigation Buttons
# ==========================================

class NavigationButtons(ui.View):
    """Standard navigation buttons for setup wizard."""
    
    def __init__(self, on_back: Optional[Callable] = None, 
                 on_continue: Optional[Callable] = None,
                 on_cancel: Optional[Callable] = None,
                 show_back: bool = True,
                 show_continue: bool = True,
                 show_cancel: bool = True):
        super().__init__(timeout=None)
        self.on_back = on_back
        self.on_continue = on_continue
        self.on_cancel = on_cancel
        
        if show_back:
            self.add_item(BackButton(self.on_back))
        if show_continue:
            self.add_item(ContinueButton(self.on_continue))
        if show_cancel:
            self.add_item(CancelButton(self.on_cancel))


class BackButton(ui.Button):
    """Back button."""
    
    def __init__(self, callback: Optional[Callable]):
        super().__init__(label='← Back', style=discord.ButtonStyle.secondary)
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class ContinueButton(ui.Button):
    """Continue button."""
    
    def __init__(self, callback: Optional[Callable]):
        super().__init__(label='Continue →', style=discord.ButtonStyle.primary)
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class CancelButton(ui.Button):
    """Cancel button."""
    
    def __init__(self, callback: Optional[Callable]):
        super().__init__(label='Cancel', style=discord.ButtonStyle.danger)
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class ConfirmButton(ui.Button):
    """Confirm button."""
    
    def __init__(self, callback: Optional[Callable]):
        super().__init__(label='✅ Confirm', style=discord.ButtonStyle.success)
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class OpenModalButton(ui.Button):
    """Button that opens a modal directly (modals can only be sent as a
    fresh interaction response, never via followup), so this must always
    be its own button rather than bundled into a message send."""

    def __init__(self, label: str, callback: Callable):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class ModalStepView(ui.View):
    """View for a step that needs to open a modal, optionally alongside
    Back / Skip(Continue) / Cancel buttons."""

    def __init__(self, modal_label: str, on_open_modal: Callable,
                 on_back: Optional[Callable] = None,
                 on_skip: Optional[Callable] = None,
                 on_cancel: Optional[Callable] = None):
        super().__init__(timeout=None)
        self.add_item(OpenModalButton(modal_label, on_open_modal))
        if on_back:
            self.add_item(BackButton(on_back))
        if on_skip:
            skip_button = ContinueButton(on_skip)
            skip_button.label = "Skip →"
            self.add_item(skip_button)
        if on_cancel:
            self.add_item(CancelButton(on_cancel))


class EditButton(ui.Button):

    """Edit button."""
    
    def __init__(self, callback: Optional[Callable]):
        super().__init__(label='✏️ Edit', style=discord.ButtonStyle.secondary)
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


# ==========================================
# Panel Preview View
# ==========================================

class PanelPreviewView(ui.View):
    """View for panel preview with Confirm and Edit buttons."""
    
    def __init__(self, on_confirm: Callable, on_edit: Callable):
        super().__init__(timeout=None)
        self.on_confirm = on_confirm
        self.on_edit = on_edit
        
        self.add_item(ConfirmButton(self.on_confirm))
        self.add_item(EditButton(self.on_edit))


# ==========================================
# Category Configuration View
# ==========================================

class CategoryConfigView(ui.View):
    """View for configuring individual categories."""
    
    def __init__(self, category_name: str, on_back: Callable, on_confirm: Callable, on_edit: Callable):
        super().__init__(timeout=None)
        self.category_name = category_name
        self.on_back = on_back
        self.on_confirm = on_confirm
        self.on_edit = on_edit
        
        self.add_item(BackButton(self.on_back))
        self.add_item(ConfirmButton(self.on_confirm))
        self.add_item(EditButton(self.on_edit))


# ==========================================
# Ticket Management Buttons
# ==========================================

class TicketManagementView(ui.View):
    """View for ticket management buttons."""
    
    def __init__(self, ticket_channel_id: int, 
                 on_close: Callable,
                 on_claim: Optional[Callable] = None,
                 on_add_user: Optional[Callable] = None,
                 on_remove_user: Optional[Callable] = None,
                 on_transcript: Optional[Callable] = None):
        super().__init__(timeout=None)
        self.ticket_channel_id = ticket_channel_id
        self.on_close = on_close
        self.on_claim = on_claim
        self.on_add_user = on_add_user
        self.on_remove_user = on_remove_user
        self.on_transcript = on_transcript
        
        self.add_item(CloseTicketButton(self.on_close))
        if on_claim:
            self.add_item(ClaimTicketButton(self.on_claim))
        if on_add_user:
            self.add_item(AddUserButton(self.on_add_user))
        if on_remove_user:
            self.add_item(RemoveUserButton(self.on_remove_user))
        if on_transcript:
            self.add_item(TranscriptButton(self.on_transcript))


class CloseTicketButton(ui.Button):
    """Close ticket button."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_ticket')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class ClaimTicketButton(ui.Button):
    """Claim ticket button."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='🎯 Claim Ticket', style=discord.ButtonStyle.primary, custom_id='claim_ticket')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class AddUserButton(ui.Button):
    """Add user to ticket button."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='➕ Add User', style=discord.ButtonStyle.success, custom_id='add_user')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class RemoveUserButton(ui.Button):
    """Remove user from ticket button."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='➖ Remove User', style=discord.ButtonStyle.secondary, custom_id='remove_user')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


class TranscriptButton(ui.Button):
    """Generate transcript button."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='📄 Transcript', style=discord.ButtonStyle.secondary, custom_id='transcript')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction)


# ==========================================
# Ticket Panel Dropdown
# ==========================================

class TicketSelectMenu(ui.Select):
    """Dropdown menu for selecting ticket categories."""
    
    def __init__(self, categories: List[Dict[str, Any]], on_select: Optional[Callable] = None):
        options = [
            discord.SelectOption(
                label=cat['name'],
                description=cat.get('title', ''),
                value=str(cat['id'])
            )
            for cat in categories
        ]
        
        super().__init__(
            placeholder='Select a ticket category...',
            min_values=1,
            max_values=1,
            options=options
        )
        self.on_select = on_select
    
    async def callback(self, interaction: discord.Interaction):
        if self.on_select:
            await self.on_select(interaction, self.values[0])


class TicketPanelView(ui.View):
    """View for the ticket panel with dropdown."""
    
    def __init__(self, categories: List[Dict[str, Any]], on_select: Callable):
        super().__init__(timeout=None)
        self.add_item(TicketSelectMenu(categories, on_select))


def build_ticket_panel_view(
    categories: List[Dict[str, Any]],
    on_select: Callable,
    banner_url: Optional[str] = None,
    texts: Optional[List[Optional[str]]] = None,
    bottom_banner_url: Optional[str] = None
) -> discord.ui.LayoutView:
    """
    Build the ticket panel using Components V2 (LayoutView + Container)
    instead of a classic Embed, matching the style already used for the
    announcement cards in bot.py.
    """
    view = discord.ui.LayoutView(timeout=None)

    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(37, 37, 41)
    )

    if banner_url:
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=banner_url)
            )
        )
        container.add_item(discord.ui.Separator())

    if texts:
        for text in texts:
            if text:
                container.add_item(discord.ui.TextDisplay(text))
                container.add_item(discord.ui.Separator())

    container.add_item(discord.ui.TextDisplay("**Select a ticket category below:**"))

    select_row = discord.ui.ActionRow()
    select_row.add_item(TicketSelectMenu(categories, on_select))
    container.add_item(select_row)

    if bottom_banner_url:
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=bottom_banner_url)
            )
        )

    view.add_item(container)
    return view


# ==========================================
# Channel and Role Select Views
# ==========================================

class ChannelSelectView(ui.View):
    """View for channel selection."""
    
    def __init__(self, channel_type: str, on_select: Callable):
        super().__init__(timeout=None)
        self.channel_type = channel_type
        self.on_select = on_select
        
        if channel_type == 'panel':
            self.add_item(PanelChannelSelect(self.on_select))
        elif channel_type == 'category':
            self.add_item(CategoryChannelSelect(self.on_select))


class PanelChannelSelect(ui.ChannelSelect):
    """Select for panel channel."""
    
    def __init__(self, callback: Callable):
        super().__init__(
            placeholder='Select ticket panel channel',
            channel_types=[discord.ChannelType.text]
        )
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction, self.values[0].id)


class CategoryChannelSelect(ui.ChannelSelect):
    """Select for ticket category."""
    
    def __init__(self, callback: Callable):
        super().__init__(
            placeholder='Select ticket category',
            channel_types=[discord.ChannelType.category]
        )
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction, self.values[0].id)


class RoleSelectView(ui.View):
    """View for role selection (multiple)."""
    
    def __init__(self, on_select: Callable):
        super().__init__(timeout=None)
        self.on_select = on_select
        self.add_item(SupportRoleSelect(self.on_select))


class SupportRoleSelect(ui.RoleSelect):
    """Select for support roles (multiple)."""
    
    def __init__(self, callback: Callable):
        super().__init__(
            placeholder='Select support roles',
            min_values=1,
            max_values=25
        )
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        if self.callback_func:
            await self.callback_func(interaction, [role.id for role in self.values])


# ==========================================
# Add/Remove User Modals
# ==========================================

class AddUserModal(ui.Modal, title='Add User to Ticket'):
    """Modal for adding a user to ticket."""
    
    user_id = ui.TextInput(
        label='User ID',
        placeholder='Enter the user ID to add',
        style=discord.TextStyle.short,
        required=True
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            await self.on_submit_callback(interaction, user_id)
        except ValueError:
            await interaction.response.send_message('Invalid user ID. Please enter a valid number.', ephemeral=True)


class RemoveUserModal(ui.Modal, title='Remove User from Ticket'):
    """Modal for removing a user from ticket."""
    
    user_id = ui.TextInput(
        label='User ID',
        placeholder='Enter the user ID to remove',
        style=discord.TextStyle.short,
        required=True
    )
    
    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            await self.on_submit_callback(interaction, user_id)
        except ValueError:
            await interaction.response.send_message('Invalid user ID. Please enter a valid number.', ephemeral=True)
