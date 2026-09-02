import asyncio
from datetime import datetime, timezone
import discord
from discord.ext import commands
from discord import app_commands
from bot import api_client
from bot.cogs.test import active_tests, _wechsler_band, TestCog, update_presence

CONFIG_KEYS = [
    "iq_threshold_min", "iq_threshold_max", "questions_per_test", "time_per_question",
    "failed_role_id", "passed_role_id", "test_channel_id", "results_channel_id",
    "allow_retest", "retest_cooldown_hours", "score_expires_days", "flag_threshold_seconds",
    "webhook_url", "shame_channel_id", "shame_role_id", "shame_nickname",
    "audit_channel_id", "digest_channel_id", "digest_day", "digest_hour",
]


class DuelChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, admin_cog: "AdminCog"):
        super().__init__(timeout=120)
        self.challenger = challenger
        self.opponent = opponent
        self.admin_cog = admin_cog
        self.responded = False

    async def _disable(self, interaction: discord.Interaction, content: str):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=content, view=self)

    @discord.ui.button(label="Accept Duel", style=discord.ButtonStyle.danger)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged member can respond.", ephemeral=True)
            return
        if self.responded:
            return
        self.responded = True
        await self._disable(interaction, f"{self.opponent.mention} accepted. Sending tests to DMs...")
        await self.admin_cog.run_duel(self.challenger, self.opponent)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged member can respond.", ephemeral=True)
            return
        if self.responded:
            return
        self.responded = True
        await self._disable(interaction, f"{self.opponent.mention} declined the duel.")

    async def on_timeout(self):
        self.responded = True
        for item in self.children:
            item.disabled = True


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log_audit(self, cfg: dict, actor: discord.abc.User, action: str, detail: str = ""):
        channel_id = cfg.get("audit_channel_id", "").strip()
        if not channel_id:
            return
        try:
            channel_id = int(channel_id)
        except ValueError:
            return
        embed = discord.Embed(title=action, description=detail or None, color=0x111111)
        embed.set_footer(text=f"By {actor}  ·  User ID: {actor.id}")
        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    @app_commands.command(name="shame-config", description="Set the channel and role used for public shaming of failed scores")
    @app_commands.describe(
        channel="Channel where failed results get posted publicly",
        role="Role to ping when someone gets shamed (optional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shame_config(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role | None = None,
    ):
        values = {"shame_channel_id": str(channel.id)}
        values["shame_role_id"] = str(role.id) if role else ""
        try:
            await api_client.update_config(values)
        except Exception:
            await interaction.response.send_message("Failed to save config to backend.", ephemeral=True)
            return

        msg = f"Shame channel set to {channel.mention}."
        msg += f" Pinging {role.mention} on each shame post." if role else " No role will be pinged."
        await interaction.response.send_message(msg, ephemeral=True)
        try:
            cfg = await api_client.get_config(force=True)
        except Exception:
            cfg = {}
        await self._log_audit(cfg, interaction.user, "Shame Config Updated", msg)

    @app_commands.command(name="screen", description="Send a screening test to a member with custom parameters")
    @app_commands.describe(
        member="The member to screen",
        time_per_question="Seconds per question (default: config value)",
        overall_minutes="Total time limit in minutes (default: no limit)",
        num_questions="Number of questions to ask (default: config value)",
        fail_action="What to do if the member fails: mute, kick, ban, timeout, notify (default: mute)",
        timeout_minutes="Minutes to timeout for (only used if fail_action=timeout, default: 60)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def screen(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time_per_question: app_commands.Range[int, 5, 300] | None = None,
        overall_minutes: app_commands.Range[int, 1, 180] | None = None,
        num_questions: app_commands.Range[int, 1, 50] | None = None,
        fail_action: str | None = None,
        timeout_minutes: app_commands.Range[int, 1, 10080] | None = None,
    ):
        await self._do_screen(
            interaction, member,
            time_per_question, overall_minutes, num_questions,
            fail_action,
            timeout_minutes,
        )

    @screen.autocomplete("fail_action")
    async def _fail_action_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = [
            app_commands.Choice(name="Mute (assign muted role)", value="mute"),
            app_commands.Choice(name="Kick", value="kick"),
            app_commands.Choice(name="Ban", value="ban"),
            app_commands.Choice(name="Timeout", value="timeout"),
            app_commands.Choice(name="Notify admin only (no action)", value="notify"),
        ]
        return [c for c in choices if current.lower() in c.name.lower()] or choices

    async def _do_screen(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        time_per_question: int | None,
        overall_minutes: int | None,
        num_questions: int | None,
        fail_action_value: str | None,
        timeout_minutes: int | None,
    ):
        if member.bot:
            await interaction.response.send_message("Cannot screen bots.", ephemeral=True)
            return

        if member.id in active_tests:
            await interaction.response.send_message(f"{member.mention} already has an active test.", ephemeral=True)
            return

        try:
            cfg = await api_client.get_config()
        except Exception:
            await interaction.response.send_message("Cannot reach screening server.", ephemeral=True)
            return

        tpq = time_per_question or int(cfg.get("time_per_question", "45"))
        nq = num_questions or int(cfg.get("questions_per_test", "20"))
        valid_actions = {"mute", "kick", "ban", "timeout", "notify"}
        fa = fail_action_value if fail_action_value in valid_actions else "mute"
        tm = timeout_minutes or 60
        overall_secs = (overall_minutes * 60.0) if overall_minutes else None

        max_questions = int(cfg.get("questions_per_test", "20"))
        nq = min(nq, max_questions)

        try:
            questions = await api_client.fetch_test_questions(nq)
        except Exception:
            await interaction.response.send_message("Failed to load questions.", ephemeral=True)
            return

        if not questions:
            await interaction.response.send_message("No questions available. Add questions first.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Sending screening test to {member.mention}.\n"
            f"**{nq} questions** · **{tpq}s/q**"
            + (f" · **{overall_minutes}m overall**" if overall_minutes else "")
            + f" · fail action: **{fa}**",
            ephemeral=True,
        )
        await self._log_audit(
            cfg, interaction.user, "Manual Screen Initiated",
            f"Target: {member.mention}  ·  {nq}q · {tpq}s/q · fail action: {fa}",
        )

        test_cog: TestCog | None = self.bot.cogs.get("TestCog")
        if not test_cog:
            await interaction.followup.send("TestCog not loaded.", ephemeral=True)
            return

        active_tests.add(member.id)
        await update_presence(self.bot)
        try:
            await test_cog._run_test(
                member,
                questions,
                float(tpq),
                cfg,
                overall_limit_secs=overall_secs,
                fail_action=fa,
                timeout_minutes=tm,
                notify_admin=interaction.user,
            )
        finally:
            active_tests.discard(member.id)
            await update_presence(self.bot)

    @app_commands.command(name="iq", description="Check a member's most recent screening score")
    @app_commands.describe(member="The member to look up (omit for yourself)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def check_iq(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        try:
            result = await api_client.get_user_latest_result(str(target.id))
        except Exception:
            await interaction.response.send_message("Failed to fetch results.", ephemeral=True)
            return

        if not result:
            await interaction.response.send_message(
                f"{target.mention} has not completed the screening test yet.",
                ephemeral=True,
            )
            return

        iq = result["iq_score"]
        band = _wechsler_band(iq)
        passed = result["passed"]
        pct = result.get("percentile", 0)
        correct = result["answers_correct"]
        total = result["total_questions"]
        flagged = result.get("flagged", False)

        embed = discord.Embed(color=0x111111)
        embed.set_author(name=str(target), icon_url=target.display_avatar.url)
        embed.add_field(name="Score", value=f"**{iq}** — {band}", inline=True)
        embed.add_field(name="Percentile", value=f"Top {100 - pct}%", inline=True)
        embed.add_field(name="Correct", value=f"{correct}/{total}", inline=True)
        embed.add_field(name="Verdict", value="PASSED" if passed else "FAILED", inline=True)
        if flagged:
            embed.add_field(name="Flagged", value="Fast responses detected", inline=True)

        try:
            cfg = await api_client.get_config()
            allow_retest = cfg.get("allow_retest", "false").lower() == "true"
            if allow_retest:
                cooldown_hours = float(cfg.get("retest_cooldown_hours", "24"))
                completed = datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00"))
                if completed.tzinfo is None:
                    completed = completed.replace(tzinfo=timezone.utc)
                hours_since = (datetime.now(timezone.utc) - completed).total_seconds() / 3600
                remaining = cooldown_hours - hours_since
                if remaining > 0:
                    h, m = int(remaining), int((remaining % 1) * 60)
                    embed.add_field(name="Retest Available In", value=f"{h}h {m}m", inline=True)
                else:
                    embed.add_field(name="Retest", value="Available now", inline=True)
        except Exception:
            pass

        embed.set_footer(text=f"User ID: {target.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="iq-leaderboard", description="Show the top 10 screening scores")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def iq_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        try:
            board = await api_client.get_leaderboard(limit=10)
        except Exception:
            await interaction.followup.send("Failed to fetch leaderboard.")
            return

        if not board:
            await interaction.followup.send("No passing scores yet.")
            return

        lines = []
        for i, entry in enumerate(board):
            iq = entry["iq_score"]
            username = entry["discord_username"]
            band = _wechsler_band(iq)
            pct = entry.get("percentile", 0)
            lines.append(f"`{i + 1:02d}.` **{username}** — **{iq}** ({band}) · top {100 - pct}%")

        embed = discord.Embed(
            title="Intelligence Screening Leaderboard",
            description="\n".join(lines),
            color=0x111111,
        )
        embed.set_footer(text="Best passing score per member")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="iq-shame-leaderboard", description="Show the 10 worst screening scores ever recorded")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def iq_shame_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        try:
            board = await api_client.get_worst_leaderboard(limit=10)
        except Exception:
            await interaction.followup.send("Failed to fetch the hall of shame.")
            return

        if not board:
            await interaction.followup.send("Nobody has failed yet. Suspicious.")
            return

        lines = []
        for i, entry in enumerate(board):
            iq = entry["iq_score"]
            username = entry["discord_username"]
            band = _wechsler_band(iq)
            lines.append(f"`{i + 1:02d}.` **{username}** — **{iq}** ({band})")

        embed = discord.Embed(
            title="Hall of Shame — All-Time Worst",
            description="\n".join(lines),
            color=0x111111,
        )
        embed.set_footer(text="Worst failing score per member")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="iq-reset", description="Delete a member's screening history and remove screening roles")
    @app_commands.describe(member="The member to reset")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def iq_reset(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)

        try:
            deleted = await api_client.delete_user_results(str(member.id))
        except Exception:
            await interaction.followup.send("Failed to delete results from backend.")
            return

        try:
            cfg = await api_client.get_config()
        except Exception:
            cfg = {}

        passed_role_id = cfg.get("passed_role_id", "").strip()
        failed_role_id = cfg.get("failed_role_id", "").strip()
        roles_removed = []

        for role_id_str in (passed_role_id, failed_role_id):
            if role_id_str:
                try:
                    role = interaction.guild.get_role(int(role_id_str))
                    if role and role in member.roles:
                        await member.remove_roles(role, reason=f"IQ reset by {interaction.user}")
                        roles_removed.append(role.name)
                except (ValueError, discord.Forbidden):
                    pass

        embed = discord.Embed(
            title="Screening Reset",
            description=(
                f"Cleared **{deleted}** test record(s) for {member.mention}.\n"
                + (f"Removed roles: {', '.join(roles_removed)}" if roles_removed else "No screening roles to remove.")
            ),
            color=0x111111,
        )
        embed.set_footer(text=f"Reset by {interaction.user}")
        await interaction.followup.send(embed=embed)
        await self._log_audit(cfg, interaction.user, "IQ Reset", f"Target: {member.mention}  ·  {deleted} record(s) cleared")

    @app_commands.command(name="iq-history", description="Show full screening history for a member")
    @app_commands.describe(member="The member to look up")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def iq_history(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        try:
            results = await api_client.get_user_all_results(str(member.id))
        except Exception:
            await interaction.followup.send("Failed to fetch history.")
            return

        if not results:
            await interaction.followup.send(f"{member.mention} has no screening history.")
            return

        lines = []
        for i, r in enumerate(results[:10], 1):
            ts = r.get("completed_at", "")[:10]
            verdict = "PASS" if r["passed"] else "FAIL"
            lines.append(f"`{i:02d}.` `{verdict}` **{r['iq_score']}** ({r['answers_correct']}/{r['total_questions']}) — {ts}")

        embed = discord.Embed(
            title=f"Screening History — {member.display_name}",
            description="\n".join(lines),
            color=0x111111,
        )
        embed.set_footer(text=f"Showing up to 10 most recent · User ID: {member.id}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="config", description="View or update a screening config value")
    @app_commands.describe(key="Config key", value="New value (omit to view current)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_cmd(self, interaction: discord.Interaction, key: str, value: str | None = None):
        if key not in CONFIG_KEYS:
            await interaction.response.send_message(f"Unknown config key: `{key}`", ephemeral=True)
            return

        try:
            cfg = await api_client.get_config(force=True)
        except Exception:
            await interaction.response.send_message("Cannot reach screening server.", ephemeral=True)
            return

        if value is None:
            current = cfg.get(key, "")
            await interaction.response.send_message(f"`{key}` = `{current or '(empty)'}`", ephemeral=True)
            return

        try:
            await api_client.update_config({key: value})
        except Exception:
            await interaction.response.send_message("Failed to save config to backend.", ephemeral=True)
            return

        await interaction.response.send_message(f"`{key}` updated to `{value}`", ephemeral=True)
        await self._log_audit(cfg, interaction.user, "Config Updated", f"`{key}` → `{value}`")

    @config_cmd.autocomplete("key")
    async def _config_key_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        matches = [k for k in CONFIG_KEYS if current.lower() in k.lower()]
        return [app_commands.Choice(name=k, value=k) for k in (matches or CONFIG_KEYS)[:25]]

    @app_commands.command(name="iq-duel", description="Challenge another member to a head-to-head screening duel")
    @app_commands.describe(opponent="The member to challenge")
    async def iq_duel(self, interaction: discord.Interaction, opponent: discord.Member):
        challenger = interaction.user
        if opponent.bot:
            await interaction.response.send_message("Cannot duel a bot.", ephemeral=True)
            return
        if opponent.id == challenger.id:
            await interaction.response.send_message("Cannot duel yourself.", ephemeral=True)
            return
        if challenger.id in active_tests or opponent.id in active_tests:
            await interaction.response.send_message("One of you already has an active test.", ephemeral=True)
            return

        view = DuelChallengeView(challenger, opponent, self)
        await interaction.response.send_message(
            f"{opponent.mention}, {challenger.mention} has challenged you to an IQ duel. Accept?",
            view=view,
        )

    async def run_duel(self, challenger: discord.Member, opponent: discord.Member):
        if challenger.id in active_tests or opponent.id in active_tests:
            return

        try:
            cfg = await api_client.get_config()
        except Exception:
            return

        nq = int(cfg.get("questions_per_test", "20"))
        tpq = float(cfg.get("time_per_question", "45"))

        try:
            questions = await api_client.fetch_test_questions(nq)
        except Exception:
            return
        if not questions:
            return

        test_cog: TestCog | None = self.bot.cogs.get("TestCog")
        if not test_cog:
            return

        active_tests.add(challenger.id)
        active_tests.add(opponent.id)
        await update_presence(self.bot)
        try:
            r1, r2 = await asyncio.gather(
                test_cog._run_test(challenger, questions, tpq, cfg),
                test_cog._run_test(opponent, questions, tpq, cfg),
            )
        finally:
            active_tests.discard(challenger.id)
            active_tests.discard(opponent.id)
            await update_presence(self.bot)

        if not r1 or not r2:
            return
        await self._announce_duel(challenger, r1, opponent, r2, cfg)

    async def _announce_duel(
        self,
        u1: discord.Member, r1: dict,
        u2: discord.Member, r2: dict,
        cfg: dict,
    ):
        embed = discord.Embed(title="IQ Duel Result", color=0x111111)
        embed.add_field(name=str(u1), value=f"**{r1['iq_score']}**", inline=True)
        embed.add_field(name="vs", value="—", inline=True)
        embed.add_field(name=str(u2), value=f"**{r2['iq_score']}**", inline=True)

        winner = loser = w_result = l_result = None
        if r1["iq_score"] > r2["iq_score"]:
            winner, w_result, loser, l_result = u1, r1, u2, r2
        elif r2["iq_score"] > r1["iq_score"]:
            winner, w_result, loser, l_result = u2, r2, u1, r1

        embed.description = f"**{winner}** wins the duel." if winner else "It's a tie."

        channel_id = cfg.get("results_channel_id", "").strip()
        if channel_id:
            try:
                channel_id = int(channel_id)
                for guild in self.bot.guilds:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=embed)
            except (ValueError, discord.Forbidden):
                pass

        if winner:
            await self._broadcast_duel_shame(loser, l_result, winner, w_result, cfg)

    async def _broadcast_duel_shame(
        self,
        loser: discord.Member, l_result: dict,
        winner: discord.Member, w_result: dict,
        cfg: dict,
    ):
        channel_id = cfg.get("shame_channel_id", "").strip()
        if not channel_id:
            return
        try:
            channel_id = int(channel_id)
        except ValueError:
            return

        embed = discord.Embed(
            title="Duel Loss",
            description=f"{loser.mention} challenged {winner.mention} to an IQ duel and lost.",
            color=0x111111,
        )
        embed.add_field(name=f"{loser.display_name}", value=f"**{l_result['iq_score']}**", inline=True)
        embed.add_field(name=f"{winner.display_name}", value=f"**{w_result['iq_score']}**", inline=True)

        role_id = cfg.get("shame_role_id", "").strip()
        content = f"<@&{role_id}>" if role_id else None

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(
                        content=content,
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(roles=True),
                    )
                except discord.Forbidden:
                    pass

    @shame_config.error
    @screen.error
    @check_iq.error
    @iq_leaderboard.error
    @iq_shame_leaderboard.error
    @iq_reset.error
    @iq_history.error
    @config_cmd.error
    async def _permission_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need **Manage Server** permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
