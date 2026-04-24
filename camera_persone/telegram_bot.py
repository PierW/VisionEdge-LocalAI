"""
camera_persone/telegram_bot.py
Invio snapshot su Telegram.
"""

import threading
import asyncio
import telegram

import config as cfg


def send_snapshot(image_path: str, caption: str):
    """Invia snapshot su Telegram in background."""
    def _run():
        async def _send():
            try:
                async with telegram.Bot(token=cfg.TELEGRAM_TOKEN) as bot:
                    with open(image_path, "rb") as f:
                        await bot.send_photo(
                            chat_id=cfg.TELEGRAM_CHAT_ID,
                            photo=f,
                            caption=caption,
                            read_timeout=20,
                            write_timeout=30,
                        )
                print(f"📤 Snapshot inviato su Telegram")
            except Exception as e:
                print(f"❌ Errore Telegram: {e}")
        asyncio.run(_send())
    threading.Thread(target=_run, daemon=True).start()