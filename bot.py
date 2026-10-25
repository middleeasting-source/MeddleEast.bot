import os
import re
import asyncio
import sqlite3
import hashlib
import logging
from difflib import SequenceMatcher
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Render health check
app = Flask(__name__)

@app.route("/")
def home():
    return "AI-free Telegram News Bot is running!"

def keep_alive():
    Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "10000"))
        ),
        daemon=True
    ).start()

# Telegram settings
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]

EN_CHANNEL = os.environ.get("EN_CHANNEL", "@MiddleEastin")
BN_CHANNEL = os.environ.get("BN_CHANNEL", "@Middleeastinbangla")

# English/international sources
EN_SOURCES = [
    "QudsNen",
    "Irna_en",
    "rtnews",
    "MFARussia",
    "CIG_telegram",
    "ClashReport",
    "infodefENGLAND",
    "Middle_East_Spectator",
    "Slavyangrad",
    "geopolitics_prime",
    "DDGeopolitics",
    "Intelslava",
]

# Bengali sources
BN_SOURCES = [
    "inb19",
    "SocietyUncensored",
    "StudentsAgainstDiscrimination",
    "bangladeshislamichhatrashibir",
    "bjiofficial",
    "basherkella",
    "wearebdfighter",
]

FOOTER_EN = "\n\nFollow: @MiddleEastin"
FOOTER_BN = "\n\nআমাদের পাশে থাকুন ❤️\nhttps://t.me/Middleeastinbangla"

DB_PATH = os.environ.get("DB_PATH", "news_history.db")

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""
CREATE TABLE IF NOT EXISTS sent_news (
    fingerprint TEXT PRIMARY KEY,
    normalized_text TEXT NOT NULL
)
""")
db.commit()

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    connection_retries=None,
    retry_delay=5,
    auto_reconnect=True,
)

def normalize(text):
    text = text.lower()
    text = re.sub(r"https?://\S+|t\.me/\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())

def fingerprint(text):
    return hashlib.sha256(
        normalize(text).encode("utf-8")
    ).hexdigest()

def is_duplicate(text):
    cleaned = normalize(text)
    if not cleaned:
        return True

    rows = db.execute(
        "SELECT fingerprint, normalized_text "
        "FROM sent_news ORDER BY rowid DESC LIMIT 2000"
    ).fetchall()

    digest = fingerprint(text)

    for old_hash, old_text in rows:
        if digest == old_hash:
            return True

        if len(cleaned) >= 40 and len(old_text) >= 40:
            if SequenceMatcher(
                None, cleaned, old_text
            ).ratio() >= 0.90:
                return True

    db.execute(
        "INSERT OR IGNORE INTO sent_news "
        "(fingerprint, normalized_text) VALUES (?, ?)",
        (digest, cleaned)
    )
    db.commit()
    return False

def clean_text(text):
    if not text:
        return ""

    lines = []
    for line in text.splitlines():
        if re.match(
            r"^\s*(follow|join|subscribe)\s*:",
            line,
            re.I
        ):
            continue
        lines.append(line)

    return "\n".join(lines).strip()

async def forward_news(event, destination, footer):
    message = event.message
    text = clean_text(message.message or "")

    # Skip media-only posts without a caption
    if not text:
        logger.info("Skipped post without text/caption.")
        return

    if is_duplicate(text):
        logger.info("Duplicate news skipped.")
        return

    caption = text + footer
    source = event.chat
    source_username = getattr(source, "username", None)

    if source_username:
        caption = (
            text
            + f"\n\nSource: https://t.me/{source_username}"
            + footer
        )

    if message.media:
        await client.send_file(
            destination,
            message.media,
            caption=caption[:1000]
        )
    else:
        await client.send_message(
            destination,
            caption[:4000],
            link_preview=False
        )

    logger.info("News forwarded to %s", destination)

@client.on(events.NewMessage(chats=EN_SOURCES))
async def english_news(event):
    try:
        await forward_news(
            event,
            EN_CHANNEL,
            FOOTER_EN
        )
    except Exception:
        logger.exception("English news forwarding failed")

@client.on(events.NewMessage(chats=BN_SOURCES))
async def bengali_news(event):
    try:
        await forward_news(
            event,
            BN_CHANNEL,
            FOOTER_BN
        )
    except Exception:
        logger.exception("Bengali news forwarding failed")

async def main():
    keep_alive()
    logger.info("Starting AI-free news bot...")
    await client.start()

    me = await client.get_me()
    logger.info("Connected Telegram account: %s", me.id)
    logger.info("English destination: %s", EN_CHANNEL)
    logger.info("Bengali destination: %s", BN_CHANNEL)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
