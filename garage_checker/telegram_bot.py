"""
garage_checker/telegram_bot.py
Bot Telegram per il monitoraggio posti auto nel garage (senza OCR).
"""

import asyncio
import threading
import logging
import time
import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.error import NetworkError, TimedOut
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─── Throttle log errori di rete ─────────────────────────────────────────────
_last_network_log: float = 0.0
_NETWORK_LOG_COOLDOWN    = 30.0

class _NetworkThrottleFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        global _last_network_log
        msg = record.getMessage()
        if any(k in msg for k in ("NetworkError", "TimedOut", "ConnectError", "nodename")):
            now = time.monotonic()
            if now - _last_network_log < _NETWORK_LOG_COOLDOWN:
                return False
            _last_network_log = now
            record.msg  = "⚠️ [TG] Connessione assente — retry in corso... (log soppressi per 30s)"
            record.args = ()
        return True

for _n in ("httpx", "telegram", "telegram.ext.Updater", "telegram.ext._utils.networkloop"):
    _l = logging.getLogger(_n)
    _l.setLevel(logging.WARNING)
    _l.addFilter(_NetworkThrottleFilter())

# ─── Credenziali ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ─── Callback registrate dal main loop ───────────────────────────────────────
_get_stato_callback     = None   # fn() → dict[roi_id, nome_veicolo|None]

_app: Application | None = None
_loop: asyncio.AbstractEventLoop | None = None
_bot_thread: threading.Thread | None = None


# ─── Registrazione callback ───────────────────────────────────────────────────

def set_get_stato_callback(fn):
    global _get_stato_callback
    _get_stato_callback = fn


# ─── Handler: /stato ─────────────────────────────────────────────────────────

async def _cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _get_stato_callback is None:
        await update.message.reply_text("⚠️ Stato non disponibile.")
        return
    try:
        stato: dict = _get_stato_callback()
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")
        return

    if not stato or all(v is None for v in stato.values()):
        await update.message.reply_text("🅿️ *Garage vuoto* — nessun veicolo al momento.", parse_mode="Markdown")
        return

    righe = [f"🚗 *Situazione posti auto: {sum(1 for v in stato.values() if v is not None)} occupati*"]
    for roi_id, nome_veicolo in stato.items():
        if nome_veicolo:
            righe.append(f"✅ Posto {roi_id}: *{nome_veicolo}* (Occupato)")
        else:
            righe.append(f"⬜ Posto {roi_id}: Libero")

    await update.message.reply_text("\n".join(righe), parse_mode="Markdown")


# ─── Error handler ────────────────────────────────────────────────────────────

async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, (NetworkError, TimedOut)): return
    print(f"⚠️ [TG] Errore inatteso: {context.error}")


# ─── API pubblica ─────────────────────────────────────────────────────────────

def send_message(text: str):
    """Messaggio semplice. Thread-safe."""
    if _loop is None or _app is None:
        print(f"⚠️ [TG] Bot non avviato, perso: {text}")
        return

    async def _send():
        await _app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )

    asyncio.run_coroutine_threadsafe(_send(), _loop)


# ─── Avvio/Chiusura ────────────────────────────────────────────────────────────

def start_bot():
    global _app, _loop, _bot_thread

    def _run():
        global _app, _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

        _app = Application.builder().token(TELEGRAM_TOKEN).build()
        _app.add_handler(CommandHandler("stato", _cmd_stato))
        _app.add_error_handler(_error_handler)

        print("🤖 [TG] Bot avviato. Comandi: /stato")
        _app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])

    _bot_thread = threading.Thread(target=_run, daemon=False, name="TelegramBot")
    _bot_thread.start()
    # Attendi che il loop sia pronto
    time.sleep(0.5)

def stop_bot():
    global _app, _loop, _bot_thread
    if _app and _loop:
        try:
            # Ferma il polling
            future = asyncio.run_coroutine_threadsafe(_app.stop(), _loop)
            future.result(timeout=3.0)
        except Exception:
            pass
        
        # Ferma il loop
        _loop.call_soon_threadsafe(_loop.stop)
        
        # Attendi thread
        if _bot_thread and _bot_thread.is_alive():
            _bot_thread.join(timeout=2.0)
        
        print("🤖 [TG] Bot fermato.")
