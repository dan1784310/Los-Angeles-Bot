# Arizona State Management — ER:LC API Integration

## Render environment variables

Add these to your Render service:

```text
TOKEN=your_discord_bot_token
MONGO_URI=your_mongodb_connection_string
ERLC_SERVER_KEY=your_erlc_private_server_key
LLC_CHANNEL_ID=your_discord_channel_id_for_low_letter_command_logs
```

`ERLC_SERVER_KEY` is the actual ER:LC private-server API key. It is sent to
`https://api.erlc.gg/v2/server` in the `server-key` header.

## Command logs (the actual working mechanism)

**Important:** ER:LC's Event Webhook does NOT deliver command-log events —
per the official docs (https://apidocs.erlc.gg/event-webhooks), the webhook
only ever sends two kinds of events: in-game chat messages starting with
`;`, and Emergency Calls. There is no "CommandLog" webhook event, no matter
what payload shape you wait for.

Command logs are only available by **polling** the REST API:
`GET https://api.erlc.gg/v2/server?CommandLogs=true` with your server key.

`bot.py` runs a background task (`poll_erlc_command_logs`) that polls this
every 15 seconds, tracks which commands it's already seen, and forwards new
ones through `send_llc_log()` — which posts a Components V2 card to the
channel set by `LLC_CHANNEL_ID` whenever the word after the command has
fewer than 5 letters ("low letter command" detection).

## ER:LC Event Webhook (separate feature)

This is only for what ER:LC's webhook actually sends: `;`-prefixed chat
messages and Emergency Calls. It is **not** used for command logs.

The webhook is an HTTPS endpoint that ER:LC calls with signed JSON POST
requests. This project provides:

```text
https://YOUR-RENDER-SERVICE.onrender.com/erlc/events
```

Put that URL into your ER:LC private-server **Event Webhook** setting.

The endpoint verifies the official ER:LC Ed25519 signature before accepting
events. Currently it only receives and logs the event — no automation is
wired up for it yet.

## Important

Do not commit `.env` or your real ER:LC server key to GitHub. `.gitignore` now
protects `.env`.

The included `.env.example` is safe to copy for local development.

## Files

- `erlc_api.py` — ER:LC API client (`ERLCClient.get_server(...)`) + signed
  webhook verification.
- `.env.example` — safe environment-variable template.

