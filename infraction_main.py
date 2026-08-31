"""
Infraction System Module
Contains the infraction slash command, card display functionality, and live bot control proxy.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Dict
from datetime import datetime, timedelta
import asyncio


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
VOID_ROLE_ID = 1527051014992040106
MESSAGE_ROLE_ID = 1527055221098811433


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
        if clean_content.startswith("!m") or clean_content.startswith("!reply") or clean_content.startswith("!void"):
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
    
    infraction = app_commands.Group(name="infraction", description="Infraction commands")
    
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
            await self._create_infraction_card(
                target_channel,
                interaction.user,
                staff,
                action,
                reason,
                final_notes,
                expiration_timestamp
            )
            await interaction.followup.send(f"✅ Infraction issued successfully to {staff.mention} in {target_channel.mention}!", ephemeral=True)
        except Exception as e:
            print(f"Error creating infraction card: {e}")
            await interaction.followup.send(f"❌ Error creating infraction card: {e}", ephemeral=True)
    
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
        await channel.send(content=f"{recipient.mention}", embed=embed)

    # ==========================================
    # VOID COMMAND
    # ==========================================

    @commands.command(name="void")
    async def void_command(
        self, 
        ctx: commands.Context, 
        message_id: str, 
        channel: Optional[discord.TextChannel] = None
    ):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("This command can only be used in a server.")
            return
        
        void_role = ctx.guild.get_role(VOID_ROLE_ID)
        if not void_role or ctx.author.top_role < void_role:
            await ctx.send("You don't have permission to use this command.")
            return
        
        target_channel = channel or ctx.guild.get_channel(INFRACTION_CHANNEL_ID) or ctx.channel
        
        try:
            target_message = await target_channel.fetch_message(int(message_id))
            if not target_message.embeds:
                await ctx.send(f"This message in {target_channel.mention} doesn't contain an embed.")
                return
            
            embed = target_message.embeds[0]
            embed.title = f"Voided by @{ctx.author.display_name}"
            embed.color = discord.Color.red()
            
            await target_message.edit(embed=embed)
            await ctx.send(f"Successfully voided infraction in {target_channel.mention}.", delete_after=3)
            
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
            
        except ValueError:
            await ctx.send("Invalid message ID. Please provide a numerical message ID.")
        except discord.NotFound:
            await ctx.send(f"Message not found in {target_channel.mention}.")
        except Exception as e:
            await ctx.send(f"Error voiding infraction: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(InfractionSystem(bot))