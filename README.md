# MafiaUzBot 🎭

Uzbek (Latin-script) Telegram Mafia game bot built with Python 3.12+, aiogram 3, PostgreSQL, SQLAlchemy 2, and Alembic.

## Status

Development is staged. **Stages 1–2** establish the application structure, validated configuration, Uzbek menu, async SQLAlchemy models, initial Alembic migration, and starter tests/CI. Persistent room creation/join/leave handlers and starter service tests are now committed. The role-assignment and core resolution helpers are now added with unit tests; connecting them to live match phases, night/day actions, and voting remains in progress. Statistics and the protected admin panel remain subsequent stages. Do not treat features as complete until their tests pass.

## Requirements

- Python 3.12+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- PostgreSQL for production
- Optional Redis for later caching/coordination

## Local setup

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set `BOT_TOKEN`, `ADMIN_IDS`, and `DATABASE_URL`. Never commit your real `.env` file or secrets.

3. Run the bot:

   ```bash
   python -m app
   ```

4. Run tests:

   ```bash
   pytest -q
   ```

Apply the initial schema before building persistence-backed features: `alembic upgrade head`. The initial menu and help/rules commands can be tested with a Telegram bot token. The database schema is committed, but room/game persistence is not wired into the bot yet.

## Railway deployment

- Connect this repository to a new Railway service.
- Add a PostgreSQL service and configure `DATABASE_URL` from Railway's database reference variable.
- Set `BOT_TOKEN`, `ADMIN_IDS`, and any optional settings in Railway's Variables panel.
- Deploy from `main`; do not place credentials in source files.
- The current stage starts a Telegram polling worker. Configure one active polling replica unless distributed polling coordination is added.

## Required environment variables

- `BOT_TOKEN` — Telegram bot token
- `ADMIN_IDS` — comma-separated Telegram numeric user IDs
- `DATABASE_URL` — PostgreSQL URL (required for production database stages)

Optional: `REDIS_URL`, `LOG_LEVEL`, `DEFAULT_LANGUAGE`, `MIN_PLAYERS`, `MAX_PLAYERS`.

## Roadmap

1. Project structure, settings, Uzbek menu, startup/shutdown, tests — foundation committed.
2. SQLAlchemy models and initial Alembic migration — schema committed; repositories and runtime wiring remain.
3. User registration and persistent room creation/joining — initial handlers and service tests committed.
4. Role assignment and core game rules — pure logic and tests committed; not yet wired to Telegram matches.
5. Day/night transitions, actions, voting, and win conditions.
6. Profiles, statistics, and leaderboard.
7. Admin tools, audit logging, moderation.
8. Expanded tests, recovery strategy, deployment hardening.

## Security

- Never commit `.env`, Telegram tokens, database passwords, or private user data.
- Admin access must be validated for every command and callback.
- Secret roles/actions must only be delivered privately.
