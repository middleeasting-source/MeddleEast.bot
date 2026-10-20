import os
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask
from threading import Thread

# Koyeb বা Render সার্ভারের জন্য ছোট ওয়েব সার্ভার (পোর্ট ৮০৮০)
app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# ⚙️ কনফিগারেশন (আপনার প্রয়োজন অনুযায়ী পরিবর্তন করুন)
# ==========================================
api_id = 37007922                                # আপনার টেলিগ্রাম API ID
api_hash = '06daa70876742419f268ffaadc42a251'      # আপনার টেলিগ্রাম API Hash
string_session = os.environ.get('SESSION_STRING', '') # রেন্ডার/কোয়েব এনভায়রনমেন্ট ভ্যারিয়েবল

# যে চ্যানেলগুলো থেকে নিউজ সংগ্রহ করা হবে
source_channels = [
    '@QudsNen',
    '@Irna_en',
    '@rtnews',
    '@MFARussia',
    '@CIG_telegram',
    '@ClashReport',
    '@infodefENGLAND',
    '@Middle_East_Spectator',
    '@Slavyangrad',
    '@geopolitics_prime',
    '@DDGeopolitics',
    '@Intelslava'
]

# আপনার নিজস্ব চ্যানেল যেখানে নিউজ পোস্ট হবে
my_channel = '@MiddleEastin'

# আপনার আগের চ্যানেল ক্রেডিট
channel_credit = "\n\nFollow me: @MiddleEastin"
# ==========================================

# ডুপ্লিকেট নিউজ আটকানোর জন্য ট্র্যাক সেট
processed_ids = set()

# StringSession ব্যবহার করে ক্লায়েন্ট ইনিশিয়ালাইজেশন
client = TelegramClient(StringSession(string_session), api_id, api_hash, system_version='4.16.3-vx')

def generate_hashtags(text):
    """নিউজের বিষয়বস্তু বা কিওয়ার্ড চেক করে স্বয়ংক্রিয়ভাবে প্রাসঙ্গিক হ্যাশট্যাগ তৈরি করবে"""
    text_lower = text.lower()
    tags = ["#Breaking", "#MiddleEast", "#News"]
    
    if any(keyword in text_lower for keyword in ['gaza', 'palestine', 'hamas', 'israel', 'idf', 'tel aviv']):
        tags.extend(["#Gaza", "#Palestine", "#Israel"])
    elif any(keyword in text_lower for keyword in ['russia', 'ukraine', 'moscow', 'kyiv', 'putin', 'zelensky']):
        tags.extend(["#Russia", "#Ukraine", "#Conflict"])
    elif any(keyword in text_lower for keyword in ['iran', 'tehran', 'syria', 'lebanon', 'hezbollah', 'yemen', 'houthi']):
        tags.extend(["#Iran", "#Geopolitics", "#MiddleEastCrisis"])
    elif any(keyword in text_lower for keyword in ['oil', 'economy', 'market', 'dollar', 'trade']):
        tags.extend(["#Economy", "#GlobalNews"])
    else:
        tags.append("#WorldNews")
        
    return " " + " ".join(tags)

@client.on(events.NewMessage(chats=source_channels))
async def handler(event):
    try:
        # একই নিউজ বারবার আসা রোধ করতে মেসেজ আইডি চেক করা
        message_unique_key = (event.chat_id, event.id)
        if message_unique_key in processed_ids:
            return
        
        # মেমরি লিমিটেডের মধ্যে রাখতে সেট সাইজ নিয়ন্ত্রণ (সর্বোচ্চ ২০০০টি আইডি)
        if len(processed_ids) > 2000:
            processed_ids.clear()
            
        processed_ids.add(message_unique_key)

        if event.raw_text:
            text = event.raw_text
            
            # ১. সমস্ত লিংক, চ্যানেলের ইউজারনেম (@username) এবং সোর্স/ক্রেডিট মুছে ফেলা
            clean_text = re.sub(
                r'http\S+|www\S+|@\w+|t\.me\/\S+|Source:.*|Via:.*|Credit:.*|频道:.*|Telegram:.*', 
                '', 
                text, 
                flags=re.IGNORECASE
            ).strip()[:850] # ক্যাপশন লিমিট ঠিক রাখতে ৯০০ এর নিচে রাখা হলো
            
            if not clean_text and not event.media:
                return

            # ২. নিউজের সাথে প্রাসঙ্গিক হ্যাশট্যাগ জেনারেট করা
            dynamic_hashtags = generate_hashtags(clean_text)

            # ৩. টেক্সট, হ্যাশট্যাগ এবং আপনার আগের চ্যানেল ক্রেডিট একসাথে সাজানো
            final_caption = clean_text + "\n" + dynamic_hashtags + channel_credit if clean_text else channel_credit.strip()
            
            # ৪. মিডিয়া থাকলে ক্যাপশনসহ এবং না থাকলে শুধু টেক্সট পাঠানো
            if event.media and not getattr(event.media, 'webpage', None):
                await client.send_file(my_channel, event.media, caption=final_caption)
            else:
                await client.send_message(my_channel, final_caption)
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    keep_alive()
    print("বট ক্লাউডে চালু হচ্ছে...")
    client.start()
    client.run_until_disconnected()
