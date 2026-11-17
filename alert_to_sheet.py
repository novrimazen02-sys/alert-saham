#!/usr/bin/env python3
"""
Alert DataSaham0Bot / DataSahamBot (Telegram) -> Google Sheet "Data Telegram", otomatis.

- HANYA membaca chat bot di ALLOWED_BOTS. Chat/grup lain diabaikan: tidak dibaca, tidak disimpan.
- Setiap alert "Formula-based alert" dikirim apa adanya (teks asli) ke Apps Script (Code.gs).
- Saat mulai, alert hari ini yang sudah ada ikut dikirim; alert dobel otomatis dibuang di Sheet.
- Log hanya mencatat JUMLAH alert (tanpa kode saham / harga / isi chat).
"""
import asyncio
import datetime as dt
import json
import logging
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIB = dt.timezone(dt.timedelta(hours=7))
KEYS = ("API_ID", "API_HASH", "SESSION_STRING", "SHEET_WEBHOOK_URL", "SHEET_SECRET", "ALLOWED_BOTS", "RUN_UNTIL")
ALERT_RE = re.compile(r"^\[(\d{1,2})/(\d{1,2})/(\d{4}) [\d:]+\]\s*Formula-based alert")


def load_config():
    cfg = {k: os.environ[k] for k in KEYS if os.environ.get(k)}
    for k in ("API_ID", "API_HASH", "SESSION_STRING", "SHEET_WEBHOOK_URL", "SHEET_SECRET"):
        if not cfg.get(k):
            sys.exit(f"Secret {k} belum diisi di GitHub (Settings > Secrets and variables > Actions).")
    cfg["ALLOWED_BOTS"] = [b.strip().lstrip("@") for b in cfg.get("ALLOWED_BOTS", "DataSaham0Bot,DataSahamBot").split(",") if b.strip()]
    return cfg


def to_alert(text, bot, msg_id):
    text = (text or "").strip()
    m = ALERT_RE.match(text)
    if not m:
        return None
    d, mo, y = m.groups()
    return {"key": f"{bot}:{msg_id}", "date": f"{y}-{int(mo):02d}-{int(d):02d}", "text": text}


class SheetSender:
    def __init__(self, url, secret):
        self.url, self.secret = url, secret

    def _post(self, alerts):
        data = json.dumps({"secret": self.secret, "alerts": alerts}).encode()
        req = urllib.request.Request(self.url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read().decode() or "{}")
        if not res.get("ok"):
            raise RuntimeError(f"Sheet menolak: {res.get('error')}")
        return res

    async def send(self, alerts):
        if not alerts:
            return True
        for attempt in range(4):
            try:
                res = await asyncio.to_thread(self._post, alerts)
                logging.info("Terkirim ke Sheet: %s alert (baru %s)", res.get("received"), res.get("added"))
                return True
            except Exception as e:  # noqa: BLE001
                logging.warning("Gagal kirim (percobaan %d): %s", attempt + 1, e)
                await asyncio.sleep(5 * (attempt + 1))
        return False


async def main():
    cfg = load_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(cfg["SESSION_STRING"]), int(cfg["API_ID"]), cfg["API_HASH"])
    sender = SheetSender(cfg["SHEET_WEBHOOK_URL"], cfg["SHEET_SECRET"])
    await client.connect()
    if not await client.is_user_authorized():
        sys.exit("SESSION_STRING tidak valid / sudah dicabut. Buat ulang di Google Colab.")

    bots = {}
    for name in cfg["ALLOWED_BOTS"]:
        try:
            ent = await client.get_entity(name)
            bots[ent.id] = name
        except Exception as e:  # noqa: BLE001
            logging.warning("Bot %s tidak ditemukan: %s", name, e)
    if not bots:
        sys.exit("Tidak ada chat bot yang bisa dibaca.")
    logging.info("Mendengarkan HANYA chat: %s", ", ".join(bots.values()))

    # Ambil alert hari ini yang mungkin terlewat (hanya dari chat bot di atas)
    start_today = dt.datetime.now(WIB).replace(hour=0, minute=0, second=0, microsecond=0)
    backlog = []
    for bid, name in bots.items():
        async for msg in client.iter_messages(bid, limit=3000):
            if msg.date.astimezone(WIB) < start_today:
                break
            a = to_alert(msg.raw_text, name, msg.id)
            if a:
                backlog.append(a)
    backlog.reverse()
    logging.info("Alert hari ini yang dicek ulang: %d", len(backlog))
    for i in range(0, len(backlog), 200):
        await sender.send(backlog[i:i + 200])

    queue, lock = [], asyncio.Lock()

    @client.on(events.NewMessage(chats=list(bots.keys())))
    async def on_alert(event):
        a = to_alert(event.raw_text, bots.get(event.chat_id, str(event.chat_id)), event.id)
        if a:
            async with lock:
                queue.append(a)

    async def flusher():
        while True:
            await asyncio.sleep(5)
            async with lock:
                batch, queue[:] = queue[:], []
            if batch and not await sender.send(batch):
                async with lock:
                    queue[:0] = batch      # coba lagi di putaran berikutnya

    asyncio.create_task(flusher())
    logging.info("Siap. Alert baru otomatis masuk ke Google Sheet.")

    h, m = map(int, cfg.get("RUN_UNTIL", "16:15").split(":"))
    end = dt.datetime.now(WIB).replace(hour=h, minute=m, second=0, microsecond=0)
    secs = max(0, (end - dt.datetime.now(WIB)).total_seconds())
    logging.info("Berjalan sampai %02d:%02d WIB", h, m)
    try:
        await asyncio.wait_for(client.run_until_disconnected(), timeout=secs)
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(6)
    async with lock:
        batch, queue[:] = queue[:], []
    await sender.send(batch)
    await client.disconnect()
    logging.info("Sesi selesai.")


if __name__ == "__main__":
    asyncio.run(main())
