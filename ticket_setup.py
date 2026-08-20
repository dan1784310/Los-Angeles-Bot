"""
Ticket Setup Module
Handles the /ticket_setup command and the complete setup wizard.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict, Any
import asyncio

from ticket_database import db
from ticket_views import (
    ChannelSelectView, RoleSelectView, BannerURLModal, TextBlockModal,
    CategoryInputModal, CategoryConfigModal, CategoryMentionModal,
    NavigationButtons, CategoryConfigView, ModalStepView,
    BlacklistRoleSelectView
)


def _empty_session(guild_id: int) -> Dict[str, Any]:
    return {
        'step': 1,
        'guild_id': guild_id,
        'panel_channel_id': None,
        'ticket_category_id': None,
        'support_roles': [],
        'blacklisted_roles': [],
        'banner_url': None,
        'bottom_banner_url': None,
        'text_blocks': {1: None, 2: None, 3: None, 4: None, 5: None},
        'categories': [],
        'category_configs': {},
        'category_mentions': {},  # New: category -> mention message
        'category_roles': {}      # New: category -> list of role IDs
    }


class TicketSetup(commands.Cog):
    """Ticket system setup and configuration."""

    def __init__(self, bot: commands.Bot, has_role_or_higher=None):
        self.bot = bot
        self.has_role_or_higher = has_role_or_higher
        self.setup_sessions: Dict[int, Dict[str, Any]] = {}

        # Apply the role check dynamically if a wrapper was provided
        if self.has_role_or_higher:
            self.setup = self.has_role_or_higher("ticket_setup")(self.setup)

    # ==========================================
    # SETUP COMMAND
    # ==========================================

    @app_commands.command(name="ticket_setup", description="Setup the ticket system")
    async def setup(self, interaction: discord.Interaction):
        """Start the ticket system setup wizard, or offer to edit/redeploy an existing one."""
        await interaction.response.defer(ephemeral=True)

        # Always show the menu with all options
        embed = discord.Embed(
            title="⚙️ Ticket System Configuration",
            description="Choose an action below:",
            color=discord.Color.blue()
        )
        view = discord.ui.View(timeout=None)

        # Full setup button
        setup_button = discord.ui.Button(
            label="Full Setup",
            style=discord.ButtonStyle.success,
            custom_id="full_setup"
        )

        async def on_full_setup(button_interaction: discord.Interaction):
            await button_interaction.response.defer(ephemeral=True)
            self.setup_sessions[button_interaction.user.id] = _empty_session(button_interaction.guild_id)
            await self.step_1_ticket_config(button_interaction)

        setup_button.callback = on_full_setup
        view.add_item(setup_button)

        # Edit configuration button (always available)
        edit_button = discord.ui.Button(
            label="Edit Configuration",
            style=discord.ButtonStyle.primary,
            custom_id="edit_setup"
        )

        async def on_edit(button_interaction: discord.Interaction):
            await button_interaction.response.defer(ephemeral=True)
            await self.show_edit_dropdown(button_interaction)

        edit_button.callback = on_edit
        view.add_item(edit_button)

        # Only show reconfigure/refresh if config exists
        if db.has_guild_settings(interaction.guild_id):
            reconfigure_button = discord.ui.Button(
                label="Reconfigure All",
                style=discord.ButtonStyle.danger,
                custom_id="reconfigure_setup"
            )

            async def on_reconfigure(button_interaction: discord.Interaction):
                await button_interaction.response.defer(ephemeral=True)
                self.setup_sessions[button_interaction.user.id] = _empty_session(button_interaction.guild_id)
                await self.step_1_ticket_config(button_interaction)

            reconfigure_button.callback = on_reconfigure
            view.add_item(reconfigure_button)

            refresh_button = discord.ui.Button(
                label="Refresh Panel",
                style=discord.ButtonStyle.success,
                custom_id="refresh_setup"
            )

            async def on_refresh(button_interaction: discord.Interaction):
                await button_interaction.response.defer(ephemeral=True)
                from ticket_panel import update_panel

                try:
                    success = await update_panel(button_interaction.guild, db)
                except Exception as e:
                    success = False
                    print(f"Error refreshing ticket panel: {e}")

                if success:
                    await button_interaction.followup.send(
                        "✅ Panel refreshed from your saved settings!",
                        ephemeral=True
                    )
                else:
                    await button_interaction.followup.send(
                        "❌ Couldn't refresh the panel. Check channel permissions.",
                        ephemeral=True
                    )

            refresh_button.callback = on_refresh
            view.add_item(refresh_button)

        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="cancel_reconfigure"
        )

        async def on_cancel(button_interaction: discord.Interaction):
            await button_interaction.response.edit_message(
                content="❌ Operation cancelled.",
                embed=None,
                view=None
            )

        cancel_button.callback = on_cancel
        view.add_item(cancel_button)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def show_edit_dropdown(self, interaction: discord.Interaction):
        """Show dropdown for editing specific configuration items."""
        embed = discord.Embed(
            title="✏️ Edit Configuration",
            description="Select which part of the configuration you want to edit:",
            color=discord.Color.blue()
        )
        
        view = discord.ui.View(timeout=None)
        
        # Create dropdown with all editable configuration items
        select = discord.ui.Select(
            placeholder="Select configuration to edit...",
            options=[
                discord.SelectOption(label="Panel Channel", value="panel_channel"),
                discord.SelectOption(label="Ticket Category", value="ticket_category"),
                discord.SelectOption(label="Support Roles", value="support_roles"),
                discord.SelectOption(label="Blacklisted Roles", value="blacklisted_roles"),
                discord.SelectOption(label="Banner URL", value="banner_url"),
                discord.SelectOption(label="Text Blocks", value="text_blocks"),
                discord.SelectOption(label="Ticket Types (Dropdown Buttons)", value="categories"),
                discord.SelectOption(label="Ticket Type Messages", value="category_mentions"),
                discord.SelectOption(label="Ticket Type Roles", value="category_roles")
            ]
        )
        
        async def on_select(select_interaction: discord.Interaction):
            await select_interaction.response.defer(ephemeral=True)
            selected = select_interaction.data['values'][0]
            await self.handle_edit_selection(select_interaction, selected)
        
        select.callback = on_select
        view.add_item(select)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def handle_edit_selection(self, interaction: discord.Interaction, selection: str):
        """Handle the edit selection from dropdown."""
        # Load current settings from database
        settings = db.get_guild_settings(interaction.guild_id)
        
        if not settings:
            await interaction.followup.send(
                "❌ No configuration found. Please run 'Full Setup' first.",
                ephemeral=True
            )
            return
        
        if selection == "panel_channel":
            await interaction.followup.send(
                "Select the new **Ticket Panel Channel**:",
                view=ChannelSelectView('panel', lambda i, c: self.edit_panel_channel(i, c)),
                ephemeral=True
            )
        elif selection == "ticket_category":
            await interaction.followup.send(
                "Select the new **Ticket Category**:",
                view=ChannelSelectView('category', lambda i, c: self.edit_ticket_category(i, c)),
                ephemeral=True
            )
        elif selection == "support_roles":
            await interaction.followup.send(
                "Select the new **Support Roles**:",
                view=RoleSelectView('support', lambda i, r: self.edit_support_roles(i, r)),
                ephemeral=True
            )
        elif selection == "blacklisted_roles":
            await interaction.followup.send(
                "Select the new **Blacklisted Roles**:",
                view=RoleSelectView('blacklist', lambda i, r: self.edit_blacklisted_roles(i, r)),
                ephemeral=True
            )
        elif selection == "banner_url":
            await interaction.followup.send(
                "Enter the new **Banner URL** (or leave empty to remove):",
                view=BannerURLModal(lambda i, u: self.edit_banner_url(i, u)),
                ephemeral=True
            )
        elif selection == "text_blocks":
            await self.edit_text_blocks_menu(interaction)
        elif selection == "categories":
            await self.edit_ticket_types_menu(interaction)
        elif selection == "category_mentions":
            await self.edit_ticket_type_messages_menu(interaction)
        elif selection == "category_roles":
            await self.edit_ticket_type_roles_menu(interaction)

    async def edit_banner_url(self, interaction: discord.Interaction, banner_url: Optional[str]):
        """Edit banner URL."""
        db.update_setting(interaction.guild_id, 'banner_url', banner_url)
        await interaction.followup.send("✅ Banner URL updated!", ephemeral=True)

    async def edit_panel_channel(self, interaction: discord.Interaction, channel_id: int):
        """Edit panel channel."""
        db.update_setting(interaction.guild_id, 'panel_channel_id', channel_id)
        await interaction.followup.send("✅ Panel channel updated!", ephemeral=True)

    async def edit_ticket_category(self, interaction: discord.Interaction, category_id: int):
        """Edit ticket category."""
        db.update_setting(interaction.guild_id, 'ticket_category_id', category_id)
        await interaction.followup.send("✅ Ticket category updated!", ephemeral=True)

    async def edit_support_roles(self, interaction: discord.Interaction, role_ids: List[int]):
        """Edit support roles."""
        db.update_setting(interaction.guild_id, 'support_roles', role_ids)
        await interaction.followup.send("✅ Support roles updated!", ephemeral=True)

    async def edit_blacklisted_roles(self, interaction: discord.Interaction, role_ids: List[int]):
        """Edit blacklisted roles."""
        db.update_setting(interaction.guild_id, 'blacklisted_roles', role_ids)
        await interaction.followup.send("✅ Blacklisted roles updated!", ephemeral=True)

    async def edit_text_blocks_menu(self, interaction: discord.Interaction):
        """Show menu for editing text blocks."""
        view = discord.ui.View(timeout=None)
        
        for i in range(1, 6):
            button = discord.ui.Button(
                label=f"Text Block {i}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"edit_text_block_{i}"
            )
            
            async def on_edit_button(button_interaction: discord.Interaction, block_num=i):
                await button_interaction.response.defer(ephemeral=True)
                await button_interaction.followup.send(
                    f"Edit **Text Block {block_num}**:",
                    view=TextBlockModal(block_num, lambda i, t: self.edit_text_block(i, block_num, t)),
                    ephemeral=True
                )
            
            button.callback = lambda i, b=button, bn=i: on_edit_button(i, bn)
            view.add_item(button)
        
        await interaction.followup.send("Select which text block to edit:", view=view, ephemeral=True)

    async def edit_text_block(self, interaction: discord.Interaction, block_number: int, text: Optional[str]):
        """Edit a specific text block."""
        settings = db.get_guild_settings(interaction.guild_id)
        text_blocks = settings.get('text_blocks', {})
        text_blocks[str(block_number)] = text
        db.update_setting(interaction.guild_id, 'text_blocks', text_blocks)
        await interaction.followup.send(f"✅ Text Block {block_number} updated!", ephemeral=True)

    async def edit_categories_menu(self, interaction: discord.Interaction):
        """Show menu for editing categories."""
        settings = db.get_guild_settings(interaction.guild_id)
        categories = settings.get('categories', [])
        
        if not categories:
            await interaction.followup.send("❌ No categories configured.", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=None)
        
        for category in categories:
            button = discord.ui.Button(
                label=category,
                style=discord.ButtonStyle.secondary,
                custom_id=f"edit_category_{category}"
            )
            
            async def on_edit_category(button_interaction: discord.Interaction, cat_name=category):
                await button_interaction.response.defer(ephemeral=True)
                config = settings.get('category_configs', {}).get(cat_name, {})
                await button_interaction.followup.send(
                    f"Edit **{cat_name}** configuration:",
                    view=CategoryConfigModal(cat_name, config.get('title', ''), config.get('description', ''), 
                                            lambda i, t, d: self.edit_category_config(i, cat_name, t, d)),
                    ephemeral=True
                )
            
            button.callback = lambda i, b=button, cn=category: on_edit_category(i, cn)
            view.add_item(button)
        
        await interaction.followup.send("Select which category to edit:", view=view, ephemeral=True)

    async def edit_category_config(self, interaction: discord.Interaction, category_name: str, title: str, description: str):
        """Edit category configuration."""
        settings = db.get_guild_settings(interaction.guild_id)
        category_configs = settings.get('category_configs', {})
        category_configs[category_name] = {'title': title, 'description': description}
        db.update_setting(interaction.guild_id, 'category_configs', category_configs)
        await interaction.followup.send(f"✅ {category_name} configuration updated!", ephemeral=True)

    async def edit_category_mentions_menu(self, interaction: discord.Interaction):
        """Show menu for editing category mentions."""
        settings = db.get_guild_settings(interaction.guild_id)
        categories = settings.get('categories', [])
        
        if not categories:
            await interaction.followup.send("❌ No categories configured.", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=None)
        
        for category in categories:
            button = discord.ui.Button(
                label=f"Mention: {category}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"edit_mention_{category}"
            )
            
            async def on_edit_mention(button_interaction: discord.Interaction, cat_name=category):
                current_mention = settings.get('category_mentions', {}).get(cat_name, '')
                await button_interaction.response.send_modal(
                    CategoryMentionModal(cat_name, current_mention, lambda i, m: self.edit_category_mention(i, cat_name, m))
                )
            
            button.callback = lambda i, b=button, cn=category: on_edit_mention(i, cn)
            view.add_item(button)
        
        await interaction.followup.send("Select which category mention to edit:", view=view, ephemeral=True)

    async def edit_category_mention(self, interaction: discord.Interaction, category_name: str, mention: str):
        """Edit category mention message."""
        settings = db.get_guild_settings(interaction.guild_id)
        category_mentions = settings.get('category_mentions', {})
        category_mentions[category_name] = mention
        db.update_setting(interaction.guild_id, 'category_mentions', category_mentions)
        await interaction.followup.send(f"✅ {category_name} mention updated!", ephemeral=True)

    async def edit_category_roles_menu(self, interaction: discord.Interaction):
        """Show menu for editing category roles."""
        settings = db.get_guild_settings(interaction.guild_id)
        categories = settings.get('categories', [])
        
        if not categories:
            await interaction.followup.send("❌ No categories configured.", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=None)
        
        for category in categories:
            button = discord.ui.Button(
                label=f"Roles: {category}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"edit_roles_{category}"
            )
            
            async def on_edit_roles(button_interaction: discord.Interaction, cat_name=category):
                current_roles = settings.get('category_roles', {}).get(cat_name, [])
                await button_interaction.response.defer(ephemeral=True)
                await button_interaction.followup.send(
                    f"Select roles for **{cat_name}** (multiple allowed):",
                    view=RoleSelectView('category', lambda i, r: self.edit_category_roles(i, cat_name, r)),
                    ephemeral=True
                )
            
            button.callback = lambda i, b=button, cn=category: on_edit_roles(i, cn)
            view.add_item(button)
        
        await interaction.followup.send("Select which category roles to edit:", view=view, ephemeral=True)

    async def edit_category_roles(self, interaction: discord.Interaction, category_name: str, role_ids: List[int]):
        """Edit category roles."""
        settings = db.get_guild_settings(interaction.guild_id)
        category_roles = settings.get('category_roles', {})
        category_roles[category_name] = role_ids
        db.update_setting(interaction.guild_id, 'category_roles', category_roles)
        await interaction.followup.send(f"✅ {category_name} roles updated!", ephemeral=True)

    # ==========================================
    # STEP 1: Ticket Configuration
    # ==========================================

    async def step_1_ticket_config(self, interaction: discord.Interaction):
        """STEP 1 - Configure panel channel, ticket category, and support roles."""

        embed = discord.Embed(
            title="📋 Step 1: Ticket Configuration",
            description="Configure the basic settings for your ticket system.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Panel Channel", value="Select where the ticket panel will be sent", inline=False)
        embed.add_field(name="Ticket Category", value="Select the category where ticket channels will be created", inline=False)
        embed.add_field(name="Support Roles", value="Select roles that can access tickets", inline=False)
        embed.add_field(name="Blacklisted Roles", value="Select roles that are blocked from opening tickets (optional)", inline=False)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.edit_message(content=None, embed=embed, view=None)

        await interaction.followup.send(
            "Select the **Ticket Panel Channel**:",
            view=ChannelSelectView('panel', lambda i, c: self.on_panel_channel_select(i, c)),
            ephemeral=True
        )

    async def on_panel_channel_select(self, interaction: discord.Interaction, channel_id: int):
        """Handle panel channel selection."""
        session = self.setup_sessions[interaction.user.id]
        session['panel_channel_id'] = channel_id

        await interaction.response.send_message(
            "Select the **Ticket Category**:",
            view=ChannelSelectView('category', lambda i, c: self.on_ticket_category_select(i, c)),
            ephemeral=True
        )

    async def on_ticket_category_select(self, interaction: discord.Interaction, category_id: int):
        """Handle ticket category (Discord channel category) selection."""
        session = self.setup_sessions[interaction.user.id]
        session['ticket_category_id'] = category_id

        await interaction.response.send_message(
            "Select the **Support Roles** (you can select multiple):",
            view=RoleSelectView(lambda i, r: self.on_support_roles_select(i, r)),
            ephemeral=True
        )

    async def on_support_roles_select(self, interaction: discord.Interaction, role_ids: List[int]):
        """Handle support roles selection."""
        session = self.setup_sessions[interaction.user.id]
        session['support_roles'] = role_ids

        await interaction.response.send_message(
            "Select roles to **blacklist** from opening tickets (optional — click "
            "**No Blacklist** to skip):",
            view=BlacklistRoleSelectView(lambda i, r: self.on_blacklisted_roles_select(i, r)),
            ephemeral=True
        )

    async def on_blacklisted_roles_select(self, interaction: discord.Interaction, role_ids: List[int]):
        """Handle blacklisted roles selection."""
        session = self.setup_sessions[interaction.user.id]
        session['blacklisted_roles'] = role_ids

        await interaction.response.send_message(
            "✅ Configuration saved! Click **Continue** to proceed to the next step.",
            view=NavigationButtons(
                show_back=False,
                on_continue=lambda i: self.step_2_panel_designer(i),
                on_cancel=lambda i: self.cancel_setup(i)
            ),
            ephemeral=True
        )

    # ==========================================
    # STEP 2: Panel Designer
    # ==========================================

    async def step_2_panel_designer(self, interaction: discord.Interaction):
        """STEP 2 - Configure the panel banner and text blocks."""

        embed = discord.Embed(
            title="🎨 Step 2: Panel Designer",
            description="Optionally add a banner image and up to 5 text blocks to the ticket panel.",
            color=discord.Color.purple()
        )

        if not interaction.response.is_done():
            await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

        await interaction.followup.send(
            "Add a **banner image** for the top of the panel (optional):",
            view=ModalStepView(
                modal_label="🖼️ Set Banner",
                on_open_modal=lambda i: self.open_banner_modal(i),
                on_skip=lambda i: self.on_banner_submit(i, None),
                on_cancel=lambda i: self.cancel_setup(i)
            ),
            ephemeral=True
        )

    async def open_banner_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            BannerURLModal(lambda i, url: self.on_banner_submit(i, url))
        )

    async def on_banner_submit(self, interaction: discord.Interaction, banner_url: Optional[str]):
        """Handle banner URL submission with validation."""
        session = self.setup_sessions[interaction.user.id]
        cleaned_url = banner_url.strip() if banner_url else ""
        session['banner_url'] = cleaned_url if cleaned_url.startswith(("http://", "https://")) else None

        await self.text_block_step(interaction, 1)

    async def text_block_step(self, interaction: discord.Interaction, block_number: int):
        """Prompt for a single text block (1-5), then move to the next one."""

        message = f"Add **Text Block {block_number}/5** (optional, Markdown supported):"

        view = ModalStepView(
            modal_label=f"📝 Set Text {block_number}",
            on_open_modal=lambda i: self.open_text_block_modal(i, block_number),
            on_skip=lambda i: self.on_text_block_submit(i, block_number, None),
            on_cancel=lambda i: self.cancel_setup(i)
        )

        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    async def open_text_block_modal(self, interaction: discord.Interaction, block_number: int):
        await interaction.response.send_modal(
            TextBlockModal(block_number, lambda i, num, text: self.on_text_block_submit(i, num, text))
        )

    async def on_text_block_submit(self, interaction: discord.Interaction, block_number: int, text: Optional[str]):
        """Handle a text block submission (or skip), then advance."""
        session = self.setup_sessions[interaction.user.id]
        cleaned = text.strip() if text else None
        session['text_blocks'][block_number] = cleaned if cleaned else None

        if block_number < 5:
            await self.text_block_step(interaction, block_number + 1)
        else:
            await interaction.response.send_message(
                "✅ Panel design saved! Click **Continue** to configure ticket categories.",
                view=NavigationButtons(
                    show_back=False,
                    on_continue=lambda i: self.step_3_configure_categories(i),
                    on_cancel=lambda i: self.cancel_setup(i)
                ),
                ephemeral=True
            )

    # ==========================================
    # STEP 3: Ticket Categories
    # ==========================================

    async def step_3_configure_categories(self, interaction: discord.Interaction):
        """STEP 3 - Add one or more ticket categories."""

        embed = discord.Embed(
            title="🗂️ Step 3: Ticket Categories",
            description="Add the categories users will choose from when opening a ticket. You need at least one.",
            color=discord.Color.orange()
        )

        if not interaction.response.is_done():
            await interaction.response.edit_message(content=None, embed=embed, view=None)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

        await self._prompt_add_category(interaction)

    async def _prompt_add_category(self, interaction: discord.Interaction):
        session = self.setup_sessions[interaction.user.id]
        count = len(session['categories'])

        message = f"You have **{count}** categor{'y' if count == 1 else 'ies'} added so far."
        view = discord.ui.View(timeout=None)

        add_button = discord.ui.Button(label="➕ Add Category", style=discord.ButtonStyle.primary)

        async def on_add(button_interaction: discord.Interaction):
            await button_interaction.response.send_modal(
                CategoryInputModal(lambda i, name: self.on_category_name_submit(i, name))
            )

        add_button.callback = on_add
        view.add_item(add_button)

        if count > 0:
            done_button = discord.ui.Button(label="✅ Done Adding", style=discord.ButtonStyle.success)

            async def on_done(button_interaction: discord.Interaction):
                await button_interaction.response.defer(ephemeral=True)
                first_category = session['categories'][0]
                await self.configure_category(button_interaction, first_category)

            done_button.callback = on_done
            view.add_item(done_button)

        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)

        async def on_cancel(button_interaction: discord.Interaction):
            await self.cancel_setup(button_interaction)

        cancel_button.callback = on_cancel
        view.add_item(cancel_button)

        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    async def on_category_name_submit(self, interaction: discord.Interaction, category_name: str):
        """Handle a new category name being submitted."""
        session = self.setup_sessions[interaction.user.id]
        name = category_name.strip()

        if not name:
            await interaction.response.send_message("❌ Category name can't be empty.", ephemeral=True)
            return

        if name in session['categories']:
            await interaction.response.send_message("❌ That category already exists.", ephemeral=True)
            return

        session['categories'].append(name)
        await interaction.response.defer(ephemeral=True)
        await self._prompt_add_category(interaction)

    async def configure_category(self, interaction: discord.Interaction, category_name: str):
        """Prompt for the title/description of a specific category."""

        message = f"Configure the embed shown when a ticket is opened for **{category_name}**:"
        view = discord.ui.View(timeout=None)

        configure_button = discord.ui.Button(label="✏️ Configure", style=discord.ButtonStyle.primary)

        async def on_configure(button_interaction: discord.Interaction):
            await button_interaction.response.send_modal(
                CategoryConfigModal(
                    category_name,
                    lambda i, name, title, description: self.on_category_config_submit(i, name, title, description)
                )
            )

        configure_button.callback = on_configure
        view.add_item(configure_button)

        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    async def on_category_config_submit(self, interaction: discord.Interaction, category_name: str,
                                        title: str, description: str):
        """Handle a category's title/description submission."""
        await interaction.response.defer(ephemeral=True)

        session = self.setup_sessions[interaction.user.id]
        session['category_configs'][category_name] = {
            'title': title,
            'description': description
        }

        current_index = session['categories'].index(category_name)
        if current_index < len(session['categories']) - 1:
            next_category = session['categories'][current_index + 1]
            await interaction.followup.send(
                f"✅ Saved **{category_name}**. Configuring next...",
                ephemeral=True
            )
            await asyncio.sleep(0.8)
            await self.configure_category(interaction, next_category)
        else:
            await self.show_categories_preview(interaction)

    async def show_categories_preview(self, interaction: discord.Interaction):
        """Show preview of all configured categories."""
        session = self.setup_sessions[interaction.user.id]

        embed = discord.Embed(
            title="👁️ Categories Preview",
            description="Review your category configurations:",
            color=discord.Color.gold()
        )

        for category_name in session['categories']:
            config = session['category_configs'].get(category_name, {})
            description_preview = (config.get('description') or 'N/A')[:100]
            embed.add_field(
                name=f"📌 {category_name}",
                value=f"**Title:** {config.get('title', 'N/A')}\n**Description:** {description_preview}...",
                inline=False
            )

        view = CategoryConfigView(
            category_name=session['categories'][0],
            on_back=lambda i: self.step_3_configure_categories(i),
            on_confirm=lambda i: self.step_4_finish_setup(i),
            on_edit=lambda i: self.edit_category(i, session['categories'][0])
        )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error showing preview: {e}", ephemeral=True)

    async def edit_category(self, interaction: discord.Interaction, category_name: str):
        """Edit a specific category configuration."""
        await interaction.response.defer(ephemeral=True)
        await self.configure_category(interaction, category_name)

    # ==========================================
    # STEP 4: Finish Setup
    # ==========================================

    async def step_4_finish_setup(self, interaction: discord.Interaction):
        """STEP 4 - Save all settings and deploy the panel."""

        session = self.setup_sessions[interaction.user.id]

        settings = {
            'panel_channel_id': session['panel_channel_id'],
            'ticket_category_id': session['ticket_category_id'],
            'support_roles': session['support_roles'],
            'blacklisted_roles': session.get('blacklisted_roles', []),
            'banner_url': session['banner_url'],
            'bottom_banner_url': session.get('bottom_banner_url'),
            'text1': session['text_blocks'][1],
            'text2': session['text_blocks'][2],
            'text3': session['text_blocks'][3],
            'text4': session['text_blocks'][4],
            'text5': session['text_blocks'][5],
            'ticket_counter': 0
        }

        if db.save_guild_settings(session['guild_id'], settings):
            db.clear_ticket_categories(session['guild_id'])

            for category_name in session['categories']:
                config = session['category_configs'].get(category_name, {})
                db.save_ticket_category(
                    session['guild_id'],
                    category_name,
                    config.get('title', category_name),
                    config.get('description', '')
                )

            await self.deploy_panel(interaction)

            if interaction.user.id in self.setup_sessions:
                del self.setup_sessions[interaction.user.id]

            await interaction.response.edit_message(
                content="✅ **Setup Complete!** Your ticket system is now ready to use.",
                embed=None,
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Failed to save settings. Please try again.",
                embed=None,
                view=None
            )

    async def deploy_panel(self, interaction: discord.Interaction):
        """Deploy the ticket panel to the configured channel."""
        session = self.setup_sessions.get(interaction.user.id)
        if not session:
            return

        from ticket_creation import on_category_select
        from ticket_views import build_ticket_panel_view

        panel_channel = interaction.guild.get_channel(session['panel_channel_id'])
        if not panel_channel:
            await interaction.followup.send("❌ Panel channel not found.", ephemeral=True)
            return

        categories = db.get_ticket_categories(session['guild_id'])
        if not categories:
            await interaction.followup.send("❌ No categories found.", ephemeral=True)
            return

        view = build_ticket_panel_view(
            categories,
            lambda i, cid: on_category_select(i, cid, session['guild_id'], db),
            banner_url=session.get('banner_url'),
            texts=[session['text_blocks'].get(i) for i in range(1, 6)],
            bottom_banner_url=session.get('bottom_banner_url')
        )

        existing_message_id = db.get_panel_message(session['guild_id'])
        if existing_message_id:
            try:
                existing_message = await panel_channel.fetch_message(existing_message_id)
                await existing_message.delete()
            except Exception:
                pass

        message = await panel_channel.send(view=view)
        db.save_panel_message(session['guild_id'], message.id)

        await interaction.followup.send("✅ Panel deployed successfully!", ephemeral=True)

    # ==========================================
    # Cancel Setup
    # ==========================================

    async def cancel_setup(self, interaction: discord.Interaction):
        """Cancel the setup process."""

        if interaction.user.id in self.setup_sessions:
            del self.setup_sessions[interaction.user.id]

        if interaction.response.is_done():
            await interaction.edit_original_response(
                content="❌ Setup cancelled.",
                embed=None,
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Setup cancelled.",
                embed=None,
                view=None
            )


async def setup(bot: commands.Bot, has_role_or_higher=None):
    """Setup the ticket setup cog."""
    if has_role_or_higher is None:
        has_role_or_higher = getattr(bot, 'has_role_or_higher', None)

    await bot.add_cog(TicketSetup(bot, has_role_or_higher))
