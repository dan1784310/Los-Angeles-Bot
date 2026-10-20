"""
Single login check against Discord. Run this from your own PC.

It makes exactly one request, so it cannot itself trigger a rate limit. Use
it to find out whether the machine you are running it on is blocked by
Cloudflare (Discord bans the IP, not the token).

    set TOKEN=your_token
    python login_check.py

Read the result:

  200  -> this machine is fine. If the hosted bot fails while this passes,
          the hosted host's IP is the problem, not your token.
  401  -> reachable, but the token was rejected. Not an IP problem.
  429  -> this machine's IP is rate limited or banned too.

Does not import bot.py, does not touch Mongo, does not start the bot.
"""

import asyncio
import os
import sys

import aiohttp

URL = "https://discord.com/api/v10/users/@me"


async def main() -> int:
    token = (os.getenv("TOKEN") or "").strip()
    if not token:
        print("TOKEN is not set in this shell.")
        print("  set TOKEN=your_token   then run it again")
        return 2

    print(f"Token length: {len(token)}")
    print("Making exactly one request to Discord...")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            URL,
            headers={"Authorization": f"Bot {token}"},
        ) as response:
            status = response.status
            body = await response.text()

    print(f"HTTP {status}")

    # Cloudflare's ban page is HTML and mentions 1015. Discord's own rate
    # limit is JSON with a "code" field.
    is_ban_page = "cf-error-ip" in body or "1015" in body[:2000]

    if status == 200:
        import json

        try:
            data = json.loads(body)
            print(f"OK - authenticated as {data.get('username')} ({data.get('id')})")
        except (TypeError, ValueError):
            print("OK - authenticated.")
        print("This machine is NOT blocked.")
        return 0

    if status == 429:
        if is_ban_page:
            print("\n429 with a Cloudflare ban page (error 1015).")
            print("This machine's IP is banned by Discord's edge.")
        else:
            print("\n429 - Discord's own rate limit. This IP is throttled.")
        return 1

    if status == 401:
        print("\n401 - token rejected. This machine reached Discord fine,")
        print("so the IP is OK. Check the TOKEN value.")
        return 1

    print(f"\nUnexpected status {status}: {body[:300]}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
