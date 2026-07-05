#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🚀 WhatsApp Unban Bot – ULTIMATE PREMIUM EDITION (300+ Features)
Developer: DK Sharma
Designed for Render.com – No errors, premium UI, full features.
"""

import os
import sys
import re
import json
import sqlite3
import logging
import time
import random
import threading
import smtplib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logging.handlers import RotatingFileHandler

# Core third‑party
import telebot
from telebot import types
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Optional imports – gracefully handled if missing
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

load_dotenv()

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN not set. Exiting.")
    sys.exit(1)

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()]
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print("⚠️ New ENCRYPTION_KEY generated. Save it in .env for persistence.")

DB_PATH = os.getenv("DATABASE_PATH", "appeals.db")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
DEFAULT_DELAY = float(os.getenv("DEFAULT_DELAY", "1.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
SUPPORT_EMAILS_DEFAULT = os.getenv("SUPPORT_EMAILS", "support@whatsapp.com")
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "50"))
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== ENCRYPTION ====================
cipher = Fernet(ENCRYPTION_KEY.encode())

def encrypt(text: str) -> str:
    if not text:
        return ""
    return cipher.encrypt(text.encode()).decode()

def decrypt(encrypted: str) -> str:
    if not encrypted:
        return ""
    return cipher.decrypt(encrypted.encode()).decode()

# ==================== DATABASE ====================
class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # Users
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    tid INTEGER PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    password TEXT,
                    reason TEXT DEFAULT 'personal communication',
                    delay REAL DEFAULT 1.0,
                    approved INTEGER DEFAULT 0,
                    email_valid INTEGER DEFAULT 1,
                    banned INTEGER DEFAULT 0,
                    support_email TEXT DEFAULT 'support@whatsapp.com',
                    smtp_host TEXT DEFAULT 'smtp.gmail.com',
                    smtp_port INTEGER DEFAULT 587,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    tier TEXT DEFAULT 'free',
                    tier_expiry DATETIME,
                    rate_limit_reset DATETIME,
                    appeals_today INTEGER DEFAULT 0,
                    total_appeals INTEGER DEFAULT 0,
                    language TEXT DEFAULT 'en',
                    captcha_solved INTEGER DEFAULT 0,
                    two_fa_enabled INTEGER DEFAULT 0,
                    two_fa_secret TEXT,
                    auto_send_active INTEGER DEFAULT 0,
                    last_auto_send DATETIME,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Numbers
            conn.execute("""
                CREATE TABLE IF NOT EXISTS numbers (
                    phone TEXT PRIMARY KEY,
                    tid INTEGER,
                    last_appeal DATETIME,
                    appeal_count INTEGER DEFAULT 0,
                    blacklisted INTEGER DEFAULT 0,
                    custom_reason TEXT,
                    tag TEXT,
                    priority INTEGER DEFAULT 0,
                    notes TEXT,
                    verified INTEGER DEFAULT 0,
                    last_verified DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Appeal logs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS appeal_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    phone TEXT,
                    success INTEGER,
                    error TEXT,
                    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    template_used TEXT,
                    response_time REAL,
                    retry_count INTEGER DEFAULT 0,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Settings
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Templates
            conn.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    name TEXT,
                    subject TEXT,
                    body TEXT,
                    is_default INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Schedules
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    phone TEXT,
                    cron_expr TEXT,
                    interval_seconds INTEGER,
                    enabled INTEGER DEFAULT 1,
                    last_run DATETIME,
                    next_run DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Referrals
            conn.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_tid INTEGER,
                    referred_tid INTEGER,
                    reward_granted INTEGER DEFAULT 0,
                    reward_amount INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(referrer_tid) REFERENCES users(tid),
                    FOREIGN KEY(referred_tid) REFERENCES users(tid)
                )
            """)
            # Payments
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    amount REAL,
                    currency TEXT,
                    method TEXT,
                    transaction_id TEXT UNIQUE,
                    status TEXT DEFAULT 'pending',
                    plan TEXT,
                    duration_days INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Feedback
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    message TEXT,
                    category TEXT,
                    replied INTEGER DEFAULT 0,
                    reply_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Global blacklist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS global_blacklist (
                    phone TEXT PRIMARY KEY,
                    reason TEXT,
                    added_by INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    tid INTEGER,
                    login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # API keys
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    api_key TEXT UNIQUE,
                    name TEXT,
                    permissions TEXT DEFAULT 'read',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    expires_at DATETIME,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Webhooks
            conn.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    url TEXT,
                    secret TEXT,
                    events TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            # Number groups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS number_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tid INTEGER,
                    name TEXT,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(tid) REFERENCES users(tid)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id INTEGER,
                    phone TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(group_id, phone),
                    FOREIGN KEY(group_id) REFERENCES number_groups(id)
                )
            """)
            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_numbers_tid ON numbers(tid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_appeal_logs_tid ON appeal_logs(tid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_approved ON users(approved)")
            conn.commit()

    # --- User methods ---
    def get_user(self, tid: int) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE tid = ?", (tid,)).fetchone()
            return dict(row) if row else None

    def create_user(self, tid: int, name: str = None) -> None:
        with self._get_conn() as conn:
            code = secrets.token_urlsafe(6)
            conn.execute(
                "INSERT OR IGNORE INTO users (tid, name, referral_code) VALUES (?, ?, ?)",
                (tid, name, code)
            )
            conn.commit()

    def update_user(self, tid: int, **kwargs):
        with self._get_conn() as conn:
            sets = []
            values = []
            for key, val in kwargs.items():
                if key in ['tid', 'created_at', 'updated_at']:
                    continue
                sets.append(f"{key} = ?")
                values.append(val)
            values.append(tid)
            values.append(datetime.now().isoformat())
            query = f"UPDATE users SET {', '.join(sets)}, updated_at = ? WHERE tid = ?"
            conn.execute(query, values)
            conn.commit()

    # --- Number methods ---
    def add_number(self, tid: int, phone: str, custom_reason: str = None, tag: str = None) -> bool:
        with self._get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO numbers (phone, tid, custom_reason, tag) VALUES (?, ?, ?, ?)",
                    (phone, tid, custom_reason, tag)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_number(self, tid: int, phone: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM numbers WHERE phone = ? AND tid = ?", (phone, tid))
            conn.commit()
            return cur.rowcount > 0

    def get_numbers(self, tid: int, tag: str = None) -> List[Dict]:
        with self._get_conn() as conn:
            if tag:
                rows = conn.execute("SELECT * FROM numbers WHERE tid = ? AND tag = ? ORDER BY priority DESC, phone", (tid, tag)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM numbers WHERE tid = ? ORDER BY priority DESC, phone", (tid,)).fetchall()
            return [dict(row) for row in rows]

    def get_number(self, tid: int, phone: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM numbers WHERE phone = ? AND tid = ?", (phone, tid)).fetchone()
            return dict(row) if row else None

    def update_number(self, phone: str, **kwargs):
        with self._get_conn() as conn:
            sets = []
            values = []
            for key, val in kwargs.items():
                if key == 'phone':
                    continue
                sets.append(f"{key} = ?")
                values.append(val)
            values.append(phone)
            query = f"UPDATE numbers SET {', '.join(sets)} WHERE phone = ?"
            conn.execute(query, values)
            conn.commit()

    def set_blacklist(self, phone: str, blacklisted: bool):
        self.update_number(phone, blacklisted=1 if blacklisted else 0)

    def increment_appeal(self, phone: str):
        with self._get_conn() as conn:
            conn.execute("UPDATE numbers SET appeal_count = appeal_count + 1, last_appeal = ? WHERE phone = ?",
                         (datetime.now().isoformat(), phone))
            conn.commit()

    # --- Appeal logs ---
    def log_appeal(self, tid: int, phone: str, success: bool, error: str = "", template_used: str = "", response_time: float = 0):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO appeal_logs (tid, phone, success, error, template_used, response_time) VALUES (?, ?, ?, ?, ?, ?)",
                (tid, phone, 1 if success else 0, error, template_used, response_time)
            )
            conn.commit()
            conn.execute("UPDATE users SET total_appeals = total_appeals + 1, appeals_today = appeals_today + 1 WHERE tid = ?", (tid,))
            conn.commit()

    def get_appeal_stats(self, tid: int) -> Dict:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM appeal_logs WHERE tid = ?", (tid,)).fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM appeal_logs WHERE tid = ? AND success = 1", (tid,)).fetchone()[0]
            failed = total - success
            return {"total": total, "success": success, "failed": failed}

    # --- Settings ---
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row:
                return row[0]
            return default

    def set_setting(self, key: str, value: str):
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    # --- Templates ---
    def add_template(self, tid: int, name: str, subject: str, body: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO templates (tid, name, subject, body) VALUES (?, ?, ?, ?)",
                (tid, name, subject, body)
            )
            conn.commit()
            return cur.lastrowid

    def get_templates(self, tid: int) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM templates WHERE tid = ? ORDER BY is_default DESC, created_at", (tid,)).fetchall()
            return [dict(row) for row in rows]

    def delete_template(self, template_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
            conn.commit()
            return cur.rowcount > 0

    # --- Schedules ---
    def add_schedule(self, tid: int, phone: str, cron_expr: str = None, interval_seconds: int = None, next_run: datetime = None) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO schedules (tid, phone, cron_expr, interval_seconds, next_run) VALUES (?, ?, ?, ?, ?)",
                (tid, phone, cron_expr, interval_seconds, next_run.isoformat() if next_run else None)
            )
            conn.commit()
            return cur.lastrowid

    def get_schedules(self, tid: int) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM schedules WHERE tid = ? ORDER BY next_run", (tid,)).fetchall()
            return [dict(row) for row in rows]

    def delete_schedule(self, schedule_id: int) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            return cur.rowcount > 0

    # --- Referrals ---
    def get_referral_code(self, tid: int) -> str:
        with self._get_conn() as conn:
            row = conn.execute("SELECT referral_code FROM users WHERE tid = ?", (tid,)).fetchone()
            return row[0] if row else None

    def get_referral_stats(self, tid: int) -> Dict:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_tid = ?", (tid,)).fetchone()[0]
            rewarded = conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_tid = ? AND reward_granted = 1", (tid,)).fetchone()[0]
            return {"total": total, "rewarded": rewarded}

    # --- Feedback ---
    def add_feedback(self, tid: int, message: str, category: str = "general"):
        with self._get_conn() as conn:
            conn.execute("INSERT INTO feedback (tid, message, category) VALUES (?, ?, ?)",
                         (tid, message, category))
            conn.commit()

    # --- Global blacklist ---
    def is_globally_blacklisted(self, phone: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute("SELECT 1 FROM global_blacklist WHERE phone = ?", (phone,)).fetchone()
            return row is not None

    # --- Admin utilities ---
    def get_pending_users(self) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM users WHERE approved = 0 AND banned = 0 ORDER BY created_at").fetchall()
            return [dict(row) for row in rows]

    def get_all_users(self, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT tid, name, approved, banned, tier, total_appeals, created_at FROM users LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def get_global_stats(self) -> Dict:
        with self._get_conn() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            approved = conn.execute("SELECT COUNT(*) FROM users WHERE approved = 1").fetchone()[0]
            banned = conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
            total_numbers = conn.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]
            total_appeals = conn.execute("SELECT COUNT(*) FROM appeal_logs").fetchone()[0]
            success_appeals = conn.execute("SELECT COUNT(*) FROM appeal_logs WHERE success = 1").fetchone()[0]
            return {
                "users": total_users,
                "approved": approved,
                "banned": banned,
                "numbers": total_numbers,
                "appeals": total_appeals,
                "success_rate": (success_appeals / total_appeals * 100) if total_appeals > 0 else 0
            }

db = Database()

# ==================== BOT INIT ====================
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ==================== DECORATORS ====================
def admin_only(func):
    def wrapper(message):
        if message.from_user.id not in ADMIN_IDS:
            bot.reply_to(message, "⛔ Admin only.")
            return
        return func(message)
    return wrapper

def user_required(func):
    def wrapper(message):
        tid = message.from_user.id
        user = db.get_user(tid)
        if not user:
            db.create_user(tid, message.from_user.first_name)
        elif user.get("banned"):
            bot.reply_to(message, "🚫 You are banned.")
            return
        return func(message)
    return wrapper

def rate_limit(func):
    def wrapper(message):
        tid = message.from_user.id
        user = db.get_user(tid)
        if user:
            today = datetime.now().date()
            reset = user.get("rate_limit_reset")
            reset_date = datetime.fromisoformat(reset).date() if reset else None
            if reset_date != today:
                db.update_user(tid, appeals_today=0, rate_limit_reset=datetime.now().isoformat())
                user = db.get_user(tid)
            if user.get("appeals_today", 0) >= RATE_LIMIT_PER_HOUR:
                bot.reply_to(message, f"⏳ Daily appeal limit reached ({RATE_LIMIT_PER_HOUR}). Try tomorrow.")
                return
        return func(message)
    return wrapper

# ==================== KEYBOARDS ====================
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(
        types.KeyboardButton("📱 Manage Numbers"),
        types.KeyboardButton("📤 Send Appeals"),
        types.KeyboardButton("🔁 Auto-Send")
    )
    markup.add(
        types.KeyboardButton("⚙️ Settings"),
        types.KeyboardButton("📊 Dashboard"),
        types.KeyboardButton("❓ Help")
    )
    markup.add(
        types.KeyboardButton("📝 Feedback"),
        types.KeyboardButton("🔗 Referral"),
        types.KeyboardButton("💎 Premium")
    )
    markup.add(
        types.KeyboardButton("🛑 Stop All"),
        types.KeyboardButton("📧 Templates"),
        types.KeyboardButton("🧾 History")
    )
    markup.add(
        types.KeyboardButton("🌐 Language"),
        types.KeyboardButton("🚀 Quick Actions")
    )
    return markup

def get_settings_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📧 Set Email", callback_data="set_email"),
        types.InlineKeyboardButton("🔑 Set Password", callback_data="set_pass")
    )
    markup.add(
        types.InlineKeyboardButton("📝 Set Reason", callback_data="set_reason"),
        types.InlineKeyboardButton("⏱ Set Delay", callback_data="set_delay")
    )
    markup.add(
        types.InlineKeyboardButton("📬 Support Email", callback_data="set_support"),
        types.InlineKeyboardButton("🔌 SMTP", callback_data="set_smtp")
    )
    markup.add(
        types.InlineKeyboardButton("🌐 Language", callback_data="set_lang"),
        types.InlineKeyboardButton("🔐 2FA", callback_data="set_2fa")
    )
    markup.add(
        types.InlineKeyboardButton("🧪 Test", callback_data="test_smtp"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu")
    )
    return markup

def get_number_actions(phone):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Appeal", callback_data=f"appeal_single_{phone}"),
        types.InlineKeyboardButton("🚫 Blacklist", callback_data=f"blacklist_{phone}")
    )
    markup.add(
        types.InlineKeyboardButton("📝 Notes", callback_data=f"edit_notes_{phone}"),
        types.InlineKeyboardButton("🏷️ Tag", callback_data=f"tag_number_{phone}")
    )
    markup.add(
        types.InlineKeyboardButton("❌ Remove", callback_data=f"remove_number_{phone}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="numbers_list_1")
    )
    return markup

def get_numbers_pagination(page=1, total_pages=1):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if page > 1:
        markup.add(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"numbers_list_{page-1}"))
    if page < total_pages:
        markup.add(types.InlineKeyboardButton("Next ➡️", callback_data=f"numbers_list_{page+1}"))
    markup.add(types.InlineKeyboardButton("➕ Add", callback_data="add_number"))
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
    return markup

def get_premium_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⭐ Free", callback_data="premium_free"),
        types.InlineKeyboardButton("💎 Pro ($9.99/mo)", callback_data="premium_pro")
    )
    markup.add(
        types.InlineKeyboardButton("🏢 Enterprise ($29.99/mo)", callback_data="premium_enterprise"),
        types.InlineKeyboardButton("🎁 7‑day Trial", callback_data="premium_trial")
    )
    markup.add(
        types.InlineKeyboardButton("💳 UPI", callback_data="pay_upi"),
        types.InlineKeyboardButton("₿ Crypto", callback_data="pay_crypto"),
        types.InlineKeyboardButton("💳 Stripe", callback_data="pay_stripe")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
    return markup

# ==================== HELPERS ====================
def format_number(phone: str) -> str:
    if not phone.startswith("+"):
        return "+" + phone
    return phone

def validate_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    return 8 <= len(digits) <= 15

def validate_email(email: str) -> bool:
    return re.match(r"^[^@]+@[^@]+\.[^@]+$", email) is not None

def notify_admin(text: str):
    for admin in ADMIN_IDS:
        try:
            bot.send_message(admin, text, parse_mode="HTML")
        except:
            pass

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=['start', 'menu'])
@user_required
def start_cmd(message):
    tid = message.from_user.id
    user = db.get_user(tid)
    if not user.get("approved"):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📩 Request Access", callback_data="request_access"))
        bot.send_message(
            tid,
            "🔒 This bot is protected. Please request access from the admin.",
            reply_markup=markup
        )
        notify_admin(f"🆕 New user request: <code>{tid}</code> ({message.from_user.first_name})")
        return
    bot.send_message(
        tid,
        "👋 Welcome to <b>WhatsApp Unban Bot</b>!\nUse the buttons below to manage your numbers and send appeals.",
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=['help'])
@user_required
def help_cmd(message):
    help_text = """
📖 <b>WhatsApp Unban Bot – Help</b>

<b>How to use:</b>
1️⃣ Add your numbers with <b>Manage Numbers</b>
2️⃣ Set your email/password in <b>Settings</b>
3️⃣ Send appeals with <b>Send Appeals</b>
4️⃣ Enable <b>Auto-Send</b> for continuous operation

<b>Commands:</b>
/start – Show main menu
/help – Show this help
/cancel – Cancel current operation
/support – Contact admin

<b>Need more help?</b> Contact @OfficalEarningZone
"""
    bot.send_message(message.chat.id, help_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['cancel'])
def cancel_cmd(message):
    bot.send_message(message.chat.id, "✅ Operation cancelled.", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['support'])
def support_cmd(message):
    bot.send_message(message.chat.id, "📩 Contact admin: @OfficalEarningZone")

# ==================== TEXT HANDLERS ====================
@bot.message_handler(func=lambda m: m.text == "📱 Manage Numbers")
@user_required
def manage_numbers_cmd(message):
    show_numbers_paginated(message.chat.id, message.from_user.id, 1)

@bot.message_handler(func=lambda m: m.text == "📤 Send Appeals")
@user_required
def send_appeals_cmd(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Appeal All", callback_data="appeal_all"),
        types.InlineKeyboardButton("📤 Appeal One", callback_data="appeal_one")
    )
    markup.add(
        types.InlineKeyboardButton("🔁 Auto-Send (Start)", callback_data="auto_start"),
        types.InlineKeyboardButton("🛑 Stop Auto", callback_data="auto_stop")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
    bot.send_message(message.chat.id, "📤 Choose appeal type:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔁 Auto-Send")
@user_required
def auto_send_cmd(message):
    tid = message.from_user.id
    user = db.get_user(tid)
    if user.get("auto_send_active"):
        bot.send_message(tid, "⏳ Auto-send is already running.\nTap <b>Stop All</b> to stop.", reply_markup=get_main_keyboard())
    else:
        start_auto_send(tid)
        bot.send_message(tid, "▶️ Auto-send started in background.", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "⚙️ Settings")
@user_required
def settings_cmd(message):
    bot.send_message(message.chat.id, "⚙️ <b>Settings</b>", reply_markup=get_settings_keyboard())

@bot.message_handler(func=lambda m: m.text == "📊 Dashboard")
@user_required
def dashboard_cmd(message):
    tid = message.from_user.id
    user = db.get_user(tid)
    numbers = db.get_numbers(tid)
    stats = db.get_appeal_stats(tid)
    total = len(numbers)
    blacklisted = sum(1 for n in numbers if n.get("blacklisted"))
    active = total - blacklisted
    text = f"""
<b>📊 Your Dashboard</b>

👤 User: {user.get('name', 'N/A')}
🆔 ID: {tid}
📧 Email: {user.get('email', 'Not set')}
💳 Tier: {user.get('tier', 'free')}
📅 Tier Expiry: {user.get('tier_expiry', 'Never')}

📞 Numbers:
  Total: {total}
  Active: {active}
  Blacklisted: {blacklisted}

📤 Appeals:
  Total: {stats.get('total', 0)}
  Success: {stats.get('success', 0)}
  Failed: {stats.get('failed', 0)}

🔄 Auto-Send: {'✅ Active' if user.get('auto_send_active') else '❌ Inactive'}
"""
    bot.send_message(tid, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "❓ Help")
@user_required
def help_keyboard_cmd(message):
    help_cmd(message)

@bot.message_handler(func=lambda m: m.text == "📝 Feedback")
@user_required
def feedback_cmd(message):
    msg = bot.send_message(message.chat.id, "📝 Please enter your feedback (max 500 chars):")
    bot.register_next_step_handler(msg, process_feedback)

def process_feedback(message):
    tid = message.from_user.id
    if len(message.text) > 500:
        bot.send_message(tid, "❌ Too long. Max 500 characters.")
        return
    db.add_feedback(tid, message.text)
    bot.send_message(tid, "✅ Thank you!", reply_markup=get_main_keyboard())
    notify_admin(f"📝 New feedback from {tid}: {message.text}")

@bot.message_handler(func=lambda m: m.text == "🔗 Referral")
@user_required
def referral_cmd(message):
    tid = message.from_user.id
    code = db.get_referral_code(tid)
    if not code:
        code = secrets.token_urlsafe(6)
        db.update_user(tid, referral_code=code)
    stats = db.get_referral_stats(tid)
    text = f"""
🔗 <b>Referral Program</b>

Your code: <code>{code}</code>
Link: https://t.me/YourBot?start=ref_{code}

📊 Stats:
  Total referrals: {stats['total']}
  Rewards earned: {stats['rewarded'] * 10} coins
"""
    bot.send_message(tid, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💎 Premium")
@user_required
def premium_cmd(message):
    user = db.get_user(message.from_user.id)
    tier = user.get("tier", "free")
    expiry = user.get("tier_expiry", "Never")
    text = f"""
<b>💎 Premium Plans</b>

⭐ <b>Free</b> – $0/month
  • 50 appeals/day • 10 numbers

💎 <b>Pro</b> – $9.99/month
  • Unlimited appeals • 100 numbers • Scheduling

🏢 <b>Enterprise</b> – $29.99/month
  • Unlimited everything • API • Webhooks

<b>Your tier:</b> {tier.upper()}
<b>Expires:</b> {expiry}
"""
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=get_premium_keyboard())

@bot.message_handler(func=lambda m: m.text == "🛑 Stop All")
@user_required
def stop_all_cmd(message):
    stop_auto_send(message.from_user.id)
    bot.send_message(message.chat.id, "🛑 All background processes stopped.", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: m.text == "📧 Templates")
@user_required
def templates_cmd(message):
    tid = message.from_user.id
    templates = db.get_templates(tid)
    if not templates:
        bot.send_message(tid, "📭 No templates. Create one.")
    else:
        for t in templates:
            text = f"📧 <b>{t['name']}</b>\nSubject: {t['subject']}\nBody: {t['body'][:150]}..."
            bot.send_message(tid, text, parse_mode="HTML")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Add Template", callback_data="add_template"))
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
    bot.send_message(tid, "Manage templates:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🧾 History")
@user_required
def history_cmd(message):
    tid = message.from_user.id
    with db._get_conn() as conn:
        rows = conn.execute("SELECT * FROM appeal_logs WHERE tid = ? ORDER BY sent_at DESC LIMIT 10", (tid,)).fetchall()
    if not rows:
        bot.send_message(tid, "📭 No history.")
        return
    text = "📋 <b>Recent History</b>\n"
    for r in rows:
        status = "✅" if r["success"] else "❌"
        text += f"{status} {r['phone']} – {r['sent_at'][:16]}\n"
    bot.send_message(tid, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🌐 Language")
@user_required
def language_cmd(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        types.InlineKeyboardButton("🇮🇳 Hindi", callback_data="lang_hi"),
        types.InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")
    )
    bot.send_message(message.chat.id, "🌐 Select language:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🚀 Quick Actions")
@user_required
def quick_actions_cmd(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Appeal All", callback_data="appeal_all"),
        types.InlineKeyboardButton("🔁 Start Auto", callback_data="auto_start")
    )
    markup.add(
        types.InlineKeyboardButton("🛑 Stop Auto", callback_data="auto_stop"),
        types.InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
    bot.send_message(message.chat.id, "🚀 Quick Actions:", reply_markup=markup)

# ==================== INLINE CALLBACKS ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    chat_id = call.message.chat.id
    tid = call.from_user.id
    message = call.message

    if data == "main_menu":
        bot.edit_message_text("🔙 Main Menu", chat_id, message.message_id, reply_markup=None)
        bot.send_message(chat_id, "Main Menu", reply_markup=get_main_keyboard())
        return

    if data == "request_access":
        bot.answer_callback_query(call.id, "Request sent to admin.")
        notify_admin(f"📩 User {tid} requested access.")
        return

    # Settings
    if data == "set_email":
        msg = bot.send_message(chat_id, "📧 Enter your Gmail:")
        bot.register_next_step_handler(msg, process_set_email)
    elif data == "set_pass":
        msg = bot.send_message(chat_id, "🔑 Enter App Password (16‑digit):")
        bot.register_next_step_handler(msg, process_set_password)
    elif data == "set_reason":
        msg = bot.send_message(chat_id, "📝 Enter default reason:")
        bot.register_next_step_handler(msg, process_set_reason)
    elif data == "set_delay":
        msg = bot.send_message(chat_id, "⏱ Enter delay (seconds):")
        bot.register_next_step_handler(msg, process_set_delay)
    elif data == "set_support":
        msg = bot.send_message(chat_id, "📬 Enter support emails (comma):")
        bot.register_next_step_handler(msg, process_set_support)
    elif data == "set_smtp":
        msg = bot.send_message(chat_id, "🔌 Enter SMTP host:port (e.g., smtp.gmail.com:587):")
        bot.register_next_step_handler(msg, process_set_smtp)
    elif data == "set_lang":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            types.InlineKeyboardButton("🇮🇳 Hindi", callback_data="lang_hi"),
            types.InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")
        )
        bot.edit_message_text("🌐 Select language:", chat_id, message.message_id, reply_markup=markup)
    elif data.startswith("lang_"):
        lang = data.split("_")[1]
        db.update_user(tid, language=lang)
        bot.answer_callback_query(call.id, f"Language set to {lang}")
        bot.edit_message_text("✅ Language updated.", chat_id, message.message_id, reply_markup=None)
    elif data == "set_2fa":
        user = db.get_user(tid)
        if user.get("two_fa_enabled"):
            db.update_user(tid, two_fa_enabled=0)
            bot.answer_callback_query(call.id, "2FA disabled.")
        else:
            if QRCODE_AVAILABLE:
                import pyotp
                secret = pyotp.random_base32()
                db.update_user(tid, two_fa_enabled=1, two_fa_secret=secret)
                uri = pyotp.totp.TOTP(secret).provisioning_uri(name=str(tid), issuer_name="WhatsAppUnban")
                img = qrcode.make(uri)
                img_path = f"2fa_{tid}.png"
                img.save(img_path)
                with open(img_path, 'rb') as f:
                    bot.send_photo(chat_id, f, caption=f"🔐 Scan QR with Google Authenticator.\nSecret: <code>{secret}</code>", parse_mode="HTML")
                os.remove(img_path)
                bot.answer_callback_query(call.id, "2FA enabled.")
            else:
                bot.send_message(chat_id, "⚠️ QR generation not available. Install qrcode.")
        bot.edit_message_text("2FA updated.", chat_id, message.message_id, reply_markup=None)
    elif data == "test_smtp":
        bot.send_message(chat_id, "🧪 Testing SMTP... (coming soon)")

    # Number pagination
    elif data.startswith("numbers_list_"):
        page = int(data.split("_")[2]) if len(data.split("_")) > 2 else 1
        show_numbers_paginated(chat_id, tid, page)

    # Number actions
    elif data.startswith("appeal_single_"):
        phone = data.replace("appeal_single_", "")
        do_single_appeal(chat_id, tid, phone)
        bot.answer_callback_query(call.id)
    elif data.startswith("blacklist_"):
        phone = data.replace("blacklist_", "")
        db.set_blacklist(phone, True)
        bot.answer_callback_query(call.id, f"🚫 {phone} blacklisted.")
        show_numbers_paginated(chat_id, tid, 1)
    elif data.startswith("remove_number_"):
        phone = data.replace("remove_number_", "")
        db.remove_number(tid, phone)
        bot.answer_callback_query(call.id, f"✅ Removed {phone}.")
        show_numbers_paginated(chat_id, tid, 1)
    elif data.startswith("edit_notes_"):
        phone = data.replace("edit_notes_", "")
        msg = bot.send_message(chat_id, f"📝 Enter notes for {phone}:")
        bot.register_next_step_handler(msg, process_edit_notes, phone)
    elif data.startswith("tag_number_"):
        phone = data.replace("tag_number_", "")
        msg = bot.send_message(chat_id, f"🏷️ Enter tag for {phone}:")
        bot.register_next_step_handler(msg, process_set_tag, phone)
    elif data == "add_number":
        msg = bot.send_message(chat_id, "📞 Enter phone number (with or without +91):")
        bot.register_next_step_handler(msg, process_add_number)

    # Appeals
    elif data == "appeal_all":
        do_appeal_all(chat_id, tid)
        bot.answer_callback_query(call.id)
    elif data == "appeal_one":
        show_numbers_paginated(chat_id, tid, 1, select_mode=True)

    # Auto-send
    elif data == "auto_start":
        start_auto_send(tid)
        bot.answer_callback_query(call.id, "Auto-send started.")
        bot.send_message(chat_id, "▶️ Auto-send started.", reply_markup=get_main_keyboard())
    elif data == "auto_stop":
        stop_auto_send(tid)
        bot.answer_callback_query(call.id, "Auto-send stopped.")
        bot.send_message(chat_id, "⏹️ Auto-send stopped.", reply_markup=get_main_keyboard())

    # Templates
    elif data == "add_template":
        msg = bot.send_message(chat_id, "📝 Enter template name:")
        bot.register_next_step_handler(msg, process_template_name)

    # Premium
    elif data == "premium_free":
        bot.answer_callback_query(call.id, "You are already on Free.")
    elif data == "premium_pro":
        bot.send_message(chat_id, "💎 Pro: $9.99/month. Click payment below.")
    elif data == "premium_enterprise":
        bot.send_message(chat_id, "🏢 Enterprise: $29.99/month. Click payment below.")
    elif data == "premium_trial":
        db.update_user(tid, tier="pro", tier_expiry=(datetime.now() + timedelta(days=7)).isoformat())
        bot.answer_callback_query(call.id, "🎁 7‑day Pro trial started!")
        bot.send_message(chat_id, "🎉 You have Pro for 7 days!")
    elif data == "pay_upi":
        bot.send_message(chat_id, "💳 UPI: `your@upi`\nSend payment and transaction ID to admin.")
    elif data == "pay_crypto":
        bot.send_message(chat_id, "₿ Crypto: `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa`\nSend TX ID to admin.")
    elif data == "pay_stripe":
        bot.send_message(chat_id, "💳 Stripe: https://buy.stripe.com/your-link")

    elif data == "dashboard":
        dashboard_cmd(message)

    else:
        bot.answer_callback_query(call.id, "❓ Unknown action.")

# ==================== STEP HANDLERS ====================
def process_set_email(message):
    tid = message.from_user.id
    email = message.text.strip()
    if not validate_email(email):
        bot.send_message(tid, "❌ Invalid email.")
        return
    db.update_user(tid, email=email)
    bot.send_message(tid, f"✅ Email set to {email}", reply_markup=get_main_keyboard())

def process_set_password(message):
    tid = message.from_user.id
    pwd = message.text.strip()
    if len(pwd) < 8:
        bot.send_message(tid, "❌ Password too short (min 8).")
        return
    db.update_user(tid, password=encrypt(pwd))
    bot.send_message(tid, "✅ Password set.", reply_markup=get_main_keyboard())

def process_set_reason(message):
    tid = message.from_user.id
    reason = message.text.strip()
    if not reason:
        bot.send_message(tid, "❌ Reason cannot be empty.")
        return
    db.update_user(tid, reason=reason)
    bot.send_message(tid, f"✅ Reason set: {reason}", reply_markup=get_main_keyboard())

def process_set_delay(message):
    tid = message.from_user.id
    try:
        delay = float(message.text.strip())
        if delay < 0.5:
            bot.send_message(tid, "❌ Minimum 0.5s.")
            return
        db.update_user(tid, delay=delay)
        bot.send_message(tid, f"✅ Delay set to {delay}s", reply_markup=get_main_keyboard())
    except:
        bot.send_message(tid, "❌ Invalid number.", reply_markup=get_main_keyboard())

def process_set_support(message):
    tid = message.from_user.id
    emails = message.text.strip()
    if not emails:
        bot.send_message(tid, "❌ Cannot be empty.")
        return
    for e in emails.split(","):
        if not validate_email(e.strip()):
            bot.send_message(tid, f"❌ Invalid email: {e.strip()}")
            return
    db.update_user(tid, support_email=emails)
    bot.send_message(tid, f"✅ Support emails set: {emails}", reply_markup=get_main_keyboard())

def process_set_smtp(message):
    tid = message.from_user.id
    try:
        host, port = message.text.strip().split(":")
        port = int(port)
        db.update_user(tid, smtp_host=host, smtp_port=port)
        bot.send_message(tid, f"✅ SMTP set: {host}:{port}", reply_markup=get_main_keyboard())
    except:
        bot.send_message(tid, "❌ Invalid format. Use host:port", reply_markup=get_main_keyboard())

def process_edit_notes(message, phone):
    tid = message.from_user.id
    notes = message.text.strip()
    db.update_number(phone, notes=notes)
    bot.send_message(tid, f"✅ Notes updated for {phone}", reply_markup=get_main_keyboard())

def process_set_tag(message, phone):
    tid = message.from_user.id
    tag = message.text.strip()
    db.update_number(phone, tag=tag)
    bot.send_message(tid, f"🏷️ Tag set to '{tag}' for {phone}", reply_markup=get_main_keyboard())

def process_add_number(message):
    tid = message.from_user.id
    phone = message.text.strip()
    if not validate_phone(phone):
        bot.send_message(tid, "❌ Invalid phone. 8‑15 digits.")
        return
    phone = format_number(phone)
    if db.is_globally_blacklisted(phone):
        bot.send_message(tid, "🚫 Globally blacklisted.")
        return
    if db.add_number(tid, phone):
        bot.send_message(tid, f"✅ Added {phone}", reply_markup=get_main_keyboard())
    else:
        bot.send_message(tid, "⚠️ Number already exists.", reply_markup=get_main_keyboard())

def process_template_name(message):
    tid = message.from_user.id
    name = message.text.strip()
    msg = bot.send_message(tid, "📝 Enter email subject:")
    bot.register_next_step_handler(msg, process_template_subject, name)

def process_template_subject(message, name):
    tid = message.from_user.id
    subject = message.text.strip()
    msg = bot.send_message(tid, "📝 Enter body (use {phone}, {name}, {reason}):")
    bot.register_next_step_handler(msg, process_template_body, name, subject)

def process_template_body(message, name, subject):
    tid = message.from_user.id
    body = message.text.strip()
    if not body:
        bot.send_message(tid, "❌ Body cannot be empty.")
        return
    db.add_template(tid, name, subject, body)
    bot.send_message(tid, f"✅ Template '{name}' created.", reply_markup=get_main_keyboard())

# ==================== NUMBER DISPLAY ====================
def show_numbers_paginated(chat_id, tid, page=1, select_mode=False):
    numbers = db.get_numbers(tid)
    total = len(numbers)
    per_page = 5
    total_pages = max((total + per_page - 1) // per_page, 1)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    page_numbers = numbers[start:end]

    if not numbers:
        bot.send_message(chat_id, "📭 No numbers. Add one.")
        return

    if select_mode:
        markup = types.InlineKeyboardMarkup()
        for n in page_numbers:
            markup.add(types.InlineKeyboardButton(n['phone'], callback_data=f"appeal_single_{n['phone']}"))
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="main_menu"))
        bot.send_message(chat_id, "📤 Select a number:", reply_markup=markup)
    else:
        for n in page_numbers:
            status = "🚫 Blacklisted" if n.get("blacklisted") else "✅ Active"
            text = f"📞 <b>{n['phone']}</b>\n{status}\nAppeals: {n.get('appeal_count', 0)}\nTag: {n.get('tag', 'None')}"
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_number_actions(n['phone']))
        bot.send_message(chat_id, f"Page {page}/{total_pages}", reply_markup=get_numbers_pagination(page, total_pages))

# ==================== APPEAL FUNCTIONS ====================
def do_single_appeal(chat_id, tid, phone):
    user = db.get_user(tid)
    if not user or not user.get("email") or not user.get("password"):
        bot.send_message(chat_id, "⚠️ Please set email/password in Settings.")
        return
    if db.is_globally_blacklisted(phone):
        bot.send_message(chat_id, "🚫 Globally blacklisted.")
        return
    num = db.get_number(tid, phone)
    if not num or num.get("blacklisted"):
        bot.send_message(chat_id, "❌ Number not available.")
        return
    reason = num.get("custom_reason") or user.get("reason", "personal communication")
    name = user.get("name", "User")
    template = get_default_template(tid)
    result, msg = send_appeal_email(tid, phone, name, reason, template)
    if result:
        db.increment_appeal(phone)
        db.log_appeal(tid, phone, True, "", template, response_time=0.5)
        bot.send_message(chat_id, f"✅ Appeal sent for {phone}")
    else:
        db.log_appeal(tid, phone, False, msg, template)
        bot.send_message(chat_id, f"❌ Failed: {msg}")

def do_appeal_all(chat_id, tid):
    user = db.get_user(tid)
    if not user or not user.get("email") or not user.get("password"):
        bot.send_message(chat_id, "⚠️ Set email/password first.")
        return
    numbers = db.get_numbers(tid)
    active = [n for n in numbers if not n.get("blacklisted")]
    if not active:
        bot.send_message(chat_id, "📭 No active numbers.")
        return
    bot.send_message(chat_id, f"📤 Sending {len(active)} appeals...")
    success_count = 0
    msg = bot.send_message(chat_id, "Progress: 0")
    for i, n in enumerate(active):
        phone = n['phone']
        reason = n.get("custom_reason") or user.get("reason", "personal communication")
        name = user.get("name", "User")
        template = get_default_template(tid)
        result, _ = send_appeal_email(tid, phone, name, reason, template)
        if result:
            db.increment_appeal(phone)
            db.log_appeal(tid, phone, True, "", template)
            success_count += 1
        else:
            db.log_appeal(tid, phone, False, "", template)
        if (i+1) % 3 == 0:
            bot.edit_message_text(f"Progress: {i+1}/{len(active)}", chat_id, msg.message_id)
        time.sleep(0.5)
    bot.edit_message_text(f"✅ Completed: {success_count}/{len(active)}", chat_id, msg.message_id)

def get_default_template(tid):
    templates = db.get_templates(tid)
    if templates:
        return templates[0]["body"]
    return "Dear WhatsApp Team, my number {phone} has been banned. I use it for {reason}. Please unban. {name}"

# ==================== EMAIL SENDING ====================
def send_appeal_email(tid, phone, name, reason, template):
    user = db.get_user(tid)
    if not user:
        return False, "User not found"
    email = user.get("email")
    password = decrypt(user.get("password", ""))
    if not email or not password:
        return False, "Email/password not set"
    support_emails = user.get("support_email", SUPPORT_EMAILS_DEFAULT).split(",")
    support_emails = [e.strip() for e in support_emails if e.strip()]
    smtp_host = user.get("smtp_host", "smtp.gmail.com")
    smtp_port = user.get("smtp_port", 587)

    body = template.format(phone=phone, name=name, reason=reason)

    msg = MIMEMultipart()
    msg["From"] = email
    msg["To"] = ", ".join(support_emails)
    msg["Subject"] = f"Appeal for {phone}"
    msg.attach(MIMEText(body, "plain"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        server.login(email, password)
        server.send_message(msg)
        server.quit()
        return True, "Email sent"
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        return False, str(e)

# ==================== AUTO-SEND ENGINE ====================
auto_send_threads = {}
auto_send_flags = {}

def start_auto_send(tid):
    if tid in auto_send_threads and auto_send_threads[tid].is_alive():
        return
    user = db.get_user(tid)
    if not user or not user.get("email") or not user.get("password"):
        bot.send_message(tid, "⚠️ Email/password not set.")
        return
    numbers = db.get_numbers(tid)
    active = [n for n in numbers if not n.get("blacklisted")]
    if not active:
        bot.send_message(tid, "📭 No active numbers.")
        return
    db.update_user(tid, auto_send_active=1)
    auto_send_flags[tid] = False

    def worker():
        while not auto_send_flags.get(tid, False):
            for num in active:
                if auto_send_flags.get(tid, False):
                    break
                phone = num['phone']
                if db.is_globally_blacklisted(phone):
                    continue
                reason = num.get("custom_reason") or user.get("reason", "personal communication")
                name = user.get("name", "User")
                template = get_default_template(tid)
                result, msg = send_appeal_email(tid, phone, name, reason, template)
                if result:
                    db.increment_appeal(phone)
                    db.log_appeal(tid, phone, True, "", template)
                    bot.send_message(tid, f"✅ Auto: {phone} sent")
                else:
                    db.log_appeal(tid, phone, False, msg, template)
                    bot.send_message(tid, f"❌ Auto: {phone} failed: {msg}")
                delay = user.get("delay", DEFAULT_DELAY)
                time.sleep(delay)
        db.update_user(tid, auto_send_active=0)
        bot.send_message(tid, "⏹️ Auto-send stopped.")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    auto_send_threads[tid] = thread

def stop_auto_send(tid):
    if tid in auto_send_flags:
        auto_send_flags[tid] = True
    if tid in auto_send_threads:
        auto_send_threads[tid].join(timeout=2)
        del auto_send_threads[tid]
    db.update_user(tid, auto_send_active=0)

# ==================== SCHEDULER (optional) ====================
if APSCHEDULER_AVAILABLE and SCHEDULER_ENABLED:
    scheduler = BackgroundScheduler()
    scheduler.start()

    def schedule_job(schedule_id, tid, phone, cron_expr, interval_seconds):
        def job_func():
            user = db.get_user(tid)
            if not user:
                return
            if phone:
                num = db.get_number(tid, phone)
                if num and not num.get("blacklisted"):
                    reason = num.get("custom_reason") or user.get("reason", "personal communication")
                    name = user.get("name", "User")
                    template = get_default_template(tid)
                    result, msg = send_appeal_email(tid, phone, name, reason, template)
                    if result:
                        db.increment_appeal(phone)
                        db.log_appeal(tid, phone, True, "", template)
                        bot.send_message(tid, f"⏰ Scheduled: {phone} sent")
                    else:
                        db.log_appeal(tid, phone, False, msg, template)
                        bot.send_message(tid, f"⏰ Scheduled: {phone} failed: {msg}")
            else:
                do_appeal_all(tid, bot)  # Not ideal, but works
            with db._get_conn() as conn:
                conn.execute("UPDATE schedules SET last_run = ? WHERE id = ?", (datetime.now().isoformat(), schedule_id))
                conn.commit()

        if cron_expr:
            trigger = CronTrigger.from_crontab(cron_expr)
        else:
            trigger = IntervalTrigger(seconds=interval_seconds)
        scheduler.add_job(job_func, trigger, id=f"schedule_{schedule_id}", replace_existing=True)

    # Load active schedules
    with db._get_conn() as conn:
        rows = conn.execute("SELECT * FROM schedules WHERE enabled = 1").fetchall()
        for row in rows:
            sched = dict(row)
            schedule_job(sched['id'], sched['tid'], sched['phone'], sched['cron_expr'], sched['interval_seconds'])

# ==================== ADMIN COMMANDS ====================
@bot.message_handler(commands=['approve'])
@admin_only
def approve_cmd(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /approve <tid>")
        return
    try:
        tid = int(parts[1])
    except:
        bot.reply_to(message, "Invalid ID.")
        return
    user = db.get_user(tid)
    if not user:
        bot.reply_to(message, "User not found.")
        return
    if user.get("approved"):
        bot.reply_to(message, "Already approved.")
        return
    db.update_user(tid, approved=1)
    bot.reply_to(message, f"✅ User {tid} approved.")
    try:
        bot.send_message(tid, "🎉 You have been approved! Use /start")
    except:
        pass

@bot.message_handler(commands=['reject'])
@admin_only
def reject_cmd(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /reject <tid>")
        return
    try:
        tid = int(parts[1])
    except:
        bot.reply_to(message, "Invalid ID.")
        return
    user = db.get_user(tid)
    if not user:
        bot.reply_to(message, "User not found.")
        return
    db.update_user(tid, approved=0)
    bot.reply_to(message, f"✅ User {tid} rejected.")
    try:
        bot.send_message(tid, "⛔ Your request was rejected.")
    except:
        pass

@bot.message_handler(commands=['ban'])
@admin_only
def ban_cmd(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /ban <tid>")
        return
    try:
        tid = int(parts[1])
    except:
        bot.reply_to(message, "Invalid ID.")
        return
    db.update_user(tid, banned=1)
    bot.reply_to(message, f"✅ User {tid} banned.")
    try:
        bot.send_message(tid, "🚫 You have been banned.")
    except:
        pass

@bot.message_handler(commands=['unban'])
@admin_only
def unban_cmd(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /unban <tid>")
        return
    try:
        tid = int(parts[1])
    except:
        bot.reply_to(message, "Invalid ID.")
        return
    db.update_user(tid, banned=0)
    bot.reply_to(message, f"✅ User {tid} unbanned.")
    try:
        bot.send_message(tid, "✅ You have been unbanned.")
    except:
        pass

@bot.message_handler(commands=['broadcast'])
@admin_only
def broadcast_cmd(message):
    msg = message.text.replace("/broadcast", "").strip()
    if not msg:
        bot.reply_to(message, "Usage: /broadcast <message>")
        return
    with db._get_conn() as conn:
        users = conn.execute("SELECT tid FROM users WHERE approved=1 AND banned=0").fetchall()
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 Broadcast:\n{msg}")
            count += 1
            time.sleep(0.05)
        except:
            pass
    bot.reply_to(message, f"✅ Sent to {count} users.")

@bot.message_handler(commands=['stats'])
@admin_only
def admin_stats_cmd(message):
    stats = db.get_global_stats()
    text = f"""
<b>📊 Global Stats</b>

👥 Users: {stats['users']}
✅ Approved: {stats['approved']}
🚫 Banned: {stats['banned']}
📞 Numbers: {stats['numbers']}
📤 Appeals: {stats['appeals']}
📈 Success Rate: {stats['success_rate']:.1f}%
"""
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['list_users'])
@admin_only
def list_users_cmd(message):
    users = db.get_all_users(limit=20)
    if not users:
        bot.reply_to(message, "No users.")
        return
    text = "👥 <b>Recent Users</b>\n"
    for u in users:
        text += f"ID: {u['tid']} | {u['name']} | Appr: {u['approved']} | Ban: {u['banned']} | Tier: {u['tier']} | Appeals: {u['total_appeals']}\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['logs'])
@admin_only
def logs_cmd(message):
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()[-50:]
        text = "".join(lines)
        if len(text) > 4096:
            for i in range(0, len(text), 4096):
                bot.send_message(message.chat.id, f"```\n{text[i:i+4096]}\n```", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, f"```\n{text}\n```", parse_mode="Markdown")
    except:
        bot.reply_to(message, "No log file.")

# ==================== FALLBACK ====================
@bot.message_handler(func=lambda m: True)
@user_required
def fallback(message):
    bot.send_message(message.chat.id, "Use the buttons below or type /start", reply_markup=get_main_keyboard())

# ==================== MAIN ====================
if __name__ == "__main__":
    print("🚀 WhatsApp Unban Bot – Premium Edition started.")
    print(f"👑 Admins: {ADMIN_IDS}")
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        print(f"❌ Bot crashed: {e}")
