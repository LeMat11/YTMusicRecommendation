# YT Music Daily Bot

A personal automation bot that refreshes your YouTube Music playlists every day with AI-curated song recommendations, tailored to each user's listening history and taste.

## How It Works

1. **Fetches taste data** — reads your YouTube Music listening history and/or liked songs
2. **Asks an AI** — sends your taste profile to an AI model (Stepfun or Gemini) and gets back fresh recommendations
3. **Deduplicates** — skips songs you've already been recommended in the past 30 days
4. **Updates playlist** — clears the old playlist and fills it with new songs

Each user can have their own playlist, mood preferences, and recommendation count.

## Features

- Multi-user support (each user has their own auth, playlist, and preferences)
- Pluggable AI backend: **Stepfun** (`step-3.5-flash`) or **Google Gemini** (`gemini-2.5-flash`)
- Smart deduplication via a local SQLite database (30-day memory)
- Mixed taste mode: blend history + liked songs at a configurable ratio
- Retry logic for network errors
- Waits for internet on startup (safe for boot-time automation)
- Daily run log at `run_history.log`

## Project Structure

```
.
├── main.py              # Main script
├── db_manager.py        # SQLite memory (deduplication)
├── setup_login.py       # One-time OAuth login helper
├── make_browser_json.py # Helper to generate browser auth files
├── requirements.txt
├── .env                 # Your secrets (never committed)
├── .env.example         # Template for .env
├── users.local.json     # Private user preferences (never committed)
├── users.example.json   # Anonymous user configuration template
├── com.example.ytmusicbot.plist  # macOS LaunchAgent template
└── run_daily.command    # Manual run shortcut (macOS)
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure secrets

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
AI_BACKEND=stepfun          # or "gemini"

STEPFUN_API_KEY=your_key_here
GENAI_API_KEY=your_key_here  # only needed if using gemini

YTMUSIC_CLIENT_ID=your_google_oauth_client_id
YTMUSIC_CLIENT_SECRET=your_google_oauth_client_secret
```

To get YouTube Music OAuth credentials, create a project in [Google Cloud Console](https://console.cloud.google.com/), enable the YouTube Data API, and download the OAuth client secret.

### 3. Log in to YouTube Music

Run the login helper once per user account:

```bash
python setup_login.py
```

This opens a browser for OAuth and saves a `browser_<user>.json` auth file locally.

### 4. Configure users

Copy the anonymous template, then edit the local file with your account-specific settings:

```bash
cp users.example.json users.local.json
```

`users.local.json` is gitignored because it can reveal account names and listening preferences. Set `YTMUSIC_USERS_FILE` if you want to store it somewhere else.

If you use browser authentication, convert copied request headers with explicit, local filenames:

```bash
python make_browser_json.py headers_raw.txt browser_user1.json
```

### 5. Run manually

```bash
python main.py
```

## Automatic Daily Run (macOS)

A `launchd` plist is included to run the bot automatically every day.

1. Copy the template outside the repository.
2. Replace `__PYTHON_PATH__` and `__PROJECT_DIR__` in the installed copy.
3. Load the customized LaunchAgent:

```bash
cp com.example.ytmusicbot.plist ~/Library/LaunchAgents/com.example.ytmusicbot.plist
# Edit ~/Library/LaunchAgents/com.example.ytmusicbot.plist now.
launchctl load ~/Library/LaunchAgents/com.example.ytmusicbot.plist
```

The bot will run daily at 11:00 AM. Logs go to `/tmp/ytmusicbot.log` and `/tmp/ytmusicbot_err.log`.

## Notes

- Auth files (`browser_*.json`, `oauth_*.json`) and the database (`music_memory.db`) are gitignored — they stay only on your local machine
- The `.env` file is gitignored — never commit it
- `users.local.json`, raw headers, cookies, and logs are gitignored because they may contain private data
- If your YouTube Music cookies expire, re-run `setup_login.py` for that user
