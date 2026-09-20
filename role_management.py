"""
Role Management System Module
Contains /role-create, /role-delete, /role-give, /role-in, /role-remove, and /auto-role.
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List


# ==========================================
# CONFIGURATION
# ==========================================

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


def _parse_color(raw: Optional[str]) -> Optional[discord.Colour]:
    """Parse a #RRGGBB / RRGGBB string into a discord.Colour, or None if blank/invalid."""
    if not raw:
        return None
    raw = raw.strip()
    if not HEX_COLOR_PATTERN.match(raw):
        return None
    return discord.Colour(int(raw.lstrip("#"), 16))


# ==========================================
# ROLE DELETE CONFIRMATION
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
# MULTI-ROLE SELECTOR VIEWS
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
    """Slash commands for creating, deleting, assigning roles, and auto-roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> list of role IDs assigned automatically on join
        self.auto_roles: dict[int, List[int]] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = member.guild.id
        if guild_id in self.auto_roles and self.auto_roles[guild_id]:
            role_ids = self.auto_roles[guild_id]
            roles_to_add = [member.guild.get_role(rid) for rid in role_ids]
            roles_to_add = [r for r in roles_to_add if r is not None and _bot_can_manage(member.guild, r)]
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason="Automatic join role")
                except Exception:
                    pass

    # ---------- /role-create ----------

    @app_commands.command(name="role-create", description="Create a new role with a name and optional color")
    @app_commands.describe(
        name="The name of the new role",
        color="Hex color code (e.g. #5865F2)"
    )
    async def role_create(self, interaction: discord.Interaction, name: str, color: Optional[str] = None):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
            return

        if not _bot_can_manage(interaction.guild):
            await interaction.response.send_message("❌ I don't have permission to manage roles here.", ephemeral=True)
            return

        parsed_color = _parse_color(color) if color else discord.Colour.default()
        if color and not parsed_color:
            await interaction.response.send_message(
                "❌ Invalid color format. Use a hex code like `#5865F2` or `5865F2`.",
                ephemeral=True
            )
            return

        try:
            role = await interaction.guild.create_role(
                name=name,
                colour=parsed_color,
                reason=f"Created by {interaction.user} via /role-create"
            )
            await interaction.response.send_message(f"✅ Successfully created role {role.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to create that role.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating role: {e}", ephemeral=True)

    # ---------- /role-delete ----------

    @app_commands.command(name="role-delete", description="Delete a role")
    @app_commands.describe(role="The role to delete")
    async def role_delete(self, interaction: discord.Interaction, role: discord.Role):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
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
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
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
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
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
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
            return

        members = list(in_role.members)
        if not members:
            await interaction.response.send_message(f"❌ Nobody currently has {in_role.mention}.", ephemeral=True)
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

            message = f"✅ Gave {', '.join(r.mention for r in giveable)} to {given_count}/{len(members)} member(s)."
            if skipped:
                message += f"\n⚠️ Skipped (positioned above my top role): {', '.join(r.mention for r in skipped)}"

            await select_interaction.followup.send(message, ephemeral=True)

        await interaction.response.send_message(
            f"{len(members)} member(s) have {in_role.mention}. Select role(s) to give them:",
            view=MultiRoleSelectView(on_select),
            ephemeral=True
        )

    # ---------- /auto-role group ----------

    auto_role_group = app_commands.Group(name="auto-role", description="Manage auto-roles for new members joining")

    @auto_role_group.command(name="add", description="Add an auto-role given automatically to new members")
    @app_commands.describe(role="The role to automatically assign")
    async def auto_role_add(self, interaction: discord.Interaction, role: discord.Role):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
            return

        if not _bot_can_manage(interaction.guild, role):
            await interaction.response.send_message("❌ I cannot manage that role (it is higher than or equal to my top role).", ephemeral=True)
            return

        guild_id = interaction.guild.id
        if guild_id not in self.auto_roles:
            self.auto_roles[guild_id] = []

        if role.id in self.auto_roles[guild_id]:
            await interaction.response.send_message(f"⚠️ {role.mention} is already configured as an auto-role.", ephemeral=True)
            return

        self.auto_roles[guild_id].append(role.id)
        await interaction.response.send_message(f"✅ Added {role.mention} to auto-roles for new members.", ephemeral=True)

    @auto_role_group.command(name="delete", description="Delete/clear all auto-roles configured for this server")
    async def auto_role_delete(self, interaction: discord.Interaction):
        if not _can_manage_roles(interaction):
            await interaction.response.send_message("❌ You don't have permission to manage roles.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        if guild_id in self.auto_roles and self.auto_roles[guild_id]:
            count = len(self.auto_roles[guild_id])
            self.auto_roles[guild_id].clear()
            await interaction.response.send_message(f"✅ Successfully deleted/cleared all {count} auto-role(s) for this server.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ There are no auto-roles currently configured for this server.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleManagement(bot))