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
ERLC_STATS_UPDATE_INTERVAL: int = 120  # Increased from 60 to 120 seconds to reduce API load
cached_erlc_stats = {
    "players": "0/50",
    "queue": "0",
    "staff": "0",
    "last_updated_timestamp": int(datetime.now().timestamp())
}

# Tracks the currently "live" Session Start message (channel_id, message_id)
# so the background updater can edit it in place with fresh stats every
# ERLC_STATS_UPDATE_INTERVAL seconds. Cleared when a new Session Start is
# posted (old one stops updating) or when Session End is pressed.
active_session_start_message = None

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

def fetch_erlc_stats():
    """Fetch current server stats from ERLC API (synchronous)."""
    try:
        from erlc_api import ERLCClient
        import os
        
        erlc_client = ERLCClient()
        server_key = os.getenv("ERLC_SERVER_KEY", "")
        
        print(f"[ERLC STATS] Server key configured: {bool(server_key)}")
        
        if not erlc_client.configured:
            print("[ERLC STATS] ERLC client not configured - check ERLC_SERVER_KEY")
            return None
        
        print("[ERLC STATS] Fetching stats from ERLC API...")
        # Staff=True gives the Admins/Mods/Helpers breakdown, Queue=True
        # gives the queue array. CurrentPlayers/MaxPlayers are always
        # present on the base response, no query param needed for those.
        data = erlc_client.get_server(Staff=True, Queue=True)
        
        print(f"[ERLC STATS] Full API Response: {data}")  # Debug logging
        
        # Player count — CurrentPlayers/MaxPlayers are top-level integers
        # on the response, not nested under a "Players" key.
        current_players = data.get("CurrentPlayers", 0)
        max_players = data.get("MaxPlayers", 0)
        players_text = f"{current_players}/{max_players}"
        
        # Queue — an array of player IDs waiting to join; count = length.
        queue_list = data.get("Queue") or []
        queue_count = str(len(queue_list))
        
        # Staff — {"Admins": {...}, "Mods": {...}, "Helpers": {...}}, each
        # mapping Roblox ID -> username. Total staff = sum of all three.
        staff = data.get("Staff") or {}
        staff_count = str(
            len(staff.get("Admins") or {}) +
            len(staff.get("Mods") or {}) +
            len(staff.get("Helpers") or {})
        )
        
        print(f"[ERLC STATS] Final stats - Players: {players_text}, Queue: {queue_count}, Staff: {staff_count}")
        
        return {
            "players": players_text,
            "queue": queue_count,
            "staff": staff_count
        }
    except Exception as e:
        print(f"[ERLC STATS] Error fetching stats: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_erlc_stats():
    """Update cached ERLC stats (synchronous)."""
    global cached_erlc_stats
    try:
        print("[ERLC STATS] Starting stats update...")
        stats = fetch_erlc_stats()
        if stats:
            cached_erlc_stats.update(stats)
            # Update the timestamp to current time for Discord timestamp
            cached_erlc_stats["last_updated_timestamp"] = int(datetime.now().timestamp())
            print(f"[ERLC STATS] Stats updated successfully: {stats}")
        else:
            print("[ERLC STATS] Stats update failed - no data returned")
    except Exception as e:
        print(f"[ERLC STATS] Error updating stats: {e}")
        import traceback
        traceback.print_exc()

async def erlc_stats_updater(bot: commands.Bot):
    """Background task to update ERLC stats every minute."""
    print("[ERLC STATS] Stats updater task started, waiting for bot to be ready...")
    await bot.wait_until_ready()
    print("[ERLC STATS] Bot is ready, starting stats update loop...")
    while not bot.is_closed():
        print(f"[ERLC STATS] Running stats update cycle at {datetime.now()}")
        # Run the synchronous function in a thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, update_erlc_stats)
        
        # Only refresh if there's an active session message
        if active_session_start_message:
            await refresh_active_session_message(bot)
        else:
            print("[ERLC STATS] No active session message to refresh, skipping")
        
        print(f"[ERLC STATS] Sleeping for {ERLC_STATS_UPDATE_INTERVAL} seconds...")
        await asyncio.sleep(ERLC_STATS_UPDATE_INTERVAL)
    print("[ERLC STATS] Stats updater task stopped")


async def refresh_active_session_message(bot: commands.Bot):
    """Edit the currently posted Session Start message in place with the
    freshly-updated stats/timestamp, so the counters and the 'Last updated'
    line actually change instead of sitting frozen at whatever they were
    when the message was first sent."""
    global active_session_start_message

    if not active_session_start_message:
        return

    channel = bot.get_channel(active_session_start_message["channel_id"])
    if not channel:
        print("[ERLC STATS] Tracked session channel not found — clearing.")
        active_session_start_message = None
        return

    try:
        message = await channel.fetch_message(active_session_start_message["message_id"])
    except (discord.NotFound, discord.Forbidden):
        print("[ERLC STATS] Tracked session message no longer exists — clearing.")
        active_session_start_message = None
        return
    except Exception as e:
        print(f"[ERLC STATS] Error fetching tracked session message: {e}")
        return

    new_view = create_session_card(
        banner_url=SESSION_START_BANNER,
        text=SESSION_START_INFO_TEXT,
        color=SESSION_START_COLOUR,
        button_url=SESSION_START_BUTTON_URL,
        button_label="Quick Join",
        server_details=SESSION_START_SERVER_TEXT,
        bottom_banner_url=SESSION_START_BOTTOM_BANNER,
        include_stats=True
    )

    try:
        await message.edit(view=new_view)
        print("[ERLC STATS] Refreshed live session panel with new stats.")
    except discord.HTTPException as e:
        if e.status == 429:
            retry_after = getattr(e, 'retry_after', 5)
            print(f"[ERLC STATS] Rate limited on message edit. Waiting {retry_after}s...")
            await asyncio.sleep(retry_after)
            # Skip this update cycle, will try again next minute
        else:
            print(f"[ERLC STATS] HTTP error editing tracked session message: {e.status} - {e.text}")
    except Exception as e:
        print(f"[ERLC STATS] Error editing tracked session message: {e}")


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
                "**Players**\n-# How many players are in-game",
                accessory=discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=cached_erlc_stats['players'],
                    disabled=True
                )
            )
        )

        # Queue Section with Button Accessory
        container.add_item(
            discord.ui.Section(
                "**Queue**\n-# How many players are waiting to join",
                accessory=discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=cached_erlc_stats['queue'],
                    disabled=True
                )
            )
        )

        # Staff Section with Button Accessory & Last Updated Subtext
        container.add_item(
            discord.ui.Section(
                f"**Staff**\n-# How many staff are in-game moderating\n\n-# Last updated: <t:{cached_erlc_stats['last_updated_timestamp']}:R>",
                accessory=discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=cached_erlc_stats['staff'],
                    disabled=True
                )
            )
        )

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
            message = await channel.send(view=card_view)
            await interaction.followup.send("✅ Session update posted!", ephemeral=True)
            return message
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to send messages in target channel.",
                ephemeral=True
            )
            return None
        except Exception as e:
            await interaction.followup.send(f"❌ Error sending card: {e}", ephemeral=True)
            return None

    @discord.ui.button(label="Session Start", style=discord.ButtonStyle.success, custom_id="session_panel:start")
    async def session_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        global active_session_start_message

        # Refresh the cache first so the very first post already shows live
        # numbers, instead of waiting up to 60s for the background updater.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, update_erlc_stats)

        message = await self.send_session_card(
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
        if message:
            active_session_start_message = {
                "channel_id": message.channel.id,
                "message_id": message.id
            }

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
        global active_session_start_message
        active_session_start_message = None
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