import discord
from discord.ext import commands
from discord import app_commands

# ==========================================
# CONFIGURATION SECTION
# Customize RGB colors, text, and banner URLs
# ==========================================

SESSION_CHANNEL_ID: int = 1528497650595270707  # Replace with your actual channel ID

# Shared Universal Assets
GLOBAL_BANNER_URL: str = "https://cdn.discordapp.com/attachments/1526890579080773693/1528739376044048414/bg.png?ex=6a63597d&is=6a6207fd&hm=163d8a7c3eb83e7b77cad933794b56e18439098546a7f4ab3a0547177eb05ea4&"
GLOBAL_RGB_COLOR: discord.Color = discord.Color.from_rgb(37, 37, 41)
GLOBAL_JOIN_URL: str = "https://www.roblox.com/games/2534724415/Emergency-Response-Liberty-County"

# --- SESSION START ---
SESSION_START_BANNER: str = GLOBAL_BANNER_URL
SESSION_START_TEXT: str = "## 🟢 Session Starting!\nThe in-game server is now open! Join up through the code ypOye or the button below. We are excited to welcome you in!"
SESSION_START_COLOUR: discord.Color = GLOBAL_RGB_COLOR
SESSION_START_BUTTON_URL: str = GLOBAL_JOIN_URL

# --- FULL PLAYERS ---
FULL_PLAYERS_BANNER: str = GLOBAL_BANNER_URL
FULL_PLAYERS_TEXT: str = "## ⛔ Server Full\nThe server is currently full! Please wait in queue or check back later."
FULL_PLAYERS_COLOUR: discord.Color = GLOBAL_RGB_COLOR

# --- LOW PLAYERS ---
LOW_PLAYERS_BANNER: str = GLOBAL_BANNER_URL
LOW_PLAYERS_TEXT: str = "## ⚠️ Low Player Count\nThe in-game server is getting low on members. Join up for some great roleplays! If the player count does not go up, we may have to close the session."
LOW_PLAYERS_COLOUR: discord.Color = GLOBAL_RGB_COLOR

# --- SESSION END ---
SESSION_END_BANNER: str = GLOBAL_BANNER_URL
SESSION_END_TEXT: str = "## 🔴 Session Ended\nThe session has officially ended. Thank you to everyone who participated! You are welcome to stay if you want!"
SESSION_END_COLOUR: discord.Color = GLOBAL_RGB_COLOR


# ==========================================
# V2 CARD BUILDER HELPER
# ==========================================

def create_session_card(
    banner_url: str,
    text: str,
    color: discord.Color,
    button_url: str = None
) -> discord.ui.LayoutView:
    """Builds a Components V2 LayoutView card with custom RGB container accents."""
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=color)

    # Add media banner if provided
    if banner_url and banner_url.startswith("http"):
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=banner_url)
            )
        )
        container.add_item(discord.ui.Separator())

    # Text Display
    container.add_item(discord.ui.TextDisplay(text))

    # Join link button (optional, used for Session Start)
    if button_url:
        row = discord.ui.ActionRow()
        row.add_item(
            discord.ui.Button(
                label="Join Session",
                style=discord.ButtonStyle.link,
                url=button_url
            )
        )
        container.add_item(row)

    view.add_item(container)
    return view


# ==========================================
# SESSION CONTROL PANEL (PERSISTENT VIEW)
# ==========================================

class SessionPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def send_session_card(
        self,
        interaction: discord.Interaction,
        banner_url: str,
        text: str,
        color: discord.Color,
        button_url: str = None
    ):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.guild.get_channel(SESSION_CHANNEL_ID)
        if not channel:
            await interaction.followup.send(
                "❌ Session channel not found! Check `SESSION_CHANNEL_ID`.",
                ephemeral=True
            )
            return

        card_view = create_session_card(banner_url, text, color, button_url)

        try:
            # Use a temporary webhook so V2 components send directly into the channel cleanly
            webhook = await channel.create_webhook(name="Session Manager")
            await webhook.send(view=card_view)
            await webhook.delete()

            await interaction.followup.send("✅ Session update posted!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to create/send webhooks in the target channel.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error sending card: {e}", ephemeral=True)

    @discord.ui.button(label="Session Start", style=discord.ButtonStyle.success, custom_id="session_panel:start")
    async def session_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction,
            SESSION_START_BANNER,
            SESSION_START_TEXT,
            SESSION_START_COLOUR,
            SESSION_START_BUTTON_URL
        )

    @discord.ui.button(label="Full Players", style=discord.ButtonStyle.primary, custom_id="session_panel:full")
    async def full_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction,
            FULL_PLAYERS_BANNER,
            FULL_PLAYERS_TEXT,
            FULL_PLAYERS_COLOUR
        )

    @discord.ui.button(label="Session End", style=discord.ButtonStyle.danger, custom_id="session_panel:end")
    async def session_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction,
            SESSION_END_BANNER,
            SESSION_END_TEXT,
            SESSION_END_COLOUR
        )

    @discord.ui.button(label="Low Players", style=discord.ButtonStyle.secondary, custom_id="session_panel:low")
    async def low_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction,
            LOW_PLAYERS_BANNER,
            LOW_PLAYERS_TEXT,
            LOW_PLAYERS_COLOUR
        )


# ==========================================
# COMMAND REGISTRATION SETUP
# ==========================================

def setup_session_commands(bot: commands.Bot, has_role_or_higher):

    @bot.tree.command(
        name="session_panel",
        description="Deploy the interactive session management panel"
    )
    @has_role_or_higher("session_panel")
    async def session_panel(interaction: discord.Interaction):
        panel_view = SessionPanelView()
        
        # Build panel interface using V2 Container
        panel_layout = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(
            accent_colour=GLOBAL_RGB_COLOR
        )
        container.add_item(
            discord.ui.TextDisplay("## Session Management Panel\nListed below are the buttons you can use to send the required session messages.")
        )
        container.add_item(discord.ui.Separator())
        
        # Add the 4 action buttons to the panel container in exact sequence
        button_row = discord.ui.ActionRow()
        for item in panel_view.children:
            button_row.add_item(item)
        container.add_item(button_row)
        
        panel_layout.add_item(container)
        
        await interaction.response.send_message(view=panel_layout, ephemeral=True)
