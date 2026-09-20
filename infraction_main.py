"""
Infraction System Module
Contains the infraction slash command, card display functionality, and live bot control proxy.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import asyncio

from moderation_database import db as mod_db


# ==========================================
# INFRACTION VIEW SYSTEM
# ==========================================




class InfractionDetailButton(discord.ui.Button):
    """Button to show detailed infraction information."""
    
    def __init__(self, message_id: Optional[int], channel_id: int, index: int, user: discord.Member, infraction_data: dict):
        super().__init__(
            label=f"View",
            style=discord.ButtonStyle.secondary,
            custom_id=f"infraction_detail_{user.id}_{index}"
        )
        self.message_id = message_id
        self.channel_id = channel_id
        self.index = index
        self.user = user
        self.infraction_data = infraction_data
    
    async def callback(self, interaction: discord.Interaction):
        try:
            target_message = None
            
            # First try to fetch from the specific channel if we have a message_id
            if self.message_id and self.message_id != 0:
                target_channel = interaction.guild.get_channel(self.channel_id)
                if target_channel:
                    try:
                        target_message = await target_channel.fetch_message(self.message_id)
                        if target_message and target_message.embeds:
                            actual_embed = target_message.embeds[0]
                            await interaction.response.send_message(embed=actual_embed, ephemeral=True)
                            return
                    except Exception as e:
                        print(f"[INFRACTION] Could not fetch message from specific channel: {e}")
            
            # If not found, search through the server for the infraction message
            print(f"[INFRACTION] Searching server for infraction message for user {self.user.id}")
            
            # Search through likely channels (infraction channel and moderation channels)
            channels_to_search = []
            
            # Add the infraction channel
            infraction_channel = interaction.guild.get_channel(INFRACTION_CHANNEL_ID)
            if infraction_channel:
                channels_to_search.append(infraction_channel)
            
            # Add channels with "infraction", "moderation", "deleted", "logs", "audit" in the name (limit to 8 to avoid rate limits)
            for channel in interaction.guild.text_channels:
                if len(channels_to_search) >= 8:  # Limit search to 8 channels max
                    break
                channel_lower = channel.name.lower()
                if any(keyword in channel_lower for keyword in ["infraction", "moderation", "deleted", "logs", "audit", "message-log"]):
                    if channel not in channels_to_search:
                        channels_to_search.append(channel)
            
            # Search through these channels for messages mentioning the user
            action = self.infraction_data.get("action", "")
            created_at = self.infraction_data.get("created_at", 0)
            
            for channel in channels_to_search:
                try:
                    # Search recent messages in the channel (limit to 50 to avoid rate limits)
                    async for message in channel.history(limit=50):
                        # Check if message is an embed with staff mention
                        if message.embeds:
                            embed_desc = str(message.embeds[0].description) if message.embeds[0].description else ""
                            if str(self.user.id) in embed_desc or str(self.user.id) in message.content:
                                # Check if it matches the action type
                                if action.lower() in embed_desc.lower() or action.lower() in message.content.lower():
                                    actual_embed = message.embeds[0]
                                    await interaction.response.send_message(embed=actual_embed, ephemeral=True)
                                    print(f"[INFRACTION] Found infraction message in channel {channel.name}")
                                    return
                        
                        # Also check if message mentions the user in content (for log channels)
                        if str(self.user.id) in message.content and action.lower() in message.content.lower():
                            # Try to reconstruct embed from message content if possible
                            if message.embeds:
                                actual_embed = message.embeds[0]
                                await interaction.response.send_message(embed=actual_embed, ephemeral=True)
                                print(f"[INFRACTION] Found infraction message (via content) in channel {channel.name}")
                                return
                            
                except Exception as e:
                    print(f"[INFRACTION] Error searching channel {channel.name}: {e}")
                    continue
            
            # If still not found, use Components V2 fallback with stored data
            print(f"[INFRACTION] Could not find original message in server search, using stored data")
            
            # Check if this might be a deleted message scenario
            if not self.message_id or self.message_id == 0:
                fallback_note = "*Original message not available (likely deleted)*"
            else:
                fallback_note = "*Original message not found in server search (may be deleted)*"
            
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(
                accent_colour=discord.Color.from_rgb(37, 37, 41)
            )
            
            action = self.infraction_data.get("action", "Unknown")
            reason = self.infraction_data.get("reason", "No reason provided")
            notes = self.infraction_data.get("notes", "N/A")
            moderator_id = self.infraction_data.get("moderator_id")
            created_at = self.infraction_data.get("created_at")
            
            moderator = interaction.guild.get_member(moderator_id) if moderator_id else None
            moderator_mention = moderator.mention if moderator else f"<@{moderator_id}>"
            
            content = f"### Infraction #{self.index + 1}\n\n"
            content += f"**Action:** {action}\n"
            content += f"**Reason:** {reason}\n"
            content += f"**Notes:** {notes}\n"
            content += f"**Issued By:** {moderator_mention}\n"
            
            if created_at:
                timestamp = int(created_at)
                content += f"**Issued At:** <t:{timestamp}:F>\n"
            
            content += f"\n{fallback_note}"
            
            container.add_item(discord.ui.TextDisplay(content))
            view.add_item(container)
            
            await interaction.response.send_message(view=view, ephemeral=True)
                
        except Exception as e:
            print(f"[INFRACTION] Error loading infraction details: {e}")
            await interaction.response.send_message(f"❌ Error loading infraction details: {e}", ephemeral=True)


# ==========================================
# CONFIGURATION
# ==========================================

INFRACTION_ACTIONS = [
    "Activity Notice",
    "Verbal Warning", 
    "Warning",
    "Strike",
    "Demotion",
    "Termination",
    "Staff Blacklist",
    "Under Investigation",
    "Suspension"
]

INFRACTION_ROLE_ID = 1539201630161993728
INFRACTION_CHANNEL_ID = 1526898975704350822
VOID_ROLE_ID = 1527050504733986987
MESSAGE_ROLE_ID = 1527055221098811433
INFRACTIONS_VIEW_ROLE_ID = 1539201630161993728  # Role ID for viewing infractions


def _can_issue_infraction(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return True

    required_role = interaction.guild.get_role(INFRACTION_ROLE_ID)
    if not required_role:
        return False

    return interaction.user.top_role >= required_role


# ==========================================
# INFRACTION COG
# ==========================================

class VoidButton(discord.ui.View):
    """Button view for voiding infractions."""
    
    def __init__(self, message_id: int, channel_id: int, void_role_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.channel_id = channel_id
        self.void_role_id = void_role_id
    
    @discord.ui.button(label="Void Infraction", style=discord.ButtonStyle.danger, custom_id="void_infraction_button")
    async def void_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has the void role or higher
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        void_role = interaction.guild.get_role(self.void_role_id)
        if not void_role or interaction.user.top_role < void_role:
            await interaction.response.send_message("❌ You don't have permission to void this infraction.", ephemeral=True)
            return
        
        target_channel = interaction.guild.get_channel(self.channel_id)
        if not target_channel:
            await interaction.response.send_message("❌ Could not find the infraction channel.", ephemeral=True)
            return
        
        try:
            target_message = await target_channel.fetch_message(self.message_id)
            if not target_message.embeds:
                await interaction.response.send_message("❌ This message doesn't contain an embed.", ephemeral=True)
                return
            
            embed = target_message.embeds[0]
            embed.title = f"Voided by @{interaction.user.display_name}"
            embed.color = discord.Color.red()
            
            await target_message.edit(embed=embed, view=None)  # Remove the button after voiding
            await interaction.response.send_message("✅ Successfully voided infraction.", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error voiding infraction: {e}", ephemeral=True)


class InfractionSystem(commands.Cog):
    """Main infraction system cog with control proxy capabilities."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Maps user_id -> { "control_channel_id": int, "target_channel_id": int }
        self.active_proxies: Dict[int, dict] = {}

    # ==========================================
    # CONTROL CHANNEL LISTENER
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for controller messages, triggers bot typing, and forwards content."""
        if message.author.bot or not message.guild:
            return

        clean_content = message.content.strip().lower()

        # Ignore state toggles and command prefixes so they run normally
        if clean_content.startswith("!m") or clean_content.startswith("!reply"):
            return

        # Check if the author has an active proxy session set up
        if message.author.id in self.active_proxies:
            session = self.active_proxies[message.author.id]

            # Only process messages typed inside the designated control channel
            if message.channel.id != session["control_channel_id"]:
                return

            target_channel = message.guild.get_channel(session["target_channel_id"])
            if not isinstance(target_channel, discord.TextChannel):
                return

            # Verify send permissions in target channel
            permissions = target_channel.permissions_for(message.guild.me)
            if not permissions.send_messages:
                return

            # 1. Trigger the BOT's typing indicator in the target channel
            async with target_channel.typing():
                # Extract attachments if any were included
                files = [await attachment.to_file() for attachment in message.attachments]
                
                # Check if user used Discord's native Reply feature on a message in control room
                reference_msg = message.reference.resolved if message.reference else None

                # 2. Dispatch message as the bot
                try:
                    if reference_msg and isinstance(reference_msg, discord.Message):
                        await reference_msg.reply(
                            content=message.content if message.content else None, 
                            files=files,
                            mention_author=False
                        )
                    else:
                        await target_channel.send(
                            content=message.content if message.content else None, 
                            files=files
                        )
                except discord.HTTPException as e:
                    print(f"Failed to forward control message: {e}")

            # 3. Clean up the control channel message log
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    # ==========================================
    # TOGGLE & REPLY COMMANDS
    # ==========================================

    @commands.command(name="m")
    async def message_proxy_toggle(
        self, 
        ctx: commands.Context, 
        target: Optional[str] = None, 
        target_channel: Optional[discord.TextChannel] = None
    ):
        """Toggle live bot proxy controller.
        
        Usage:
          !m #channel   -> Sets current channel as control room, sends bot messages to #channel
          !m off        -> Disables active proxy control
        """
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return

        message_role = ctx.guild.get_role(MESSAGE_ROLE_ID)
        if not message_role or ctx.author.top_role < message_role:
            return

        # Delete the trigger command
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        # Handle turn off
        if target and target.lower().strip() == "off":
            if ctx.author.id in self.active_proxies:
                del self.active_proxies[ctx.author.id]
                await ctx.send("🛑 **Bot Controller Disabled**.", delete_after=5)
            else:
                await ctx.send("❌ You do not have an active controller session.", delete_after=3)
            return

        # Resolve target channel
        destination = target_channel
        if not destination and ctx.message.channel_mentions:
            destination = ctx.message.channel_mentions[0]

        if not destination:
            destination = ctx.channel

        # Enable controller
        self.active_proxies[ctx.author.id] = {
            "control_channel_id": ctx.channel.id,
            "target_channel_id": destination.id
        }

        await ctx.send(
            f"🤖 **Bot Controller Active!**\n"
            f"• **Control Room:** {ctx.channel.mention}\n"
            f"• **Target Output:** {destination.mention}\n"
            f"*(Type messages here; the bot will display typing status and post in {destination.mention}. Type `!m off` to stop.)*", 
            delete_after=7
        )

    @commands.command(name="reply")
    async def reply_as_bot(self, ctx: commands.Context, message_id: str, *, content: str):
        """Reply directly to a specific message ID in the targeted channel as the bot.
        
        Usage:
          !reply <message_id> <message_text>
        """
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return

        message_role = ctx.guild.get_role(MESSAGE_ROLE_ID)
        if not message_role or ctx.author.top_role < message_role:
            return

        # Delete command message
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        # Determine target channel (from active proxy session or current channel)
        if ctx.author.id in self.active_proxies:
            target_channel_id = self.active_proxies[ctx.author.id]["target_channel_id"]
            target_channel = ctx.guild.get_channel(target_channel_id)
        else:
            target_channel = ctx.channel

        if not isinstance(target_channel, discord.TextChannel):
            return

        try:
            # Trigger typing and send reply
            async with target_channel.typing():
                msg_to_reply = await target_channel.fetch_message(int(message_id))
                await msg_to_reply.reply(content=content, mention_author=False)

        except ValueError:
            await ctx.send("❌ Message ID must be numeric.", delete_after=3)
        except discord.NotFound:
            await ctx.send(f"❌ Message `{message_id}` not found in {target_channel.mention}.", delete_after=4)
        except discord.Forbidden:
            await ctx.send(f"❌ Missing permissions to read/reply in {target_channel.mention}.", delete_after=4)
        except Exception as e:
            await ctx.send(f"❌ Failed to reply: {e}", delete_after=4)

    # ==========================================
    # INFRACTION COMMAND GROUP
    # ==========================================
    
    infraction = app_commands.Group(name="infractions", description="Infraction commands")
    
    @infraction.command(name="issue", description="Issue an infraction to a staff member")
    @app_commands.describe(
        staff="The staff member to issue the infraction to",
        action="The type of infraction action",
        reason="The reason for the infraction",
        expiration="Expiration time (e.g., 10m, 10h, 10d, 10w)",
        notes="Additional notes for the infraction"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Activity Notice", value="Activity Notice"),
        app_commands.Choice(name="Verbal Warning", value="Verbal Warning"),
        app_commands.Choice(name="Warning", value="Warning"),
        app_commands.Choice(name="Strike", value="Strike"),
        app_commands.Choice(name="Demotion", value="Demotion"),
        app_commands.Choice(name="Termination", value="Termination"),
        app_commands.Choice(name="Staff Blacklist", value="Staff Blacklist"),
        app_commands.Choice(name="Under Investigation", value="Under Investigation"),
        app_commands.Choice(name="Suspension", value="Suspension")
    ])
    async def issue_infraction(
        self,
        interaction: discord.Interaction,
        staff: discord.Member,
        action: str,
        reason: str,
        expiration: Optional[str] = None,
        notes: Optional[str] = None
    ):
        if not _can_issue_infraction(interaction):
            await interaction.response.send_message("❌ You don't have permission to issue infractions.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        if action not in INFRACTION_ACTIONS:
            await interaction.followup.send(f"❌ Invalid action. Valid actions: {', '.join(INFRACTION_ACTIONS)}", ephemeral=True)
            return
        
        expiration_timestamp = None
        if expiration:
            try:
                expiration_timestamp = self._parse_expiration(expiration)
            except ValueError:
                await interaction.followup.send("❌ Invalid expiration format. Use formats like: 10m, 10h, 10d, 10w", ephemeral=True)
                return
        
        final_notes = notes if notes else "N/A"
        
        target_channel = interaction.guild.get_channel(INFRACTION_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send("❌ Could not find the infraction channel.", ephemeral=True)
            return
        
        try:
            message = await self._create_infraction_card(
                target_channel,
                interaction.user,
                staff,
                action,
                reason,
                final_notes,
                expiration_timestamp
            )
            # Log to moderation database with message_id
            mod_db.add_modlog(interaction.guild.id, staff.id, interaction.user.id, "INFRACTION", reason, f"Action: {action}", message_id=message.id if message else None)
            await interaction.followup.send(f"✅ Infraction issued successfully to {staff.mention} in {target_channel.mention}!", ephemeral=True)
        except Exception as e:
            print(f"Error creating infraction card: {e}")
            await interaction.followup.send(f"❌ Error creating infraction card: {e}", ephemeral=True)
    
    @infraction.command(name="view", description="View a user's infraction history")
    @app_commands.describe(
        user="The user to view infractions for (defaults to yourself)",
        infractions_type="Filter by specific infraction type (optional)"
    )
    @app_commands.choices(infractions_type=[
        app_commands.Choice(name="Activity Notice", value="Activity Notice"),
        app_commands.Choice(name="Verbal Warning", value="Verbal Warning"),
        app_commands.Choice(name="Warning", value="Warning"),
        app_commands.Choice(name="Strike", value="Strike"),
        app_commands.Choice(name="Demotion", value="Demotion"),
        app_commands.Choice(name="Termination", value="Termination"),
        app_commands.Choice(name="Staff Blacklist", value="Staff Blacklist"),
        app_commands.Choice(name="Under Investigation", value="Under Investigation"),
        app_commands.Choice(name="Suspension", value="Suspension")
    ])
    async def infractions_view(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        infractions_type: Optional[str] = None
    ):
        # Check permissions
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return
        
        required_role = interaction.guild.get_role(INFRACTIONS_VIEW_ROLE_ID)
        if not required_role or interaction.user.top_role < required_role:
            await interaction.response.send_message("❌ You don't have permission to view infractions.", ephemeral=True)
            return
        
        # Default to self if no user specified
        target_user = user if user else interaction.user
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get modlogs from database
            guild_id = interaction.guild.id
            user_id = target_user.id
            
            # Fetch modlogs
            modlogs = mod_db.get_modlogs(guild_id, user_id, limit=100)
            
            # Only show INFRACTION type logs
            infractions = [log for log in modlogs if log.get("action_type") == "INFRACTION"]
            
            # Filter by specific action type if specified
            if infractions_type:
                infractions = [log for log in infractions if f"Action: {infractions_type}" in log.get("details", "")]
            
            if not infractions:
                type_text = f" of type '{infractions_type}'" if infractions_type else ""
                await interaction.followup.send(f"❌ No infractions found for {target_user.mention}{type_text}.", ephemeral=True)
                return
            
            # Sort by created_at (newest first)
            infractions.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            
            # Process infractions for display
            infractions_data = []
            for log in infractions:
                details = log.get("details", "")
                action = "Unknown"
                if details.startswith("Action: "):
                    action = details.replace("Action: ", "")
                
                infractions_data.append({
                    "action": action,
                    "reason": log.get("reason", "No reason"),
                    "notes": log.get("details", "N/A"),
                    "moderator_id": log.get("moderator_id"),
                    "created_at": log.get("created_at"),
                    "message_id": log.get("message_id", None),  # Store message ID if available
                    "channel_id": INFRACTION_CHANNEL_ID  # Use the infraction channel
                })
            
            # Build message using Components V2 for inline buttons (show first 10)
            components_view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(
                accent_colour=discord.Color.from_rgb(37, 37, 41)
            )
            
            # Add header
            container.add_item(discord.ui.TextDisplay(f"### Infraction History for {target_user.display_name}"))
            container.add_item(discord.ui.TextDisplay(f"Showing {len(infractions)} total infraction(s)"))
            container.add_item(discord.ui.Separator())
            
            # Add list items with inline buttons (limit to 10)
            display_count = min(10, len(infractions_data))
            for idx in range(display_count):
                infraction = infractions_data[idx]
                moderator_id = infraction.get("moderator_id")
                moderator = interaction.guild.get_member(moderator_id) if moderator_id else None
                moderator_name = moderator.display_name if moderator else f"<@{moderator_id}>"
                
                # Create a section with text and button accessory
                text_content = f"**#{idx + 1} - {infraction['action']}**\nBy {moderator_name}"
                
                button = InfractionDetailButton(
                    infraction.get("message_id", None),
                    infraction.get("channel_id", INFRACTION_CHANNEL_ID),
                    idx,
                    target_user,
                    infraction
                )
                
                section = discord.ui.Section(
                    discord.ui.TextDisplay(text_content),
                    accessory=button
                )
                container.add_item(section)
            
            if len(infractions_data) > 10:
                container.add_item(discord.ui.TextDisplay(f"*Showing first 10 of {len(infractions_data)} infractions*"))
            
            components_view.add_item(container)
            
            await interaction.followup.send(view=components_view, ephemeral=True)
            
        except Exception as e:
            print(f"Error viewing infractions: {e}")
            await interaction.followup.send(f"❌ Error retrieving infractions: {e}", ephemeral=True)
    
    def _parse_expiration(self, expiration_str: str) -> float:
        expiration_str = expiration_str.lower().strip()
        if expiration_str.endswith('m'):
            return (datetime.now() + timedelta(minutes=int(expiration_str[:-1]))).timestamp()
        elif expiration_str.endswith('h'):
            return (datetime.now() + timedelta(hours=int(expiration_str[:-1]))).timestamp()
        elif expiration_str.endswith('d'):
            return (datetime.now() + timedelta(days=int(expiration_str[:-1]))).timestamp()
        elif expiration_str.endswith('w'):
            return (datetime.now() + timedelta(weeks=int(expiration_str[:-1]))).timestamp()
        else:
            raise ValueError("Invalid expiration format")
    
    async def _create_infraction_card(
        self,
        channel: discord.TextChannel,
        issuer: discord.Member,
        recipient: discord.Member,
        action: str,
        reason: str,
        notes: str,
        expiration_timestamp: Optional[float] = None
    ):
        embed = discord.Embed(
            title="Staff Consequences & Discipline",
            color=discord.Color.from_rgb(37, 37, 41)
        )
        
        embed.set_author(name=f"Signed, {issuer.display_name}", icon_url=issuer.display_avatar.url)
        embed.set_thumbnail(url=recipient.display_avatar.url)
        
        formatted_notes = f"`{notes}`" if notes == "N/A" else notes
        
        description = f"• **Staff Member:** {recipient.mention}\n"
        description += f"• **Action:** {action}\n"
        description += f"• **Reason:** {reason}\n"
        
        if expiration_timestamp:
            expiration_text = f"<t:{int(expiration_timestamp)}:R>"
            description += f"• **Expiration:** {expiration_text}\n"
            
        description += f"• **Notes:** {formatted_notes}"
        embed.description = description
        
        # Create the void button view
        void_view = VoidButton(0, channel.id, VOID_ROLE_ID)  # message_id will be set after sending
        
        # Send the message with the view
        message = await channel.send(content=f"{recipient.mention}", embed=embed, view=void_view)
        
        # Update the view with the actual message ID
        void_view.message_id = message.id
        
        # Create a thread for the infraction
        try:
            thread = await message.create_thread(
                name=f"Infraction - {recipient.display_name} - {action}",
                auto_archive_duration=1440  # 24 hours
            )
        except Exception as e:
            print(f"Error creating thread for infraction: {e}")
        
        return message  # Return the message so we can get the message_id




async def setup(bot: commands.Bot):
    await bot.add_cog(InfractionSystem(bot))