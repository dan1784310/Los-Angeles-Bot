import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime

# ==========================================
# CONFIGURATION SECTION
# ==========================================

SESSION_CHANNEL_ID: int = 1528497650595270707  # Target channel ID
REGULATIONS_CHANNEL_ID: int = 1526890579080773693  # Replace with actual regulations channel ID

# Shared Universal Assets
GLOBAL_BANNER_URL: str = "https://i.postimg.cc/rpjqr24b/azrp-sessions-banner.jpg"
GLOBAL_BOTTOM_BANNER_URL: str = "https://cdn.imageurlgenerator.com/uploads/85ff6f6b-754f-4988-b505-56a171cef43b.png"
GLOBAL_RGB_COLOR: discord.Color = discord.Color.from_rgb(37, 37, 41)
GLOBAL_JOIN_URL: str = "https://erlc.gg/join/ypOye"

# Server Information Configuration
SERVER_CODE: str = "ypOye"
SERVER_NAME: str = "Arizona State Roleplay I Realistic I New"
SERVER_OWNER: str = "Certified_Pro02"

# ERLC Stats Configuration
ERLC_STATS_UPDATE_INTERVAL: int = 60  # Update every 60 seconds
cached_erlc_stats = {
    "players": "0/50",
    "queue": "0",
    "staff": "0",
    "last_updated": "Just now"
}

# --- SESSION START CONFIG ---
SESSION_START_BANNER: str = GLOBAL_BANNER_URL
SESSION_START_BOTTOM_BANNER: str = GLOBAL_BOTTOM_BANNER_URL
SESSION_START_COLOUR: discord.Color = GLOBAL_RGB_COLOR
SESSION_START_BUTTON_URL: str = GLOBAL_JOIN_URL

SESSION_START_INFO_TEXT: str = (
    "## Information\n"
    "> Welcome to the sessions channel, here we'll post notifications about our session "
    "including session start-ups, shutdowns, breaks and low players. Make sure to read "
    f"up on all our guidelines in <#{REGULATIONS_CHANNEL_ID}> before joining our session."
)

SESSION_START_SERVER_TEXT: str = (
    f"> **Server Code:** `{SERVER_CODE}`\n"
    f"> **Server Name:** `{SERVER_NAME}`\n"
    f"> **Server Owner:** `{SERVER_OWNER}`"
)

# --- FULL PLAYERS ---
FULL_PLAYERS_BANNER: str = GLOBAL_BANNER_URL
FULL_PLAYERS_BOTTOM_BANNER: str = GLOBAL_BOTTOM_BANNER_URL
FULL_PLAYERS_TEXT: str = "## Server Full\nThe server is currently full! Please wait in queue or check back later."
FULL_PLAYERS_COLOUR: discord.Color = GLOBAL_RGB_COLOR

# --- LOW PLAYERS ---
LOW_PLAYERS_BANNER: str = GLOBAL_BANNER_URL
LOW_PLAYERS_BOTTOM_BANNER: str = GLOBAL_BOTTOM_BANNER_URL
LOW_PLAYERS_TEXT: str = "## Low Player Count\nThe in-game server is getting low on members. Join up for some great roleplays! If the player count does not go up, we may have to close the session."
LOW_PLAYERS_COLOUR: discord.Color = GLOBAL_RGB_COLOR

# --- SESSION END ---
SESSION_END_BANNER: str = GLOBAL_BANNER_URL
SESSION_END_BOTTOM_BANNER: str = GLOBAL_BOTTOM_BANNER_URL
SESSION_END_TEXT: str = "## Session Ended\nThe session has officially ended. Thank you to everyone who participated! You are welcome to stay if you want!"
SESSION_END_COLOUR: discord.Color = GLOBAL_RGB_COLOR


# ==========================================
# ERLC STATS SECTION
# ==========================================

async def fetch_erlc_stats():
    """Fetch current server stats from ERLC API."""
    try:
        from erlc_api import ERLCClient
        erlc_client = ERLCClient()
        if not erlc_client.configured:
            return None
        
        # Fetch server info with players and staff
        data = erlc_client.get_server(Players=True, Staff=True)
        
        print(f"[ERLC STATS] API Response: {data}")  # Debug logging
        
        # Extract relevant information
        players = data.get("Players", {})
        staff = data.get("Staff", {})
        
        # Format player count (current/max)
        current_players = players.get("current", 0)
        max_players = players.get("max", 50)
        players_text = f"{current_players}/{max_players}"
        
        # Get queue count (typically players waiting to join)
        queue_count = str(players.get("queue", 0))
        
        # Get staff count - handle different possible data structures
        if isinstance(staff, list):
            staff_count = str(len(staff))
        elif isinstance(staff, dict):
            staff_count = str(staff.get("count", len(staff)))
        else:
            staff_count = "0"
        
        print(f"[ERLC STATS] Staff data type: {type(staff)}, Staff count: {staff_count}")  # Debug logging
        
        return {
            "players": players_text,
            "queue": queue_count,
            "staff": staff_count
        }
    except Exception as e:
        print(f"[ERLC STATS] Error fetching stats: {e}")
        return None

async def update_erlc_stats():
    """Update cached ERLC stats."""
    global cached_erlc_stats
    try:
        stats = await fetch_erlc_stats()
        if stats:
            cached_erlc_stats.update(stats)
            # Calculate time ago
            now = datetime.now()
            time_diff = now - cached_erlc_stats.get("last_update_time", now)
            minutes_ago = int(time_diff.total_seconds() / 60)
            if minutes_ago == 0:
                cached_erlc_stats["last_updated"] = "Just now"
            elif minutes_ago == 1:
                cached_erlc_stats["last_updated"] = "1 minute ago"
            else:
                cached_erlc_stats["last_updated"] = f"{minutes_ago} minutes ago"
            cached_erlc_stats["last_update_time"] = now
    except Exception as e:
        print(f"[ERLC STATS] Error updating stats: {e}")

async def erlc_stats_updater(bot: commands.Bot):
    """Background task to update ERLC stats every minute."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        await update_erlc_stats()
        await asyncio.sleep(ERLC_STATS_UPDATE_INTERVAL)


# ==========================================
# V2 CARD BUILDER HELPER
# ==========================================

def create_session_card(
    banner_url: str,
    text: str,
    color: discord.Color,
    button_url: str = None,
    button_label: str = "Quick Join",
    server_details: str = None,
    bottom_banner_url: str = None,
    include_stats: bool = False
) -> discord.ui.LayoutView:
    """Builds a Components V2 LayoutView card."""
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=color)

    # 1. Top Media Banner
    if banner_url and banner_url.startswith("http"):
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=banner_url)
            )
        )
        container.add_item(discord.ui.Separator())

    # 2. Main Info Section
    container.add_item(discord.ui.TextDisplay(text))

    # 3. Server Details Section
    if server_details:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(server_details))

    # 4. ERLC Stats Section (only for Session Start)
    if include_stats:
        container.add_item(discord.ui.Separator())
        
        # Players Section with Button Accessory
        container.add_item(
            discord.ui.Section(
                "**Players**\nHow many players are in-game",
                accessory=discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=cached_erlc_stats['players'],
                    disabled=True
                )
            )
        )
        container.add_item(discord.ui.Separator())

        # Queue Section with Button Accessory
        container.add_item(
            discord.ui.Section(
                "**Queue**\nHow many players are waiting to join",
                accessory=discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=cached_erlc_stats['queue'],
                    disabled=True
                )
            )
        )
        container.add_item(discord.ui.Separator())

        # Staff Section with Button Accessory & Last Updated Subtext
        container.add_item(
            discord.ui.Section(
                f"**Staff**\nHow many staff are in-game moderating\n-# Last updated: {cached_erlc_stats['last_updated']}",
                accessory=discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=cached_erlc_stats['staff'],
                    disabled=True
                )
            )
        )
        container.add_item(discord.ui.Separator())

    # 5. Quick Join Button Section (Separator above, no bottom banner)
    if button_url:
        container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(
            discord.ui.Button(
                label=button_label,
                style=discord.ButtonStyle.link,
                url=button_url
            )
        )
        container.add_item(row)

    # 6. Bottom Media Banner
    if bottom_banner_url and bottom_banner_url.startswith("http"):
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=bottom_banner_url)
            )
        )

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
        button_url: str = None,
        button_label: str = "Quick Join",
        server_details: str = None,
        bottom_banner_url: str = None,
        include_stats: bool = False
    ):
        # Deferred immediately to prevent a 10062 Unknown Interaction timeout error
        await interaction.response.defer(ephemeral=True)

        channel = interaction.guild.get_channel(SESSION_CHANNEL_ID)
        if not channel:
            await interaction.followup.send(
                "❌ Session channel not found! Check `SESSION_CHANNEL_ID`.",
                ephemeral=True
            )
            return

        card_view = create_session_card(
            banner_url=banner_url,
            text=text,
            color=color,
            button_url=button_url,
            button_label=button_label,
            server_details=server_details,
            bottom_banner_url=bottom_banner_url,
            include_stats=include_stats
        )

        try:
            await channel.send(view=card_view)
            await interaction.followup.send("✅ Session update posted!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to send messages in target channel.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error sending card: {e}", ephemeral=True)

    @discord.ui.button(label="Session Start", style=discord.ButtonStyle.success, custom_id="session_panel:start")
    async def session_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction=interaction,
            banner_url=SESSION_START_BANNER,
            text=SESSION_START_INFO_TEXT,
            color=SESSION_START_COLOUR,
            button_url=SESSION_START_BUTTON_URL,
            button_label="Quick Join",
            server_details=SESSION_START_SERVER_TEXT,
            bottom_banner_url=SESSION_START_BOTTOM_BANNER,
            include_stats=True
        )

    @discord.ui.button(label="Full Players", style=discord.ButtonStyle.primary, custom_id="session_panel:full")
    async def full_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction=interaction,
            banner_url=FULL_PLAYERS_BANNER,
            text=FULL_PLAYERS_TEXT,
            color=FULL_PLAYERS_COLOUR,
            bottom_banner_url=FULL_PLAYERS_BOTTOM_BANNER
        )

    @discord.ui.button(label="Session End", style=discord.ButtonStyle.danger, custom_id="session_panel:end")
    async def session_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction=interaction,
            banner_url=SESSION_END_BANNER,
            text=SESSION_END_TEXT,
            color=SESSION_END_COLOUR,
            bottom_banner_url=SESSION_END_BOTTOM_BANNER
        )

    @discord.ui.button(label="Low Players", style=discord.ButtonStyle.secondary, custom_id="session_panel:low")
    async def low_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_session_card(
            interaction=interaction,
            banner_url=LOW_PLAYERS_BANNER,
            text=LOW_PLAYERS_TEXT,
            color=LOW_PLAYERS_COLOUR,
            bottom_banner_url=LOW_PLAYERS_BOTTOM_BANNER
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
        
        panel_layout = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=GLOBAL_RGB_COLOR)
        container.add_item(
            discord.ui.TextDisplay("## Session Management Panel\nListed below are the buttons you can use to send the required session messages.")
        )
        container.add_item(discord.ui.Separator())
        
        button_row = discord.ui.ActionRow()
        for item in panel_view.children:
            button_row.add_item(item)
        container.add_item(button_row)
        
        panel_layout.add_item(container)
        
        await interaction.response.send_message(view=panel_layout, ephemeral=True)


# Function to start ERLC stats updater (call this from bot.py on_ready)
def start_erlc_stats_updater(bot: commands.Bot):
    """Start the ERLC stats updater task. Call this from bot.py on_ready."""
    asyncio.create_task(erlc_stats_updater(bot))