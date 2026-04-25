"""
targhe_auto/telegram_bot.py

Comandi: /stato

Flusso targa sconosciuta:
  1. Foto + targa + bottoni [✅ Autorizza] [❌ Nega] [⏭ Skippa] [✏️ Modifica targa]
  2a. Autorizza/Nega  → chiede nome → salva in whitelist
  2b. Skippa          → ignora per questa sessione
  2c. Modifica targa  → chiede la targa corretta →
                        mostra nuovi bottoni Autorizza/Nega (su messaggio testo, non foto)
                        → chiede nome → salva
"""

import asyncio
import threading
import logging
import time
import os
from typing import Dict, Set, Optional

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

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from whitelist_manager import add_or_update, get_entry

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

# ─── Stato conversazioni ─────────────────────────────────────────────────────
# Targa in attesa del nome dopo Autorizza/Nega: { targa: autorizzato_bool }
_pending_name: Dict[str, bool] = {}

# Targa in attesa di correzione: { "correction": targa_originale }
# Usiamo una chiave fissa perché c'è sempre al massimo una correzione attiva
_pending_correction: Dict[str, str] = {}

# Targhe skippate per questa sessione
_skippate: Set[str] = set()

# ─── Callback registrate dal main loop ───────────────────────────────────────
_on_registered_callback = None   # fn(targa, nome, autorizzato)
_on_skip_callback       = None   # fn(targa)
_on_correction_callback = None   # fn(targa_originale, targa_corretta)
_get_stato_callback     = None   # fn() -> Dict[int, Optional[str]]

_app: Optional[Application] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_bot_thread: Optional[threading.Thread] = None


# ─── Registrazione callback ───────────────────────────────────────────────────

def set_on_registered_callback(fn):
    global _on_registered_callback
    _on_registered_callback = fn

def set_on_skip_callback(fn):
    global _on_skip_callback
    _on_skip_callback = fn

def set_on_correction_callback(fn):
    global _on_correction_callback
    _on_correction_callback = fn

def set_get_stato_callback(fn):
    global _get_stato_callback
    _get_stato_callback = fn

def is_skippata(targa: str) -> bool:
    return targa in _skippate


# ─── Handler: bottoni inline ─────────────────────────────────────────────────

async def _handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts  = query.data.split(":", 1)
    action = parts[0]
    targa  = parts[1] if len(parts) > 1 else ""

    # ── Skippa ────────────────────────────────────────────────────────────────
    if action == "skip":
        _skippate.add(targa)
        _pending_name.pop(targa, None)
        _pending_correction.clear()
        if _on_skip_callback:
            try:
                _on_skip_callback(targa)
            except Exception as e:
                print(f"⚠️ Errore skip callback: {e}")
        # Il messaggio originale ha una foto → usa edit_message_caption
        try:
            await query.edit_message_caption(
                caption=f"⏭ `{targa}` — ignorata per questa sessione.",
                parse_mode="Markdown",
            )
        except Exception:
            await query.edit_message_text(
                text=f"⏭ `{targa}` — ignorata per questa sessione.",
                parse_mode="Markdown",
            )
        return

    # ── Modifica targa ────────────────────────────────────────────────────────
    if action == "edit":
        _pending_correction["correction"] = targa
        try:
            await query.edit_message_caption(
                caption=f"✏️ OCR ha letto: `{targa}`\n\nScrivi la targa corretta:",
                parse_mode="Markdown",
            )
        except Exception:
            await query.edit_message_text(
                text=f"✏️ OCR ha letto: `{targa}`\n\nScrivi la targa corretta:",
                parse_mode="Markdown",
            )
        return

    # ── Autorizza / Nega ──────────────────────────────────────────────────────
    if action in ("allow", "deny"):
        autorizzato = action == "allow"
        _pending_name[targa] = autorizzato
        label = "✅ Accesso consentito" if autorizzato else "❌ Accesso negato"

        # Il messaggio può essere una foto (alert originale) o testo (dopo correzione)
        # Proviamo edit_message_caption prima, fallback su edit_message_text
        try:
            await query.edit_message_caption(
                caption=f"{label} per `{targa}`\n\n📝 Scrivi il nome del proprietario:",
                parse_mode="Markdown",
            )
        except Exception:
            await query.edit_message_text(
                text=f"{label} per `{targa}`\n\n📝 Scrivi il nome del proprietario:",
                parse_mode="Markdown",
            )
        return


# ─── Handler: messaggi testo ─────────────────────────────────────────────────

async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = update.message.text.strip()
    if not testo:
        return

    # ── Priorità 1: in attesa di correzione targa ─────────────────────────────
    if "correction" in _pending_correction:
        targa_originale = _pending_correction.pop("correction")
        targa_corretta  = testo.upper()

        # Notifica il main loop della correzione (aggiorna targa_per_id)
        if _on_correction_callback:
            try:
                _on_correction_callback(targa_originale, targa_corretta)
            except Exception as e:
                print(f"⚠️ Errore correction callback: {e}")

        # Invia nuovo messaggio testo con bottoni Autorizza/Nega per la targa corretta
        await update.message.reply_text(
            f"✏️ Targa corretta: `{targa_corretta}`\n"
            f"_(era: `{targa_originale}`)_\n\n"
            f"Scegli cosa fare:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Autorizza", callback_data=f"allow:{targa_corretta}"),
                InlineKeyboardButton("❌ Nega",      callback_data=f"deny:{targa_corretta}"),
            ]])
        )
        return

    # ── Priorità 2: in attesa del nome proprietario ───────────────────────────
    if not _pending_name:
        return

    targa       = next(iter(_pending_name))
    autorizzato = _pending_name.pop(targa)

    add_or_update(targa, testo, autorizzato)

    if _on_registered_callback:
        try:
            _on_registered_callback(targa, testo, autorizzato)
        except Exception as e:
            print(f"⚠️ Errore callback post-registrazione: {e}")

    emoji = "✅" if autorizzato else "❌"
    await update.message.reply_text(
        f"{emoji} Salvato!\n🚗 `{targa}`\n👤 {testo}\n"
        f"🔑 {'Consentito' if autorizzato else 'Negato'}",
        parse_mode="Markdown",
    )


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

    if not stato:
        await update.message.reply_text(
            "🅿️ *Garage vuoto* — nessun veicolo al momento.",
            parse_mode="Markdown",
        )
        return

    righe = [f"🚗 *Veicoli nel garage: {len(stato)}*\n"]
    for obj_id, targa in stato.items():
        if targa:
            entry = get_entry(targa)
            if entry:
                e = "✅" if entry["autorizzato"] else "🚫"
                righe.append(f"{e} `{targa}` — {entry['nome']} _(ID: {obj_id})_")
            else:
                righe.append(f"❓ `{targa}` — non in whitelist _(ID: {obj_id})_")
        else:
            righe.append(f"🔍 Targa non letta _(ID: {obj_id})_")

    await update.message.reply_text("\n".join(righe), parse_mode="Markdown")


# ─── Error handler ────────────────────────────────────────────────────────────

async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, (NetworkError, TimedOut)):
        return
    print(f"⚠️ [TG] Errore inatteso: {context.error}")


# ─── API pubblica ─────────────────────────────────────────────────────────────

def send_unknown_plate_alert(targa: str, photo_path: Optional[str] = None):
    """Invia foto (se disponibile) + bottoni. Thread-safe."""
    if _loop is None or _app is None:
        print("⚠️ [TG] Bot non avviato, skip alert.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Autorizza", callback_data=f"allow:{targa}"),
        InlineKeyboardButton("❌ Nega",      callback_data=f"deny:{targa}"),
    ], [
        InlineKeyboardButton("⏭ Skippa",         callback_data=f"skip:{targa}"),
        InlineKeyboardButton("✏️ Modifica targa", callback_data=f"edit:{targa}"),
    ]])
    caption = (
        f"🚨 *Targa sconosciuta rilevata!*\n\n"
        f"🚗 `{targa}`\n\n"
        f"Cosa vuoi fare?"
    )

    async def _send():
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                await _app.bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID,
                    photo=f,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
        else:
            await _app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=caption,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

    asyncio.run_coroutine_threadsafe(_send(), _loop)


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


# ─── Avvio ────────────────────────────────────────────────────────────────────

def start_bot():
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

        print("🤖 [TG] Bot avviato. Comandi: /stato")
        _app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])

    _bot_thread = threading.Thread(target=_run, daemon=True, name="TelegramBot")
    _bot_thread.start()