"""
Infraction System Module
Contains the infraction slash command, card display functionality, and ephemeral message dispatch panel.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime, timedelta


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

# Role ID required to use /infraction issue (or higher hierarchy)
INFRACTION_ROLE_ID = 1539201630161993728

# Channel to automatically send infraction embeds to
INFRACTION_CHANNEL_ID = 1526898975704350822

# Role ID required to use !void command
VOID_ROLE_ID = 1527051014992040106

# Role ID required to use !m command
MESSAGE_ROLE_ID = 1527055221098811433


def _can_issue_infraction(interaction: discord.Interaction) -> bool:
    """Server owner, administrators, or anyone whose top role is at or above
    INFRACTION_ROLE_ID in the role hierarchy."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return True

    required_role = interaction.guild.get_role(INFRACTION_ROLE_ID)
    if not required_role:
        return False

    return interaction.user.top_role >= required_role


# ==========================================
# UI COMPONENTS
# ==========================================

class MessageModal(discord.ui.Modal, title="Send Bot Message"):
    """Modal for entering channel, message content, and optional reply ID."""
    
    def __init__(self, default_channel: Optional[discord.TextChannel] = None):
        super().__init__()
        self.default_channel = default_channel
        
        # Pre-fill channel field if selected from dropdown
        if default_channel:
            self.channel_input.default = f"#{default_channel.name} ({default_channel.id})"
    
    channel_input = discord.ui.TextInput(
        label="Channel (#mention, Name, or ID)",
        placeholder="e.g. #general, general, or 123456789...",
        style=discord.TextStyle.short,
        required=True,
        max_length=100
    )
    
    reply_to_id = discord.ui.TextInput(
        label="Reply to Message ID (Optional)",
        placeholder="Paste target message ID here to send as a reply...",
        style=discord.TextStyle.short,
        required=False,
        max_length=30
    )
    
    message = discord.ui.TextInput(
        label="Message",
        placeholder="Enter your message here...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Parse channel target and dispatch message or reply."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This panel can only be used in a server.", ephemeral=True)
            return

        raw_channel = self.channel_input.value.strip()
        target_channel = None

        # 1. Check if user kept default dropdown selection
        if self.default_channel and f"({self.default_channel.id})" in raw_channel:
            target_channel = self.default_channel
        else:
            # 2. Extract digits from raw input (#mention or raw ID)
            clean_id = "".join(filter(str.isdigit, raw_channel))
            if clean_id:
                target_channel = guild.get_channel(int(clean_id))
            
            # 3. Fallback: Search channel by name if no numeric ID matched
            if not target_channel:
                clean_name = raw_channel.lstrip("#").lower()
                target_channel = discord.utils.get(guild.text_channels, name=clean_name)

        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                f"❌ Could not find a text channel matching `{raw_channel}`.", 
                ephemeral=True
            )
            return

        target_message_id = self.reply_to_id.value.strip() if self.reply_to_id.value else None
        
        # Handle message reply
        if target_message_id:
            try:
                target_msg = await target_channel.fetch_message(int(target_message_id))
                await target_msg.reply(content=self.message.value)
                await interaction.response.send_message(
                    f"✅ Reply sent successfully to message `{target_message_id}` in {target_channel.mention}!", 
                    ephemeral=True
                )
                return
            except ValueError:
                await interaction.response.send_message("❌ Invalid Message ID format.", ephemeral=True)
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    f"❌ Could not find message `{target_message_id}` in {target_channel.mention}.", 
                    ephemeral=True
                )
                return
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to send reply: {e}", ephemeral=True)
                return
        
        # Handle standard channel dispatch
        await target_channel.send(content=self.message.value)
        await interaction.response.send_message(
            f"✅ Message sent successfully to {target_channel.mention}!", 
            ephemeral=True
        )


class EphemeralMessagePanelView(discord.ui.View):
    """Hidden panel rendered via interaction response."""
    
    def __init__(self, user: discord.Member, guild: discord.Guild):
        super().__init__(timeout=180)
        self.user = user
        self.guild = guild
        self.selected_channel = None
        
        # Populate select dropdown (up to 25 channels)
        channel_options = [
            discord.SelectOption(label=f"#{channel.name}", value=str(channel.id))
            for channel in guild.text_channels[:25]
        ]
        
        if channel_options:
            self.channel_select.options = channel_options

    @discord.ui.select(
        placeholder="Select target channel (or type in modal)...",
        min_values=1,
        max_values=1,
        row=0
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle channel selection."""
        self.selected_channel = self.guild.get_channel(int(select.values[0]))
        await interaction.response.defer()

    @discord.ui.button(label="Compose Message", style=discord.ButtonStyle.primary, row=1)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to compose message."""
        modal = MessageModal(default_channel=self.selected_channel)
        await interaction.response.send_modal(modal)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Restricts interaction to author."""
        return interaction.user == self.user


class PersistentPanelLaunchView(discord.ui.View):
    """Button control posted by !m that spawns an ephemeral panel upon click."""
    
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Message Panel", 
        style=discord.ButtonStyle.primary, 
        emoji="📋",
        custom_id="launch_message_panel_btn"
    )
    async def launch_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
            
        message_role = interaction.guild.get_role(MESSAGE_ROLE_ID)
        if not message_role or interaction.user.top_role < message_role:
            await interaction.response.send_message("❌ You lack permission to use this panel.", ephemeral=True)
            return

        ephemeral_view = EphemeralMessagePanelView(interaction.user, interaction.guild)
        await interaction.response.send_message(
            "📋 **Message Dispatch Panel** — Choose a channel from the dropdown or click Compose to type one manually:", 
            view=ephemeral_view, 
            ephemeral=True
        )


# ==========================================
# INFRACTION COG
# ==========================================

class InfractionSystem(commands.Cog):
    """Main infraction system cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
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
        """Issue an infraction to a staff member."""
        if not _can_issue_infraction(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to issue infractions.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        if action not in INFRACTION_ACTIONS:
            await interaction.followup.send(
                f"❌ Invalid action. Valid actions: {', '.join(INFRACTION_ACTIONS)}",
                ephemeral=True
            )
            return
        
        expiration_timestamp = None
        if expiration:
            try:
                expiration_timestamp = self._parse_expiration(expiration)
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid expiration format. Use formats like: 10m, 10h, 10d, 10w",
                    ephemeral=True
                )
                return
        
        final_notes = notes if notes else "N/A"
        
        target_channel = interaction.guild.get_channel(INFRACTION_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send(
                "❌ Could not find the infraction channel.",
                ephemeral=True
            )
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
            
            await interaction.followup.send(
                f"✅ Infraction issued successfully to {staff.mention} in {target_channel.mention}!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating infraction card: {e}")
            await interaction.followup.send(
                f"❌ Error creating infraction card: {e}",
                ephemeral=True
            )
    
    def _parse_expiration(self, expiration_str: str) -> float:
        """Parse expiration string to timestamp."""
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
        """Create the infraction card matching the exact layout."""
        embed = discord.Embed(
            title="Staff Consequences & Discipline",
            color=discord.Color.from_rgb(37, 37, 41)
        )
        
        embed.set_author(
            name=f"Signed, {issuer.display_name}",
            icon_url=issuer.display_avatar.url
        )
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
    # PREFIX COMMANDS
    # ==========================================

    @commands.command(name="m")
    async def message_command(self, ctx: commands.Context):
        """Post a persistent control button that launches an ephemeral panel."""
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        
        message_role = ctx.guild.get_role(MESSAGE_ROLE_ID)
        if not message_role or ctx.author.top_role < message_role:
            return
        
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        
        view = PersistentPanelLaunchView()
        await ctx.send("Click the button below to open your hidden message panel:", view=view)

    @commands.command(name="void")
    async def void_command(
        self, 
        ctx: commands.Context, 
        message_id: str, 
        channel: Optional[discord.TextChannel] = None
    ):
        """Void an infraction by message ID.
        
        Usage:
          !void <message_id>
          !void <message_id> #channel
        """
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            await ctx.send("This command can only be used in a server.")
            return
        
        void_role = ctx.guild.get_role(VOID_ROLE_ID)
        if not void_role or ctx.author.top_role < void_role:
            await ctx.send("You don't have permission to use this command.")
            return
        
        # Default to INFRACTION_CHANNEL_ID if no channel is typed, or fallback to current channel
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
    """Setup the infraction cog."""
    await bot.add_cog(InfractionSystem(bot))