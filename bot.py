import os
import re
import asyncio
import logging
import base64
from io import BytesIO
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from openai import AsyncOpenAI

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
    return "Bilingual Telegram News Bot is running!"

def keep_alive():
    Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "10000"))
        ),
        daemon=True
    ).start()

# =====================================
# CONFIGURATION
# =====================================

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

EN_CHANNEL = os.environ.get(
    "EN_CHANNEL", "@MiddleEastin"
)
BN_CHANNEL = os.environ.get(
    "BN_CHANNEL", "@Middleeastinbangla"
)

MODEL = os.environ.get("AI_MODEL", "gpt-4.1-mini")

INTERNATIONAL_SOURCES = [
    "@QudsNen",
    "@Irna_en",
    "@rtnews",
    "@MFARussia",
    "@CIG_telegram",
    "@ClashReport",
    "@infodefENGLAND",
    "@Middle_East_Spectator",
    "@Slavyangrad",
    "@geopolitics_prime",
    "@DDGeopolitics",
    "@Intelslava",
]

BANGLADESH_SOURCES = [
    "@basherkella",
]

if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError(
        "Set API_ID, API_HASH and SESSION_STRING in Render."
    )

if not OPENAI_API_KEY:
    raise RuntimeError(
        "Set OPENAI_API_KEY in Render Environment."
    )

ai = AsyncOpenAI(api_key=OPENAI_API_KEY)

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    connection_retries=None,
    retry_delay=5,
    auto_reconnect=True,
)

# =====================================
# REMOVE PROMOTIONAL CAPTION LINES
# =====================================

def clean_news_text(text):
    if not text:
        return ""

    cleaned = []

    promo = re.compile(
        r"^\s*(follow|join|subscribe|source|via|"
        r"credit|originally posted by)\s*:",
        re.I
    )

    for line in text.splitlines():
        if promo.match(line.strip()):
            continue

        # Remove standalone promotional Telegram links.
        if re.match(
            r"^\s*(https?://)?t\.me/\S+\s*$",
            line.strip(),
            re.I
        ):
            continue

        cleaned.append(line)

    text = "\n".join(cleaned)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

# =====================================
# AI NEWS WRITER / TRANSLATOR
# =====================================

async def write_news(text, language, photo_bytes=None):
    lang = "English" if language == "en" else "Bengali"

    prompt = f"""
Write a news post in {lang}.

Create:
- A clear headline
- A detailed but concise news report
- Relevant hashtags

Rules:
- Use only information supported by the supplied text/image.
- Never invent events, names, quotes, dates or casualty figures.
- Treat claims from interested parties as claims, not proven facts.
- If there is not enough information, return exactly:
INSUFFICIENT_INFORMATION
- Remove source-channel advertisements and promotional requests.
- Do not claim that our channel originally reported the event.
- Do not include any source-channel Follow or Join lines.

Input text:
{text or "(No caption supplied.)"}
"""

    content = [{"type": "input_text", "text": prompt}]

    if photo_bytes:
        encoded = base64.b64encode(photo_bytes).decode("ascii")
        content.append({
            "type": "input_image",
            "image_url": "data:image/jpeg;base64," + encoded,
            "detail": "high",
        })

    response = await ai.responses.create(
        model=MODEL,
        input=[{
            "role": "user",
            "content": content,
        }],
    )

    result = (response.output_text or "").strip()

    if (
        not result
        or "INSUFFICIENT_INFORMATION" in result
    ):
        return ""

    return result

# =====================================
# MEDIA HELPERS
# =====================================

async def get_photo_bytes(message):
    if not message.photo:
        return None

    try:
        buffer = BytesIO()
        await client.download_media(message, file=buffer)
        return buffer.getvalue()
    except Exception:
        logger.exception("Could not download photo for AI analysis")
        return None

async def send_post(destination, text, message, language):
    photo_bytes = await get_photo_bytes(message)

    news = await write_news(
        text,
        language,
        photo_bytes
    )

    if not news:
        logger.warning(
            "Skipped: insufficient verified information."
        )
        return

    if destination == EN_CHANNEL:
        footer = "\n\nFollow: @MiddleEastin"
    else:
        footer = "\n\nঅনুসরণ করুন: @Middleeastinbangla"

    caption = news + footer

    if message.media:
        # Telegram caption limit: keep within safe range.
        await client.send_file(
            destination,
            message.media,
            caption=caption[:1000],
        )
    else:
        await client.send_message(
            destination,
            caption[:4000],
            link_preview=False,
        )

# =====================================
# INTERNATIONAL NEWS
# English -> English channel
# English -> Bengali channel
# =====================================

@client.on(events.NewMessage(chats=INTERNATIONAL_SOURCES))
async def international_news(event):
    try:
        text = clean_news_text(event.raw_text or "")

        if not text and not event.message.photo:
            logger.warning(
                "International post has no text/photo; skipped."
            )
            return

        await send_post(
            EN_CHANNEL,
            text,
            event.message,
            "en",
        )

        await send_post(
            BN_CHANNEL,
            text,
            event.message,
            "bn",
        )

        logger.info(
            "International post processed: %s",
            event.id,
        )

    except Exception:
        logger.exception("International news processing failed")

# =====================================
# BANGLADESH NEWS
# Bengali channel ONLY
# =====================================

@client.on(events.NewMessage(chats=BANGLADESH_SOURCES))
async def bangladesh_news(event):
    try:
        text = clean_news_text(event.raw_text or "")

        if not text and not event.message.photo:
            logger.warning(
                "Bangladesh post has no text/photo; skipped."
            )
            return

        await send_post(
            BN_CHANNEL,
            text,
            event.message,
            "bn",
        )

        logger.info(
            "Bangladesh post sent to Bengali channel: %s",
            event.id,
        )

    except Exception:
        logger.exception("Bangladesh news processing failed")

# =====================================
# START
# =====================================

async def main():
    keep_alive()

    logger.info("Starting bilingual news bot...")
    await client.start()

    me = await client.get_me()

    logger.info("Connected Telegram account: %s", me.id)
    logger.info("English destination: %s", EN_CHANNEL)
    logger.info("Bangla destination: %s", BN_CHANNEL)
    logger.info(
        "International sources: %s",
        len(INTERNATIONAL_SOURCES),
    )
    logger.info(
        "Bangladesh sources: %s",
        len(BANGLADESH_SOURCES),
    )

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
