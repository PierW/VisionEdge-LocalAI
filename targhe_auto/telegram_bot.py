"""
targhe_auto/telegram_bot.py
Gestione notifiche Telegram con inline keyboard per la whitelist.

Comandi disponibili:
  /stato  →  veicoli attivi in questo momento nel garage

Dipendenze: pip install python-telegram-bot python-dotenv
"""

import asyncio
import threading
import logging
import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import NetworkError, TimedOut
from dotenv import load_dotenv

# .env è nella root del progetto (un livello sopra targhe_auto/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from whitelist_manager import add_or_update, get_entry

# ─── Logging: mostra solo il primo errore di rete, poi silenzio per 30s ───────
_last_network_error_log: float = 0.0
_NETWORK_ERROR_COOLDOWN  = 30.0   # secondi tra un log e l'altro

class _NetworkThrottleFilter(logging.Filter):
    """Sopprime i log ripetuti di NetworkError/TimedOut dal poller di telegram."""
    def filter(self, record: logging.LogRecord) -> bool:
        global _last_network_error_log
        msg = record.getMessage()
        if "NetworkError" in msg or "TimedOut" in msg or "ConnectError" in msg:
            now = time.monotonic()
            if now - _last_network_error_log < _NETWORK_ERROR_COOLDOWN:
                return False   # sopprimi
            _last_network_error_log = now
            record.msg = "⚠️ [TG] Connessione assente — nuovo tentativo in corso... (log soppressi per 30s)"
            record.args = ()
        return True

for _logger_name in ("httpx", "telegram", "telegram.ext.Updater", "telegram.ext._utils.networkloop"):
    _l = logging.getLogger(_logger_name)
    _l.setLevel(logging.WARNING)
    _l.addFilter(_NetworkThrottleFilter())

# ─── Credenziali da .env ──────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# ─────────────────────────────────────────────────────────────────────────────

# Stato conversazioni in attesa di nome  { targa: autorizzato_bool }
_pending_name: dict[str, bool] = {}

# Callback registrate dal main loop
_on_registered_callback = None   # fn(targa, nome, autorizzato)
_get_stato_callback     = None   # fn() → dict { obj_id: targa_str | None }

_app: Application | None = None
_loop: asyncio.AbstractEventLoop | None = None
_bot_thread: threading.Thread | None = None


# ─── Registrazione callback ───────────────────────────────────────────────────

def set_on_registered_callback(fn):
    """fn(targa: str, nome: str, autorizzato: bool)"""
    global _on_registered_callback
    _on_registered_callback = fn


def set_get_stato_callback(fn):
    """fn() → dict[int, str | None]  —  obj_id → targa letta oppure None"""
    global _get_stato_callback
    _get_stato_callback = fn


# ─── Handler ─────────────────────────────────────────────────────────────────

async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i pulsanti inline Autorizza / Nega."""
    query = update.callback_query
    await query.answer()

    action, targa = query.data.split(":", 1)
    autorizzato = action == "allow"
    _pending_name[targa] = autorizzato

    await query.edit_message_text(
        f"{'✅ Accesso consentito' if autorizzato else '❌ Accesso negato'} per `{targa}`\n\n"
        f"📝 Scrivi il nome del proprietario:",
        parse_mode="Markdown",
    )


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve il nome del proprietario e salva in whitelist."""
    if not _pending_name:
        return

    nome = update.message.text.strip()
    if not nome:
        await update.message.reply_text("⚠️ Nome vuoto, riprova.")
        return

    targa       = next(iter(_pending_name))
    autorizzato = _pending_name.pop(targa)

    add_or_update(targa, nome, autorizzato)

    if _on_registered_callback:
        try:
            _on_registered_callback(targa, nome, autorizzato)
        except Exception as e:
            print(f"⚠️ Errore callback post-registrazione: {e}")

    emoji = "✅" if autorizzato else "❌"
    await update.message.reply_text(
        f"{emoji} Salvato!\n"
        f"🚗 Targa: `{targa}`\n"
        f"👤 Nome: {nome}\n"
        f"🔑 Accesso: {'Consentito' if autorizzato else 'Negato'}",
        parse_mode="Markdown",
    )


async def _cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stato — mostra i veicoli attualmente nel garage."""
    if _get_stato_callback is None:
        await update.message.reply_text("⚠️ Stato non disponibile.")
        return

    try:
        stato: dict = _get_stato_callback()
    except Exception as e:
        await update.message.reply_text(f"❌ Errore lettura stato: {e}")
        return

    if not stato:
        await update.message.reply_text(
            "🅿️ *Garage vuoto* — nessun veicolo rilevato al momento.",
            parse_mode="Markdown",
        )
        return

    righe = [f"🚗 *Veicoli nel garage: {len(stato)}*\n"]
    for obj_id, targa in stato.items():
        if targa:
            entry = get_entry(targa)
            if entry:
                emoji = "✅" if entry["autorizzato"] else "🚫"
                righe.append(f"{emoji} `{targa}` — {entry['nome']} _(ID: {obj_id})_")
            else:
                righe.append(f"❓ `{targa}` — sconosciuto _(ID: {obj_id})_")
        else:
            righe.append(f"🔍 Targa non ancora letta _(ID: {obj_id})_")

    await update.message.reply_text("\n".join(righe), parse_mode="Markdown")


# ─── Error handler globale del bot ───────────────────────────────────────────

async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Intercetta NetworkError/TimedOut senza stampare lo stack trace completo."""
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        # Il filtro sul logger già gestisce il throttle; qui evitiamo il raise
        return
    # Per errori inattesi, stampa comunque (utile in sviluppo)
    print(f"⚠️ [TG] Errore inatteso: {err}")


# ─── API pubblica ─────────────────────────────────────────────────────────────

def send_unknown_plate_alert(targa: str):
    """Invia alert con pulsanti Autorizza/Nega. Thread-safe."""
    if _loop is None or _app is None:
        print("⚠️ [TG] Bot non ancora avviato, skip notifica.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Autorizza", callback_data=f"allow:{targa}"),
        InlineKeyboardButton("❌ Nega",      callback_data=f"deny:{targa}"),
    ]])

    async def _send():
        await _app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"🚨 *Targa sconosciuta rilevata!*\n\n🚗 `{targa}`\n\nVuoi aggiungerla alla whitelist?",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    asyncio.run_coroutine_threadsafe(_send(), _loop)


def send_message(text: str):
    """Invia messaggio semplice. Thread-safe."""
    if _loop is None or _app is None:
        print(f"⚠️ [TG] Bot non avviato, messaggio perso: {text}")
        return

    async def _send():
        await _app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )

    asyncio.run_coroutine_threadsafe(_send(), _loop)


# ─── Avvio bot in thread separato ─────────────────────────────────────────────

def start_bot():
    """Lancia il bot Telegram in un thread daemon separato."""
    global _app, _loop, _bot_thread

    def _run():
        global _app, _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

        _app = Application.builder().token(TELEGRAM_TOKEN).build()
        _app.add_handler(CallbackQueryHandler(_handle_callback))
        _app.add_handler(CommandHandler("stato", _cmd_stato))
        _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
        _app.add_error_handler(_error_handler)

        print("🤖 [TG] Bot Telegram avviato. Comandi: /stato")
        _app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])

    _bot_thread = threading.Thread(target=_run, daemon=True, name="TelegramBot")
    _bot_thread.start()