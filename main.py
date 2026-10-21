import asyncio, hashlib, hmac, json, os, time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from threat_parser import parse_message, is_clear, clear_places

load_dotenv()
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = os.getenv("TG_SESSION", "")
CHANNELS = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REQUIRE_AUTH = os.getenv("REQUIRE_TG_AUTH", "0") == "1"
TTL = int(os.getenv("EVENT_TTL_MIN", "30")) * 60

EVENTS: list[dict] = []
client = TelegramClient(StringSession(SESSION) if SESSION else "monitor", API_ID, API_HASH)

def prune():
    now = time.time()
    EVENTS[:] = [e for e in EVENTS if now - e["ts"] < TTL]

def check_init_data(init_data: str) -> bool:
    """Проверка подписи Telegram WebApp initData."""
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        recv = data.pop("hash")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calc, recv) and time.time() - int(data["auth_date"]) < 86400
    except Exception:
        return False

@asynccontextmanager
async def lifespan(app):
    await client.start()
    if not SESSION:
        print("TG_SESSION (вставьте в .env):", StringSession.save(client.session))
    @client.on(events.NewMessage(chats=CHANNELS))
    async def on_msg(ev):
        text = ev.raw_text or ""
        src = getattr(ev.chat, "username", None) or str(ev.chat_id)
        if is_clear(text):
            names = clear_places(text)
            EVENTS[:] = [e for e in EVENTS if not (e["source"] == src and (not names or e["place"] in names))]
            return
        e = parse_message(text, src, ev.date.timestamp())
        if e:
            EVENTS.append(e)
    yield
    await client.disconnect()

app = FastAPI(lifespan=lifespan)

@app.get("/api/events")
async def events_api(x_tg_init_data: str = Header(default="")):
    if REQUIRE_AUTH and not check_init_data(x_tg_init_data):
        raise HTTPException(401, "Откройте карту из Telegram")
    prune()
    return {"now": time.time(), "events": EVENTS}

app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "webapp"), html=True))
