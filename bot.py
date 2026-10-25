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

# =====================================
# LOGGING
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# =====================================
# RENDER WEB SERVER
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "AI-free Telegram News Bot is running!"

def keep_alive():
    Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "10000")),
            use_reloader=False
        ),
        daemon=True
    ).start()

# =====================================
# TELEGRAM CONFIGURATION
# =====================================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]

EN_CHANNEL = os.environ.get(
    "EN_CHANNEL", "@MiddleEastin"
)
BN_CHANNEL = os.environ.get(
    "BN_CHANNEL", "@Middleeastinbangla"
)

# =====================================
# ENGLISH / INTERNATIONAL SOURCES
# =====================================

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

# =====================================
# BENGALI SOURCES
# =====================================

BN_SOURCES = [
    "inb19",
    "SocietyUncensored",
    "StudentsAgainstDiscrimination",
    "bangladeshislamichhatrashibir",
    "bjiofficial",
    "basherkella",
    "wearebdfighter",
]

# =====================================
# YOUR CHANNEL FOOTERS
# =====================================

FOOTER_EN = "\n\nFollow: @MiddleEastin"

FOOTER_BN = (
    "\n\nআমাদের পাশে থাকুন ❤️"
    "\nhttps://t.me/Middleeastinbangla"
)

# =====================================
# DUPLICATE HISTORY
# =====================================

DB_PATH = os.environ.get(
    "DB_PATH", "news_history.db"
)

db = sqlite3.connect(
    DB_PATH, check_same_thread=False
)

db.execute("""
CREATE TABLE IF NOT EXISTS sent_news (
    fingerprint TEXT NOT NULL,
    destination TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    PRIMARY KEY (fingerprint, destination)
)
""")
db.commit()

# Prevent simultaneous handlers from processing the same post.
processing_lock = asyncio.Lock()

# =====================================
# TELEGRAM CLIENT
# =====================================

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    connection_retries=None,
    retry_delay=5,
    auto_reconnect=True,
)

# =====================================
# TEXT CLEANING
# =====================================

def clean_text(text):
    if not text:
        return ""

    cleaned_lines = []

    for line in text.splitlines():
        line = line.strip()

        # Remove promotional lines, not news content.
        if re.match(
            r"^\s*(follow|join|subscribe)\s*:",
            line,
            re.I
        ):
            continue

        if re.match(
            r"^\s*আমাদের পাশে থাকুন\s*$",
            line,
            re.I
        ):
            continue

        if re.match(
            r"^\s*https?://t\.me/\S+\s*$",
            line,
            re.I
        ):
            continue

        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"[ \t]+\n", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()

# =====================================
# DUPLICATE DETECTION
# =====================================

def normalize(text):
    text = text.lower()
    text = re.sub(
        r"https?://\S+|t\.me/\S+",
        " ",
        text,
        flags=re.I
    )
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())

def fingerprint(text):
    return hashlib.sha256(
        normalize(text).encode("utf-8")
    ).hexdigest()

def is_duplicate(text, destination):
    normalized = normalize(text)

    if not normalized:
        return True

    digest = fingerprint(text)

    rows = db.execute(
        """
        SELECT fingerprint, normalized_text
        FROM sent_news
        WHERE destination = ?
        ORDER BY rowid DESC
        LIMIT 2000
        """,
        (destination,)
    ).fetchall()

    for old_hash, old_text in rows:
        if digest == old_hash:
            return True

        if len(normalized) >= 40 and len(old_text) >= 40:
            similarity = SequenceMatcher(
                None, normalized, old_text
            ).ratio()

            if similarity >= 0.90:
                return True

    return False

def remember_news(text, destination):
    db.execute(
        """
        INSERT OR IGNORE INTO sent_news
        (fingerprint, destination, normalized_text)
        VALUES (?, ?, ?)
        """,
        (
            fingerprint(text),
            destination,
            normalize(text)
        )
    )
    db.commit()

# =====================================
# FORWARD NEWS
# =====================================

async def forward_news(event, destination, footer):
    message = event.message
    text = clean_text(message.message or "")

    # Skip posts without text or caption.
    if not text:
        logger.info(
            "Skipped post without text/caption."
        )
        return

    async with processing_lock:
        if is_duplicate(text, destination):
            logger.info(
                "Duplicate skipped for %s",
                destination
            )
            return

        # 소스 채널 크레딧(출처 추가 로직)을 제거함으로 오직 본인 푸터만 추가됩니다.
        caption = text + footer

        try:
            if message.media:
                if len(caption) <= 1000:
                    await client.send_file(
                        destination,
                        message.media,
                        caption=caption
                    )
                else:
                    await client.send_file(
                        destination,
                        message.media
                    )
                    await client.send_message(
                        destination,
                        caption[:4000],
                        link_preview=False
                    )
            else:
                await client.send_message(
                    destination,
                    caption[:4000],
                    link_preview=False
                )

            remember_news(text, destination)

            logger.info(
                "News sent successfully to %s",
                destination
            )

        except Exception:
            logger.exception(
                "Failed to send news to %s",
                destination
            )

# =====================================
# ENGLISH NEWS -> ENGLISH CHANNEL
# =====================================

@client.on(events.NewMessage(chats=EN_SOURCES))
async def english_news(event):
    try:
        await forward_news(
            event,
            EN_CHANNEL,
            FOOTER_EN
        )
    except Exception:
        logger.exception(
            "English news processing failed"
        )

# =====================================
# BENGALI NEWS -> BENGALI CHANNEL
# =====================================

@client.on(events.NewMessage(chats=BN_SOURCES))
async def bengali_news(event):
    try:
        await forward_news(
            event,
            BN_CHANNEL,
            FOOTER_BN
        )
    except Exception:
        logger.exception(
            "Bengali news processing failed"
        )

# =====================================
# START BOT
# =====================================

async def main():
    keep_alive()

    logger.info("Starting AI-free news bot...")
    await client.start()

    me = await client.get_me()

    logger.info(
        "Connected Telegram account: %s",
        me.id
    )
    logger.info(
        "English destination: %s",
        EN_CHANNEL
    )
    logger.info(
        "Bengali destination: %s",
        BN_CHANNEL
    )
    logger.info(
        "English sources: %s",
        len(EN_SOURCES)
    )
    logger.info(
        "Bengali sources: %s",
        len(BN_SOURCES)
    )

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
