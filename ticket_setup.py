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
    CategoryInputModal, CategoryConfigModal,
    NavigationButtons, CategoryConfigView, ModalStepView,
    BlacklistRoleSelectView, CategoryPingRoleSelectView
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
        'category_configs': {}
    }


class TicketSetup(commands.Cog):
    """Ticket system setup and configuration."""

    def __init__(self, bot: commands.Bot, has_role_or_higher=None):
        self.bot = bot
        self.has_role_or_higher = has_role_or_higher
        self.setup_sessions: Dict[int, Dict[str, Any]] = {}
        self.quick_edit_sessions: Dict[int, Dict[str, Any]] = {}

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

        if db.has_guild_settings(interaction.guild_id):
            embed = discord.Embed(
                title="⚙️ Ticket System Configuration",
                description="Your server already has a ticket system configured. Choose an action below:",
                color=discord.Color.blue()
            )
            view = discord.ui.View(timeout=None)

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

            addedit_button = discord.ui.Button(
                label="Add/Edit",
                style=discord.ButtonStyle.primary,
                custom_id="addedit_setup"
            )

            async def on_addedit(button_interaction: discord.Interaction):
                await self.show_quick_edit_menu(button_interaction)

            addedit_button.callback = on_addedit
            view.add_item(addedit_button)

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
            return

        # Start a fresh setup if no configuration exists
        self.setup_sessions[interaction.user.id] = _empty_session(interaction.guild_id)
        await self.step_1_ticket_config(interaction)

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
        session = self.setup_sessions[interaction.user.id]
        session['category_configs'][category_name] = {
            'title': title,
            'description': description,
            'ping_role_ids': []
        }

        await self.prompt_category_ping_roles(interaction, category_name)

    async def prompt_category_ping_roles(self, interaction: discord.Interaction, category_name: str):
        """Ask which role(s), if any, should be pinged when this category's tickets are opened."""

        message = (
            f"Select role(s) to **ping** when a **{category_name}** ticket is opened "
            f"(optional — click **Skip** for none):"
        )
        view = CategoryPingRoleSelectView(
            lambda i, role_ids: self.on_category_ping_roles_submit(i, category_name, role_ids)
        )

        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    async def on_category_ping_roles_submit(self, interaction: discord.Interaction, category_name: str,
                                            role_ids: List[int]):
        """Handle a category's ping role selection (or skip), then ask about visibility."""
        session = self.setup_sessions[interaction.user.id]
        session['category_configs'][category_name]['ping_role_ids'] = role_ids

        await self.prompt_category_visible_roles(interaction, category_name)

    async def prompt_category_visible_roles(self, interaction: discord.Interaction, category_name: str):
        """Ask which role(s), if any, can SEE this category's tickets."""

        message = (
            f"Select role(s) that can **see** **{category_name}** tickets "
            f"(optional — click **Skip** to just use the global Support Roles):"
        )
        view = CategoryPingRoleSelectView(
            lambda i, role_ids: self.on_category_visible_roles_submit(i, category_name, role_ids)
        )

        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    async def on_category_visible_roles_submit(self, interaction: discord.Interaction, category_name: str,
                                                role_ids: List[int]):
        """Handle a category's visibility role selection (or skip), then advance."""
        await interaction.response.defer(ephemeral=True)

        session = self.setup_sessions[interaction.user.id]
        session['category_configs'][category_name]['visible_role_ids'] = role_ids

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
            ping_role_ids = config.get('ping_role_ids', [])
            ping_text = ", ".join(f"<@&{rid}>" for rid in ping_role_ids) if ping_role_ids else "None"
            visible_role_ids = config.get('visible_role_ids', [])
            visible_text = ", ".join(f"<@&{rid}>" for rid in visible_role_ids) if visible_role_ids else "Global Support Roles"
            embed.add_field(
                name=f"📌 {category_name}",
                value=(
                    f"**Title:** {config.get('title', 'N/A')}\n"
                    f"**Description:** {description_preview}...\n"
                    f"**Ping Roles:** {ping_text}\n"
                    f"**Visible To:** {visible_text}"
                ),
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
    # Add/Edit (quick edit without restarting setup)
    # ==========================================

    QUICK_EDIT_FIELDS = [
        ("panel_channel", "Panel Channel"),
        ("ticket_category", "Ticket Category (Discord Category)"),
        ("support_roles", "Support Roles (global)"),
        ("blacklisted_roles", "Blacklisted Roles"),
        ("banner", "Banner Image"),
        ("text1", "Text Block 1"),
        ("text2", "Text Block 2"),
        ("text3", "Text Block 3"),
        ("text4", "Text Block 4"),
        ("text5", "Text Block 5"),
        ("categories", "Ticket Categories (add/edit)"),
    ]

    async def show_quick_edit_menu(self, interaction: discord.Interaction):
        """Show a dropdown with all settings to add/edit individually."""
        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            placeholder="Choose what to add/edit...",
            options=[
                discord.SelectOption(label=label, value=key)
                for key, label in self.QUICK_EDIT_FIELDS
            ]
        )

        async def on_select(select_interaction: discord.Interaction):
            await self.on_quick_edit_select(select_interaction, select.values[0])

        select.callback = on_select
        view.add_item(select)

        if interaction.response.is_done():
            await interaction.followup.send("What would you like to add or edit?", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("What would you like to add or edit?", view=view, ephemeral=True)

    async def on_quick_edit_select(self, interaction: discord.Interaction, field_key: str):
        """Route the dropdown choice to the right selector/modal."""

        if field_key == "panel_channel":
            await interaction.response.send_message(
                "Select the new **Ticket Panel Channel**:",
                view=ChannelSelectView(
                    'panel',
                    lambda i, c: self.quick_save_setting(i, 'panel_channel_id', c, "Panel channel")
                ),
                ephemeral=True
            )
        elif field_key == "ticket_category":
            await interaction.response.send_message(
                "Select the new **Ticket Category**:",
                view=ChannelSelectView(
                    'category',
                    lambda i, c: self.quick_save_setting(i, 'ticket_category_id', c, "Ticket category")
                ),
                ephemeral=True
            )
        elif field_key == "support_roles":
            await interaction.response.send_message(
                "Select the new **Support Roles**:",
                view=RoleSelectView(
                    lambda i, r: self.quick_save_setting(i, 'support_roles', r, "Support roles")
                ),
                ephemeral=True
            )
        elif field_key == "blacklisted_roles":
            await interaction.response.send_message(
                "Select the new **Blacklisted Roles** (or click **No Blacklist** for none):",
                view=BlacklistRoleSelectView(
                    lambda i, r: self.quick_save_setting(i, 'blacklisted_roles', r, "Blacklisted roles")
                ),
                ephemeral=True
            )
        elif field_key == "banner":
            await interaction.response.send_modal(
                BannerURLModal(lambda i, url: self.quick_save_banner(i, url))
            )
        elif field_key.startswith("text") and field_key[-1].isdigit():
            block_number = int(field_key[-1])
            await interaction.response.send_modal(
                TextBlockModal(
                    block_number,
                    lambda i, num, text: self.quick_save_text_block(i, num, text)
                )
            )
        elif field_key == "categories":
            await self.show_quick_edit_categories(interaction)

    async def quick_save_setting(self, interaction: discord.Interaction, field_key: str, value, label: str):
        """Save a single top-level setting immediately and refresh the live panel."""
        await interaction.response.defer(ephemeral=True)

        if db.save_guild_settings(interaction.guild_id, {field_key: value}):
            from ticket_panel import update_panel
            try:
                await update_panel(interaction.guild, db)
            except Exception as e:
                print(f"Error refreshing panel after quick edit: {e}")
            await interaction.followup.send(f"✅ {label} updated and panel refreshed!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to update {label.lower()}.", ephemeral=True)

    async def quick_save_banner(self, interaction: discord.Interaction, banner_url: Optional[str]):
        cleaned_url = banner_url.strip() if banner_url else ""
        final_url = cleaned_url if cleaned_url.startswith(("http://", "https://")) else None
        await self.quick_save_setting(interaction, 'banner_url', final_url, "Banner image")

    async def quick_save_text_block(self, interaction: discord.Interaction, block_number: int, text: Optional[str]):
        cleaned = text.strip() if text else None
        await self.quick_save_setting(interaction, f'text{block_number}', cleaned, f"Text block {block_number}")

    async def show_quick_edit_categories(self, interaction: discord.Interaction):
        """List existing categories to edit, plus an option to add a new one."""
        categories = db.get_ticket_categories(interaction.guild_id)

        view = discord.ui.View(timeout=None)

        if categories:
            select = discord.ui.Select(
                placeholder="Select a category to edit...",
                options=[
                    discord.SelectOption(label=cat['name'], value=str(cat['id']))
                    for cat in categories[:25]
                ]
            )

            async def on_select(select_interaction: discord.Interaction):
                await self.start_quick_edit_category(select_interaction, int(select.values[0]))

            select.callback = on_select
            view.add_item(select)

        add_button = discord.ui.Button(label="➕ Add New Category", style=discord.ButtonStyle.success)

        async def on_add(button_interaction: discord.Interaction):
            await button_interaction.response.send_modal(
                CategoryInputModal(lambda i, name: self.start_quick_add_category(i, name))
            )

        add_button.callback = on_add
        view.add_item(add_button)

        message = "Select an existing category to edit, or add a new one:" if categories else "No categories yet — add one:"

        if interaction.response.is_done():
            await interaction.followup.send(message, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=view, ephemeral=True)

    async def start_quick_edit_category(self, interaction: discord.Interaction, category_id: int):
        """Begin editing an existing category's title/description/ping/visibility."""
        category = db.get_ticket_category_by_id(interaction.guild_id, category_id)
        if not category:
            await interaction.response.send_message("❌ Category not found.", ephemeral=True)
            return

        self.quick_edit_sessions[interaction.user.id] = {
            'guild_id': interaction.guild_id,
            'category_id': category_id,
            'name': category['name'],
            'is_new': False
        }

        await interaction.response.send_modal(
            CategoryConfigModal(
                category['name'],
                lambda i, name, title, description: self.on_quick_category_config_submit(i, title, description),
                existing_title=category.get('title'),
                existing_description=category.get('description')
            )
        )

    async def start_quick_add_category(self, interaction: discord.Interaction, category_name: str):
        """Begin adding a brand new category."""
        name = category_name.strip()

        if not name:
            await interaction.response.send_message("❌ Category name can't be empty.", ephemeral=True)
            return

        existing = db.get_ticket_categories(interaction.guild_id)
        if any(c['name'] == name for c in existing):
            await interaction.response.send_message("❌ That category already exists.", ephemeral=True)
            return

        self.quick_edit_sessions[interaction.user.id] = {
            'guild_id': interaction.guild_id,
            'category_id': None,
            'name': name,
            'is_new': True
        }

        await interaction.response.send_modal(
            CategoryConfigModal(
                name,
                lambda i, cat_name, title, description: self.on_quick_category_config_submit(i, title, description)
            )
        )

    async def on_quick_category_config_submit(self, interaction: discord.Interaction, title: str, description: str):
        """Handle title/description submission for a quick-edit category, then ask for ping roles."""
        session = self.quick_edit_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message("❌ Something went wrong — session expired.", ephemeral=True)
            return

        session['title'] = title
        session['description'] = description

        message = (
            f"Select role(s) to **ping** when a **{session['name']}** ticket is opened "
            f"(optional — click **Skip** for none):"
        )
        view = CategoryPingRoleSelectView(
            lambda i, role_ids: self.on_quick_category_ping_roles_submit(i, role_ids)
        )
        await interaction.response.send_message(message, view=view, ephemeral=True)

    async def on_quick_category_ping_roles_submit(self, interaction: discord.Interaction, role_ids: List[int]):
        """Handle ping role selection for a quick-edit category, then ask for visibility roles."""
        session = self.quick_edit_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message("❌ Something went wrong — session expired.", ephemeral=True)
            return

        session['ping_role_ids'] = role_ids

        message = (
            f"Select role(s) that can **see** **{session['name']}** tickets "
            f"(optional — click **Skip** to just use the global Support Roles):"
        )
        view = CategoryPingRoleSelectView(
            lambda i, r: self.on_quick_category_visible_roles_submit(i, r)
        )
        await interaction.response.send_message(message, view=view, ephemeral=True)

    async def on_quick_category_visible_roles_submit(self, interaction: discord.Interaction, role_ids: List[int]):
        """Handle visibility role selection for a quick-edit category, then save it."""
        await interaction.response.defer(ephemeral=True)

        session = self.quick_edit_sessions.pop(interaction.user.id, None)
        if not session:
            await interaction.followup.send("❌ Something went wrong — session expired.", ephemeral=True)
            return

        session['visible_role_ids'] = role_ids

        if session['is_new']:
            db.save_ticket_category(
                session['guild_id'],
                session['name'],
                session['title'],
                session['description'],
                session['ping_role_ids'],
                session['visible_role_ids']
            )
        else:
            db.update_ticket_category(
                session['guild_id'],
                session['category_id'],
                title=session['title'],
                description=session['description'],
                ping_role_ids=session['ping_role_ids'],
                visible_role_ids=session['visible_role_ids']
            )

        from ticket_panel import update_panel
        try:
            await update_panel(interaction.guild, db)
        except Exception as e:
            print(f"Error refreshing panel after category quick edit: {e}")

        await interaction.followup.send(f"✅ **{session['name']}** saved and panel refreshed!", ephemeral=True)

    # ==========================================
    # STEP 4: Finish Setup
    # ==========================================

    async def step_4_finish_setup(self, interaction: discord.Interaction):
        """STEP 4 - Save all settings and deploy the panel."""

        session = self.setup_sessions.get(interaction.user.id)
        if not session:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Setup session expired.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Setup session expired.", ephemeral=True)
            return

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
                    config.get('description', ''),
                    config.get('ping_role_ids', []),
                    config.get('visible_role_ids', [])
                )

            await self.deploy_panel(interaction)

            self.setup_sessions.pop(interaction.user.id, None)

            if interaction.response.is_done():
                await interaction.edit_original_response(
                    content="✅ **Setup Complete!** Your ticket system is now ready to use.",
                    embed=None,
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="✅ **Setup Complete!** Your ticket system is now ready to use.",
                    embed=None,
                    view=None
                )
        else:
            if interaction.response.is_done():
                await interaction.edit_original_response(
                    content="❌ Failed to save settings. Please try again.",
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

        self.setup_sessions.pop(interaction.user.id, None)

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