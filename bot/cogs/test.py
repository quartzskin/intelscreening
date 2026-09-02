import asyncio
import random
import re
import time
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
from discord import app_commands
from bot import api_client

NICK_SUFFIX_RE = re.compile(r"\s*\[IQ \d+\]$")

active_tests: set[int] = set()

FAIL_ACTIONS = {"mute", "kick", "ban", "timeout", "notify"}

# (iq_ceiling, animal, blurb) — first entry whose ceiling >= score wins
_ANIMAL_COMPARISONS = [
    (45, "sea sponge", "has no brain, nervous system, or capacity for reasoning"),
    (55, "garden snail", "takes roughly a full day to cross a road"),
    (65, "chicken", "can be trained to peck a lever for food, and that's the ceiling"),
    (75, "goldfish", "the 3-second-memory myth is false — it out-remembered you"),
    (85, "pigeon", "can pass the mirror self-recognition test"),
    (95, "crow", "solves multi-step puzzles and holds grudges against specific humans"),
    (999, "dolphin", "has self-awareness and a name-like signature whistle"),
]

# (iq, country) — from Lynn & Becker (2019), national averages; nearest match wins
_COUNTRY_IQ = [
    (68, "Equatorial Guinea"), (70, "Liberia"), (72, "Sierra Leone"),
    (74, "Guatemala"), (76, "Nigeria"), (78, "India"), (80, "Iran"),
    (82, "Philippines"), (84, "Mexico"), (86, "Turkey"), (88, "Greece"),
    (90, "Bulgaria"), (92, "Russia"), (94, "Spain"), (96, "France"),
    (98, "United States"), (100, "United Kingdom"), (102, "Germany"),
    (104, "Netherlands"), (106, "South Korea"), (108, "Japan"), (110, "Singapore"),
]


def _animal_for_iq(iq: int) -> str:
    for ceiling, animal, blurb in _ANIMAL_COMPARISONS:
        if iq <= ceiling:
            return f"a **{animal}** — {blurb}"
    return "a dolphin"


def _country_for_iq(iq: int) -> str:
    closest = min(_COUNTRY_IQ, key=lambda pair: abs(pair[0] - iq))
    return closest[1]


_ROASTS = {
    "Extremely Low": [
        "This wasn't a screening, it was a formality.",
        "Some questions have four wrong answers. This one found a fifth way to be wrong.",
        "The test has a guessing floor. This score required effort to go below it.",
    ],
    "Borderline": [
        "So close to average, and yet.",
        "This is the score equivalent of tripping over a flat surface.",
        "Technically not the worst. Emphasis on technically.",
    ],
    "Low Average": [
        "Passable in most rooms. Not this one.",
        "The bar was on the floor and it still needed a running start.",
    ],
}


def _roast_for_band(band: str) -> str:
    lines = _ROASTS.get(band, ["No further comment is necessary."])
    return random.choice(lines)


async def update_presence(bot: commands.Bot):
    count = len(active_tests)
    if count == 0:
        await bot.change_presence(activity=None)
    else:
        label = "1 screening in progress" if count == 1 else f"{count} screenings in progress"
        await bot.change_presence(activity=discord.CustomActivity(name=label))


async def apply_nickname_branding(member: discord.Member, iq: int, passed: bool, cfg: dict):
    if cfg.get("shame_nickname", "false").lower() != "true":
        return
    base = NICK_SUFFIX_RE.sub("", member.nick or member.name)
    try:
        if passed:
            if member.nick and NICK_SUFFIX_RE.search(member.nick):
                await member.edit(nick=base or None, reason="Screening passed")
        else:
            suffix = f" [IQ {iq}]"
            new_nick = (base[: 32 - len(suffix)] + suffix) if base else f"Member{suffix}"
            await member.edit(nick=new_nick, reason="Screening failed")
    except (discord.Forbidden, discord.HTTPException):
        pass


class AnswerView(discord.ui.View):
    def __init__(self, question: dict, time_limit: float):
        super().__init__(timeout=time_limit)
        self.answer: str | None = None
        self.time_taken: float = time_limit
        self._start = time.monotonic()

        labels = {
            "A": question["option_a"],
            "B": question["option_b"],
            "C": question["option_c"],
            "D": question["option_d"],
        }
        for letter, text in labels.items():
            btn = discord.ui.Button(
                label=f"{letter}. {text[:60]}",
                custom_id=letter,
                style=discord.ButtonStyle.secondary,
                row=0 if letter in ("A", "B") else 1,
            )
            btn.callback = self._make_callback(letter)
            self.add_item(btn)

    def _make_callback(self, letter: str):
        async def callback(interaction: discord.Interaction):
            self.answer = letter
            self.time_taken = time.monotonic() - self._start
            for item in self.children:
                item.disabled = True
                if isinstance(item, discord.ui.Button):
                    item.style = (
                        discord.ButtonStyle.primary
                        if item.custom_id == letter
                        else discord.ButtonStyle.secondary
                    )
            await interaction.response.edit_message(view=self)
            self.stop()
        return callback

    async def on_timeout(self):
        self.time_taken = self.timeout or self.time_taken
        self.stop()


def _build_question_embed(
    question: dict, index: int, total: int, time_limit: float, overall_remaining: float | None = None
) -> discord.Embed:
    filled = round((index - 1) / total * 20)
    progress = "█" * filled + "░" * (20 - filled)
    embed = discord.Embed(
        title=f"Question {index} / {total}",
        description=question["text"],
        color=0x111111,
    )
    embed.add_field(
        name="​",
        value=(
            f"**A.** {question['option_a']}\n"
            f"**B.** {question['option_b']}\n"
            f"**C.** {question['option_c']}\n"
            f"**D.** {question['option_d']}"
        ),
        inline=False,
    )
    stars = "★" * question["difficulty"] + "☆" * (5 - question["difficulty"])
    footer = f"{progress}  ·  {stars}  ·  {int(time_limit)}s/q"
    if overall_remaining is not None:
        mins, secs = divmod(int(overall_remaining), 60)
        footer += f"  ·  {mins}m {secs:02d}s overall"
    embed.set_footer(text=footer)
    return embed


def _build_result_embed(result: dict, threshold: int, fail_action: str = "mute") -> discord.Embed:
    iq = result["iq_score"]
    passed = result["passed"]
    correct = result["answers_correct"]
    total = result["total_questions"]
    pct = result.get("percentile", 0)
    flagged = result.get("flagged", False)
    theta = result["raw_score"]
    band = _wechsler_band(iq)

    embed = discord.Embed(title="Screening Complete", color=0x111111)
    if flagged:
        embed.description = "*This result has been flagged for review.*"

    embed.add_field(name="Ability Estimate", value=f"**{iq}** — {band}", inline=True)
    embed.add_field(name="Percentile", value=f"Top **{100 - pct}%**", inline=True)
    embed.add_field(name="Correct", value=f"{correct}/{total}", inline=True)
    embed.add_field(
        name="Verdict",
        value="**PASSED**" if passed else "**FAILED**",
        inline=False,
    )
    if not passed and fail_action not in ("mute", "notify"):
        action_text = {
            "kick": "You have been **kicked** from the server.",
            "ban": "You have been **banned** from the server.",
            "timeout": "You have been **timed out**.",
        }.get(fail_action, "")
        if action_text:
            embed.add_field(name="Action Taken", value=action_text, inline=False)

    embed.set_footer(
        text=(
            f"θ = {theta:.3f}  ·  Rasch IRT (Lord & Novick 1968)  ·  "
            f"WAIS-IV bands (Wechsler 2008)  ·  Screening estimate only"
        )
    )
    return embed


def _wechsler_band(iq: int) -> str:
    if iq >= 130: return "Very Superior"
    if iq >= 120: return "Superior"
    if iq >= 110: return "High Average"
    if iq >= 90:  return "Average"
    if iq >= 80:  return "Low Average"
    if iq >= 70:  return "Borderline"
    return "Extremely Low"


class ShameEditModal(discord.ui.Modal, title="Edit Shame Message"):
    def __init__(self, message: discord.Message, embed: discord.Embed):
        super().__init__()
        self.message = message
        self.embed = embed
        current = embed.description or ""
        self.text_input = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,
            default=current,
            max_length=1000,
            required=False,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.embed.description = str(self.text_input.value) or None
        await self.message.edit(embed=self.embed)
        await interaction.response.send_message("Updated.", ephemeral=True)


class ShameEditView(discord.ui.View):
    def __init__(self, embed: discord.Embed):
        super().__init__(timeout=None)
        self.embed = embed

    @discord.ui.button(label="Edit Message", style=discord.ButtonStyle.secondary)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need **Manage Server** permission to edit this.", ephemeral=True)
            return
        await interaction.response.send_modal(ShameEditModal(interaction.message, self.embed))


class TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.digest_task.start()

    def cog_unload(self):
        self.digest_task.cancel()

    @tasks.loop(hours=1)
    async def digest_task(self):
        try:
            cfg = await api_client.get_config()
        except Exception:
            return

        channel_id = cfg.get("digest_channel_id", "").strip()
        if not channel_id:
            return

        digest_day = cfg.get("digest_day", "sunday").lower()
        digest_hour = int(cfg.get("digest_hour", "12"))
        now = datetime.now(timezone.utc)
        if now.strftime("%A").lower() != digest_day or now.hour != digest_hour:
            return

        try:
            worst = await api_client.get_worst_of_week()
        except Exception:
            return
        if not worst:
            return

        try:
            channel_id = int(channel_id)
        except ValueError:
            return

        embed = discord.Embed(
            title="Dumbest of the Week",
            description=f"**{worst['discord_username']}** takes this week's crown.",
            color=0x111111,
        )
        embed.add_field(name="Score", value=f"**{worst['iq_score']}** — {_wechsler_band(worst['iq_score'])}", inline=True)
        embed.add_field(name="Correct", value=f"{worst['answers_correct']}/{worst['total_questions']}", inline=True)

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    @digest_task.before_loop
    async def _before_digest(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="test", description="Start the intelligence screening test (sent to your DMs)")
    async def start_test(self, interaction: discord.Interaction):
        user = interaction.user

        if user.id in active_tests:
            await interaction.response.send_message("You already have an active test session.", ephemeral=True)
            return

        try:
            cfg = await api_client.get_config()
        except Exception:
            await interaction.response.send_message("Cannot reach screening server. Contact an admin.", ephemeral=True)
            return

        allow_retest = cfg.get("allow_retest", "false").lower() == "true"
        retest_cooldown_hours = float(cfg.get("retest_cooldown_hours", "24"))
        score_expires_days = int(cfg.get("score_expires_days", "0"))
        questions_per_test = int(cfg.get("questions_per_test", "20"))
        time_per_question = float(cfg.get("time_per_question", "45"))

        existing = await api_client.get_user_latest_result(str(user.id))
        if existing:
            completed = datetime.fromisoformat(existing["completed_at"].replace("Z", "+00:00"))
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_days = (now - completed).total_seconds() / 86400
            score_expired = score_expires_days > 0 and age_days > score_expires_days

            if not score_expired:
                if not allow_retest:
                    await interaction.response.send_message(
                        f"You have already completed screening. "
                        f"Score: **{existing['iq_score']}** ({_wechsler_band(existing['iq_score'])}). "
                        f"Retesting is disabled.",
                        ephemeral=True,
                    )
                    return
                hours_since = age_days * 24
                if hours_since < retest_cooldown_hours:
                    remaining = retest_cooldown_hours - hours_since
                    h, m = int(remaining), int((remaining % 1) * 60)
                    await interaction.response.send_message(
                        f"You must wait **{h}h {m}m** before retesting.",
                        ephemeral=True,
                    )
                    return

        try:
            questions = await api_client.fetch_test_questions(questions_per_test)
        except Exception:
            await interaction.response.send_message("Failed to load questions. Contact an admin.", ephemeral=True)
            return

        if not questions:
            await interaction.response.send_message("No questions available. An admin must add questions first.", ephemeral=True)
            return

        await interaction.response.send_message("The screening test has been sent to your DMs.", ephemeral=True)

        active_tests.add(user.id)
        await update_presence(self.bot)
        try:
            await self._run_test(user, questions, time_per_question, cfg)
        finally:
            active_tests.discard(user.id)
            await update_presence(self.bot)

    async def _run_test(
        self,
        user: discord.User,
        questions: list[dict],
        time_per_q: float,
        cfg: dict,
        overall_limit_secs: float | None = None,
        fail_action: str = "mute",
        timeout_minutes: int = 60,
        notify_admin: discord.User | None = None,
    ) -> dict | None:
        try:
            dm = await user.create_dm()
        except discord.Forbidden:
            return None

        threshold = int(cfg.get("iq_threshold_min", "85"))
        total = len(questions)

        desc_parts = [f"**{total} questions** · **{int(time_per_q)}s per question**"]
        if overall_limit_secs:
            mins = int(overall_limit_secs // 60)
            desc_parts.append(f"**{mins}m overall time limit**")
        desc_parts.append("\nAnswer using the buttons. This message will update with each question.\n\n*Starting in 3 seconds...*")

        intro_embed = discord.Embed(
            title="Intelligence Screening",
            description="\n".join(desc_parts),
            color=0x111111,
        )
        try:
            msg = await dm.send(embed=intro_embed)
        except discord.Forbidden:
            return None

        await asyncio.sleep(3)

        answers_log = []
        test_start = time.monotonic()

        for i, question in enumerate(questions, 1):
            q_time = time_per_q
            overall_remaining = None
            if overall_limit_secs is not None:
                elapsed = time.monotonic() - test_start
                remaining_overall = overall_limit_secs - elapsed
                if remaining_overall <= 2:
                    break
                q_time = min(time_per_q, remaining_overall - 1)
                overall_remaining = remaining_overall

            embed = _build_question_embed(question, i, total, q_time, overall_remaining)
            view = AnswerView(question, q_time)
            try:
                await msg.edit(embed=embed, view=view)
            except (discord.NotFound, discord.Forbidden):
                return None

            await view.wait()

            chosen = view.answer if view.answer else "X"
            answers_log.append({
                "question_id": question["id"],
                "answer": chosen,
                "time_taken": view.time_taken,
            })

            if not view.answer:
                te = discord.Embed(
                    title=f"Time's Up — Question {i}",
                    description="Moving to next question..." if i < total else "Submitting...",
                    color=0x111111,
                )
                try:
                    await msg.edit(embed=te, view=None)
                except (discord.NotFound, discord.Forbidden):
                    return None
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(1)

        try:
            await msg.edit(embed=discord.Embed(title="Calculating score...", color=0x111111), view=None)
        except (discord.NotFound, discord.Forbidden):
            pass

        try:
            result = await api_client.submit_test(
                discord_user_id=str(user.id),
                discord_username=str(user),
                answers=answers_log,
            )
        except Exception:
            err = discord.Embed(title="Submission Failed", description="Contact an admin.", color=0x111111)
            try:
                await msg.edit(embed=err, view=None)
            except Exception:
                pass
            return None

        try:
            await msg.edit(embed=_build_result_embed(result, threshold, fail_action), view=None)
        except (discord.NotFound, discord.Forbidden):
            pass

        await self._apply_fail_action(user, result["passed"], cfg, fail_action, timeout_minutes)
        await self._broadcast_result(user, result, cfg, fail_action)

        member = self._find_member(user.id)
        if member:
            await apply_nickname_branding(member, result["iq_score"], result["passed"], cfg)

        if not result["passed"]:
            await self._broadcast_shame(user, result, cfg)
        else:
            try:
                if await api_client.needs_redemption(str(user.id)):
                    await self._broadcast_redemption(user, result, cfg)
                    await api_client.mark_redeemed(str(user.id))
            except Exception:
                pass

        if notify_admin:
            await self._notify_admin(notify_admin, user, result, fail_action, timeout_minutes)

        return result

    def _find_member(self, user_id: int) -> discord.Member | None:
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member:
                return member
        return None

    async def _apply_fail_action(
        self,
        user: discord.User,
        passed: bool,
        cfg: dict,
        fail_action: str = "mute",
        timeout_minutes: int = 60,
    ):
        passed_role_id = cfg.get("passed_role_id", "").strip()
        failed_role_id = cfg.get("failed_role_id", "").strip()

        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if not member:
                continue
            try:
                if passed:
                    if passed_role_id:
                        role = guild.get_role(int(passed_role_id))
                        if role:
                            await member.add_roles(role, reason="Screening passed")
                else:
                    if fail_action == "mute":
                        if failed_role_id:
                            role = guild.get_role(int(failed_role_id))
                            if role:
                                await member.add_roles(role, reason="Screening failed")
                    elif fail_action == "kick":
                        await member.kick(reason="Failed intelligence screening")
                    elif fail_action == "ban":
                        await member.ban(reason="Failed intelligence screening", delete_message_days=0)
                    elif fail_action == "timeout":
                        await member.timeout(timedelta(minutes=timeout_minutes), reason="Failed intelligence screening")
            except (discord.Forbidden, ValueError):
                pass

    async def _broadcast_result(self, user: discord.User, result: dict, cfg: dict, fail_action: str = "mute"):
        channel_id = cfg.get("results_channel_id", "").strip()
        if not channel_id:
            return
        try:
            channel_id = int(channel_id)
        except ValueError:
            return

        iq = result["iq_score"]
        passed = result["passed"]
        flagged = result.get("flagged", False)
        pct = result.get("percentile", 0)
        band = _wechsler_band(iq)

        embed = discord.Embed(color=0x111111)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="Score", value=f"**{iq}** — {band}", inline=True)
        embed.add_field(name="Percentile", value=f"Top {100 - pct}%", inline=True)
        embed.add_field(name="Verdict", value="PASSED" if passed else "FAILED", inline=True)
        if flagged:
            embed.add_field(name="Flagged", value="Unusually fast responses", inline=False)
        if not passed and fail_action not in ("mute", "notify"):
            action_labels = {"kick": "Kicked", "ban": "Banned", "timeout": "Timed out"}
            embed.add_field(name="Action", value=action_labels.get(fail_action, fail_action.title()), inline=True)

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def _broadcast_shame(self, user: discord.User, result: dict, cfg: dict):
        channel_id = cfg.get("shame_channel_id", "").strip()
        if not channel_id:
            return
        try:
            channel_id = int(channel_id)
        except ValueError:
            return

        iq = result["iq_score"]
        pct = result.get("percentile", 0)
        band = _wechsler_band(iq)
        animal = _animal_for_iq(iq)
        country = _country_for_iq(iq)

        embed = discord.Embed(
            title="Hall of Shame",
            description=(
                f"{user.mention} took the intelligence screening and failed. Publicly. "
                f"On record. In this channel.\n\n*{_roast_for_band(band)}*"
            ),
            color=0x111111,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Score", value=f"**{iq}** — {band}", inline=True)
        embed.add_field(name="Correct", value=f"{result['answers_correct']}/{result['total_questions']}", inline=True)
        embed.add_field(name="Percentile", value=f"Bottom {pct}%", inline=True)
        embed.add_field(name="Cognitive Peer", value=f"Roughly {animal}.", inline=False)
        embed.add_field(
            name="National Comparison",
            value=f"This score is on par with the national average of **{country}**.",
            inline=False,
        )
        embed.set_footer(text=f"θ = {result['raw_score']:.3f}  ·  Rasch IRT  ·  User ID: {user.id}")

        role_id = cfg.get("shame_role_id", "").strip()
        content = None
        if role_id:
            try:
                content = f"<@&{int(role_id)}>"
            except ValueError:
                content = None

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(
                        content=content,
                        embed=embed,
                        view=ShameEditView(embed),
                        allowed_mentions=discord.AllowedMentions(roles=True),
                    )
                    await api_client.mark_shamed(result["id"])
                except discord.Forbidden:
                    pass
                except Exception:
                    pass

    async def _broadcast_redemption(self, user: discord.User, result: dict, cfg: dict):
        channel_id = cfg.get("shame_channel_id", "").strip()
        if not channel_id:
            return
        try:
            channel_id = int(channel_id)
        except ValueError:
            return

        iq = result["iq_score"]
        band = _wechsler_band(iq)

        embed = discord.Embed(
            title="Redemption Arc",
            description=f"{user.mention} was shamed here before. Not anymore.",
            color=0x111111,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="New Score", value=f"**{iq}** — {band}", inline=True)
        embed.add_field(name="Correct", value=f"{result['answers_correct']}/{result['total_questions']}", inline=True)
        embed.add_field(name="Verdict", value="**PASSED**", inline=True)

        for guild in self.bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def _notify_admin(
        self,
        admin: discord.User,
        member: discord.User,
        result: dict,
        fail_action: str,
        timeout_minutes: int,
    ):
        iq = result["iq_score"]
        passed = result["passed"]
        flagged = result.get("flagged", False)

        embed = discord.Embed(
            title=f"Screen Complete — {member.display_name}",
            color=0x111111,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Score", value=f"**{iq}** — {_wechsler_band(iq)}", inline=True)
        embed.add_field(name="Correct", value=f"{result['answers_correct']}/{result['total_questions']}", inline=True)
        embed.add_field(name="Percentile", value=f"Top {100 - result.get('percentile', 0)}%", inline=True)
        embed.add_field(name="Verdict", value="PASSED" if passed else "FAILED", inline=True)

        if not passed:
            if fail_action == "timeout":
                action_str = f"Timed out for {timeout_minutes}m"
            else:
                action_str = {"kick": "Kicked", "ban": "Banned", "mute": "Muted (role)", "notify": "No action"}.get(fail_action, fail_action)
            embed.add_field(name="Action Taken", value=action_str, inline=True)

        if flagged:
            embed.add_field(name="Flagged", value="Fast responses detected", inline=False)

        embed.set_footer(text=f"Initiated by you  ·  User ID: {member.id}")

        try:
            dm = await admin.create_dm()
            await dm.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TestCog(bot))
