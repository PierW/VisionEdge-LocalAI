"""
camera_conteggio/telegram_bot.py
Invio riepilogo conteggio su Telegram.
"""

import time
import threading
import asyncio
import telegram

import config as cfg


# Buffer per riepilogo periodico
telegram_buffer = {"IN": 0, "OUT": 0}
timer_active = False
buffer_lock = threading.Lock()


def send_message(text: str):
    """Invia messaggio su Telegram in background."""
    def _run():
        async def _send():
            try:
                async with telegram.Bot(token=cfg.TELEGRAM_TOKEN) as bot:
                    await bot.send_message(
                        chat_id=cfg.TELEGRAM_CHAT_ID,
                        text=text,
                        read_timeout=20,
                        write_timeout=30,
                    )
            except Exception as e:
                print(f"Telegram Error: {e}")
        asyncio.run(_send())
    threading.Thread(target=_run, daemon=True).start()


def telegram_worker(get_counts):
    """Worker che invia riepilogo ogni minuto."""
    global timer_active
    time.sleep(60)
    with buffer_lock:
        if telegram_buffer["IN"] > 0 or telegram_buffer["OUT"] > 0:
            count_in, count_out = get_counts()
            msg = (f"📊 Riepilogo ultimo minuto:\n"
                   f"➡️ Entrati: {telegram_buffer['IN']}\n"
                   f"⬅️ Usciti: {telegram_buffer['OUT']}\n"
                   f"📍 Presenti totali: {max(0, count_in - count_out)}")
            send_message(msg)
            telegram_buffer["IN"] = 0
            telegram_buffer["OUT"] = 0
        timer_active = False


def add_to_telegram_queue(evento: str, get_counts):
    """Aggiunge evento alla coda per il riepilogo."""
    global timer_active
    with buffer_lock:
        telegram_buffer[evento] += 1
        if not timer_active:
            timer_active = True
            threading.Thread(target=telegram_worker, args=(get_counts,), daemon=True).start()