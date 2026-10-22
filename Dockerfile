FROM python:3.12-slim

# Unbuffered so the platform can stream logs live, and no .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not rebuild the whole layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# bot.py reads PORT for the Flask server; Northflank injects its own PORT at
# runtime, which matches this. The HTTP port is what serves /erlc/events
# and /diag/discord.
ENV PORT=8080
EXPOSE 8080

# bot.py runs the Discord bot in the foreground and the Flask server in a
# daemon thread, so one process serves both.
CMD ["python", "-u", "bot.py"]
