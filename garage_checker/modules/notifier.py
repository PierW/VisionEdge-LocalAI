"""
garage_checker/modules/notifier.py

Telegram bot and notification management.
"""

import asyncio
import threading
import logging
import os
import cv2
from typing import Optional, Callable
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, whitelist_manager):
        self.token = token
        self.chat_id = chat_id
        self.whitelist = whitelist_manager
        
        self.app = None
        self.loop = None
        self.thread = None
        
        # Callbacks for engine
        self.on_skip = None
        self.on_correction = None
        self.on_registered = None
        self.get_status = None

        # State for interactions
        self.pending_name = {}  # { targa: autorizzato_bool }
        self.pending_correction = {}  # { "correction": targa_originale }
        self.skipped_plates = set()

    def start(self):
        def _run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            self.app = Application.builder().token(self.token).build()
            self.app.add_handler(CallbackQueryHandler(self._handle_callback))
            self.app.add_handler(CommandHandler("status", self._cmd_status))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
            
            print("🤖 Telegram Bot Started")
            self.app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=[])

        self.thread = threading.Thread(target=_run, daemon=True, name="TelegramBot")
        self.thread.start()

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split(":", 1)
        action = parts[0]
        targa = parts[1] if len(parts) > 1 else ""

        if action == "skip":
            self.skipped_plates.add(targa)
            if self.on_skip: self.on_skip(targa)
            await query.edit_message_caption(caption=f"⏭ `{targa}` ignored for this session.")
            
        elif action == "edit":
            self.pending_correction["correction"] = targa
            await query.edit_message_caption(caption=f"✏️ OCR read: `{targa}`\n\nPlease type the correct plate:")
            
        elif action in ("allow", "deny"):
            authorized = (action == "allow")
            self.pending_name[targa] = authorized
            label = "✅ Authorized" if authorized else "❌ Denied"
            try:
                await query.edit_message_caption(caption=f"{label} for `{targa}`\n\n📝 Type owner name:")
            except:
                await query.edit_message_text(text=f"{label} for `{targa}`\n\n📝 Type owner name:")

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        if not text: return

        if "correction" in self.pending_correction:
            orig = self.pending_correction.pop("correction")
            corrected = text.upper()
            if self.on_correction: self.on_correction(orig, corrected)
            
            await update.message.reply_text(
                f"✏️ Corrected: `{corrected}` (was `{orig}`)\nChoose action:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Authorize", callback_data=f"allow:{corrected}"),
                    InlineKeyboardButton("❌ Deny", callback_data=f"deny:{corrected}"),
                ]])
            )
            
        elif self.pending_name:
            targa = next(iter(self.pending_name))
            auth = self.pending_name.pop(targa)
            
            self.whitelist.add_or_update(targa, text, auth)
            if self.on_registered: self.on_registered(targa, text, auth)
            
            emoji = "✅" if auth else "❌"
            await update.message.reply_text(f"{emoji} Saved!\n🚗 `{targa}`\n👤 {text}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.get_status: return
        status = self.get_status()
        if not status:
            await update.message.reply_text("🅿️ Garage is empty.")
            return
        
        lines = [f"🚗 *Active Vehicles: {len(status)}*\n"]
        for obj_id, plate in status.items():
            if plate:
                entry = self.whitelist.get_entry(plate)
                if entry:
                    e = "✅" if entry["autorizzato"] else "🚫"
                    lines.append(f"{e} `{plate}` — {entry['nome']} (ID: {obj_id})")
                else:
                    lines.append(f"❓ `{plate}` — Unknown (ID: {obj_id})")
            else:
                lines.append(f"🔍 Reading... (ID: {obj_id})")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    def send_unknown_plate_alert(self, plate: str, photo_path: str = None):
        if not self.loop: return
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Authorize", callback_data=f"allow:{plate}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny:{plate}"),
        ], [
            InlineKeyboardButton("⏭ Skip", callback_data=f"skip:{plate}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{plate}"),
        ]])
        
        caption = f"🚨 *Unknown Plate Detected!*\n\n🚗 `{plate}`\n\nWhat to do?"

        async def _send():
            if photo_path and os.path.exists(photo_path):
                with open(photo_path, 'rb') as f:
                    await self.app.bot.send_photo(chat_id=self.chat_id, photo=f, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await self.app.bot.send_message(chat_id=self.chat_id, text=caption, parse_mode="Markdown", reply_markup=keyboard)

        asyncio.run_coroutine_threadsafe(_send(), self.loop)

    def send_message(self, text: str):
        if not self.loop: return
        async def _send():
            await self.app.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="Markdown")
        asyncio.run_coroutine_threadsafe(_send(), self.loop)
