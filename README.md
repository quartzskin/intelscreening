# intelscreening

A self-hosted Discord bot that screens server members with an adaptive intelligence test. Scores are computed using Item Response Theory and mapped to WAIS-IV classification bands. Results feed into a real-time admin dashboard.

---

## Stack

| Layer | Tech |
|---|---|
| Bot | discord.py 2.x, slash commands |
| Backend | FastAPI, SQLAlchemy, SQLite |
| Auth | JWT (python-jose), bcrypt, API key |
| Dashboard | Vanilla JS, SSE log streaming |
| Launcher | Rich TUI |

---

## Features

- Adaptive per-question and overall time limits
- Admin-controlled fail actions — mute, kick, ban, timeout, or notify
- Psychometric scoring via 3-parameter logistic IRT with Newton-Raphson MLE
- Live leaderboard, per-member history, and flagged-result review
- Public shaming channel — failed results post with an animal-cognition comparison, nearest national IQ average, and a random roast, with an admin-editable message and role ping
- Head-to-head IQ duels between members, loser gets shamed automatically
- Redemption posts when a previously-shamed member later passes
- Optional nickname branding (`[IQ ##]`) on failed members, auto-cleared on a pass
- Weekly "Dumbest of the Week" digest on a configurable day/hour
- In-Discord `/config` for any setting, with autocomplete — no dashboard trip required
- Audit log channel for admin actions
- CSV question import with a dry-run preview before committing
- CSV question import and per-question discrimination analytics
- Real-time log streaming to the web dashboard via SSE
- Rich TUI launcher with service status, keyboard controls, and backend-down webhook alerts

---

## Setup

**Requirements:** Python 3.12+, a Discord bot with the `members` intent enabled.

```bash
setup.bat
```

Edit `.env`:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
| `DISCORD_GUILD_ID` | Right-click server → Copy Server ID |
| `API_SECRET_KEY` | `py -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PASSWORD` | Web UI login password |
| `JWT_SECRET` | `py -c "import secrets; print(secrets.token_hex(32))"` |

```bash
py launcher.py
```

Dashboard → `http://127.0.0.1:8000`

Launcher keys: `R` restart all · `B` restart backend · `O` restart bot · `Q` quit

---

## Commands

| Command | Who | Description |
|---|---|---|
| `/test` | Members | Start the screening test (sent to DMs) |
| `/iq-duel` | Members | Challenge another member to a head-to-head test |
| `/screen` | Admins | Send a test to a specific member with custom parameters |
| `/iq` | Admins | Look up a member's latest score, including retest countdown |
| `/iq-leaderboard` | Admins | Top 10 passing scores |
| `/iq-shame-leaderboard` | Admins | Bottom 10 failing scores, all-time |
| `/iq-reset` | Admins | Clear a member's history and remove screening roles |
| `/iq-history` | Admins | Full test history for a member |
| `/shame-config` | Admins | Pick the shame channel and ping role (native Discord pickers) |
| `/config` | Admins | View or set any config key, with autocomplete |

---

## Configuration

Set from the dashboard under **Config**:

| Key | Default | Description |
|---|---|---|
| `iq_threshold_min` | `85` | Minimum IQ to pass |
| `questions_per_test` | `20` | Questions per session |
| `time_per_question` | `45` | Seconds per question |
| `allow_retest` | `false` | Allow members to retest |
| `retest_cooldown_hours` | `24` | Hours between retests |
| `flag_threshold_seconds` | `4` | Average response time below this flags the result |
| `passed_role_id` | — | Role assigned on pass |
| `failed_role_id` | — | Role assigned on fail (mute action) |
| `results_channel_id` | — | Channel to post results |
| `webhook_url` | — | Discord webhook for fail/flag notifications |
| `shame_channel_id` | — | Channel for public shame posts (set via `/shame-config`) |
| `shame_role_id` | — | Role pinged on each shame post |
| `shame_nickname` | `false` | Append `[IQ ##]` to a failed member's nickname |
| `audit_channel_id` | — | Channel for admin-action audit logs |
| `digest_channel_id` | — | Channel for the weekly "Dumbest of the Week" post |
| `digest_day` / `digest_hour` | `sunday` / `12` | When the weekly digest fires (UTC) |

`ALERT_WEBHOOK_URL` (in `.env`, not the dashboard) fires a webhook from the launcher itself if the backend goes down unexpectedly while the launcher keeps running.

---

## Scoring

Ability is estimated using the 3-parameter logistic model:

```
P(correct | θ) = c + (1 - c) / (1 + exp(-(θ - b)))
```

`θ` = latent ability, `b` = item difficulty (1–5 stars mapped to −2 to +2 logits), `c = 0.25` guessing parameter. `θ` is estimated via Newton-Raphson MLE, then converted to IQ:

```
IQ = 100 + (15 / (π / √3)) × θ
```

WAIS-IV classification bands (Wechsler, 2008):

| Band | Range |
|---|---|
| Very Superior | ≥ 130 |
| Superior | 120 – 129 |
| High Average | 110 – 119 |
| Average | 90 – 109 |
| Low Average | 80 – 89 |
| Borderline | 70 – 79 |
| Extremely Low | < 70 |

---

## Project Structure

```
├── bot/
│   ├── cogs/
│   │   ├── admin.py       # admin slash commands
│   │   └── test.py        # test runner and embed builders
│   ├── api_client.py      # backend API wrapper
│   └── main.py
├── backend/
│   ├── routers/
│   │   ├── questions.py   # question CRUD, CSV import, analytics
│   │   ├── results.py     # IRT scoring, submission, leaderboard
│   │   ├── config.py      # key-value config
│   │   └── logs.py        # SSE log streaming
│   ├── static/
│   │   └── index.html     # admin dashboard
│   ├── auth.py
│   ├── database.py
│   ├── log_buffer.py
│   ├── main.py
│   └── models.py
├── launcher.py            # Rich TUI process manager
├── seed_questions.py      # question bank seeder
├── setup.bat
└── .env.example
```

---

## License

MIT
