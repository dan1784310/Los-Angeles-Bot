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
    NavigationButtons, PanelPreviewView, CategoryConfigView, ModalStepView,
    BlacklistRoleSelectView
)


class TicketSetup(commands.Cog):
    """Ticket system setup and configuration."""
    
    def __init__(self, bot: commands.Bot, has_role_or_higher):
        self.bot = bot
        self.has_role_or_higher = has_role_or_higher
        self.setup_sessions = {}  # Store active setup sessions by user_id
        
        # Apply the role check dynamically to the slash command
        self.setup = self.has_role_or_higher("ticket_setup")(self.setup)

    # ==========================================
    # SETUP COMMAND
    # ==========================================
    
    @app_commands.command(name="ticket_setup", description="Setup the ticket system")
    async def setup(self, interaction: discord.Interaction):
        """Start the ticket system setup wizard or edit existing settings."""
        
        # Check if setup already exists
        if db.has_guild_settings(interaction.guild_id):
            embed = discord.Embed(
                title="⚙️ Ticket System Configuration",
                description="Your server already has a ticket system configured. Choose an action below:",
                color=discord.Color.blue()
            )
            view = discord.ui.View(timeout=None)

            # Quick Edit Button
            edit_button = discord.ui.Button(
                label="✏️ Quick Edit",
                style=discord.ButtonStyle.primary,
                custom_id="quick_edit_setup"
            )

            async def on_quick_edit(button_interaction: discord.Interaction):
                await self.show_edit_menu(button_interaction)

            edit_button.callback = on_quick_edit
            view.add_item(edit_button)

            # Reconfigure Button
            reconfigure_button = discord.ui.Button(
                label="Reconfigure All",
                style=discord.ButtonStyle.danger,
                custom_id="reconfigure_setup"
            )

            async def on_reconfigure(button_interaction: discord.Interaction):
                await button_interaction.response.defer(ephemeral=True)
                self.setup_sessions[button_interaction.user.id] = {
                    'step': 1,
                    'guild_id': button_interaction.guild_id,
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
                await self.step_1_ticket_config(button_interaction)

            reconfigure_button.callback = on_reconfigure
            view.add_item(reconfigure_button)

            # Refresh Button
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

            # Cancel Button
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

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return
        
        # Start new setup if no configuration exists
        await interaction.response.defer(ephemeral=True)
        self.setup_sessions[interaction.user.id] = {
            'step': 1,
            'guild_id': interaction.guild_id,
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
        await self.step_1_ticket_config(interaction)

    # ==========================================
    # Quick Edit Component & Handler
    # ==========================================

    async def show_edit_menu(self, interaction: discord.Interaction):
        """Displays a dropdown menu to select a specific setting to edit."""
        
        select = discord.ui.Select(
            placeholder="Select a setting to edit...",
            options=[
                discord.SelectOption(label="Top Banner URL", value="banner_url", description="Change the top image banner", emoji="🖼️"),
            ]
        )

        async def select_callback(select_interaction: discord.Interaction):
            selected = select.values[0]

            if selected == "banner_url":
                await select_interaction.response.send_modal(
                    BannerURLModal(lambda i, url: self.save_quick_edit(i, 'banner_url', url))
                )

        select.callback = select_callback
        edit_view = discord.ui.View(timeout=None)
        edit_view.add_item(select)

        await interaction.response.send_message(
            "Select which component you want to update:",
            view=edit_view,
            ephemeral=True
        )

    async def save_quick_edit(self, interaction: discord.Interaction, field_key: str, value: str):
        """Saves the edited setting directly to DB and redeploys the panel."""
        await interaction.response.defer(ephemeral=True)

        settings = db.get_guild_settings(interaction.guild_id)
        if not settings:
            await interaction.followup.send("❌ Settings not found in database.", ephemeral=True)
            return

        # Clean URL or set to None
        cleaned_val = value.strip() if value else None
        if cleaned_val and not cleaned_val.startswith(("http://", "https://")):
            cleaned_val = None

        # Update setting field
        settings[field_key] = cleaned_val

        # Save back to database
        if db.save_guild_settings(interaction.guild_id, settings):
            from ticket_panel import update_panel
            success = await update_panel(interaction.guild, db)

            if success:
                await interaction.followup.send(
                    f"✅ **{field_key.replace('_', ' ').title()}** updated! Ticket panel has been refreshed.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Saved to database, but failed to refresh the panel message automatically.",
                    ephemeral=True
                )
        else:
            await interaction.followup.send("❌ Failed to update database.", ephemeral=True)
    
    # ==========================================
    # STEP 1: Ticket Configuration
    # ==========================================
        """Saves the edited setting directly to DB and redeploys the panel."""
        await interaction.response.defer(ephemeral=True)

        settings = db.get_guild_settings(interaction.guild_id)
        if not settings:
            await interaction.followup.send("❌ Settings not found in database.", ephemeral=True)
            return

        # Clean URL or set to None
        cleaned_val = value.strip() if value else None
        if cleaned_val and not cleaned_val.startswith(("http://", "https://")):
            cleaned_val = None

        # Update setting field
        settings[field_key] = cleaned_val

        # Save back to database
        if db.save_guild_settings(interaction.guild_id, settings):
            from ticket_panel import update_panel
            success = await update_panel(interaction.guild, db)

            if success:
                await interaction.followup.send(
                    f"✅ **{field_key.replace('_', ' ').title()}** updated! Ticket panel has been refreshed.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Saved to database, but failed to refresh the panel message automatically.",
                    ephemeral=True
                )
        else:
            await interaction.followup.send("❌ Failed to update database.", ephemeral=True)
    
    # ==========================================
    # STEP 1: Ticket Configuration
    # ==========================================
    
    async def step_1_ticket_config(self, interaction: discord.Interaction):
        """STEP 1 - Configure panel channel, ticket category, and support roles."""
        
        session = self.setup_sessions[interaction.user.id]
        
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
            view=ChannelSelectView('category', lambda i, c: self.on_category_select(i, c)),
            ephemeral=True
        )
    
    async def on_category_select(self, interaction: discord.Interaction, category_id: int):
        """Handle ticket category selection."""
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
                on_continue=lambda i: self.step_2_panel_designer(i),
                on_cancel=lambda i: self.cancel_setup(i)
            ),
            ephemeral=True
        )
    
    # ==========================================
    # STEP 2: Panel Designer
    # ==========================================
    
    async def step_2_panel_designer(self, interaction: discord.Interaction):
        """STEP 2 - Design the ticket panel appearance."""
        
        session = self.setup_sessions[interaction.user.id]
        session['step'] = 2
        session['current_text_block'] = 1
        
        embed = discord.Embed(
            title="🎨 Step 2: Ticket Panel Designer",
            description="Customize how your ticket panel looks.",
            color=discord.Color.purple()
        )
        
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=None, embed=embed, view=None)

        async def open_banner_modal(i: discord.Interaction):
            await i.response.send_modal(
                BannerURLModal(lambda i2, url: self.on_banner_submit(i2, url))
            )

        await interaction.followup.send(
            "Click below to enter your **Banner Image URL** (or click **Skip** to leave blank):",
            view=ModalStepView(
                "🖼️ Enter Banner URL",
                open_banner_modal,
                on_back=lambda i: self.step_1_ticket_config(i),
                on_skip=lambda i: self.on_banner_submit(i, None),
                on_cancel=lambda i: self.cancel_setup(i)
            ),
            ephemeral=True
        )
    
    async def on_banner_continue(self, interaction: discord.Interaction):
        """Continue after banner configuration."""
        await interaction.response.send_modal(
            BannerURLModal(lambda i, url: self.on_banner_submit(i, url))
        )
    
async def on_banner_submit(self, interaction: discord.Interaction, banner_url: str):
    """Handle banner URL submission with validation."""
    session = self.setup_sessions[interaction.user.id]
    cleaned_url = banner_url.strip() if banner_url else ""
    session['banner_url'] = cleaned_url if cleaned_url.startswith(("http://", "https://")) else None
    
    await self.text_block_step(interaction, 1)
    
    async def text_block_step(self, interaction: discord.Interaction, block_number: int):
        """Handle text block configuration."""
        session = self.setup_sessions[interaction.user.id]
        session['current_text_block'] = block_number

        async def open_modal(i: discord.Interaction):
            await i.response.send_modal(
                TextBlockModal(block_number, lambda i2, b, t: self.on_text_submit(i2, b, t))
            )

        if block_number == 1:
            await interaction.response.send_message(
                f"Enter **Text {block_number}** (Required):",
                view=ModalStepView(
                    f"📝 Enter Text {block_number}",
                    open_modal,
                    on_back=lambda i: self.step_2_panel_designer(i),
                    on_cancel=lambda i: self.cancel_setup(i)
                ),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Enter **Text {block_number}** (Optional, or click Skip):",
                view=ModalStepView(
                    f"📝 Enter Text {block_number}",
                    open_modal,
                    on_back=lambda i: self.on_text_back(i, block_number),
                    on_skip=lambda i: self.on_text_continue(i, block_number),
                    on_cancel=lambda i: self.cancel_setup(i)
                ),
                ephemeral=True
            )
    
    async def on_text_submit(self, interaction: discord.Interaction, block_number: int, text: str):
        """Handle text block submission."""
        session = self.setup_sessions[interaction.user.id]
        session['text_blocks'][block_number] = text if text else None
        
        if block_number < 5:
            await self.text_block_step(interaction, block_number + 1)
        else:
            await self.categories_step(interaction)
    
    async def on_text_back(self, interaction: discord.Interaction, block_number: int):
        """Handle back button in text block."""
        if block_number > 1:
            await self.text_block_step(interaction, block_number - 1)
        else:
            await self.step_2_panel_designer(interaction)
    
    async def on_text_continue(self, interaction: discord.Interaction, block_number: int):
        """Handle continue button (skip) in text block."""
        session = self.setup_sessions[interaction.user.id]
        session['text_blocks'][block_number] = None
        
        if block_number < 5:
            await self.text_block_step(interaction, block_number + 1)
        else:
            await self.categories_step(interaction)
    
    async def categories_step(self, interaction: discord.Interaction):
        """Handle ticket categories configuration."""
        session = self.setup_sessions[interaction.user.id]
        session['categories'] = []

        async def open_modal(i: discord.Interaction):
            await i.response.send_modal(
                CategoryInputModal(lambda i2, name: self.on_category_add(i2, name))
            )

        await interaction.response.send_message(
            "Add ticket categories. Type each category name one at a time.\n\n"
            "Examples: General Questions, Staff Report, Player Report, Bug Report, Appeal, Donation Support\n\n"
            "Click **Continue** when you're done adding categories.",
            view=ModalStepView(
                "➕ Add Category",
                open_modal,
                on_back=lambda i: self.text_block_step(i, 5),
                on_skip=lambda i: self.on_categories_done(i),
                on_cancel=lambda i: self.cancel_setup(i)
            ),
            ephemeral=True
        )
    
    async def on_category_add(self, interaction: discord.Interaction, category_name: str):
        """Handle adding a category."""
        session = self.setup_sessions[interaction.user.id]

        async def open_modal(i: discord.Interaction):
            await i.response.send_modal(
                CategoryInputModal(lambda i2, name: self.on_category_add(i2, name))
            )
        
        if category_name not in session['categories']:
            session['categories'].append(category_name)
            await interaction.response.send_message(
                f"✅ Added category: **{category_name}**\n"
                f"Current categories: {', '.join(session['categories'])}",
                view=ModalStepView(
                    "➕ Add Another Category",
                    open_modal,
                    on_back=lambda i: self.text_block_step(i, 5),
                    on_skip=lambda i: self.on_categories_done(i),
                    on_cancel=lambda i: self.cancel_setup(i)
                ),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ This category already exists. Please enter a different name.",
                ephemeral=True
            )
    
    async def on_categories_done(self, interaction: discord.Interaction):
        """Handle completion of categories."""
        session = self.setup_sessions[interaction.user.id]
        
        if not session['categories']:
            await interaction.response.send_message(
                "❌ You must add at least one category.",
                ephemeral=True
            )
            await self.categories_step(interaction)
            return
        
        await self.show_panel_preview(interaction)
    
    # ==========================================
    # Panel Preview
    # ==========================================
    
    async def show_panel_preview(self, interaction: discord.Interaction):
        """Show read-only preview of the ticket panel."""
        
        session = self.setup_sessions[interaction.user.id]
        
        embed = discord.Embed(
            title="👁️ Ticket Panel Preview",
            description="This is how your ticket panel will look:",
            color=discord.Color.gold()
        )
        
        components = []
        
        if session['banner_url']:
            components.append(f"🖼️ **Banner:** {session['banner_url']}")
            components.append("────────────────────────")
        
        for i in range(1, 6):
            text = session['text_blocks'][i]
            if text:
                components.append(f"📝 **Text {i}:**\n{text}")
                if i < 5 and any(session['text_blocks'][j] for j in range(i+1, 6)):
                    components.append("────────────────────────")
        
        components.append("📋 **Dropdown Menu:**")
        for cat in session['categories']:
            components.append(f"  • {cat}")
        
        if components:
            embed.description = "\n".join(components)
        
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=PanelPreviewView(
                on_confirm=lambda i: self.step_3_configure_categories(i),
                on_edit=lambda i: self.step_2_panel_designer(i)
            )
        )
    
    # ==========================================
    # STEP 3: Configure Categories
    # ==========================================
    
    async def step_3_configure_categories(self, interaction: discord.Interaction):
        """STEP 3 - Configure each dropdown category."""
        session = self.setup_sessions[interaction.user.id]
        session['step'] = 3
        session['current_category_index'] = 0
        await interaction.response.defer(ephemeral=True)
        await self.configure_category(interaction, session['categories'][0])
    
    async def configure_category(self, interaction: discord.Interaction, category_name: str):
        """Configure a single category's title and description."""
        session = self.setup_sessions[interaction.user.id]
        session['current_category'] = category_name
        
        embed = discord.Embed(
            title=f"📝 Configure: {category_name}",
            description="Set the title and description for this category's ticket embed.",
            color=discord.Color.green()
        )

        async def open_modal(i: discord.Interaction):
            await i.response.send_modal(
                CategoryConfigModal(
                    category_name,
                    lambda i2, n, t, d: self.on_category_config_submit(i2, n, t, d)
                )
            )
        
        await interaction.followup.send(
            embed=embed,
            view=ModalStepView(f"📝 Configure {category_name}", open_modal),
            ephemeral=True
        )
    
    async def on_category_config_submit(self, interaction: discord.Interaction, 
                                       category_name: str, title: str, description: str):
        """Handle category configuration submission."""
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
            embed.add_field(
                name=f"📌 {category_name}",
                value=f"**Title:** {config.get('title', 'N/A')}\n**Description:** {config.get('description', 'N/A')[:100]}...",
                inline=False
            )
        
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=embed,
                    view=CategoryConfigView(
                        category_name=session['categories'][0],
                        on_back=lambda i: self.step_3_configure_categories(i),
                        on_confirm=lambda i: self.step_4_finish_setup(i),
                        on_edit=lambda i: self.edit_category(i, session['categories'][0])
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.edit_message(
                    content=None,
                    embed=embed,
                    view=CategoryConfigView(
                        category_name=session['categories'][0],
                        on_back=lambda i: self.step_3_configure_categories(i),
                        on_confirm=lambda i: self.step_4_finish_setup(i),
                        on_edit=lambda i: self.edit_category(i, session['categories'][0])
                    )
                )
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
        
        # Save to database
        settings = {
            'panel_channel_id': session['panel_channel_id'],
            'ticket_category_id': session['ticket_category_id'],
            'support_roles': session['support_roles'],
            'blacklisted_roles': session.get('blacklisted_roles', []),
            'banner_url': session['banner_url'],
            'bottom_banner_url': None,
            'text1': session['text_blocks'][1],
            'text2': session['text_blocks'][2],
            'text3': session['text_blocks'][3],
            'text4': session['text_blocks'][4],
            'text5': session['text_blocks'][5],
            'ticket_counter': 0
        }
        
        if db.save_guild_settings(session['guild_id'], settings):
            # Clear existing categories
            db.clear_ticket_categories(session['guild_id'])
            
            # Save categories
            for category_name in session['categories']:
                config = session['category_configs'].get(category_name, {})
                db.save_ticket_category(
                    session['guild_id'],
                    category_name,
                    config.get('title', category_name),
                    config.get('description', '')
                )
            
            # Deploy panel
            await self.deploy_panel(interaction)
            
            # Clean up session
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
        
        # Import here to avoid circular imports
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
        
        # Delete existing panel if exists
        existing_message_id = db.get_panel_message(session['guild_id'])
        if existing_message_id:
            try:
                existing_message = await panel_channel.fetch_message(existing_message_id)
                await existing_message.delete()
            except Exception:
                pass
        
        # Send new panel
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
        
        await interaction.response.edit_message(
            content="❌ Setup cancelled.",
            embed=None,
            view=None
        )


async def setup(bot: commands.Bot, has_role_or_higher=None):
    """Setup the ticket setup cog."""
    # Fallback function if loaded without passing permission check
    if has_role_or_higher is None:
        has_role_or_higher = getattr(bot, 'has_role_or_higher', None)
        
    await bot.add_cog(TicketSetup(bot, has_role_or_higher))
