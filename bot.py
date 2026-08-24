import discord
import asyncio
import datetime
import threading
import os
import time
import sys

from flask import Flask, request
from erlc_api import handle_erlc_webhook, ERLCClient, ERLCAPIError

from discord.ext import commands
from discord import app_commands
from typing import Optional

from config import TOKEN, ERLC_SERVER_KEY

# Import ticket system modules
from ticket_database import db
from ticket_setup import TicketSetup
from ticket_creation import TicketCreation

# Import session panel module
from session_panel import setup_session_commands, SessionPanelView

# Import giveaway system modules
from giveaway_main import setup as setup_giveaway

# Import infraction system modules
from infraction_main import setup as setup_infraction

# ==========================================
# COMMAND ROLE PERMISSIONS CONFIGURATION
# Format: "command_name": REQUIRED_ROLE_ID
# Users with this role OR ANY ROLE HIGHER in hierarchy can run the command.
# ==========================================
COMMAND_ROLE_PERMISSIONS = {
    "session_panel": 1528496340315672777,  # Replace with actual Role ID
    "announce":      1527053497525207163,  # Replace with actual Role ID
    "ticket_setup":  1526959787219091486,  # Replace with actual Role ID
    "inputresults":  1527367791592607755,  # Replace with actual Role ID for results
    "feedback":      1527051350016397312,  # Replace with actual Role ID allowed to give/manage feedback
    "infraction":    1539201630161993728,  # Replace with actual Role ID for infractions
}


# ==========================================
# MARKETPLACE CONFIGURATION
# ==========================================
# Use direct image URLs (not page URLs like ibb.co)
# Get direct URLs by right-clicking image > "Copy Image Address"
SHOP_BANNER_URL = "https://i.postimg.cc/Rh7J6tk4/Gemini-Generated-Image-kxz78gkxz78gkxz7.jpg"  # Replace with direct image URL

# Your Discord custom emoji
# Upload the basket PNG to Server Settings > Emoji
SHOP_EMOJI = "<:shopping_cart:1541552477910990899>"

# Only this user can use !send_shop
AUTHORIZED_USER_ID = 1488252011374710958


# ==========================================
# FEEDBACK CHANNEL CONFIGURATION
# ==========================================
FEEDBACK_CHANNEL_ID = 1527066281084321863  # Replace with your target Feedback Channel ID


def has_role_or_higher(command_name: str):
    """Custom check to ensure the user has the required role OR a higher role in hierarchy."""
    async def predicate(interaction: discord.Interaction) -> bool:
        required_role_id = COMMAND_ROLE_PERMISSIONS.get(command_name)
        # If no role ID is configured for this command, allow usage by default
        if not required_role_id:
            return True

        # Ensure command is run inside a server
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False

        # Server owner & Administrators always bypass permission checks
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True

        target_role = interaction.guild.get_role(required_role_id)
        if not target_role:
            # Block command if configured role doesn't exist in server
            return False

        # Compare member's top role against target role hierarchy position
        return interaction.user.top_role >= target_role

    return app_commands.check(predicate)


# ==========================================
# BOT SETUP
# ==========================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# Global Error Handler for Role Permission Failure
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = "❌ You do not have the required role or higher to use this command."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    else:
        # Re-raise unhandled errors to console
        print(f"[ERROR] App Command Error: {error}")
        raise error


# Stores in-progress "dropdown info" setup sessions, keyed by card_id
dropdown_setups = {}

# Stores the option/description/text data for active dropdowns
active_dropdowns = {}

# Stores in-progress "add text?" setup sessions, keyed by card_id
text_setups = {}


# ==========================================
# READY
# ==========================================

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} ({bot.user.id})")
    
    # Store the has_role_or_higher function on the bot for cogs to use
    bot.has_role_or_higher = has_role_or_higher
    
    print("[SETUP] Loading ticket system...")

    try:
        await bot.add_cog(TicketSetup(bot, has_role_or_higher))
        await bot.add_cog(TicketCreation(bot))
        print("[SETUP] Ticket system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading ticket system: {e}")
        import traceback
        traceback.print_exc()

    print("[SETUP] Loading giveaway system...")

    try:
        await setup_giveaway(bot)
        print("[SETUP] Giveaway system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading giveaway system: {e}")
        import traceback
        traceback.print_exc()

    print("[SETUP] Loading infraction system...")

    try:
        await setup_infraction(bot)
        print("[SETUP] Infraction system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading infraction system: {e}")
        import traceback
        traceback.print_exc()

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s): {', '.join(c.name for c in synced)}")
    except Exception as e:
        print(e)

    try:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Game("Announcements")
        )
    except Exception as e:
        print(f"[READY] Could not set presence: {e}")

    # Start ER:LC command log polling exactly once (on_ready can fire again
    # after a reconnect — guard against starting a second copy of the loop).
    if not getattr(bot, "_erlc_poll_task", None):
        bot._erlc_poll_task = bot.loop.create_task(poll_erlc_command_logs())

    # Refresh ticket panels
    try:
        from ticket_panel import update_panel
        for guild in bot.guilds:
            try:
                await update_panel(guild, db)
            except Exception as e:
                print(f"Could not refresh ticket panel for {guild.name}: {e}")
    except Exception as e:
        print(f"Error refreshing ticket panels: {e}")
        import traceback
        traceback.print_exc()


# ==========================================
# BUTTON NAME CLEANER
# ==========================================

def clean_button_name(channel):
    name = channel.name
    name = "".join(c for c in name if c.isalnum() or c in [" ", "-", "_"])
    name = name.replace("-", " ").replace("_", " ")
    return name.title()


# ==========================================
# CREATE CARD
# ==========================================

def create_card(
    guild_name,
    banner_url,
    text,
    tags,
    channels,
    publish_id=None,
    dropdown_options=None,
    card_id=None
):
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(37, 37, 41)
    )

    # Banner (optional)
    if banner_url:
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=banner_url)
            )
        )
        container.add_item(discord.ui.Separator())

    # Announcement text
    if text:
        container.add_item(
            discord.ui.TextDisplay(text.replace("\\n", "\n"))
        )

    # Tags (optional)
    if tags:
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(tags.replace("\\n", "\n"))
        )

    # Channel buttons (optional)
    if channels:
        row = discord.ui.ActionRow()
        for channel in channels:
            row.add_item(
                discord.ui.Button(
                    label=clean_button_name(channel),
                    style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}"
                )
            )
        container.add_item(row)

    # Dropdown info menu (optional)
    if dropdown_options:
        select_id = card_id or publish_id or "preview"
        select_options = []

        for idx, opt in enumerate(dropdown_options):
            option_kwargs = {
                "label": (opt.get("name") or f"Option {idx + 1}")[:100],
                "value": str(idx)
            }

            description = (opt.get("description") or "")[:100]
            if description:
                option_kwargs["description"] = description

            emoji = opt.get("emoji")
            if emoji:
                option_kwargs["emoji"] = emoji

            try:
                select_options.append(discord.SelectOption(**option_kwargs))
            except Exception:
                option_kwargs.pop("emoji", None)
                select_options.append(discord.SelectOption(**option_kwargs))

        select = discord.ui.Select(
            custom_id=f"dselect_{select_id}",
            placeholder="📋 Select an option for more info",
            options=select_options
        )

        select_row = discord.ui.ActionRow()
        select_row.add_item(select)
        container.add_item(select_row)

    # Publish button
    if publish_id:
        publish_row = discord.ui.ActionRow()
        publish_row.add_item(
            discord.ui.Button(
                label="🚀 Publish",
                style=discord.ButtonStyle.green,
                custom_id=f"publish_{publish_id}"
            )
        )
        container.add_item(publish_row)

    view.add_item(container)
    return view


# ==========================================
# TEST CARD COMMAND
# ==========================================

@bot.command()
async def card(ctx):
    view = create_card(
        ctx.guild.name,
        None,
        "This is a **Components V2 card test.**",
        "Example tags",
        [],
        "test"
    )
    await ctx.send(view=view)


# ==========================================
# SHOP COMMAND
# ==========================================

@bot.command()
async def send_shop(ctx):
    """Send the marketplace panel using Components V2."""

    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        await ctx.send("❌ You don't have permission to use this command.")
        return

    try:

        # CREATE COMPONENTS V2 VIEW
        view = discord.ui.LayoutView(timeout=None)

        container = discord.ui.Container(
            accent_colour=discord.Color.gold()
        )

        # BANNER
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    media=SHOP_BANNER_URL
                )
            )
        )

        # SEPARATOR
        container.add_item(
            discord.ui.Separator()
        )

        # TITLE + CUSTOM SHOP EMOJI
        container.add_item(
            discord.ui.TextDisplay(
                f"# {SHOP_EMOJI} Marketplace"
            )
        )

        # DESCRIPTION
        container.add_item(
            discord.ui.TextDisplay(
                "Welcome to the marketplace! Here, you can purchase "
                "various perks to boost your server experience—including "
                "paid ads, sponsored giveaways, premium subscriptions, "
                "and more.\n\n"
                "Browse all our offerings and check current pricing "
                "by visiting the shop below:"
            )
        )

        # SEPARATOR
        container.add_item(
            discord.ui.Separator()
        )

        # DROPDOWN 1: Donations
        dropdown1 = discord.ui.Select(
            placeholder="<:robux:1541552732937265305> Donations",
            options=[
                discord.SelectOption(
                    label="Coming Soon",
                    value="donations_coming_soon"
                )
            ]
        )
        dropdown1.disabled = True
        container.add_item(dropdown1)

        # DROPDOWN 2: Server Advertisements
        dropdown2 = discord.ui.Select(
            placeholder="<:announcement:1541253550997504020> Server Advertisements",
            options=[
                discord.SelectOption(
                    label="Coming Soon",
                    value="ads_coming_soon"
                )
            ]
        )
        dropdown2.disabled = True
        container.add_item(dropdown2)

        # DROPDOWN 3: Server Memberships
        dropdown3 = discord.ui.Select(
            placeholder="<:star:1541552889993101323> Server Memberships",
            options=[
                discord.SelectOption(
                    label="Coming Soon",
                    value="memberships_coming_soon"
                )
            ]
        )
        dropdown3.disabled = True
        container.add_item(dropdown3)

        # DROPDOWN 4: Nitro Boost
        dropdown4 = discord.ui.Select(
            placeholder="<:nitro_gem:1541553100547162132> Nitro Boost",
            options=[
                discord.SelectOption(
                    label="Coming Soon",
                    value="nitro_coming_soon"
                )
            ]
        )
        dropdown4.disabled = True
        container.add_item(dropdown4)

        # Add container to view
        view.add_item(container)

        # Send marketplace
        await ctx.send(view=view)

    except Exception as e:
        print(f"[SHOP] Error creating marketplace: {e}")
        import traceback
        traceback.print_exc()
        await ctx.send(
            f"❌ Error creating marketplace: `{e}`"
        )


# ==========================================
# DROPDOWN SETUP HELPERS
# ==========================================

def build_simple_v2_view(message: str) -> discord.ui.LayoutView:
    """Builds a simple Components V2 message view."""
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(message))
    view.add_item(container)
    return view


def build_setup_view(card_id: str) -> discord.ui.View:
    """Builds the control buttons for configuring dropdown choices."""
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="➕ Add Option",
            style=discord.ButtonStyle.secondary,
            custom_id=f"dropdown_add_{card_id}"
        )
    )
    view.add_item(
        discord.ui.Button(
            label="✅ Confirm Choices",
            style=discord.ButtonStyle.success,
            custom_id=f"dropdown_confirm_{card_id}"
        )
    )
    return view


def build_setup_content(options: list) -> str:
    """Formats the current list of dropdown options added so far."""
    if options:
        lines = "\n".join(
            f"**{i + 1}.** {(opt.get('emoji') + ' ') if opt.get('emoji') else ''}"
            f"{opt['name']} — {opt['description'] or '*no description*'}"
            for i, opt in enumerate(options)
        )
    else:
        lines = "*No options added yet.*"

    return (
        "**🔽 Dropdown Info Setup**\n"
        "1. Click **Add Option** to add choices (name + optional description).\n"
        "2. Add as many choices as you need.\n"
        "3. Click **Confirm Choices** when you are ready to write the hidden response text for each choice.\n\n"
        f"**Current Choices:**\n{lines}"
    )


async def publish_final_card(root_interaction: discord.Interaction, card_data: dict, final_card):
    """Publishes a finished announcement card."""
    target_channel_id = card_data.get("target_channel_id")
    target_channel = (
        root_interaction.guild.get_channel(target_channel_id)
        if target_channel_id else root_interaction.channel
    )

    try:
        if target_channel == root_interaction.channel:
            await root_interaction.followup.send(view=final_card)
        else:
            await target_channel.send(view=final_card)
            await root_interaction.followup.send(
                f"✅ Announcement successfully published to {target_channel.mention}!",
                ephemeral=True
            )
    except Exception as e:
        print(f"Failed to post card: {e}")
        try:
            await target_channel.send(view=final_card)
        except Exception as send_err:
            try:
                await root_interaction.followup.send(f"❌ Error sending message: {send_err}", ephemeral=True)
            except Exception:
                pass


async def finalize_dropdown_announcement(interaction: discord.Interaction, card_id: str):
    """Publishes the finalized card after all text inputs are completed."""
    setup = dropdown_setups.get(card_id)
    if not setup:
        msg = "❌ This setup session expired."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return

    card_data = setup["card_data"]
    active_dropdowns[card_id] = setup["options"]

    final_card = create_card(
        card_data["guild"],
        card_data["banner"],
        card_data["text"],
        card_data["tags"],
        card_data["channels"],
        dropdown_options=setup["options"],
        card_id=card_id
    )

    target_channel_id = card_data.get("target_channel_id")
    target_channel = interaction.guild.get_channel(target_channel_id) if target_channel_id else interaction.channel

    try:
        if target_channel == interaction.channel and not target_channel_id:
            await interaction.followup.send(view=final_card)
        else:
            webhook = await target_channel.create_webhook(name="Announcement Bot")
            await webhook.send(
                view=final_card,
                username=interaction.client.user.name,
                avatar_url=interaction.client.user.display_avatar.url
            )
            await webhook.delete()
            if target_channel != interaction.channel:
                await interaction.followup.send(
                    f"✅ Announcement successfully published to {target_channel.mention}!",
                    ephemeral=True
                )
    except Exception as e:
        print(f"Error publishing via webhook: {e}")
        try:
            await target_channel.send(view=final_card)
        except Exception as send_err:
            await interaction.followup.send(f"❌ Failed to publish card: {send_err}", ephemeral=True)

    if card_id in dropdown_setups:
        del dropdown_setups[card_id]


# ==========================================
# DROPDOWN SETUP MODALS
# ==========================================

class DropdownOptionModal(discord.ui.Modal):
    def __init__(self, card_id: str):
        super().__init__(title="Add Dropdown Option")
        self.card_id = card_id

        self.name_input = discord.ui.TextInput(
            label="Option Name",
            placeholder="e.g. Server Rules",
            max_length=100,
            required=True
        )

        self.emoji_input = discord.ui.TextInput(
            label="Emoji (Optional)",
            placeholder="e.g. 📌 or a custom emoji",
            max_length=100,
            required=False
        )

        self.description_input = discord.ui.TextInput(
            label="Option Description (Optional)",
            placeholder="Short description shown under the option name",
            max_length=100,
            required=False
        )

        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction):
        setup = dropdown_setups.get(self.card_id)
        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        setup["options"].append({
            "name": str(self.name_input.value),
            "emoji": str(self.emoji_input.value) if self.emoji_input.value else None,
            "description": str(self.description_input.value) if self.description_input.value else ""
        })

        await interaction.response.edit_message(
            content=build_setup_content(setup["options"]),
            view=build_setup_view(self.card_id)
        )


class DropdownTextModal(discord.ui.Modal):
    def __init__(self, card_id: str, index: int):
        setup = dropdown_setups[card_id]
        option = setup["options"][index]

        super().__init__(title=f"Text for: {option['name'][:30]}")
        self.card_id = card_id
        self.index = index

        self.text_input = discord.ui.TextInput(
            label="Hidden Info Text",
            style=discord.TextStyle.paragraph,
            placeholder="This message will only be shown to users who click this option",
            max_length=4000,
            required=True
        )

        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        setup = dropdown_setups.get(self.card_id)
        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        setup["options"][self.index]["text"] = str(self.text_input.value)
        option = setup["options"][self.index]

        preview_message = (
            f"👀 **Preview — {option['name']}**\n"
            f"{option['text']}"
        )

        next_index = self.index + 1

        if next_index < len(setup["options"]):
            next_option = setup["options"][next_index]
            next_view = discord.ui.View(timeout=None)
            next_view.add_item(
                discord.ui.Button(
                    label=f"📝 Add text for '{next_option['name'][:40]}'",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"dropdown_next_{self.card_id}_{next_index}"
                )
            )

            await interaction.response.edit_message(
                content=(
                    f"{preview_message}\n\n"
                    f"Next up: **{next_option['name']}** ({next_index + 1}/{len(setup['options'])})\n"
                    f"Click the button below to enter text for this option."
                ),
                view=next_view
            )
        else:
            await interaction.response.defer(ephemeral=True)
            await finalize_dropdown_announcement(interaction, self.card_id)


class AnnouncementTextModal(discord.ui.Modal):
    """Collects the announcement body text after the admin chose 'Yes'."""

    def __init__(self, card_id: str):
        super().__init__(title="Write Announcement Text")
        self.card_id = card_id

        self.text_input = discord.ui.TextInput(
            label="Announcement Text",
            style=discord.TextStyle.paragraph,
            placeholder="This is the main body text of your announcement",
            max_length=4000,
            required=True
        )

        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        setup = text_setups.get(self.card_id)
        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        setup["card_data"]["text"] = str(self.text_input.value).replace("\\n", "\n")

        if setup["enable_dropdown_info"]:
            dropdown_setups[self.card_id] = {
                "user_id": setup["user_id"],
                "card_data": setup["card_data"],
                "options": [],
                "message": setup["message"],
                "root_interaction": setup["root_interaction"]
            }

            await interaction.response.edit_message(
                content=build_setup_content([]),
                view=build_setup_view(self.card_id)
            )

            del text_setups[self.card_id]
            return

        send_view = discord.ui.View(timeout=None)
        send_view.add_item(
            discord.ui.Button(
                label="📤 Send",
                style=discord.ButtonStyle.success,
                custom_id=f"text_send_{self.card_id}"
            )
        )

        await interaction.response.edit_message(
            content=(
                f"👀 **Preview**\n{setup['card_data']['text']}\n\n"
                f"Click **Send** to publish this announcement."
            ),
            view=send_view
        )


# ==========================================
# COMPONENT BUTTON HANDLER
# ==========================================

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")
    if not custom_id:
        return

    if custom_id.startswith("dropdown_add_"):
        card_id = custom_id.replace("dropdown_add_", "")
        setup = dropdown_setups.get(card_id)

        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the person who ran /announce can configure this.", ephemeral=True)
            return

        await interaction.response.send_modal(DropdownOptionModal(card_id))
        return

    if custom_id.startswith("dropdown_confirm_"):
        card_id = custom_id.replace("dropdown_confirm_", "")
        setup = dropdown_setups.get(card_id)

        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the person who ran /announce can configure this.", ephemeral=True)
            return

        if not setup["options"]:
            await interaction.response.send_message("❌ Add at least one option before confirming.", ephemeral=True)
            return

        await interaction.response.send_modal(DropdownTextModal(card_id, 0))
        return

    if custom_id.startswith("dropdown_next_"):
        remainder = custom_id.replace("dropdown_next_", "")
        card_id, _, index_str = remainder.rpartition("_")
        setup = dropdown_setups.get(card_id)

        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the person who ran /announce can configure this.", ephemeral=True)
            return

        try:
            index = int(index_str)
        except ValueError:
            index = None

        if index is None or index >= len(setup["options"]):
            await interaction.response.send_message("❌ Something went wrong with that option.", ephemeral=True)
            return

        await interaction.response.send_modal(DropdownTextModal(card_id, index))
        return

    if custom_id.startswith("dselect_"):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        card_id = custom_id.replace("dselect_", "")
        options = active_dropdowns.get(card_id)

        if not options:
            await interaction.followup.send("❌ This dropdown has expired.", ephemeral=True)
            return

        try:
            selected_index = int(interaction.data["values"][0])
        except (KeyError, IndexError, ValueError):
            selected_index = -1

        if selected_index < 0 or selected_index >= len(options):
            await interaction.followup.send("❌ Invalid option.", ephemeral=True)
            return

        option_text = options[selected_index].get("text") or "*No text was set for this option.*"

        await interaction.followup.send(
            view=build_simple_v2_view(option_text),
            ephemeral=True
        )
        return

    if custom_id.startswith("text_confirm_"):
        card_id = custom_id.replace("text_confirm_", "")
        setup = text_setups.get(card_id)

        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the person who ran /announce can configure this.", ephemeral=True)
            return

        await interaction.response.send_modal(AnnouncementTextModal(card_id))
        return

    if custom_id.startswith("text_send_"):
        card_id = custom_id.replace("text_send_", "")
        setup = text_setups.get(card_id)

        if not setup:
            await interaction.response.send_message("❌ This setup session expired.", ephemeral=True)
            return

        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the person who ran /announce can configure this.", ephemeral=True)
            return

        card_data = setup["card_data"]

        final_card = create_card(
            card_data["guild"],
            card_data["banner"],
            card_data["text"],
            card_data["tags"],
            card_data["channels"]
        )

        await interaction.response.edit_message(
            content="✅ Announcement sent!",
            view=None
        )

        await publish_final_card(setup["root_interaction"], card_data, final_card)

        del text_setups[card_id]
        return


# ==========================================
# ANNOUNCE COMMAND
# ==========================================

@bot.tree.command(
    name="announce",
    description="Create a professional announcement card"
)
@has_role_or_higher("announce")
@app_commands.choices(add_text=[
    app_commands.Choice(name="Yes", value="yes"),
    app_commands.Choice(name="No", value="no"),
])
@app_commands.describe(
    add_text="Do you want to add announcement text?",
    banner="Upload banner image",
    tags="Text below announcement",
    channel1="First button channel",
    channel2="Second button channel",
    channel3="Third button channel",
    enable_dropdown_info="Add an interactive dropdown with info only the clicker can see",
    target_channel="Optional channel to post the announcement to"
)
async def announce(
    interaction: discord.Interaction,
    add_text: app_commands.Choice[str],
    banner: Optional[discord.Attachment] = None,
    tags: Optional[str] = None,
    channel1: Optional[discord.TextChannel] = None,
    channel2: Optional[discord.TextChannel] = None,
    channel3: Optional[discord.TextChannel] = None,
    enable_dropdown_info: Optional[bool] = False,
    target_channel: Optional[discord.TextChannel] = None
):
    wants_text = add_text.value == "yes"

    is_ephemeral = (
        wants_text
        or bool(enable_dropdown_info)
        or (target_channel is not None and target_channel != interaction.channel)
    )

    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=is_ephemeral)
    except discord.NotFound:
        print("Warning: Interaction expired before deferring.")
        return
    except Exception as e:
        print(f"Defer error: {e}")

    channels = [c for c in [channel1, channel2, channel3] if c]
    card_id = str(interaction.id)

    nothing_to_send = (
        not wants_text
        and not banner
        and not tags
        and not channels
        and not enable_dropdown_info
    )

    if nothing_to_send:
        await interaction.followup.send(
            "❌ Nothing to send — add text, a banner, tags, channels, or enable the dropdown.",
            ephemeral=True
        )
        return

    card_data = {
        "guild": interaction.guild.name if interaction.guild else "Server",
        "banner": banner.url if banner else None,
        "text": "",
        "tags": tags.replace("\\n", "\n") if tags else "",
        "channels": channels,
        "target_channel_id": target_channel.id if target_channel else None
    }

    if wants_text:
        text_setups[card_id] = {
            "user_id": interaction.user.id,
            "card_data": card_data,
            "enable_dropdown_info": bool(enable_dropdown_info),
            "message": None,
            "root_interaction": interaction
        }

        confirm_view = discord.ui.View(timeout=None)
        confirm_view.add_item(
            discord.ui.Button(
                label="✅ Confirm",
                style=discord.ButtonStyle.success,
                custom_id=f"text_confirm_{card_id}"
            )
        )

        try:
            msg = await interaction.followup.send(
                content="You chose to add text to this announcement. Click **Confirm** to write it.",
                view=confirm_view,
                ephemeral=True,
                wait=True
            )
            text_setups[card_id]["message"] = msg
        except Exception as e:
            print(f"Error sending text confirmation view: {e}")
        return

    if enable_dropdown_info:
        dropdown_setups[card_id] = {
            "user_id": interaction.user.id,
            "card_data": card_data,
            "options": [],
            "message": None,
            "root_interaction": interaction
        }

        try:
            msg = await interaction.followup.send(
                content=build_setup_content([]),
                view=build_setup_view(card_id),
                ephemeral=True,
                wait=True
            )
            dropdown_setups[card_id]["message"] = msg
        except Exception as e:
            print(f"Error sending dropdown setup view: {e}")
        return

    # No text, no dropdown — publish immediately
    final_card = create_card(
        card_data["guild"],
        card_data["banner"],
        card_data["text"],
        card_data["tags"],
        card_data["channels"]
    )

    await publish_final_card(interaction, card_data, final_card)


# ==========================================
# FEEDBACK COMMAND GROUP
# ==========================================

feedback_group = app_commands.Group(name="feedback", description="Feedback commands")

@feedback_group.command(name="give", description="Submit feedback for a staff member")
@has_role_or_higher("feedback")
@app_commands.choices(rating=[
    app_commands.Choice(name="0/10", value="0/10"),
    app_commands.Choice(name="1/10", value="1/10"),
    app_commands.Choice(name="2/10", value="2/10"),
    app_commands.Choice(name="3/10", value="3/10"),
    app_commands.Choice(name="4/10", value="4/10"),
    app_commands.Choice(name="5/10", value="5/10"),
    app_commands.Choice(name="6/10", value="6/10"),
    app_commands.Choice(name="7/10", value="7/10"),
    app_commands.Choice(name="8/10", value="8/10"),
    app_commands.Choice(name="9/10", value="9/10"),
    app_commands.Choice(name="10/10", value="10/10"),
])
@app_commands.describe(
    staff="The staff member you want to give feedback to",
    rating="Rate the staff member from 0/10 to 10/10",
    feedback="Write your detailed feedback"
)
async def feedback_give(
    interaction: discord.Interaction,
    staff: discord.Member,
    rating: app_commands.Choice[str],
    feedback: str
):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        target_channel = interaction.guild.get_channel(FEEDBACK_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send("❌ Feedback channel not found! Check FEEDBACK_CHANNEL_ID in bot.py.", ephemeral=True)
            return

        view = discord.ui.LayoutView(timeout=None)

        # Uses exact dark charcoal hex (0x252529) for RGB(37, 37, 41)
        container = discord.ui.Container(
            accent_colour=discord.Color(0x252529)
        )

        header_text = (
            f"### Feedback from {interaction.user.display_name}\n\n"
            f"• **Staff Member:** {staff.mention}\n"
            f"• **Submitted By:** {interaction.user.mention}\n"
            f"• **Rating:** {rating.value}"
        )

        section = discord.ui.Section(
            discord.ui.TextDisplay(header_text),
            accessory=discord.ui.Thumbnail(media=staff.display_avatar.url) if staff.display_avatar else None
        )

        container.add_item(section)
        container.add_item(discord.ui.Separator())

        feedback_body = f"**Feedback:**\n{feedback}"
        container.add_item(discord.ui.TextDisplay(feedback_body))

        view.add_item(container)

        await target_channel.send(view=view)
        await interaction.followup.send("✅ Feedback submitted successfully!", ephemeral=True)

    except Exception as e:
        print(f"Error in feedback command: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
        except Exception:
            pass

bot.tree.add_command(feedback_group)


# ==========================================
# INPUT RESULTS COMMAND
# ==========================================

@bot.tree.command(
    name="inputresults",
    description="Submit training or evaluation results for a user."
)
@has_role_or_higher("inputresults")
@app_commands.describe(
    user="The applicant being evaluated",
    spag="SPaG score out of 10 (0-10)",
    driving="Driving score out of 10 (0-10)",
    mod_calls="Mod Calls score out of 10 (0-10)",
    knowledge="Knowledge score out of 10 (0-10)",
    note="Trainer's overall notes/description",
    result="Final result for the evaluation",
    channel="Optional target channel to send the results card to"
)
@app_commands.choices(result=[
    app_commands.Choice(name="✅ Pass", value="✅ Pass"),
    app_commands.Choice(name="❌ Fail", value="❌ Fail")
])
async def inputresults(
    interaction: discord.Interaction,
    user: discord.Member,
    spag: app_commands.Range[int, 0, 10],
    driving: app_commands.Range[int, 0, 10],
    mod_calls: app_commands.Range[int, 0, 10],
    knowledge: app_commands.Range[int, 0, 10],
    note: str,
    result: app_commands.Choice[str],
    channel: Optional[discord.TextChannel] = None
):
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(
        accent_colour=discord.Color.from_rgb(37, 37, 41)
    )

    content_text = (
        f"**Applicant:** {user.mention}\n\n"
        f"**SPaG:** {spag}/10\n"
        f"**Driving:** {driving}/10\n"
        f"**Mod Calls:** {mod_calls}/10\n"
        f"**Knowledge:** {knowledge}/10\n\n"
        f"**Trainer's overall description:**\n"
        f"{note}\n\n"
        f"**Final Result:** {result.value}\n\n"
        f"*Signed by {interaction.user.display_name}*"
    )

    container.add_item(discord.ui.TextDisplay(content_text))
    view.add_item(container)

    target_channel = channel or interaction.channel

    if target_channel == interaction.channel:
        await interaction.response.send_message(view=view)
    else:
        await target_channel.send(view=view)
        await interaction.response.send_message(
            f"✅ Results sent successfully to {target_channel.mention}!",
            ephemeral=True
        )


# ==========================================
# LOW LETTER COMMAND (LLC) LOGS
# ==========================================

# Global variable fallback
target_llc_channel_id = None


def has_llc_role():
    """Custom check for the LLC command using role ID 1526714098706940086."""
    async def predicate(ctx):
        REQUIRED_ROLE_ID = 1526714098706940086
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator:
            return True
        target_role = ctx.guild.get_role(REQUIRED_ROLE_ID)
        if not target_role:
            return False
        return ctx.author.top_role >= target_role
    return commands.check(predicate)


@bot.command(name="set_llc")
@has_llc_role()
async def set_llc(ctx):
    global target_llc_channel_id
    target_llc_channel_id = ctx.channel.id
    channel_name = ctx.channel.name

    # Save channel ID to MongoDB so it persists across restarts
    try:
        db.settings.update_one(
            {"_id": "llc_channel"},
            {"$set": {"channel_id": ctx.channel.id}},
            upsert=True
        )
    except Exception as e:
        print(f"[MongoDB Error] Could not save LLC channel: {e}")

    # Delete the command invocation message
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    # Send confirmation DM to user
    try:
        await ctx.author.send(f"successfully set low letter command logs in channel #{channel_name}")
    except discord.Forbidden:
        pass


async def send_llc_log(roblox_username: str, roblox_id: int, full_command: str):
    """Sends the Components V2 card if the word/argument after the command has fewer than 5 letters."""
    global target_llc_channel_id

    # 1. Check environment variable first
    channel_id = os.getenv("LLC_CHANNEL_ID")

    # 2. Check global in-memory variable
    if not channel_id and target_llc_channel_id:
        channel_id = target_llc_channel_id

    # 3. Fallback: Lookup in MongoDB Atlas
    if not channel_id:
        try:
            doc = db.settings.find_one({"_id": "llc_channel"})
            if doc:
                channel_id = doc.get("channel_id")
                target_llc_channel_id = channel_id
        except Exception as e:
            print(f"[MongoDB Error] Failed to fetch LLC channel: {e}")

    if not channel_id:
        return

    target_channel = bot.get_channel(int(channel_id))
    if not target_channel:
        return

    parts = full_command.strip().split()
    if len(parts) < 2:
        return

    target_word = parts[1]

    # Check if word after command has less than 5 letters
    if len(target_word) < 5:
        now = datetime.datetime.now()
        date_str = now.strftime("%d/%m/%Y")
        time_str = now.strftime("%I:%M %p").lower()

        roblox_profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"

        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(0, 162, 232)
        )

        content = (
            "### Low Letter Command Executed\n\n"
            f"[{roblox_username}:{roblox_id}]({roblox_profile_url}) used the command `{full_command}`\n\n"
            f"-# AZRP Command Logs | {date_str}, {time_str}"
        )

        container.add_item(discord.ui.TextDisplay(content))
        view.add_item(container)

        # Retry loop to catch rate limits (429) without crashing
        for attempt in range(3):
            try:
                await target_channel.send(view=view)
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 5)
                    print(f"[Rate Limit] Discord 429 hit. Retrying in {retry_after}s...")
                    await asyncio.sleep(retry_after)
                else:
                    print(f"[Discord Error] Could not send LLC log: {e}")
                    break


# ==========================================
# ER:LC COMMAND LOG POLLING
# ==========================================
# ER:LC's Event Webhook only ever sends two kinds of events: in-game chat
# messages that start with ";" and Emergency Calls. It does NOT deliver
# command-log events, no matter what payload shape you wait for — see
# https://apidocs.erlc.gg/event-webhooks ("What events are sent?").
# Command logs are only available by polling GET /v2/server?CommandLogs=true
# with the server key, so that's what this background task does.

_erlc_seen_commands = set()
_erlc_command_poll_first_run = True

ERLC_COMMAND_POLL_INTERVAL = 15  # seconds


async def poll_erlc_command_logs():
    """Background task: periodically pull command logs from the ER:LC API
    and forward new ones through send_llc_log."""
    global _erlc_seen_commands, _erlc_command_poll_first_run

    await bot.wait_until_ready()

    erlc_client = ERLCClient()
    if not erlc_client.configured:
        print("[ERLC] Command log polling disabled — ERLC_SERVER_KEY is not set.")
        return

    print(f"[ERLC] Polling command logs every {ERLC_COMMAND_POLL_INTERVAL}s...")

    while not bot.is_closed():
        try:
            data = await asyncio.to_thread(erlc_client.get_server, CommandLogs=True)
            logs = data.get("CommandLogs", []) or []

            if _erlc_command_poll_first_run:
                # Don't replay everything that already happened before the
                # bot started — just remember what's already there.
                _erlc_seen_commands = {
                    (log.get("Player"), log.get("Timestamp"), log.get("Command"))
                    for log in logs
                }
                _erlc_command_poll_first_run = False
            else:
                for log in logs:
                    key = (log.get("Player"), log.get("Timestamp"), log.get("Command"))
                    if key in _erlc_seen_commands:
                        continue
                    _erlc_seen_commands.add(key)

                    player_field = log.get("Player") or "Unknown:0"
                    username, _, roblox_id_str = player_field.partition(":")
                    command_text = log.get("Command") or ""

                    if command_text:
                        try:
                            await send_llc_log(
                                roblox_username=username or "Unknown",
                                roblox_id=int(roblox_id_str) if roblox_id_str.isdigit() else 0,
                                full_command=command_text
                            )
                        except Exception as e:
                            print(f"[ERLC] Error forwarding command log: {e}")

                # Keep the dedupe set from growing forever
                if len(_erlc_seen_commands) > 1000:
                    _erlc_seen_commands = set(list(_erlc_seen_commands)[-500:])

        except ERLCAPIError as e:
            print(f"[ERLC] Error polling command logs: {e}")
        except Exception as e:
            print(f"[ERLC] Unexpected error polling command logs: {e}")

        await asyncio.sleep(ERLC_COMMAND_POLL_INTERVAL)


# ==========================================
# REGISTER SESSIONS COMMANDS
# ==========================================

setup_session_commands(bot, has_role_or_higher)


# ==========================================
# WEB SERVER FOR RENDER
# ==========================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/erlc/events", methods=["POST"])
def erlc_events():
    """Receive and verify ER:LC Event Webhooks."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return "Invalid JSON", 400

    # Extract command log data from ER:LC webhook
    event_type = payload.get("EventType") or payload.get("event")
    data = payload.get("Data") or payload.get("data") or {}

    if event_type == "CommandLog" or "Command" in data:
        player_info = data.get("Player", {})
        username = player_info.get("Name") or data.get("PlayerName", "Unknown")
        roblox_id = player_info.get("UserId") or data.get("PlayerId", 0)
        command_text = data.get("Command") or data.get("command_text", "")

        if command_text and bot.is_ready():
            # Send log asynchronously to the Discord bot loop
            asyncio.run_coroutine_threadsafe(
                send_llc_log(
                    roblox_username=username,
                    roblox_id=roblox_id,
                    full_command=command_text
                ),
                bot.loop
            )

    return "OK", 200

@app.route("/erlc/status")
def erlc_status():
    """Simple integration health endpoint; never exposes the server key."""
    return {
        "configured": bool(ERLC_SERVER_KEY),
        "webhook_endpoint": "/erlc/events",
    }

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# ==========================================
# START BOT
# ==========================================

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "TOKEN environment variable is not set on Render."
        )
    
    # Start Flask web server in background thread for ER:LC webhooks
    threading.Thread(target=run_web, daemon=True).start()

    if ERLC_SERVER_KEY:
        print("[ERLC] Server key configured successfully.")
        print("[ERLC] Event webhook endpoint: /erlc/events")
    else:
        print("[ERLC] WARNING: ERLC_SERVER_KEY is not configured.")

    # Start Discord Bot ONCE (discord.py automatically handles reconnects)
    try:
        print("[Discord] Logging in...")
        bot.run(TOKEN)
    except discord.HTTPException as e:
        if e.status == 429:
            print("[Rate Limit] Currently blocked by Discord API (429). Waiting 60 seconds...")
            time.sleep(60)
        else:
            print(f"[Discord Error] {e}")
    except Exception as e:
        print(f"[Fatal Error] {e}")