"""
Interactive staff report system.

Provides /report and manages the report card's review workflow in the
configured staff report channel.
"""

import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from report_database import db

REPORT_CHANNEL_ID = 1552408086126272542
REPORT_TICKET_CATEGORY_ID = 1552431325422551111
REPORT_STAFF_ROLE_ID = 1527050504733986987

PENDING_COLOR = discord.Color.from_rgb(245, 158, 11)
UNDER_REVIEW_COLOR = discord.Color.from_rgb(249, 115, 22)
SORTED_COLOR = discord.Color.from_rgb(34, 197, 94)


def can_review_reports(member: discord.Member) -> bool:
    """Allow the report role, higher-ranked roles, and administrators."""
    if (
        member.id == member.guild.owner_id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    ):
        return True

    required_role = member.guild.get_role(REPORT_STAFF_ROLE_ID)
    return required_role is not None and member.top_role >= required_role


def _truncate(value: str, limit: int = 1024) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


class FurtherReviewTicketView(discord.ui.View):
    """Ticket controls displayed inside a private further-review channel."""

    def __init__(self, report_view: "ReportView"):
        super().__init__(timeout=None)
        self.report_view = report_view

        end_button = discord.ui.Button(
            label="End",
            style=discord.ButtonStyle.danger,
            custom_id="report_further_end",
        )
        end_button.callback = self._handle_end
        self.add_item(end_button)

    async def _handle_end(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await self.report_view._handle_end_ticket(interaction)


class ReportView(discord.ui.View):
    """Persistent workflow attached to a submitted report card."""

    def __init__(
        self,
        client: discord.Client,
        guild: discord.Guild,
        reporter: discord.Member,
        target: Optional[discord.User],
        reason: str,
        report_id: int,
    ):
        super().__init__(timeout=None)
        self.client = client
        self.guild = guild
        self.reporter = reporter
        self.target = target
        self.reason = reason
        self.report_id = report_id
        self.report_number: Optional[int] = None
        self.created_at = discord.utils.utcnow()
        self.status = "pending"
        self.reviewer_id: Optional[int] = None
        self.sorted_by_id: Optional[int] = None
        self.evidence_channel_id: Optional[int] = None
        self.message_id: Optional[int] = None
        self._lock = asyncio.Lock()
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.clear_items()
        self.review_button = None
        self.leave_button = None
        self.sorted_button = None
        self.further_button = None

        if self.status == "pending":
            self.review_button = discord.ui.Button(
                label="🟢 Review",
                style=discord.ButtonStyle.primary,
                custom_id="report_review",
            )
            self.review_button.callback = self._handle_review
            self.add_item(self.review_button)
            return

        if self.status == "under_review":
            self.leave_button = discord.ui.Button(
                label="🟡 Leave",
                style=discord.ButtonStyle.secondary,
                custom_id="report_leave",
            )
            self.leave_button.callback = self._handle_leave
            self.add_item(self.leave_button)

            self.sorted_button = discord.ui.Button(
                label="🟢 Sorted",
                style=discord.ButtonStyle.success,
                custom_id="report_sorted",
            )
            self.sorted_button.callback = self._handle_sorted
            self.add_item(self.sorted_button)

            self.further_button = discord.ui.Button(
                label="🔵 Further Review",
                style=discord.ButtonStyle.primary,
                custom_id="report_further",
                disabled=self.evidence_channel_id is not None,
            )
            self.further_button.callback = self._handle_further_review
            self.add_item(self.further_button)

    def _status_text(self) -> str:
        if self.status == "pending":
            return "Pending Review"
        if self.status == "sorted":
            return f"Sorted by {self._member_mention(self.sorted_by_id)}"
        if self.status == "further_review":
            return (
                "Under Further Review with "
                f"{self._member_mention(self.reviewer_id)}"
            )
        return f"Under Review by {self._member_mention(self.reviewer_id)}"

    def _member_mention(self, user_id: Optional[int]) -> str:
        if user_id is None:
            return "an unknown staff member"
        member = self.guild.get_member(user_id)
        return member.mention if member else f"<@{user_id}>"

    def _embed_color(self) -> discord.Color:
        if self.status == "sorted":
            return SORTED_COLOR
        if self.status in {"under_review", "further_review"}:
            return UNDER_REVIEW_COLOR
        return PENDING_COLOR

    def build_embed(self) -> discord.Embed:
        thumbnail_user = self.target or self.reporter
        embed = discord.Embed(
            title="Report",
            color=self._embed_color(),
            timestamp=self.created_at,
        )
        embed.set_author(
            name=f"Reported by {self.reporter.display_name}"[:256],
            icon_url=self.reporter.display_avatar.url,
        )
        embed.set_thumbnail(url=thumbnail_user.display_avatar.url)
        embed.description = (
            f"• **Reporter:** {self.reporter.mention}\n"
            f"• **Target:** {self.target.mention if self.target else 'N/A'}\n"
            f"• **Reason:** {_truncate(self.reason)}\n"
            f"• **Status:** {self._status_text()}"
        )
        embed.set_footer(text=f"Report ID: {self.report_id}")
        return embed

    async def _validate_reviewer(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if not interaction.guild or not isinstance(
            interaction.user,
            discord.Member,
        ):
            await interaction.response.send_message(
                "This report workflow can only be used in a server.",
                ephemeral=True,
            )
            return False

        if not can_review_reports(interaction.user):
            await interaction.response.send_message(
                "You do not have permission to review reports.",
                ephemeral=True,
            )
            return False

        if self.status == "sorted":
            await interaction.response.send_message(
                "This report has already been sorted.",
                ephemeral=True,
            )
            return False

        if (
            self.reviewer_id is not None
            and self.reviewer_id != interaction.user.id
        ):
            await interaction.response.send_message(
                "This report is currently being reviewed by "
                f"{self._member_mention(self.reviewer_id)}.",
                ephemeral=True,
            )
            return False

        return True

    async def _edit_report_message(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.message is None:
            raise RuntimeError("The report message is no longer available.")
        await interaction.message.edit(
            embed=self.build_embed(),
            view=self,
        )

    async def _grant_reviewer_access(
        self,
        reviewer: discord.Member,
        channel: discord.TextChannel,
    ) -> None:
        await channel.set_permissions(
            reviewer,
            overwrite=discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                send_messages_in_threads=True,
            ),
        )

    async def _remove_reviewer_access(
        self,
        reviewer_id: int,
    ) -> None:
        if reviewer_id == self.reporter.id:
            return
        if self.evidence_channel_id is None:
            return

        channel = self.guild.get_channel(self.evidence_channel_id)
        if not isinstance(channel, discord.TextChannel):
            self.evidence_channel_id = None
            return

        reviewer = self.guild.get_member(reviewer_id)
        if reviewer is None:
            try:
                reviewer = await self.guild.fetch_member(reviewer_id)
            except discord.NotFound:
                return
            except discord.HTTPException as e:
                print(
                    f"[REPORT] Could not fetch reviewer {reviewer_id}: {e}"
                )
                return

        try:
            await channel.set_permissions(
                reviewer,
                overwrite=discord.PermissionOverwrite(view_channel=False),
            )
        except discord.HTTPException as e:
            print(
                f"[REPORT] Could not remove reviewer {reviewer_id} "
                f"from evidence channel {channel.id}: {e}"
            )

    async def _handle_review(
        self,
        interaction: discord.Interaction,
    ) -> None:
        async with self._lock:
            if not await self._validate_reviewer(interaction):
                return

            await interaction.response.defer(ephemeral=True)

            evidence_channel = (
                self.guild.get_channel(self.evidence_channel_id)
                if self.evidence_channel_id is not None
                else None
            )
            if isinstance(evidence_channel, discord.TextChannel):
                try:
                    await self._grant_reviewer_access(
                        interaction.user,
                        evidence_channel,
                    )
                except discord.HTTPException as e:
                    print(
                        f"[REPORT] Could not grant evidence access to "
                        f"{interaction.user.id}: {e}"
                    )
                    await interaction.followup.send(
                        "I could not grant you access to the existing evidence channel.",
                        ephemeral=True,
                    )
                    return
                self.reviewer_id = interaction.user.id
                self.status = "further_review"
            else:
                if self.evidence_channel_id is not None:
                    self.evidence_channel_id = None
                self.reviewer_id = interaction.user.id
                self.status = "under_review"

            self._refresh_buttons()
            await self._edit_report_message(interaction)
            await interaction.followup.send(
                f"You are now reviewing this report. {interaction.user.mention}",
                ephemeral=True,
            )

    async def _handle_leave(
        self,
        interaction: discord.Interaction,
    ) -> None:
        async with self._lock:
            if not await self._validate_reviewer(interaction):
                return

            await interaction.response.defer(ephemeral=True)
            previous_reviewer_id = self.reviewer_id
            if previous_reviewer_id is not None:
                await self._remove_reviewer_access(previous_reviewer_id)

            self.reviewer_id = None
            self.status = "pending"
            self._refresh_buttons()
            await self._edit_report_message(interaction)
            await interaction.followup.send(
                "You have released this report for another staff member to review.",
                ephemeral=True,
            )

    async def _dm_reporter(
        self,
        staff_member: discord.Member,
    ) -> bool:
        try:
            reporter = self.guild.get_member(self.reporter.id)
            if reporter is None:
                try:
                    reporter = await self.guild.fetch_member(self.reporter.id)
                except discord.NotFound:
                    reporter = await self.client.fetch_user(self.reporter.id)

            await reporter.send(
                "Your report has been dealt with by "
                f"{staff_member.mention}."
            )
            return True
        except discord.Forbidden:
            return False
        except discord.NotFound:
            return False
        except discord.HTTPException as e:
            print(f"[REPORT] Could not DM report submitter: {e}")
            return False

    async def _handle_sorted(
        self,
        interaction: discord.Interaction,
    ) -> None:
        async with self._lock:
            if not await self._validate_reviewer(interaction):
                return

            await interaction.response.defer(ephemeral=True)
            self.status = "sorted"
            self.sorted_by_id = interaction.user.id
            self._refresh_buttons()
            await self._edit_report_message(interaction)

            dm_sent = await self._dm_reporter(interaction.user)
            confirmation = "The report has been marked as sorted."
            if not dm_sent:
                confirmation += " The reporter could not be DM'd."
            await interaction.followup.send(
                confirmation,
                ephemeral=True,
            )

    async def _get_target_member(self) -> Optional[discord.Member]:
        if self.target is None:
            return None

        target_member = self.guild.get_member(self.target.id)
        if target_member is not None:
            return target_member

        try:
            return await self.guild.fetch_member(self.target.id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _create_evidence_channel(
        self,
        reviewer: discord.Member,
    ) -> discord.TextChannel:
        if self.guild.me is None:
            raise RuntimeError("The bot is not available in this server.")

        category = self.guild.get_channel(REPORT_TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            raise RuntimeError(
                f"Report ticket category {REPORT_TICKET_CATEGORY_ID} "
                "was not found."
            )

        report_number = await asyncio.to_thread(
            db.next_report_number,
            self.guild.id,
        )
        if report_number < 1:
            raise RuntimeError("Could not allocate a report ticket number.")

        member_permissions = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            send_messages_in_threads=True,
        )
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            self.reporter: member_permissions,
            reviewer: member_permissions,
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                send_messages_in_threads=True,
                manage_channels=True,
            ),
        }

        target_member = await self._get_target_member()
        if target_member is not None:
            overwrites[target_member] = member_permissions

        channel = await self.guild.create_text_channel(
            f"Report-{report_number}",
            overwrites=overwrites,
            category=category,
            topic=f"Private further-review ticket for report {self.report_id}",
        )
        self.report_number = report_number

        evidence_embed = discord.Embed(
            title="Further Review",
            description=(
                "Hello, this is a further review of the report, the staff "
                "member may ask for any additional proof, clarification, "
                "description and more."
            ),
            color=UNDER_REVIEW_COLOR,
        )
        evidence_embed.set_footer(text=f"Report ticket: Report-{report_number}")

        try:
            await channel.send(
                content=(
                    f"{reviewer.mention}, you are reviewing this report. "
                    f"{self.reporter.mention}, you may submit evidence here."
                ),
                embed=evidence_embed,
                view=FurtherReviewTicketView(self),
                allowed_mentions=discord.AllowedMentions(
                    users=[reviewer, self.reporter]
                ),
            )
        except discord.HTTPException as e:
            print(
                f"[REPORT] Evidence channel {channel.id} was created but "
                f"its welcome message failed: {e}"
            )

        return channel

    async def _handle_end_ticket(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not interaction.guild or not isinstance(
            interaction.user,
            discord.Member,
        ):
            await interaction.response.send_message(
                "This report workflow can only be used in a server.",
                ephemeral=True,
            )
            return

        if not can_review_reports(interaction.user):
            await interaction.response.send_message(
                "You do not have permission to review reports.",
                ephemeral=True,
            )
            return

        if self.reviewer_id != interaction.user.id:
            await interaction.response.send_message(
                "Only the staff member reviewing this report can end it.",
                ephemeral=True,
            )
            return

        if (
            self.status not in {"further_review", "sorted"}
            or self.evidence_channel_id is None
            or interaction.channel_id != self.evidence_channel_id
        ):
            await interaction.response.send_message(
                "This further-review ticket is no longer active.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        report_channel = self.guild.get_channel(REPORT_CHANNEL_ID)
        if not isinstance(report_channel, discord.TextChannel):
            await interaction.followup.send(
                "The report card could not be found; the ticket was not deleted.",
                ephemeral=True,
            )
            return

        try:
            report_message = await report_channel.fetch_message(self.message_id)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"[REPORT] Could not fetch report card for sorting: {e}")
            await interaction.followup.send(
                "The report card could not be updated; the ticket was not deleted.",
                ephemeral=True,
            )
            return

        previous_status = self.status
        previous_sorted_by_id = self.sorted_by_id
        self.status = "sorted"
        self.sorted_by_id = interaction.user.id
        self._refresh_buttons()
        try:
            await report_message.edit(
                embed=self.build_embed(),
                view=self,
            )
        except discord.HTTPException as e:
            self.status = previous_status
            self.sorted_by_id = previous_sorted_by_id
            self._refresh_buttons()
            print(
                f"[REPORT] Could not mark report {self.report_id} "
                f"as sorted: {e}"
            )
            await interaction.followup.send(
                "The report card could not be updated; the ticket was not deleted.",
                ephemeral=True,
            )
            return

        await self._dm_reporter(interaction.user)

        evidence_channel = self.guild.get_channel(self.evidence_channel_id)
        if evidence_channel is not None:
            try:
                await evidence_channel.delete(
                    reason=f"Report {self.report_id} sorted by {interaction.user}"
                )
                self.evidence_channel_id = None
            except discord.HTTPException as e:
                print(
                    f"[REPORT] Report was sorted, but evidence channel "
                    f"{evidence_channel.id} could not be deleted: {e}"
                )
        else:
            self.evidence_channel_id = None

    async def _handle_further_review(
        self,
        interaction: discord.Interaction,
    ) -> None:
        async with self._lock:
            if not await self._validate_reviewer(interaction):
                return

            await interaction.response.defer(ephemeral=True)
            try:
                evidence_channel = await self._create_evidence_channel(
                    interaction.user
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "I could not create the private evidence channel. "
                    "Please check my Manage Channels permission.",
                    ephemeral=True,
                )
                return
            except Exception as e:
                print(f"[REPORT] Could not create evidence channel: {e}")
                await interaction.followup.send(
                    "I could not create the private evidence channel.",
                    ephemeral=True,
                )
                return

            self.evidence_channel_id = evidence_channel.id
            self.status = "further_review"
            self._refresh_buttons()
            await self._edit_report_message(interaction)
            await interaction.followup.send(
                f"Private evidence channel created: {evidence_channel.mention}",
                ephemeral=True,
            )


class ReportSystem(commands.Cog):
    """Command and workflow management for staff reports."""

    @app_commands.command(
        name="report",
        description="Report an issue or a user to the staff team.",
    )
    @app_commands.describe(
        reason="The details or reason for the report.",
        target="The @user being reported (optional).",
    )
    async def report(
        self,
        interaction: discord.Interaction,
        reason: str,
        target: Optional[discord.User] = None,
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user,
            discord.Member,
        ):
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        reason = reason.strip()
        if not reason:
            await interaction.response.send_message(
                "Please provide a reason for the report.",
                ephemeral=True,
            )
            return

        report_channel = interaction.guild.get_channel(REPORT_CHANNEL_ID)
        if not isinstance(report_channel, discord.TextChannel):
            await interaction.response.send_message(
                "The staff report channel could not be found.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        view = ReportView(
            client=interaction.client,
            guild=interaction.guild,
            reporter=interaction.user,
            target=target,
            reason=reason,
            report_id=interaction.id,
        )
        staff_role = interaction.guild.get_role(REPORT_STAFF_ROLE_ID)
        if staff_role is None:
            print(
                f"[REPORT] Staff role {REPORT_STAFF_ROLE_ID} was not found "
                f"in guild {interaction.guild.id}."
            )

        try:
            message = await report_channel.send(
                content=(
                    staff_role.mention
                    if staff_role is not None
                    else None
                ),
                embed=view.build_embed(),
                view=view,
                allowed_mentions=discord.AllowedMentions(
                    roles=[staff_role] if staff_role else []
                ),
            )
            view.message_id = message.id
        except Exception as e:
            print(f"[REPORT] Failed to submit report: {e}")
            await interaction.followup.send(
                "Your report could not be submitted. Please contact a staff member.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "✅ Your report has been submitted and the staff team has been notified.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    if bot.get_cog("ReportSystem") is None:
        await bot.add_cog(ReportSystem(bot))
