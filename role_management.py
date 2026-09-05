"""
Role Management System Module
Contains /role-create, /role-delete, /role-give, /role-in, /role-remove.
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

import aiohttp


# ==========================================
# CONFIGURATION
# ==========================================

# Anyone with this role, or a role positioned higher than it in the server's
ROLE_MANAGEMENT_ROLE_ID = 1527053931304321130

HEX_COLOR_PATTERN = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _can_manage_roles(interaction: discord.Interaction) -> bool:
    """Server owner, administrators, or anyone whose top role is at or above
    ROLE_MANAGEMENT_ROLE_ID in the role hierarchy."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return True

    required_role = interaction.guild.get_role(ROLE_MANAGEMENT_ROLE_ID)
    if not required_role:
        return False

    return interaction.user.top_role >= required_role


def _bot_can_manage(guild: discord.Guild, role: Optional[discord.Role] = None) -> bool:
    """Whether the bot's own top role is high enough to create/edit/delete
    the given role (or, with role=None, just checks manage_roles permission)."""
    me = guild.me
    if not me.guild_permissions.manage_roles:
        return False
    if role is not None and role >= me.top_role:
        return False
    return True


async def _fetch_icon_bytes(url: str) -> Optional[bytes]:
    """Download an image URL's raw bytes, for use as a role icon."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
    except Exception:
        return None


def _parse_color(raw: Optional[str]) -> Optional[discord.Colour]:
    """Parse a #RRGGBB / RRGGBB string into a discord.Colour, or None if blank/invalid."""
    if not raw:
        return None
    raw = raw.strip()
    if not HEX_COLOR_PATTERN.match(raw):
        return None
    return discord.Colour(int(raw.lstrip("#"), 16))


# ==========================================
# ROLE CREATE (Custom Card Panel Flow)
# ==========================================

class RoleCreateModal(discord.ui.Modal, title="Role Name Setup"):
    name_input = discord.ui.TextInput(
        label="Role Name",
        placeholder="e.g. new role",
        max_length=100,
        required=True
    )

    def __init__(self, supports_icon: bool):
        super().__init__()
        self.supports_icon = supports_icon

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.name_input.value).strip()
        view = RoleBuilderPanel(name=name, supports_icon=self.supports_icon)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


class ColorModal(discord.ui.Modal, title="Role Colour"):
    color_input = discord.ui.TextInput(
        label="Hex Color",
        placeholder="#5865F2",
        max_length=7,
        required=True
    )

    def __init__(self, panel_view):
        super().__init__()
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.color_input.value).strip()
        parsed = _parse_color(raw)
        if not parsed:
            await interaction.response.send_message("❌ Invalid hex color code. Use format like `#5865F2`.", ephemeral=True)
            return
        
        self.panel_view.color = parsed
        self.panel_view.color_raw = raw if raw.startswith("#") else f"#{raw}"
        await interaction.response.edit_message(embed=self.panel_view.build_embed(), view=self.panel_view)


class IconModal(discord.ui.Modal, title="Role Icon"):
    icon_input = discord.ui.TextInput(
        label="Image URL or Custom Emoji",
        placeholder="https://example.com/icon.png or 🔥",
        max_length=200,
        required=True
    )

    def __init__(self, panel_view):
        super().__init__()
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        val = str(self.icon_input.value).strip()
        if val.startswith("http://") or val.startswith("https://"):
            self.panel_view.icon_url = val
            self.panel_view.icon_emoji = None
        else:
            self.panel_view.icon_emoji = val
            self.panel_view.icon_url = None

        await interaction.response.edit_message(embed=self.panel_view.build_embed(), view=self.panel_view)


class RoleBuilderPanel(discord.ui.View):
    def __init__(self, name: str, supports_icon: bool):
        super().__init__(timeout=300)
        self.name = name
        self.supports_icon = supports_icon
        self.color: Optional[discord.Colour] = None
        self.color_raw: Optional[str] = None
        self.icon_emoji: Optional[str] = None
        self.icon_url: Optional[str] = None

    def build_embed(self) -> discord.Embed:
        c = self.color or discord.Colour.default()
        embed = discord.Embed(title="Role Customization Panel", color=c)
        embed.add_field(name="Role Name", value=self.name, inline=False)
        embed.add_field(name="Role Colour", value=self.color_raw or "Default (No Colour)", inline=True)
        
        icon_display = "None"
        if self.icon_emoji:
            icon_display = f"Emoji: {self.icon_emoji}"
        elif self.icon_url:
            icon_display = f"Image URL Provided"
            embed.set_thumbnail(url=self.icon_url)
            
        embed.add_field(name="Role Icon", value=icon_display, inline=True)
        return embed

    @discord.ui.button(label="Choose Colour", style=discord.ButtonStyle.secondary, row=0)
    async def choose_color_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self))

    @discord.ui.button(label="Choose Image / Icon", style=discord.ButtonStyle.secondary, row=0)
    async def choose_icon_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.supports_icon:
            await interaction.response.send_message("❌ Server does not support `ROLE_ICONS` feature.", ephemeral=True)
            return
        await interaction.response.send_modal(IconModal(self))

    @discord.ui.button(label="✅ Create Role", style=discord.ButtonStyle.success, row=1)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        if not _bot_can_manage(guild):
            await interaction.followup.send("❌ I don't have permission to manage roles here.", ephemeral=True)
            return

        try:
            role = await guild.create_role(
                name=self.name,
                colour=self.color or discord.Colour.default(),
                reason=f"Created by {interaction.user} via /role-create panel"
            )

            if self.icon_emoji and "ROLE_ICONS" in guild.features:
                try:
                    await role.edit(unicode_emoji=self.icon_emoji)
                except Exception:
                    pass
            elif self.icon_url and "ROLE_ICONS" in guild.features:
                icon_bytes = await _fetch_icon_bytes(self.icon_url)
                if icon_bytes:
                    try:
                        await role.edit(icon=icon_bytes)
                    except Exception:
                        pass

            await interaction.edit_original_response(
                content=f"✅ Successfully created role {role.mention}!",
                embed=None,
                view=None
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create that role.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error creating role: {e}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Role creation cancelled.", embed=None, view=None)


# ==========================================
# ROLE DELETE
# ==========================================

class RoleDeleteConfirmView(discord.ui.View):
    def __init__(self, role: discord.Role):
        super().__init__(timeout=60)
        self.role = role

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if not _bot_can_manage(interaction.guild, self.role):
            await interaction.followup.send(
                "❌ I can't manage that role — it may be positioned above my own top role.",
                ephemeral=True
            )
            return

        try:
            role_name = self.role.name
            await self.role.delete(reason=f"Deleted by {interaction.user}")
            await interaction.edit_original_response(
                content=f"✅ Deleted role **{role_name}**.",
                embed=None,
                view=None
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete that role.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error deleting role: {e}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)


# ==========================================
# ROLE PICKER (used by give / remove / in)
# ==========================================

class MultiRoleSelect(discord.ui.RoleSelect):
    def __init__(self, callback_func):
        super().__init__(placeholder="Select role(s)...", min_values=1, max_values=25)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, list(self.values))


class MultiRoleSelectView(discord.ui.View):
    def __init__(self, callback_func):
        super().__init__(timeout=120)
        self.add_item(MultiRoleSelect(callback_func))


# ==========================================
# ROLE MANAGEMENT COG
# ==========================================

class RoleManagement(commands.Cog):
    """Slash commands for creating, deleting, and assigning roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- /role-create ----------

    @app_commands.command(name="role-create", description="Create a new role using an interactive panel")
    async def role_create(self, interaction: discord.Interaction):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage roles.", ephemeral=True
            )
            return

        if not _bot_can_manage(interaction.guild):
            await interaction.response.send_message(
                "❌ I don't have permission to manage roles here.", ephemeral=True
            )
            return

        supports_icon = "ROLE_ICONS" in interaction.guild.features
        await interaction.response.send_modal(RoleCreateModal(supports_icon))

    # ---------- /role-delete ----------

    @app_commands.command(name="role-delete", description="Delete a role")
    @app_commands.describe(role="The role to delete")
    async def role_delete(self, interaction: discord.Interaction, role: discord.Role):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage roles.", ephemeral=True
            )
            return

        if role.is_default():
            await interaction.response.send_message("❌ You can't delete @everyone.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Confirm Role Deletion",
            description=f"Are you sure you want to delete {role.mention}? This can't be undone.",
            color=discord.Colour.red()
        )
        await interaction.response.send_message(
            embed=embed, view=RoleDeleteConfirmView(role), ephemeral=True
        )

    # ---------- /role-give ----------

    @app_commands.command(name="role-give", description="Give role(s) to a member")
    @app_commands.describe(user="The member to give role(s) to")
    async def role_give(self, interaction: discord.Interaction, user: discord.Member):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage roles.", ephemeral=True
            )
            return

        async def on_select(select_interaction: discord.Interaction, roles: List[discord.Role]):
            await select_interaction.response.defer(ephemeral=True)

            giveable = [r for r in roles if _bot_can_manage(select_interaction.guild, r)]
            skipped = [r for r in roles if r not in giveable]

            if giveable:
                await user.add_roles(*giveable, reason=f"Given by {select_interaction.user}")

            message = f"✅ Gave {', '.join(r.mention for r in giveable)} to {user.mention}." if giveable else "❌ No roles could be given."
            if skipped:
                message += f"\n⚠️ Skipped (positioned above my top role): {', '.join(r.mention for r in skipped)}"

            await select_interaction.followup.send(message, ephemeral=True)

        await interaction.response.send_message(
            f"Select role(s) to give to {user.mention}:",
            view=MultiRoleSelectView(on_select),
            ephemeral=True
        )

    # ---------- /role-remove ----------

    @app_commands.command(name="role-remove", description="Remove role(s) from a member")
    @app_commands.describe(user="The member to remove role(s) from")
    async def role_remove(self, interaction: discord.Interaction, user: discord.Member):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage roles.", ephemeral=True
            )
            return

        async def on_select(select_interaction: discord.Interaction, roles: List[discord.Role]):
            await select_interaction.response.defer(ephemeral=True)

            removable = [r for r in roles if _bot_can_manage(select_interaction.guild, r)]
            skipped = [r for r in roles if r not in removable]

            if removable:
                await user.remove_roles(*removable, reason=f"Removed by {select_interaction.user}")

            message = f"✅ Removed {', '.join(r.mention for r in removable)} from {user.mention}." if removable else "❌ No roles could be removed."
            if skipped:
                message += f"\n⚠️ Skipped (positioned above my top role): {', '.join(r.mention for r in skipped)}"

            await select_interaction.followup.send(message, ephemeral=True)

        await interaction.response.send_message(
            f"Select role(s) to remove from {user.mention}:",
            view=MultiRoleSelectView(on_select),
            ephemeral=True
        )

    # ---------- /role-in ----------

    @app_commands.command(name="role-in", description="Give role(s) to everyone who has a specific role")
    @app_commands.describe(in_role="Members who have this role will receive the new role(s)")
    async def role_in(self, interaction: discord.Interaction, in_role: discord.Role):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to manage roles.", ephemeral=True
            )
            return

        members = [m for m in in_role.members]
        if not members:
            await interaction.response.send_message(
                f"❌ Nobody currently has {in_role.mention}.", ephemeral=True
            )
            return

        async def on_select(select_interaction: discord.Interaction, roles: List[discord.Role]):
            await select_interaction.response.defer(ephemeral=True)

            giveable = [r for r in roles if _bot_can_manage(select_interaction.guild, r)]
            skipped = [r for r in roles if r not in giveable]

            if not giveable:
                await select_interaction.followup.send("❌ No roles could be given.", ephemeral=True)
                return

            given_count = 0
            for member in members:
                try:
                    await member.add_roles(*giveable, reason=f"role-in by {select_interaction.user}")
                    given_count += 1
                except Exception:
                    continue

            message = (
                f"✅ Gave {', '.join(r.mention for r in giveable)} to "
                f"{given_count}/{len(members)} member(s) who have {in_role.mention}."
            )
            if skipped:
                message += f"\n⚠️ Skipped (positioned above my top role): {', '.join(r.mention for r in skipped)}"

            await select_interaction.followup.send(message, ephemeral=True)

        await interaction.response.send_message(
            f"{len(members)} member(s) have {in_role.mention}. Select role(s) to give them:",
            view=MultiRoleSelectView(on_select),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleManagement(bot))