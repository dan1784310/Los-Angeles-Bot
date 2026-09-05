import asyncio
import datetime
import os
import re
import threading
import time
import traceback
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request

from config import TOKEN, ERLC_SERVER_KEY
from erlc_api import ERLCClient, ERLCAPIError
from ticket_database import db
from ticket_setup import TicketSetup
from ticket_creation import TicketCreation
from session_panel import setup_session_commands, SessionPanelView
from giveaway_main import setup as setup_giveaway
from infraction_main import setup as setup_infraction
from promotion_main import setup as setup_promotion
from ping_protection import setup as setup_ping_protection
from moderation_main import setup as setup_moderation
from moderation_database import db as mod_db


# ============================================================
# COMMAND ROLE PERMISSIONS
# ============================================================

COMMAND_ROLE_PERMISSIONS = {
    "session_panel": 1528496340315672777,
    "announce": 1527053497525207163,
    "ticket_setup": 1526959787219091486,
    "inputresults": 1527367791592607755,
    "feedback": 1527051350016397312,
    "infraction": 1539201630161993728,
    "promote": 1527055221098811433,
    "ticket_rename": 1527374021572956291,
    "moderation": 1527053931304321130,
}


# ============================================================
# MARKETPLACE CONFIGURATION
# ============================================================

SHOP_BANNER_URL = "https://i.postimg.cc/L8gcVkbq/Arizona-State-Marketplace-Banner.jpg"
SHOP_BOTTOM_THUMBNAIL_URL = "https://cdn.imageurlgenerator.com/uploads/85ff6f6b-754f-4988-b505-56a171cef43b.png"
SHOP_EMOJI = "<:shopping_cart:1541552477910990899>"
AUTHORIZED_USER_ID = 1488252011374710958

EMOJI_ROBUX = discord.PartialEmoji.from_str("<:robux:1541552732937265305>")
EMOJI_ADS = discord.PartialEmoji.from_str("<:announcement:1541253550997504020>")
EMOJI_STAR = discord.PartialEmoji.from_str("<:star:1541552889993101323>")
EMOJI_NITRO = discord.PartialEmoji.from_str("<:nitro_gem:1541553100547162132>")

FEEDBACK_CHANNEL_ID = 1527066281084321863


# ============================================================
# PERMISSION HELPERS
# ============================================================

def has_role_or_higher(command_name: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        required_role_id = COMMAND_ROLE_PERMISSIONS.get(command_name)
        if not required_role_id:
            return True

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False

        if (
            interaction.user.id == interaction.guild.owner_id
            or interaction.user.guild_permissions.administrator
        ):
            return True

        target_role = interaction.guild.get_role(required_role_id)
        if not target_role:
            return False

        return interaction.user.top_role >= target_role

    return app_commands.check(predicate)


def has_role_or_higher_prefix(command_name: str):
    def predicate(ctx: commands.Context):
        required_role_id = COMMAND_ROLE_PERMISSIONS.get(command_name)
        if not required_role_id:
            return True

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False

        if (
            ctx.author.id == ctx.guild.owner_id
            or ctx.author.guild_permissions.administrator
        ):
            return True

        target_role = ctx.guild.get_role(required_role_id)
        if not target_role:
            return False

        return ctx.author.top_role.position >= target_role.position

    return commands.check(predicate)


# ============================================================
# BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    print(f"[MESSAGE DEBUG] {message.content}")
    await bot.process_commands(message)


@bot.command()
async def test(ctx: commands.Context):
    print("[TEST] !test received")
    await ctx.send("✅ Prefix commands are working!")


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.CheckFailure):
        msg = "❌ You do not have the required role or higher to use this command."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    else:
        print(f"[ERROR] App Command Error: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You do not have the required role or higher to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: `{error}`")
    else:
        print(f"[ERROR] Prefix Command Error: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)


# State for the announcement builder.
dropdown_setups = {}
active_dropdowns = {}
text_setups = {}


# ============================================================
# READY EVENT
# ============================================================

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} ({bot.user.id})")

    print("[COMMANDS] Registered prefix commands:")
    for command in bot.commands:
        print(f"  !{command.name}")

    bot.has_role_or_higher = has_role_or_higher

    print("[SETUP] Loading ticket system...")
    try:
        await bot.add_cog(TicketSetup(bot, has_role_or_higher))
        await bot.add_cog(TicketCreation(bot))
        print("[SETUP] Ticket system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading ticket system: {e}")
        traceback.print_exc()

    print("[SETUP] Loading giveaway system...")
    try:
        await setup_giveaway(bot)
        print("[SETUP] Giveaway system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading giveaway system: {e}")
        traceback.print_exc()

    print("[SETUP] Loading infraction system...")
    try:
        await setup_infraction(bot)
        print("[SETUP] Infraction system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading infraction system: {e}")
        traceback.print_exc()

    print("[SETUP] Loading promotion system...")
    try:
        await setup_promotion(bot)
        print("[SETUP] Promotion system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading promotion system: {e}")
        traceback.print_exc()

    print("[SETUP] Loading ping protection system...")
    try:
        await setup_ping_protection(bot)
        print("[SETUP] Ping protection system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading ping protection system: {e}")
        traceback.print_exc()

    print("[SETUP] Loading moderation system...")
    try:
        await setup_moderation(bot)
        print("[SETUP] Moderation system loaded successfully")
    except Exception as e:
        print(f"[SETUP] Error loading moderation system: {e}")
        traceback.print_exc()

    try:
        # Sync commands with rate limit handling
        print("[SYNC] Starting command sync...")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s): {', '.join(c.name for c in synced)}")
    except discord.errors.HTTPException as e:
        if e.status == 429:  # Rate limited
            retry_after = e.retry_after if hasattr(e, 'retry_after') else 60
            print(f"[SYNC] Rate limited. Retrying in {retry_after} seconds...")
            await asyncio.sleep(retry_after)
            try:
                synced = await bot.tree.sync()
                print(f"Synced {len(synced)} command(s) after retry: {', '.join(c.name for c in synced)}")
            except Exception as retry_e:
                print(f"[SYNC] Error syncing commands after retry: {retry_e}")
                traceback.print_exc()
        else:
            print(f"[SYNC] Error syncing commands: {e}")
            traceback.print_exc()
    except Exception as e:
        print(f"[SYNC] Error syncing commands: {e}")
        traceback.print_exc()

    try:
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Game("Announcements"),
        )
    except Exception as e:
        print(f"[READY] Could not set presence: {e}")

    if not getattr(bot, "_erlc_poll_task", None) or bot._erlc_poll_task.done():
        bot._erlc_poll_task = asyncio.create_task(poll_erlc_command_logs())

    try:
        from ticket_panel import update_panel

        for guild in bot.guilds:
            try:
                await update_panel(guild, db)
            except Exception as e:
                print(f"Could not refresh ticket panel for {guild.name}: {e}")
    except Exception as e:
        print(f"Error refreshing ticket panels: {e}")
        traceback.print_exc()


# ============================================================
# ANNOUNCEMENT CARD HELPERS
# ============================================================

def clean_button_name(channel: discord.TextChannel) -> str:
    name = channel.name
    name = "".join(c for c in name if c.isalnum() or c in [" ", "-", "_"])
    name = name.replace("-", " ").replace("_", " ")
    return name.title()


def create_card(
    guild_name,
    banner_url,
    bottom_banner_url=None,
    text=None,
    tags=None,
    channels=None,
    publish_id=None,
    dropdown_options=None,
    card_id=None,
):
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

    if text:
        container.add_item(
            discord.ui.TextDisplay(text.replace("\\n", "\n"))
        )

    if tags:
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(tags.replace("\\n", "\n"))
        )

    if channels:
        row = discord.ui.ActionRow()
        for channel in channels:
            row.add_item(
                discord.ui.Button(
                    label=clean_button_name(channel),
                    style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}",
                )
            )
        container.add_item(row)

    if bottom_banner_url:
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=bottom_banner_url)
            )
        )

    if dropdown_options:
        select_id = card_id or publish_id or "preview"
        select_options = []

        for idx, opt in enumerate(dropdown_options):
            option_kwargs = {
                "label": (opt.get("name") or f"Option {idx + 1}")[:100],
                "value": str(idx),
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
            options=select_options,
        )

        select_row = discord.ui.ActionRow()
        select_row.add_item(select)
        container.add_item(select_row)

    if publish_id:
        publish_row = discord.ui.ActionRow()
        publish_row.add_item(
            discord.ui.Button(
                label="🚀 Publish",
                style=discord.ButtonStyle.green,
                custom_id=f"publish_{publish_id}",
            )
        )
        container.add_item(publish_row)

    view.add_item(container)
    return view


@bot.command()
async def card(ctx: commands.Context):
    view = create_card(
        ctx.guild.name,
        None,
        "This is a **Components V2 card test.**",
        "Example tags",
        [],
    )
    await ctx.send(view=view)


# ============================================================
# MARKETPLACE
# ============================================================

@bot.command(name="shop")
async def send_shop(ctx: commands.Context):
    """Send the marketplace panel using Components V2."""
    if ctx.author.id != AUTHORIZED_USER_ID:
        await ctx.send("❌ You don't have permission to use this command.")
        return

    try:
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=discord.Color.from_rgb(37, 37, 41)
        )

        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=SHOP_BANNER_URL)
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(f"# {SHOP_EMOJI} Marketplace")
        )

        container.add_item(
            discord.ui.TextDisplay(
                "Welcome to the marketplace! Here, you can purchase "
                "various perks to boost your server experience—including "
                "paid ads, sponsored giveaways, premium subscriptions, "
                "and more.\n\n"
                "Browse all our offerings and check current pricing "
                "by selecting a category below:"
            )
        )
        container.add_item(discord.ui.Separator())

        marketplace_dropdown = discord.ui.Select(
            placeholder="Select a marketplace category...",
            custom_id="marketplace_category",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Donations",
                    value="donations",
                    emoji=EMOJI_ROBUX,
                ),
                discord.SelectOption(
                    label="Server Advertisements",
                    value="server_advertisements",
                    emoji=EMOJI_ADS,
                ),
                discord.SelectOption(
                    label="Server Memberships",
                    value="server_memberships",
                    emoji=EMOJI_STAR,
                ),
                discord.SelectOption(
                    label="Nitro Boost",
                    value="nitro_boost",
                    emoji=EMOJI_NITRO,
                ),
            ],
        )

        dropdown_row = discord.ui.ActionRow()
        dropdown_row.add_item(marketplace_dropdown)
        container.add_item(dropdown_row)
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=SHOP_BOTTOM_THUMBNAIL_URL)
            )
        )

        view.add_item(container)
        await ctx.send(view=view)
        print("[SHOP] Marketplace sent successfully.")

    except Exception as e:
        print(f"[SHOP] Error creating marketplace: {e}")
        traceback.print_exc()
        try:
            await ctx.send(f"❌ Error creating marketplace:\n```{e}```")
        except Exception as send_error:
            print(f"[SHOP] Could not send error message: {send_error}")


# ============================================================
# TICKET RENAME
# ============================================================

@bot.command(name="rename")
@has_role_or_higher_prefix("ticket_rename")
async def rename_ticket(ctx: commands.Context, *, new_name: str):
    clean_name = re.sub(r"[^\w\s-]", "", new_name, flags=re.UNICODE)
    clean_name = clean_name.lower().strip()
    clean_name = re.sub(r"\s+", "-", clean_name)

    if not clean_name:
        await ctx.send("❌ Invalid channel name.")
        return

    if len(clean_name) > 100:
        await ctx.send("❌ Channel name too long (max 100 characters).")
        return

    try:
        await ctx.channel.edit(name=clean_name)
        await ctx.send(f"✅ Ticket channel renamed to `{clean_name}`")
        print(
            f"[TICKET RENAME] {ctx.author} renamed ticket "
            f"{ctx.channel.id} to {clean_name}"
        )
    except Exception as e:
        await ctx.send(f"❌ Failed to rename channel: `{e}`")
        print(f"[TICKET RENAME ERROR] {e}")


# ============================================================
# DROPDOWN SETUP HELPERS
# ============================================================

def build_simple_v2_view(message: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(message))
    view.add_item(container)
    return view


def build_setup_view(card_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="➕ Add Option",
            style=discord.ButtonStyle.secondary,
            custom_id=f"dropdown_add_{card_id}",
        )
    )
    view.add_item(
        discord.ui.Button(
            label="✅ Confirm Choices",
            style=discord.ButtonStyle.success,
            custom_id=f"dropdown_confirm_{card_id}",
        )
    )
    return view


def build_setup_content(options: list) -> str:
    if options:
        lines = "\n".join(
            f"**{i + 1}.** "
            f"{(opt.get('emoji') + ' ') if opt.get('emoji') else ''}"
            f"{opt['name']} — {opt.get('description') or '*no description*'}"
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


async def publish_final_card(
    root_interaction: discord.Interaction,
    card_data: dict,
    final_card,
):
    target_channel_id = card_data.get("target_channel_id")
    target_channel = (
        root_interaction.guild.get_channel(target_channel_id)
        if target_channel_id and root_interaction.guild
        else root_interaction.channel
    )

    try:
        if target_channel == root_interaction.channel:
            await root_interaction.followup.send(view=final_card)
        else:
            await target_channel.send(view=final_card)
            await root_interaction.followup.send(
                f"✅ Announcement successfully published to {target_channel.mention}!",
                ephemeral=True,
            )
    except Exception as e:
        print(f"Failed to post card: {e}")
        try:
            await target_channel.send(view=final_card)
        except Exception as send_err:
            try:
                await root_interaction.followup.send(
                    f"❌ Error sending message: {send_err}",
                    ephemeral=True,
                )
            except Exception:
                pass


async def finalize_dropdown_announcement(
    interaction: discord.Interaction,
    card_id: str,
):
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
        card_data.get("bottom_banner"),
        card_data["text"],
        card_data["tags"],
        card_data["channels"],
        publish_id=card_id,
        dropdown_options=active_dropdowns.get(card_id),
        card_id=card_id,
    )

    target_channel_id = card_data.get("target_channel_id")
    target_channel = (
        interaction.guild.get_channel(target_channel_id)
        if target_channel_id and interaction.guild
        else interaction.channel
    )

    try:
        if target_channel == interaction.channel and not target_channel_id:
            await interaction.followup.send(view=final_card)
        else:
            webhook = await target_channel.create_webhook(name="Announcement Bot")
            try:
                await webhook.send(
                    view=final_card,
                    username=interaction.client.user.name,
                    avatar_url=interaction.client.user.display_avatar.url,
                )
            finally:
                await webhook.delete()

            if target_channel != interaction.channel:
                await interaction.followup.send(
                    f"✅ Announcement successfully published to {target_channel.mention}!",
                    ephemeral=True,
                )
    except Exception as e:
        print(f"Error publishing via webhook: {e}")
        try:
            await target_channel.send(view=final_card)
        except Exception as send_err:
            await interaction.followup.send(
                f"❌ Failed to publish card: {send_err}",
                ephemeral=True,
            )

    dropdown_setups.pop(card_id, None)


# ============================================================
# DROPDOWN MODALS
# ============================================================

class DropdownOptionModal(discord.ui.Modal):
    def __init__(self, card_id: str):
        super().__init__(title="Add Dropdown Option")
        self.card_id = card_id

        self.name_input = discord.ui.TextInput(
            label="Option Name",
            placeholder="e.g. Server Rules",
            max_length=100,
            required=True,
        )
        self.emoji_input = discord.ui.TextInput(
            label="Emoji (Optional)",
            placeholder="e.g. 📌 or a custom emoji",
            max_length=100,
            required=False,
        )
        self.description_input = discord.ui.TextInput(
            label="Option Description (Optional)",
            placeholder="Short description shown under the option name",
            max_length=100,
            required=False,
        )

        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction):
        setup = dropdown_setups.get(self.card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return

        setup["options"].append(
            {
                "name": str(self.name_input.value),
                "emoji": str(self.emoji_input.value) if self.emoji_input.value else None,
                "description": str(self.description_input.value)
                if self.description_input.value
                else "",
            }
        )

        await interaction.response.edit_message(
            content=build_setup_content(setup["options"]),
            view=build_setup_view(self.card_id),
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
            required=True,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        setup = dropdown_setups.get(self.card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
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
                    custom_id=f"dropdown_next_{self.card_id}_{next_index}",
                )
            )

            await interaction.response.edit_message(
                content=(
                    f"{preview_message}\n\n"
                    f"Next up: **{next_option['name']}** "
                    f"({next_index + 1}/{len(setup['options'])})\n"
                    "Click the button below to enter text for this option."
                ),
                view=next_view,
            )
        else:
            await interaction.response.defer(ephemeral=True)
            await finalize_dropdown_announcement(interaction, self.card_id)


class AnnouncementTextModal(discord.ui.Modal):
    def __init__(self, card_id: str):
        super().__init__(title="Write Announcement Text")
        self.card_id = card_id

        self.text_input = discord.ui.TextInput(
            label="Announcement Text",
            style=discord.TextStyle.paragraph,
            placeholder="This is the main body text of your announcement",
            max_length=4000,
            required=True,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        setup = text_setups.get(self.card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return

        setup["card_data"]["text"] = str(self.text_input.value).replace("\\n", "\n")

        if setup["enable_dropdown_info"]:
            dropdown_setups[self.card_id] = {
                "user_id": setup["user_id"],
                "card_data": setup["card_data"],
                "options": [],
                "message": setup["message"],
                "root_interaction": setup["root_interaction"],
            }

            await interaction.response.edit_message(
                content=build_setup_content([]),
                view=build_setup_view(self.card_id),
            )
            text_setups.pop(self.card_id, None)
            return

        send_view = discord.ui.View(timeout=None)
        send_view.add_item(
            discord.ui.Button(
                label="📤 Send",
                style=discord.ButtonStyle.success,
                custom_id=f"text_send_{self.card_id}",
            )
        )

        await interaction.response.edit_message(
            content=(
                f"👀 **Preview**\n{setup['card_data']['text']}\n\n"
                "Click **Send** to publish this announcement."
            ),
            view=send_view,
        )


# ============================================================
# COMPONENT HANDLER
# ============================================================

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = (interaction.data or {}).get("custom_id")
    if not custom_id:
        return

    if custom_id.startswith("dropdown_add_"):
        card_id = custom_id.replace("dropdown_add_", "", 1)
        setup = dropdown_setups.get(card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return
        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Only the person who ran /announce can configure this.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(DropdownOptionModal(card_id))
        return

    if custom_id.startswith("dropdown_confirm_"):
        card_id = custom_id.replace("dropdown_confirm_", "", 1)
        setup = dropdown_setups.get(card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return
        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Only the person who ran /announce can configure this.",
                ephemeral=True,
            )
            return
        if not setup["options"]:
            await interaction.response.send_message(
                "❌ Add at least one option before confirming.", ephemeral=True
            )
            return
        await interaction.response.send_modal(DropdownTextModal(card_id, 0))
        return

    if custom_id.startswith("dropdown_next_"):
        remainder = custom_id.replace("dropdown_next_", "", 1)
        card_id, _, index_str = remainder.rpartition("_")
        setup = dropdown_setups.get(card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return
        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Only the person who ran /announce can configure this.",
                ephemeral=True,
            )
            return

        try:
            index = int(index_str)
        except ValueError:
            index = -1

        if index < 0 or index >= len(setup["options"]):
            await interaction.response.send_message(
                "❌ Something went wrong with that option.", ephemeral=True
            )
            return

        await interaction.response.send_modal(DropdownTextModal(card_id, index))
        return

    if custom_id.startswith("dselect_"):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        card_id = custom_id.replace("dselect_", "", 1)
        options = active_dropdowns.get(card_id)
        if not options:
            await interaction.followup.send(
                "❌ This dropdown has expired.", ephemeral=True
            )
            return

        try:
            selected_index = int((interaction.data or {})["values"][0])
        except (KeyError, IndexError, ValueError):
            selected_index = -1

        if selected_index < 0 or selected_index >= len(options):
            await interaction.followup.send("❌ Invalid option.", ephemeral=True)
            return

        option_text = (
            options[selected_index].get("text")
            or "*No text was set for this option.*"
        )
        await interaction.followup.send(
            view=build_simple_v2_view(option_text),
            ephemeral=True,
        )
        return

    if custom_id.startswith("text_confirm_"):
        card_id = custom_id.replace("text_confirm_", "", 1)
        setup = text_setups.get(card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return
        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Only the person who ran /announce can configure this.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(AnnouncementTextModal(card_id))
        return

    if custom_id.startswith("text_send_"):
        card_id = custom_id.replace("text_send_", "", 1)
        setup = text_setups.get(card_id)
        if not setup:
            await interaction.response.send_message(
                "❌ This setup session expired.", ephemeral=True
            )
            return
        if setup["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Only the person who ran /announce can configure this.",
                ephemeral=True,
            )
            return

        card_data = setup["card_data"]
        final_card = create_card(
            card_data["guild"],
            card_data["banner"],
            card_data.get("bottom_banner"),
            card_data["text"],
            card_data["tags"],
            card_data["channels"],
        )

        await interaction.response.edit_message(
            content="✅ Announcement sent!",
            view=None,
        )
        await publish_final_card(setup["root_interaction"], card_data, final_card)
        text_setups.pop(card_id, None)
        return

    # Marketplace dropdown intentionally has no action yet.
    if custom_id == "marketplace_category":
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        return


# ============================================================
# ANNOUNCE COMMAND
# ============================================================

@bot.tree.command(
    name="announce",
    description="Create a professional announcement card",
)
@has_role_or_higher("announce")
@app_commands.choices(
    add_text=[
        app_commands.Choice(name="Yes", value="yes"),
        app_commands.Choice(name="No", value="no"),
    ]
)
@app_commands.describe(
    add_text="Do you want to add announcement text?",
    banner="Upload banner image",
    bottom_banner="Upload bottom banner image",
    tags="Text below announcement",
    channel1="First button channel",
    channel2="Second button channel",
    channel3="Third button channel",
    enable_dropdown_info="Add an interactive dropdown with info only the clicker can see",
    target_channel="Optional channel to post the announcement to",
)
async def announce(
    interaction: discord.Interaction,
    add_text: app_commands.Choice[str],
    banner: Optional[discord.Attachment] = None,
    bottom_banner: Optional[discord.Attachment] = None,
    tags: Optional[str] = None,
    channel1: Optional[discord.TextChannel] = None,
    channel2: Optional[discord.TextChannel] = None,
    channel3: Optional[discord.TextChannel] = None,
    enable_dropdown_info: Optional[bool] = False,
    target_channel: Optional[discord.TextChannel] = None,
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
        and not bottom_banner
        and not tags
        and not channels
        and not enable_dropdown_info
    )

    if nothing_to_send:
        await interaction.followup.send(
            "❌ Nothing to send — add text, a banner, tags, channels, or enable the dropdown.",
            ephemeral=True,
        )
        return

    card_data = {
        "guild": interaction.guild.name if interaction.guild else "Server",
        "banner": banner.url if banner else None,
        "bottom_banner": bottom_banner.url if bottom_banner else None,
        "text": "",
        "tags": tags.replace("\\n", "\n") if tags else "",
        "channels": channels,
        "target_channel_id": target_channel.id if target_channel else None,
    }

    if wants_text:
        text_setups[card_id] = {
            "user_id": interaction.user.id,
            "card_data": card_data,
            "enable_dropdown_info": bool(enable_dropdown_info),
            "message": None,
            "root_interaction": interaction,
        }

        confirm_view = discord.ui.View(timeout=None)
        confirm_view.add_item(
            discord.ui.Button(
                label="✅ Confirm",
                style=discord.ButtonStyle.success,
                custom_id=f"text_confirm_{card_id}",
            )
        )

        try:
            msg = await interaction.followup.send(
                content="You chose to add text to this announcement. Click **Confirm** to write it.",
                view=confirm_view,
                ephemeral=True,
                wait=True,
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
            "root_interaction": interaction,
        }

        try:
            msg = await interaction.followup.send(
                content=build_setup_content([]),
                view=build_setup_view(card_id),
                ephemeral=True,
                wait=True,
            )
            dropdown_setups[card_id]["message"] = msg
        except Exception as e:
            print(f"Error sending dropdown setup view: {e}")
        return

    final_card = create_card(
        card_data["guild"],
        card_data["banner"],
        card_data.get("bottom_banner"),
        card_data["text"],
        card_data["tags"],
        card_data["channels"],
    )
    await publish_final_card(interaction, card_data, final_card)


# ============================================================
# FEEDBACK COMMAND GROUP
# ============================================================

feedback_group = app_commands.Group(
    name="feedback",
    description="Feedback commands",
)


@feedback_group.command(
    name="give",
    description="Submit feedback for a staff member",
)
@has_role_or_higher("feedback")
@app_commands.choices(
    rating=[
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
    ]
)
@app_commands.describe(
    staff="The staff member you want to give feedback to",
    rating="Rate the staff member from 0/10 to 10/10",
    feedback="Write your detailed feedback",
)
async def feedback_give(
    interaction: discord.Interaction,
    staff: discord.Member,
    rating: app_commands.Choice[str],
    feedback: str,
):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        target_channel = (
            interaction.guild.get_channel(FEEDBACK_CHANNEL_ID)
            if interaction.guild
            else None
        )
        if not target_channel:
            await interaction.followup.send(
                "❌ Feedback channel not found! Check FEEDBACK_CHANNEL_ID in bot.py.",
                ephemeral=True,
            )
            return

        view = discord.ui.LayoutView(timeout=None)
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
            accessory=discord.ui.Thumbnail(media=staff.display_avatar.url),
        )

        container.add_item(section)
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**Feedback:**\n{feedback}"))
        view.add_item(container)

        await target_channel.send(view=view)
        # Log to moderation database
        mod_db.add_modlog(interaction.guild.id, staff.id, interaction.user.id, "FEEDBACK", f"Rating: {rating.value}", feedback)
        await interaction.followup.send(
            "✅ Feedback submitted successfully!",
            ephemeral=True,
        )

    except Exception as e:
        print(f"Error in feedback command: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ An error occurred: {e}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ An error occurred: {e}", ephemeral=True
                )
        except Exception:
            pass


bot.tree.add_command(feedback_group)


# ============================================================
# SERVER INFO
# ============================================================

@bot.tree.command(
    name="serverinfo",
    description="View information about the server",
)
async def serverinfo(interaction: discord.Interaction):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Calculate stats
        total_members = guild.member_count
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
        online = len([m for m in guild.members if m.status != discord.Status.offline])
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        total_channels = text_channels + voice_channels
        roles = len(guild.roles)
        boost_level = guild.premium_tier
        boosts = guild.premium_subscription_count

        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))

        # Header
        container.add_item(discord.ui.TextDisplay("🏛️ **SERVER INFORMATION**"))
        container.add_item(discord.ui.TextDisplay(guild.name))

        container.add_item(discord.ui.Separator())

        # General
        general_text = "**GENERAL**\n"
        general_text += f"Name: {guild.name}\n"
        general_text += f"Owner: {guild.owner.mention if guild.owner else 'Unknown'}\n"
        general_text += f"Server ID: {guild.id}\n"
        general_text += f"Created: <t:{int(guild.created_at.timestamp())}:F>"
        container.add_item(discord.ui.TextDisplay(general_text))

        container.add_item(discord.ui.Separator())

        # Members
        members_text = "**MEMBERS**\n"
        members_text += f"Members: {total_members}\n"
        members_text += f"Humans: {humans}\n"
        members_text += f"Bots: {bots}\n"
        members_text += f"Online: {online}"
        container.add_item(discord.ui.TextDisplay(members_text))

        container.add_item(discord.ui.Separator())

        # Server
        server_text = "**SERVER**\n"
        server_text += f"Channels: {total_channels}\n"
        server_text += f"Roles: {roles}\n"
        server_text += f"Boost Level: {boost_level}\n"
        server_text += f"Boosts: {boosts}"
        container.add_item(discord.ui.TextDisplay(server_text))

        container.add_item(discord.ui.Separator())

        # Footer
        container.add_item(discord.ui.TextDisplay(f"Requested by {interaction.user.display_name}"))

        view.add_item(container)
        await interaction.followup.send(view=view, ephemeral=True)

    except Exception as e:
        print(f"Error in serverinfo command: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
        except Exception:
            pass


# ============================================================
# USER INFO
# ============================================================

@bot.tree.command(
    name="userinfo",
    description="View information about a user",
)
@app_commands.describe(user="The user to get information about")
async def userinfo(interaction: discord.Interaction, user: discord.Member):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Get user roles sorted by position (highest first), excluding @everyone and default colored roles (#99AAB5 or 0)
        user_roles = [
            role for role in user.roles 
            if role.name != "@everyone" and role.color.value != 0 and role.color.value != 10070709
        ]
        user_roles.sort(key=lambda r: r.position, reverse=True)
        highest_role = user_roles[0] if user_roles else None
        roles_text = ", ".join([role.mention for role in user_roles[:10]]) if user_roles else "None"
        if len(user_roles) > 10:
            roles_text += f" and {len(user_roles) - 10} more..."

        class UserInfoView(discord.ui.LayoutView):
            def __init__(self, roles_text):
                super().__init__(timeout=None)
                self.roles_text = roles_text
            
            @discord.ui.button(label="📋 Roles", style=discord.ButtonStyle.secondary)
            async def roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message(f"**Roles:**\n{self.roles_text}", ephemeral=True)

        view = UserInfoView(roles_text)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))

        # Header
        container.add_item(discord.ui.TextDisplay("👤 **USER INFORMATION**"))

        # User section with avatar
        section = discord.ui.Section(
            discord.ui.TextDisplay(
                f"@{user.name}\n"
                f"{user.display_name}\n"
                f"Status: {str(user.status).capitalize()}"
            ),
            accessory=discord.ui.Thumbnail(media=user.display_avatar.url)
        )
        container.add_item(section)

        container.add_item(discord.ui.Separator())

        # Account
        account_text = "**ACCOUNT**\n"
        account_text += f"User ID: {user.id}\n"
        account_text += f"Created: <t:{int(user.created_at.timestamp())}:F>"
        container.add_item(discord.ui.TextDisplay(account_text))

        container.add_item(discord.ui.Separator())

        # Server
        server_text = "**SERVER**\n"
        server_text += f"Joined: <t:{int(user.joined_at.timestamp())}:F>\n" if user.joined_at else "Joined: Unknown\n"
        server_text += f"Nickname: {user.nick if user.nick else 'None'}\n"
        server_text += f"Highest Role: {highest_role.mention if highest_role else 'None'}"
        container.add_item(discord.ui.TextDisplay(server_text))

        container.add_item(discord.ui.Separator())

        # Roles
        roles_section_text = "**ROLES**\n"
        roles_section_text += roles_text
        container.add_item(discord.ui.TextDisplay(roles_section_text))

        container.add_item(discord.ui.Separator())

        # Footer
        container.add_item(discord.ui.TextDisplay(f"Requested by {interaction.user.display_name}"))

        view.add_item(container)
        await interaction.followup.send(view=view, ephemeral=True)

    except Exception as e:
        print(f"Error in userinfo command: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
        except Exception:
            pass


# ============================================================
# ROLE INFO
# ============================================================

@bot.tree.command(
    name="roleinfo",
    description="View information about a role",
)
@app_commands.describe(role="The role to get information about")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        # Calculate member count
        member_count = len([member for member in guild.members if role in member.roles])

        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=discord.Color.from_rgb(37, 37, 41))

        # Header
        container.add_item(discord.ui.TextDisplay("🎭 **ROLE INFORMATION**"))

        # Role name
        container.add_item(discord.ui.TextDisplay(f"{role.mention}"))

        container.add_item(discord.ui.Separator())

        # General
        general_text = "**GENERAL**\n"
        general_text += f"Role ID: {role.id}\n"
        general_text += f"Position: {role.position}\n"
        general_text += f"Created: <t:{int(role.created_at.timestamp())}:F>"
        container.add_item(discord.ui.TextDisplay(general_text))

        container.add_item(discord.ui.Separator())

        # Members
        members_text = "**MEMBERS**\n"
        members_text += f"Member count: {member_count}"
        container.add_item(discord.ui.TextDisplay(members_text))

        # Footer
        container.add_item(discord.ui.TextDisplay(f"Requested by {interaction.user.display_name}"))

        view.add_item(container)
        await interaction.followup.send(view=view, ephemeral=True)

    except Exception as e:
        print(f"Error in roleinfo command: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)
        except Exception:
            pass


# ============================================================
# INPUT RESULTS
# ============================================================

@bot.tree.command(
    name="inputresults",
    description="Submit training or evaluation results for a user.",
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
    channel="Optional target channel to send the results card to",
)
@app_commands.choices(
    result=[
        app_commands.Choice(name="✅ Pass", value="✅ Pass"),
        app_commands.Choice(name="❌ Fail", value="❌ Fail"),
    ]
)
async def inputresults(
    interaction: discord.Interaction,
    user: discord.Member,
    spag: app_commands.Range[int, 0, 10],
    driving: app_commands.Range[int, 0, 10],
    mod_calls: app_commands.Range[int, 0, 10],
    knowledge: app_commands.Range[int, 0, 10],
    note: str,
    result: app_commands.Choice[str],
    channel: Optional[discord.TextChannel] = None,
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
        "**Trainer's overall description:**\n"
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
            ephemeral=True,
        )


# ============================================================
# LOW LETTER COMMAND (LLC) LOGS
# ============================================================

target_llc_channel_id = None


def has_llc_role():
    """Check for the configured LLC role or a higher role."""
    async def predicate(ctx: commands.Context):
        required_role_id = 1526714098706940086
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False

        if (
            ctx.author.id == ctx.guild.owner_id
            or ctx.author.guild_permissions.administrator
        ):
            return True

        target_role = ctx.guild.get_role(required_role_id)
        if not target_role:
            return False

        return ctx.author.top_role >= target_role

    return commands.check(predicate)


@bot.command(name="set_llc")
@has_llc_role()
async def set_llc(ctx: commands.Context):
    global target_llc_channel_id
    target_llc_channel_id = ctx.channel.id
    channel_name = ctx.channel.name

    try:
        db.settings.update_one(
            {"_id": "llc_channel"},
            {"$set": {"channel_id": ctx.channel.id}},
            upsert=True,
        )
    except Exception as e:
        print(f"[MongoDB Error] Could not save LLC channel: {e}")

    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    try:
        await ctx.author.send(
            f"successfully set low letter command logs in channel #{channel_name}"
        )
    except discord.Forbidden:
        pass


async def send_llc_log(
    roblox_username: str,
    roblox_id: int,
    full_command: str,
):
    global target_llc_channel_id

    channel_id = os.getenv("LLC_CHANNEL_ID")

    if not channel_id and target_llc_channel_id:
        channel_id = target_llc_channel_id

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
            f"[{roblox_username}:{roblox_id}]({roblox_profile_url}) "
            f"used the command `{full_command}`\n\n"
            f"-# AZRP Command Logs | {date_str}, {time_str}"
        )

        container.add_item(discord.ui.TextDisplay(content))
        view.add_item(container)

        for attempt in range(3):
            try:
                await target_channel.send(view=view)
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 5)
                    print(
                        f"[Rate Limit] Discord 429 hit. Retrying in {retry_after}s..."
                    )
                    await asyncio.sleep(retry_after)
                else:
                    print(f"[Discord Error] Could not send LLC log: {e}")
                    break


# ============================================================
# ER:LC COMMAND LOG POLLING
# ============================================================

_erlc_seen_commands = set()
_erlc_command_poll_first_run = True
ERLC_COMMAND_POLL_INTERVAL = 15


async def poll_erlc_command_logs():
    global _erlc_seen_commands, _erlc_command_poll_first_run

    await bot.wait_until_ready()

    erlc_client = ERLCClient()
    if not erlc_client.configured:
        print("[ERLC] Command log polling disabled — ERLC_SERVER_KEY is not set.")
        return

    print(f"[ERLC] Polling command logs every {ERLC_COMMAND_POLL_INTERVAL}s...")

    while not bot.is_closed():
        try:
            data = await asyncio.to_thread(
                erlc_client.get_server,
                CommandLogs=True,
            )
            logs = data.get("CommandLogs", []) or []

            if _erlc_command_poll_first_run:
                _erlc_seen_commands = {
                    (
                        log.get("Player"),
                        log.get("Timestamp"),
                        log.get("Command"),
                    )
                    for log in logs
                }
                _erlc_command_poll_first_run = False
            else:
                for log in logs:
                    key = (
                        log.get("Player"),
                        log.get("Timestamp"),
                        log.get("Command"),
                    )
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
                                roblox_id=(
                                    int(roblox_id_str)
                                    if roblox_id_str.isdigit()
                                    else 0
                                ),
                                full_command=command_text,
                            )
                        except Exception as e:
                            print(f"[ERLC] Error forwarding command log: {e}")

                if len(_erlc_seen_commands) > 1000:
                    _erlc_seen_commands = set(
                        list(_erlc_seen_commands)[-500:]
                    )

        except ERLCAPIError as e:
            print(f"[ERLC] Error polling command logs: {e}")
        except Exception as e:
            print(f"[ERLC] Unexpected error polling command logs: {e}")

        await asyncio.sleep(ERLC_COMMAND_POLL_INTERVAL)


# ============================================================
# REGISTER SESSION COMMANDS
# ============================================================

setup_session_commands(bot, has_role_or_higher)


# ============================================================
# FLASK WEB SERVER FOR RENDER / ER:LC WEBHOOKS
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


@app.route("/erlc/events", methods=["POST"])
def erlc_events():
    """Receive ER:LC webhook data without exposing the server key."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return "Invalid JSON", 400

    event_type = payload.get("EventType") or payload.get("event")
    data = payload.get("Data") or payload.get("data") or {}

    # Keep support for payloads that contain a command directly.
    if event_type == "CommandLog" or "Command" in data:
        player_info = data.get("Player", {})
        if not isinstance(player_info, dict):
            player_info = {}

        username = player_info.get("Name") or data.get("PlayerName", "Unknown")
        roblox_id = player_info.get("UserId") or data.get("PlayerId", 0)
        command_text = data.get("Command") or data.get("command_text", "")

        if command_text and bot.is_ready():
            try:
                asyncio.run_coroutine_threadsafe(
                    send_llc_log(
                        roblox_username=username,
                        roblox_id=int(roblox_id),
                        full_command=command_text,
                    ),
                    bot.loop,
                )
            except Exception as e:
                print(f"[ERLC WEBHOOK] Failed to queue LLC log: {e}")

    return "OK", 200


@app.route("/erlc/status")
def erlc_status():
    return {
        "configured": bool(ERLC_SERVER_KEY),
        "webhook_endpoint": "/erlc/events",
    }


def run_web():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )


# ============================================================
# START BOT
# ============================================================

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("TOKEN environment variable is not set on Render.")

    threading.Thread(target=run_web, daemon=True).start()

    if ERLC_SERVER_KEY:
        print("[ERLC] Server key configured successfully.")
        print("[ERLC] Event webhook endpoint: /erlc/events")
    else:
        print("[ERLC] WARNING: ERLC_SERVER_KEY is not configured.")

    try:
        print("[Discord] Logging in...")
        bot.run(TOKEN)
    except discord.HTTPException as e:
        if e.status == 429:
            print(
                "[Rate Limit] Currently blocked by Discord API (429). "
                "Waiting 60 seconds..."
            )
            time.sleep(60)
        else:
            print(f"[Discord Error] {e}")
    except Exception as e:
        print(f"[Fatal Error] {e}")
        traceback.print_exc()
