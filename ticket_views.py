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
    
    def __init__(self, on_submit: Callable = None):
        super().__init__()
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.on_submit_callback:
            await self.on_submit_callback(interaction, self.banner_url.value)
        else:
            # Fallback for backward compatibility
            await interaction.response.send("Banner URL received (not saved - missing callback)", ephemeral=True)


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
    """Category Config Modal - accepts category_name"""
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
    
    def __init__(self, category_name: str, current_title: str, current_description: str, on_submit: Callable):
        super().__init__(title=f"Configure: {category_name}")
        self.category_name = category_name
        self.title_input.value = current_title
        self.description_input.value = current_description
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(
            interaction, 
            self.category_name, 
            self.title_input.value, 
            self.description_input.value
        )


class CategoryMentionModal(ui.Modal):
    """Modal for editing category mention message"""
    mention_input = ui.TextInput(
        label='Mention Message',
        placeholder='e.g., Staff has been notified of your ticket',
        style=discord.TextStyle.paragraph,
        required=False
    )
    
    def __init__(self, category_name: str, current_mention: str, on_submit: Callable):
        super().__init__(title=f"Mention: {category_name}")
        self.category_name = category_name
        self.mention_input.value = current_mention
        self.on_submit_callback = on_submit
    
    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.category_name, self.mention_input.value)


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

def build_ticket_management_view(
    config_title: Optional[str],
    config_description: Optional[str],
    issue_text: Optional[str],
    ticket_number: int,
    creator_mention: str,
    category_name: str,
    on_close: Callable,
    on_claim: Optional[Callable] = None,
    on_unclaim: Optional[Callable] = None,
    claimed: bool = False,
    claimant_mention: Optional[str] = None,
    on_add_user: Optional[Callable] = None,
    on_remove_user: Optional[Callable] = None,
    on_transcript: Optional[Callable] = None,
    accent_colour: Optional[discord.Colour] = None,
    mention_line: Optional[str] = None
) -> discord.ui.LayoutView:
    """
    Build the ticket management message using Components V2. Mentions
    sit at the very top (above the title), then three sections
    (configured text / inquiry / ticket info) each separated by a
    Separator, with the management buttons in a row underneath the
    last separator.

    This is the one and only public message — when a ticket is claimed
    or unclaimed, the bot edits this same message in place (via
    interaction.response.edit_message) with claimed=True/False, which
    swaps the button between Claim and Unclaim. That swap is visible
    to everyone looking at the channel, since it's a genuine edit of
    the shared message.
    """

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=accent_colour)

    # Section 1: mentions (if any), then the configured category text
    top_lines = []
    if mention_line:
        top_lines.append(mention_line)
    if config_title:
        top_lines.append(f"## {config_title}")
    if config_description:
        top_lines.append(config_description)
    container.add_item(discord.ui.TextDisplay("\n".join(top_lines)))

    # Section 2: the user's inquiry
    if issue_text:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Inquiry:**\n**{issue_text}**"))

    # Section 3: ticket info
    container.add_item(discord.ui.Separator())
    info_lines = [
        f"**Ticket Number:** #{ticket_number:04d}",
        f"**Created By:** {creator_mention}",
        f"**Category:** {category_name}"
    ]
    if claimed and claimant_mention:
        info_lines.append(f"**Claimed By:** {claimant_mention}")
    container.add_item(discord.ui.TextDisplay("\n".join(info_lines)))

    # Buttons — Claim swaps for Unclaim once claimed
    container.add_item(discord.ui.Separator())
    button_row = discord.ui.ActionRow()
    button_row.add_item(CloseTicketButton(on_close))
    if claimed and on_unclaim:
        button_row.add_item(UnclaimButton(on_unclaim))
    elif on_claim:
        button_row.add_item(ClaimTicketButton(on_claim))
    if on_add_user:
        button_row.add_item(AddUserButton(on_add_user))
    if on_remove_user:
        button_row.add_item(RemoveUserButton(on_remove_user))
    if on_transcript:
        button_row.add_item(TranscriptButton(on_transcript))
    container.add_item(button_row)

    view.add_item(container)
    return view


class CloseTicketButton(ui.Button):
    """
    Close ticket button.

    NOTE: this button's own callback is intentionally a no-op. The
    ticket-management buttons aren't registered as Discord persistent
    views, so the cog's on_interaction listener (ticket_creation.py)
    is what actually handles these clicks — that way they keep working
    even after a bot restart. Having this callback also call the
    handler would fire it twice per click (a real bug we hit: clicking
    Unclaim would run the handler twice, and the second run would see
    state the first run had already changed, throwing a false "already
    claimed" error).
    """
    
    def __init__(self, callback: Callable):
        super().__init__(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_ticket')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        pass  # handled by TicketCreation.on_interaction — see note above


class ClaimTicketButton(ui.Button):
    """Claim ticket button. See CloseTicketButton for why callback() is a no-op."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='🎯 Claim Ticket', style=discord.ButtonStyle.primary, custom_id='claim_ticket')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        pass  # handled by TicketCreation.on_interaction


class AddUserButton(ui.Button):
    """Add user to ticket button. See CloseTicketButton for why callback() is a no-op."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='➕ Add User', style=discord.ButtonStyle.success, custom_id='add_user')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        pass  # handled by TicketCreation.on_interaction


class RemoveUserButton(ui.Button):
    """Remove user from ticket button. See CloseTicketButton for why callback() is a no-op."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='➖ Remove User', style=discord.ButtonStyle.secondary, custom_id='remove_user')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        pass  # handled by TicketCreation.on_interaction


class TranscriptButton(ui.Button):
    """Generate transcript button. See CloseTicketButton for why callback() is a no-op."""
    
    def __init__(self, callback: Callable):
        super().__init__(label='📄 Transcript', style=discord.ButtonStyle.secondary, custom_id='transcript')
        self.callback_func = callback
    
    async def callback(self, interaction: discord.Interaction):
        pass  # handled by TicketCreation.on_interaction


class UnclaimButton(ui.Button):
    """Unclaim button, shown once a ticket is claimed. See CloseTicketButton for why callback() is a no-op."""

    def __init__(self, callback: Callable):
        super().__init__(label='Unclaim Ticket', style=discord.ButtonStyle.danger, custom_id='unclaim_ticket')
        self.callback_func = callback

    async def callback(self, interaction: discord.Interaction):
        pass  # handled by TicketCreation.on_interaction






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


def _is_valid_image_url(url: Optional[str]) -> bool:
    """Helper to ensure URL is non-empty and starts with http/https."""
    return bool(url and isinstance(url, str) and url.strip().startswith(("http://", "https://")))


def build_ticket_panel_view(
    categories: List[Dict[str, Any]],
    on_select: Callable,
    banner_url: Optional[str] = None,
    texts: Optional[List[Optional[str]]] = None,
    bottom_banner_url: Optional[str] = None
) -> discord.ui.LayoutView:
    """
    Build the ticket panel using Components V2 (LayoutView + Container)
    with safe URL verification to prevent broken media components.
    """
    view = discord.ui.LayoutView(timeout=None)

    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(37, 37, 41)
    )

    # Validate top banner URL before adding to container
    if _is_valid_image_url(banner_url):
        try:
            container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=banner_url.strip())
                )
            )
            container.add_item(discord.ui.Separator())
        except Exception as e:
            print(f"[Panel Error] Failed to render top banner: {e}")

    if texts:
        for text in texts:
            if text:
                container.add_item(discord.ui.TextDisplay(text))
                container.add_item(discord.ui.Separator())

    container.add_item(discord.ui.TextDisplay("**Select a ticket category below:**"))

    select_row = discord.ui.ActionRow()
    select_row.add_item(TicketSelectMenu(categories, on_select))
    container.add_item(select_row)

    # Validate bottom banner URL before adding to container
    if _is_valid_image_url(bottom_banner_url):
        try:
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=bottom_banner_url.strip())
                )
            )
        except Exception as e:
            print(f"[Panel Error] Failed to render bottom banner: {e}")

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


class BlacklistRoleSelectView(ui.View):
    """View for blacklisted role selection (multiple, optional)."""

    def __init__(self, on_select: Callable):
        super().__init__(timeout=None)
        self.on_select = on_select
        self.add_item(BlacklistRoleSelect(self.on_select))

        skip_button = ui.Button(
            label="No Blacklist",
            style=discord.ButtonStyle.secondary,
            custom_id="blacklist_skip"
        )

        async def on_skip(interaction: discord.Interaction):
            await self.on_select(interaction, [])

        skip_button.callback = on_skip
        self.add_item(skip_button)


class BlacklistRoleSelect(ui.RoleSelect):
    """Select for blacklisted roles. Selecting none means no blacklist."""

    def __init__(self, callback: Callable):
        super().__init__(
            placeholder='Select roles to blacklist (optional — leave empty for none)',
            min_values=0,
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


# ==========================================
# Ticket Issue Modal
# ==========================================

class TicketIssueModal(ui.Modal, title='What seems to be the issue?'):
    """Modal shown right after a user picks a category, asking them to describe their issue."""

    issue = ui.TextInput(
        label='Describe your issue',
        placeholder='Write what you need help with...',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    def __init__(self, on_submit: Callable):
        super().__init__()
        self.on_submit_callback = on_submit

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_callback(interaction, self.issue.value)
