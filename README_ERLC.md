# Arizona State Management — ER:LC API Integration

This version adds the ER:LC API connection foundation only. No Discord commands were added.

## Render environment variables

Add these to your Render service:

```text
TOKEN=your_discord_bot_token
MONGO_URI=your_mongodb_connection_string
ERLC_SERVER_KEY=your_erlc_private_server_key
```

`ERLC_SERVER_KEY` is the actual ER:LC private-server API key. It is sent to
`https://api.erlc.gg/v2/server` in the `server-key` header.

## ER:LC Event Webhook

The ER:LC Event Webhook is **not** another value for `ERLC_SERVER_KEY`.

The webhook is an HTTPS endpoint that ER:LC calls with signed JSON POST requests.
This project provides:

```text
https://YOUR-RENDER-SERVICE.onrender.com/erlc/events
```

Put that URL into your ER:LC private-server **Event Webhook** setting.

The endpoint verifies the official ER:LC Ed25519 signature before accepting events.

Currently, the endpoint only receives and logs the event. It does not create
commands, LLC checks, Discord messages, or other automation yet.

## Important

Do not commit `.env` or your real ER:LC server key to GitHub. `.gitignore` now
protects `.env`.

The included `.env.example` is safe to copy for local development.

## Files added

- `erlc_api.py` — ER:LC API client + signed webhook verification.
- `.env.example` — safe environment-variable template.

## Existing bot

`bot.py` still starts the existing Discord bot and Render Flask health server.
The ER:LC webhook route was added without adding any Discord commands.
