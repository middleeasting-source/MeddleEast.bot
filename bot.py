import os
import re
import asyncio
import logging
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession


# =====================================
# LOGGING: Render Logs-এ সমস্যা দেখাবে
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
    return "Telegram News Bot is running!"


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    thread = Thread(target=run_web_server, daemon=True)
    thread.start()


# =====================================
# TELEGRAM CONFIGURATION
# Render Environment Variables থেকে নেবে
# =====================================

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

MY_CHANNEL = os.environ.get("MY_CHANNEL", "@MiddleEastin")

SOURCE_CHANNELS = [
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

CHANNEL_CREDIT = "\n\nFollow: @MiddleEastin"


# =====================================
# CHECK REQUIRED SETTINGS
# =====================================

if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError(
        "Missing API_ID, API_HASH, or SESSION_STRING "
        "in Render Environment Variables."
    )


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
# AUTOMATIC HASHTAGS
# =====================================

def generate_hashtags(text):
    text_lower = text.lower()

    tags = ["#Breaking", "#News"]

    if any(word in text_lower for word in [
        "gaza", "palestine", "hamas", "israel",
        "idf", "tel aviv"
    ]):
        tags.extend(["#Gaza", "#Palestine", "#Israel"])

    elif any(word in text_lower for word in [
        "russia", "ukraine", "moscow",
        "kyiv", "putin", "zelensky"
    ]):
        tags.extend(["#Russia", "#Ukraine", "#WorldNews"])

    elif any(word in text_lower for word in [
        "iran", "tehran", "syria", "lebanon",
        "hezbollah", "yemen", "houthi"
    ]):
        tags.extend(["#Iran", "#MiddleEast", "#Geopolitics"])

    elif any(word in text_lower for word in [
        "oil", "economy", "market", "dollar", "trade"
    ]):
        tags.extend(["#Economy", "#GlobalNews"])

    else:
        tags.extend(["#WorldNews", "#InternationalNews"])

    return " ".join(dict.fromkeys(tags))


# =====================================
# CLEAN NEWS TEXT
# =====================================

def clean_news_text(text):
    if not text:
        return ""

    # সরাসরি লিংক ও প্রচলিত সোর্স ক্রেডিট বাদ দেওয়া
    text = re.sub(r"https?://\S+|www\.\S+", "", text, flags=re.I)
    text = re.sub(r"t\.me/\S+", "", text, flags=re.I)
    text = re.sub(
        r"(?im)^\s*(source|via|credit)\s*:.*$",
        "",
        text
    )

    # অতিরিক্ত ফাঁকা লাইন পরিষ্কার
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =====================================
# FORWARD NEW POSTS TO YOUR CHANNEL
# =====================================

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_new_post(event):
    try:
        original_text = event.raw_text or ""
        clean_text = clean_news_text(original_text)

        hashtags = generate_hashtags(clean_text)

        # Media caption-এর সীমা মাথায় রেখে লেখা ছোট রাখা
        if event.message.media:
            clean_text = clean_text[:650]
        else:
            clean_text = clean_text[:3500]

        parts = []

        if clean_text:
            parts.append(clean_text)

        if hashtags:
            parts.append(hashtags)

        parts.append(CHANNEL_CREDIT.strip())

        final_caption = "\n\n".join(parts)

        if event.message.media:
            await client.send_file(
                MY_CHANNEL,
                event.message.media,
                caption=final_caption[:1000]
            )

        elif clean_text:
            await client.send_message(
                MY_CHANNEL,
                final_caption[:4000],
                link_preview=False
            )

        else:
            logger.info(
                "Empty text post skipped. Source chat ID: %s",
                event.chat_id
            )
            return

        logger.info(
            "Post sent successfully. Source chat ID: %s, message ID: %s",
            event.chat_id,
            event.id
        )

    except Exception:
        logger.exception(
            "Failed to process post. Chat ID: %s, message ID: %s",
            event.chat_id,
            event.id
        )


# =====================================
# START BOT
# =====================================

async def main():
    keep_alive()

    logger.info("Telegram News Bot starting...")

    await client.start()

    me = await client.get_me()
    logger.info("Telegram account connected successfully: %s", me.id)
    logger.info("Destination channel: %s", MY_CHANNEL)
    logger.info("Listening to %s source channels.", len(SOURCE_CHANNELS))

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
