# -*- coding: utf-8 -*-
# Onix host — inicialização automática de dependências no Termux
import importlib.util as _importlib_util
import os as _bootstrap_os
import subprocess as _bootstrap_subprocess
import sys as _bootstrap_sys


def _install_termux_dependencies():
    """Instala somente os módulos externos ausentes, quando executado no Termux."""
    if not _bootstrap_os.environ.get("PREFIX", "").startswith("/data/data/com.termux/"):
        return

    required = {
        "telebot": "pyTelegramBotAPI",
        "flask": "Flask",
        "requests": "requests",
    }
    missing = [package for module, package in required.items()
               if _importlib_util.find_spec(module) is None]
    if not missing:
        return

    print("Onix host: instalando dependências ausentes: " + ", ".join(missing), flush=True)
    try:
        _bootstrap_subprocess.check_call([
            _bootstrap_sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check", *missing
        ])
    except Exception as exc:
        print(f"Falha ao instalar dependências: {exc}", flush=True)
        print("No Termux, execute: pkg install python -y", flush=True)
        raise SystemExit(1)


_install_termux_dependencies()

import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
# import psutil  # Removido para compatibilidade com Termux
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import hashlib
import mimetypes
import struct
import socket

# --- Flask Keep Alive ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Onix host — Online"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('0.0.0.0', port)) == 0

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    while is_port_in_use(port):
        logger.info(f"Porta {port} em uso, tentando a próxima...")
        port += 1
    
    logger.info(f"Iniciando servidor Flask na porta {port}")
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Servidor Keep-Alive do Flask iniciado.")
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = '8714126990:AAFy4AsIPaus_xVVg02Oz7ALMd4RBdwBlwY'
OWNER_ID = 7365028334
ADMIN_ID  = 7365028334
YOUR_USERNAME = '@ElGatodev'
UPDATE_CHANNEL = '@Toxicadminn'
FORCE_JOIN_CHANNEL = '@Toxicadminn'   # Altere para o username do seu canal (com @)
BOT_NAME = "Onix host"
CREDIT = "@ElGatodev"

# Welcome banner image (fixed image sent to every new user)
WELCOME_IMAGE_URL = 'https://carder.top/imagens/1790886272141-247207333.jpg'

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# File upload limits
FREE_USER_LIMIT = 10
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
from telebot import apihelper
apihelper.CONNECT_TIMEOUT = 90
apihelper.READ_TIMEOUT = 90
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
#  BUTTON LAYOUTS
# ═══════════════════════════════════════════════════════
COMMAND_BUTTONS_LAYOUT_USER = [
    ["📤 Enviar Arquivo", "📂 Meus Arquivos"],
    ["⚡ Teste de Velocidade",  "📊 Estatísticas"],
    ["📤 Enviar Comando","📞 Contatar Proprietário"],
]
COMMAND_BUTTONS_LAYOUT_ADMIN = [
    ["📤 Enviar Arquivo",  "📂 Meus Arquivos"],
    ["⚡ Teste de Velocidade",   "📊 Estatísticas"],
    ["💳 Assinaturas","📢 Transmissão"],
    ["🔒 Bloquear Bot",     "🟢 Rodar Todos os Scripts"],
    ["📤 Enviar Comando", "👑 Painel Admin"],
    ["📞 Contatar Proprietário"],
]

# ═══════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry for user {user_id}: {expiry}")
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(uid for (uid,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(uid for (uid,) in c.fetchall())
        conn.close()
        logger.info(f"Loaded: {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# ═══════════════════════════════════════════════════════
#  FORCE JOIN CHECK
# ═══════════════════════════════════════════════════════
def is_member(user_id: int) -> bool:
    """Retorna True se o usuário for membro do FORCE_JOIN_CHANNEL."""
    if user_id in admin_ids:
        return True
    try:
        member = bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return member.status not in ['left', 'kicked']
    except Exception as e:
        logger.warning(f"Force-join check failed for {user_id}: {e}")
        return True   # fail-open para evitar bloquear todos em caso de erro na API

def require_join(func):
    """Decorator: bloqueia qualquer handler atrás do force-join."""
    def wrapper(message, *args, **kwargs):
        uid = message.from_user.id if hasattr(message, 'from_user') else None
        if uid and not is_member(uid):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "✅ Entrar no Canal", url=f"https://t.me/{FORCE_JOIN_CHANNEL.lstrip('@')}"))
            markup.add(types.InlineKeyboardButton("🔄 Já entrei — Verificar", callback_data='verify_join'))
            bot.reply_to(message,
                f"⚠️ *Você deve entrar em nosso canal para usar o {BOT_NAME}!*\n\n"
                f"1️⃣ Clique no botão abaixo para entrar.\n"
                f"2️⃣ Depois toque em **Já entrei — Verificar**.\n\n"
                f"📣 Canal: {FORCE_JOIN_CHANNEL}",
                reply_markup=markup, parse_mode='Markdown')
            return
        return func(message, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════
def get_user_folder(user_id):
    folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(owner_id, file_name):
    key = f"{owner_id}_{file_name}"
    info = bot_scripts.get(key)
    if info and info.get('process'):
        proc = info['process']
        # Verifica se o processo ainda está rodando usando poll()
        if proc.poll() is None:
            return True
        else:
            _close_log(info)
            bot_scripts.pop(key, None)
    return False

def _close_log(info):
    lf = info.get('log_file')
    if lf and hasattr(lf, 'close') and not lf.closed:
        try: lf.close()
        except: pass

def kill_process_tree(process_info):
    key = process_info.get('script_key', 'N/A')
    _close_log(process_info)
    proc = process_info.get('process')
    if not proc:
        return
    try:
        pid = proc.pid
        # No Linux/Termux, usamos pkill para matar processos filhos
        subprocess.run(['pkill', '-9', '-P', str(pid)], stderr=subprocess.DEVNULL)
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception as e:
        logger.error(f"Error killing tree {key}: {e}")

# ═══════════════════════════════════════════════════════
#  AUTO PACKAGE INSTALLATION
# ═══════════════════════════════════════════════════════
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI','telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot','aiogram': 'aiogram',
    'pyrogram': 'pyrogram','telethon': 'telethon','telethon.sync': 'telethon',
    'telepot': 'telepot','tgcrypto': 'tgcrypto','bs4': 'beautifulsoup4',
    'requests': 'requests','pillow': 'Pillow','cv2': 'opencv-python',
    'yaml': 'PyYAML','dotenv': 'python-dotenv','dateutil': 'python-dateutil',
    'pandas': 'pandas','numpy': 'numpy','flask': 'Flask','django': 'Django',
    'sqlalchemy': 'SQLAlchemy','psutil': 'psutil',
    'asyncio': None,'json': None,'datetime': None,'os': None,'sys': None,
    're': None,'time': None,'math': None,'random': None,'logging': None,
    'threading': None,'subprocess': None,'zipfile': None,'tempfile': None,
    'shutil': None,'sqlite3': None,'atexit': None,
}

def attempt_install_pip(module_name, message):
    pkg = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if pkg is None: return True
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])
        return True
    except Exception as e:
        logger.error(f"Pip install failed for {pkg}: {e}")
        return False

def run_script(script_path, owner_id, user_folder, file_name, msg_obj):
    key = f"{owner_id}_{file_name}"
    try:
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        try:
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(msg_obj, f"❌ Não é possível abrir o arquivo de log: {e}"); return
        
        try:
            si = None
            if os.name == 'nt':
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder,
                stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
                startupinfo=si, encoding='utf-8', errors='ignore')
            
            bot_scripts[key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': msg_obj.chat.id, 'script_owner_id': owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'py', 'script_key': key
            }
            bot.reply_to(msg_obj, f"✅ `{file_name}` iniciado! (PID: {process.pid})", parse_mode='Markdown')
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(msg_obj, f"❌ Erro ao iniciar `{file_name}`: {e}")
            if key in bot_scripts: del bot_scripts[key]
    except Exception as e:
        bot.reply_to(msg_obj, f"❌ Erro inesperado: {e}")
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key]); del bot_scripts[key]

def run_js_script(script_path, owner_id, user_folder, file_name, msg_obj):
    key = f"{owner_id}_{file_name}"
    try:
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        try:
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(msg_obj, f"❌ Não é possível abrir o arquivo de log: {e}"); return
        try:
            si = None
            if os.name == 'nt':
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder,
                stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
                startupinfo=si, encoding='utf-8', errors='ignore')
            bot_scripts[key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': msg_obj.chat.id, 'script_owner_id': owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'js', 'script_key': key
            }
            bot.reply_to(msg_obj, f"✅ `{file_name}` iniciado! (PID: {process.pid})", parse_mode='Markdown')
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(msg_obj, f"❌ Erro ao iniciar `{file_name}`: {e}")
            if key in bot_scripts: del bot_scripts[key]
    except Exception as e:
        bot.reply_to(msg_obj, f"❌ Erro inesperado no JS: {e}")
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key]); del bot_scripts[key]

# ═══════════════════════════════════════════════════════
#  DATABASE OPERATIONS
# ═══════════════════════════════════════════════════════
DB_LOCK = threading.Lock()

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files VALUES (?,?,?)', (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn,ft) for fn,ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        except Exception as e: logger.error(f"❌ save_user_file: {e}")
        finally: conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
        except Exception as e: logger.error(f"❌ remove_user_file_db: {e}")
        finally: conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users VALUES (?)', (user_id,))
            conn.commit()
        except Exception as e: logger.error(f"❌ add_active_user: {e}")
        finally: conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO subscriptions VALUES (?,?)', (user_id, expiry.isoformat()))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except Exception as e: logger.error(f"❌ save_subscription: {e}")
        finally: conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id=?', (user_id,))
            conn.commit()
            user_subscriptions.pop(user_id, None)
        except Exception as e: logger.error(f"❌ remove_subscription_db: {e}")
        finally: conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (admin_id,))
            admin_ids.add(admin_id)
        except Exception as e: logger.error(f"❌ add_admin_db: {e}")
        finally: conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        removed = False
        try:
            c.execute('DELETE FROM admins WHERE user_id=?', (admin_id,))
            conn.commit()
            removed = c.rowcount > 0
            if removed: admin_ids.discard(admin_id)
        except Exception as e: logger.error(f"❌ remove_admin_db: {e}")
        finally: conn.close()
        return removed

# ═══════════════════════════════════════════════════════
#  MENU BUILDERS
# ═══════════════════════════════════════════════════════
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if user_id in admin_ids:
        markup.add(
            types.InlineKeyboardButton('📤 Enviar Arquivo',  callback_data='upload'),
            types.InlineKeyboardButton('📂 Meus Arquivos',     callback_data='check_files'),
        )
        markup.add(
            types.InlineKeyboardButton('⚡ Velocidade',   callback_data='speed'),
            types.InlineKeyboardButton('📊 Estatísticas',   callback_data='stats'),
        )
        markup.add(
            types.InlineKeyboardButton('💳 Assinaturas',callback_data='subscription'),
            types.InlineKeyboardButton('📢 Transmissão',    callback_data='broadcast'),
        )
        markup.add(
            types.InlineKeyboardButton('🔒 Bloquear Bot' if not bot_locked else '🔓 Desbloquear Bot',
                callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('🟢 Rodar Tudo', callback_data='run_all_scripts'),
        )
        markup.add(
            types.InlineKeyboardButton('📤 Enviar Comando', callback_data='send_command'),
            types.InlineKeyboardButton('👑 Painel Admin',  callback_data='admin_panel'),
        )
    else:
        markup.add(
            types.InlineKeyboardButton('📤 Enviar Arquivo',  callback_data='upload'),
            types.InlineKeyboardButton('📂 Meus Arquivos',     callback_data='check_files'),
        )
        markup.add(
            types.InlineKeyboardButton('⚡ Velocidade',   callback_data='speed'),
            types.InlineKeyboardButton('📊 Estatísticas',   callback_data='stats'),
        )
        markup.add(
            types.InlineKeyboardButton('📤 Enviar Comando', callback_data='send_command'),
        )
    markup.add(
        types.InlineKeyboardButton(f'📞 Contato — {CREDIT}',
            url=f'https://t.me/{YOUR_USERNAME.lstrip("@")}')
    )
    return markup

def create_reply_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout = COMMAND_BUTTONS_LAYOUT_ADMIN if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER
    for row in layout:
        labels = []
        for label in row:
            if label in ('🔒 Bloquear Bot', '🔓 Desbloquear Bot'):
                label = '🔓 Desbloquear Bot' if bot_locked else '🔒 Bloquear Bot'
            labels.append(types.KeyboardButton(label))
        markup.add(*labels)
    return markup

def show_reply_main_menu(chat_id, user_id, text, source_message=None):
    """Mostra o menu principal como teclado fixo na área de digitação."""
    if source_message is not None:
        try:
            bot.edit_message_reply_markup(chat_id, source_message.message_id, reply_markup=None)
        except Exception:
            pass
    return bot.send_message(
        chat_id, text, reply_markup=create_reply_keyboard(user_id), parse_mode='Markdown')

def _short_callback_id(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:16]

def file_callback_data(action, owner_id, file_name):
    return f"f:{action}:{owner_id}:{_short_callback_id(file_name)}"

def create_control_buttons(owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Parar", callback_data=file_callback_data('stop', owner_id, file_name)),
            types.InlineKeyboardButton("🔄 Reiniciar", callback_data=file_callback_data('restart', owner_id, file_name)),
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Excluir", callback_data=file_callback_data('delete', owner_id, file_name)),
            types.InlineKeyboardButton("📜 Logs", callback_data=file_callback_data('logs', owner_id, file_name)),
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Iniciar", callback_data=file_callback_data('start', owner_id, file_name)),
            types.InlineKeyboardButton("🗑️ Excluir", callback_data=file_callback_data('delete', owner_id, file_name)),
        )
        markup.row(
            types.InlineKeyboardButton("📜 Ver Logs", callback_data=file_callback_data('logs', owner_id, file_name)),
        )
    markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin',    callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remover Admin', callback_data='remove_admin'),
    )
    markup.row(types.InlineKeyboardButton('📋 Listar Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Voltar', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Sub',    callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remover Sub', callback_data='remove_subscription'),
    )
    markup.row(types.InlineKeyboardButton('🔍 Verificar Sub', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Voltar', callback_data='back_to_main'))
    return markup

def create_send_command_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📝 Enviar para Processo', callback_data='send_to_process'),
        types.InlineKeyboardButton('🗂️ Ver Todos os Logs',   callback_data='view_all_logs'),
    )
    markup.row(types.InlineKeyboardButton('🔙 Voltar', callback_data='back_to_main'))
    return markup

# ═══════════════════════════════════════════════════════
#  FILE HANDLING
# ═══════════════════════════════════════════════════════
def handle_zip_file(content, zip_name, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    tmp = None
    try:
        tmp = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(tmp, zip_name)
        with open(zip_path, 'wb') as f: f.write(content)
        with zipfile.ZipFile(zip_path, 'r') as zr:
            zr.extractall(tmp)

        target = tmp
        root_files = os.listdir(target)
        if not any(f.endswith(('.py','.js')) for f in root_files):
            for root, dirs, files in os.walk(tmp):
                dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('__')]
                if any(f.endswith(('.py','.js')) for f in files):
                    target = root; break
        if target != tmp:
            for item in os.listdir(target):
                s = os.path.join(target, item); d = os.path.join(tmp, item)
                if os.path.exists(d):
                    shutil.rmtree(d) if os.path.isdir(d) else os.remove(d)
                shutil.move(s, d)

        items = os.listdir(tmp)
        py_files = [f for f in items if f.endswith('.py')]
        js_files = [f for f in items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in items else None
        pkg_json = 'package.json'     if 'package.json'      in items else None

        if req_file:
            bot.reply_to(message, "🔄 Instalando dependências Python...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', os.path.join(tmp, req_file)],
                               check=True, capture_output=True, encoding='utf-8', errors='ignore')
                bot.reply_to(message, "✅ Deps Python instaladas.")
            except subprocess.CalledProcessError as e:
                bot.reply_to(message, f"❌ Falha no pip install:\n```\n{(e.stderr or e.stdout)[:1500]}\n```", parse_mode='Markdown'); return

        if pkg_json:
            bot.reply_to(message, "🔄 Instalando dependências Node...")
            try:
                subprocess.run(['npm', 'install'], check=True, capture_output=True, cwd=tmp, encoding='utf-8', errors='ignore')
                bot.reply_to(message, "✅ Deps Node instaladas.")
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                bot.reply_to(message, f"❌ Falha no npm install: {e}"); return

        main_script = None; file_type = None
        for p in ['main.py','bot.py','app.py']:
            if p in py_files: main_script = p; file_type = 'py'; break
        if not main_script:
            for p in ['index.js','main.js','bot.js','app.js']:
                if p in js_files: main_script = p; file_type = 'js'; break
        if not main_script:
            if py_files: main_script = py_files[0]; file_type = 'py'
            elif js_files: main_script = js_files[0]; file_type = 'js'
        if not main_script:
            bot.reply_to(message, "❌ Nenhum arquivo `.py` ou `.js` encontrado no arquivo!"); return

        for item in os.listdir(tmp):
            if item == zip_name: continue
            s = os.path.join(tmp, item); d = os.path.join(user_folder, item)
            if os.path.exists(d):
                shutil.rmtree(d) if os.path.isdir(d) else os.remove(d)
            shutil.move(s, d)

        save_user_file(user_id, main_script, file_type)
        main_path = os.path.join(user_folder, main_script)
        bot.reply_to(message, f"✅ Extraído. Iniciando `{main_script}`...", parse_mode='Markdown')
        fn = run_script if file_type == 'py' else run_js_script
        threading.Thread(target=fn, args=(main_path, user_id, user_folder, main_script, message)).start()
    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"❌ ZIP inválido: {e}")
    except Exception as e:
        logger.error(f"❌ ZIP error for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Erro ao processar zip: {e}")
    finally:
        if tmp and os.path.exists(tmp):
            try: shutil.rmtree(tmp)
            except: pass

def handle_js_file(path, owner_id, folder, name, msg):
    save_user_file(owner_id, name, 'js')
    threading.Thread(target=run_js_script, args=(path, owner_id, folder, name, msg)).start()

def handle_py_file(path, owner_id, folder, name, msg):
    save_user_file(owner_id, name, 'py')
    threading.Thread(target=run_script, args=(path, owner_id, folder, name, msg)).start()

# ═══════════════════════════════════════════════════════
#  SEND COMMAND / LOGS HELPERS
# ═══════════════════════════════════════════════════════
def send_to_process_init(message):
    user_id = message.from_user.id
    running = [(k, v) for k, v in bot_scripts.items()
               if (user_id == v['script_owner_id'] or user_id in admin_ids)
               and is_bot_running(v['script_owner_id'], v['file_name'])]
    if not running:
        bot.reply_to(message, "❌ Nenhum script em execução encontrado."); return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, info in running:
        markup.add(types.InlineKeyboardButton(
            f"{info['file_name']} (UID: {info['script_owner_id']})",
            callback_data=f"s:{_short_callback_id(key)}"))
    markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data='send_command'))
    bot.reply_to(message, "📝 Selecione o script:", reply_markup=markup)

def process_send_command(message, script_key):
    if script_key not in bot_scripts:
        bot.reply_to(message, "❌ Script não está mais rodando."); return
    info = bot_scripts[script_key]
    try:
        proc = info['process']
        if proc and proc.poll() is None:
            proc.stdin.write(message.text + '\n')
            proc.stdin.flush()
            bot.reply_to(message, f"✅ Enviado para `{info['file_name']}`:\n`{message.text}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"❌ `{info['file_name']}` não está rodando.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Erro: {e}")

def view_all_logs(message, user_id=None):
    user_id = user_id if user_id is not None else message.from_user.id
    folder = get_user_folder(user_id)
    logs = []
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.endswith('.log'):
                p = os.path.join(folder, f)
                logs.append((f, os.path.getsize(p), p))
    if not logs:
        bot.reply_to(message, "📜 Nenhum arquivo de log encontrado."); return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for lf, sz, _ in sorted(logs):
        markup.add(types.InlineKeyboardButton(f"{lf} ({sz/1024:.1f} KB)",
                                              callback_data=f"l:{user_id}:{_short_callback_id(lf)}"))
    markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data='send_command'))
    bot.reply_to(message, "📜 Arquivos de Log:", reply_markup=markup)

def send_log_file(message, log_path, log_filename):
    try:
        if os.path.getsize(log_path) > 50 * 1024 * 1024:
            bot.reply_to(message, "❌ Log muito grande (>50 MB)."); return
        with open(log_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"📜 {log_filename}")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao enviar log: {e}")

# ═══════════════════════════════════════════════════════
#  LOGIC FUNCTIONS
# ═══════════════════════════════════════════════════════
def _logic_send_welcome(message, user_override=None):
    user = user_override or message.from_user
    user_id  = user.id
    chat_id  = message.chat.id
    name     = user.first_name
    username = user.username
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ O bot está temporariamente bloqueado para novos usuários."); return
    add_active_user(user_id)
    limit = get_user_file_limit(user_id); count = get_user_file_count(user_id)
    ls = str(limit) if limit != float('inf') else "∞"
    if user_id == OWNER_ID:    st = "👑 Dono"
    elif user_id in admin_ids: st = "🛡️ Admin"
    elif user_id in user_subscriptions:
        exp = user_subscriptions[user_id].get('expiry')
        st  = "⭐ Premium" if exp and exp > datetime.now() else "🆓 Grátis"
    else: st = "🆓 Grátis"
    text = (f"💀 *{BOT_NAME}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👋 Olá, {name}!\n"
            f"🆔 Seu ID: `{user_id}`\n"
            f"🔰 Status: {st}\n"
            f"📁 Arquivos: {count}/{ls}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🚀 Envie um arquivo `.py`, `.js` ou `.zip` para começar a hospedar!")
    try:
        bot.send_photo(chat_id, WELCOME_IMAGE_URL)
    except Exception as e:
        logger.warning(f"Não foi possível enviar a imagem de boas-vindas: {e}")
    bot.send_message(chat_id, text, reply_markup=create_reply_keyboard(user_id), parse_mode='Markdown')

def _logic_upload_file(message):
    user_id = message.from_user.id
    limit = get_user_file_limit(user_id); count = get_user_file_count(user_id)
    if count >= limit:
        ls = str(limit) if limit != float('inf') else "∞"
        bot.reply_to(message, f"⚠️ Limite de arquivos ({count}/{ls}) atingido."); return
    bot.reply_to(message, "📤 Envie seu arquivo `.py`, `.js` ou `.zip` para hospedagem.")

def _logic_check_files(message):
    user_id = message.from_user.id
    files   = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "⚠️ Você ainda não enviou nenhum arquivo."); return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(files):
        icon = "🟢" if is_bot_running(user_id, fn) else "🔴"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn} [{ft}]", callback_data=file_callback_data('open', user_id, fn)))
    bot.reply_to(message, "📂 *Seus Arquivos*:", reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    t0 = time.time()
    msg = bot.reply_to(message, "⏱️ Testando velocidade...")
    lat = round((time.time() - t0) * 1000, 2)
    bot.edit_message_text(f"⚡ *Velocidade*: `{lat} ms`", message.chat.id, msg.message_id, parse_mode='Markdown')

def _logic_statistics(message, user_id=None):
    user_id = user_id if user_id is not None else message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Apenas administradores podem ver estatísticas."); return
    total_users = len(active_users)
    total_files = sum(len(f) for f in user_files.values())
    running_bots = sum(1 for v in bot_scripts.values() if is_bot_running(v['script_owner_id'], v['file_name']))
    text = (f"📊 *Estatísticas do Sistema*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 Usuários: {total_users}\n"
            f"📁 Arquivos: {total_files}\n"
            f"🟢 Bots Online: {running_bots}\n"
            f"━━━━━━━━━━━━━━━")
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_send_command(message):
    bot.reply_to(message, "📤 *Menu de Comandos*", reply_markup=create_send_command_menu(), parse_mode='Markdown')

def _logic_contact_owner(message):
    bot.reply_to(message, f"📞 Para suporte, contate {CREDIT} em {YOUR_USERNAME}")

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids: return
    bot.reply_to(message, "💳 *Gerenciador de Assinaturas*", reply_markup=create_subscription_menu(), parse_mode='Markdown')

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids: return
    msg = bot.reply_to(message, "📢 Envie a mensagem que deseja transmitir para todos os usuários ou /cancel.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Transmissão cancelada."); return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Confirmar", callback_data='confirm_broadcast_msg'))
    markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data='cancel_broadcast'))
    bot.reply_to(message, "⚠️ *Deseja enviar esta mensagem para todos?*", reply_markup=markup, parse_mode='Markdown')
    # Armazenar temporariamente a mensagem para transmissão (em uma variável global simples para este exemplo)
    global temp_broadcast_msg
    temp_broadcast_msg = message

def handle_confirm_broadcast(call):
    bot.answer_callback_query(call.id, "📢 Iniciando transmissão...")
    count = 0; fail = 0
    for uid in active_users:
        try:
            bot.copy_message(uid, temp_broadcast_msg.chat.id, temp_broadcast_msg.message_id)
            count += 1
            time.sleep(0.05)
        except: fail += 1
    bot.send_message(call.message.chat.id, f"📢 Transmissão concluída!\n✅ Sucesso: {count}\n❌ Falha: {fail}")

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Cancelado.")
    bot.edit_message_text("❌ Transmissão cancelada.", call.message.chat.id, call.message.message_id)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids: return
    global bot_locked
    bot_locked = not bot_locked
    st = "🔒 Bloqueado" if bot_locked else "🔓 Desbloqueado"
    bot.reply_to(message, f"🤖 O bot agora está: *{st}*", reply_markup=create_reply_keyboard(message.from_user.id), parse_mode='Markdown')

def _logic_run_all_scripts(message):
    is_callback = hasattr(message, 'data') and hasattr(message, 'message')
    actor_id = message.from_user.id
    chat_id = message.message.chat.id if is_callback else message.chat.id
    if actor_id not in admin_ids: return
    bot.send_message(chat_id, "🟢 Iniciando todos os scripts parados...")
    count = 0
    for uid, files in list(user_files.items()):
        for fname, ftype in list(files):
            if not is_bot_running(uid, fname):
                folder = get_user_folder(uid); fpath = os.path.join(folder, fname)
                if os.path.exists(fpath):
                    fn = run_script if ftype == 'py' else run_js_script
                    threading.Thread(target=fn, args=(fpath, uid, folder, fname, message.message if is_callback else message)).start()
                    count += 1; time.sleep(0.5)
    bot.send_message(chat_id, f"✅ Tentativa de iniciar {count} scripts concluída.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids: return
    bot.reply_to(message, "👑 *Painel Administrativo*", reply_markup=create_admin_panel(), parse_mode='Markdown')

# ═══════════════════════════════════════════════════════
#  BUTTON TEXT MAP
# ═══════════════════════════════════════════════════════
BUTTON_MAP = {
    "📤 Enviar Arquivo":    _logic_upload_file,
    "📂 Meus Arquivos":       _logic_check_files,
    "⚡ Teste de Velocidade":     _logic_bot_speed,
    "📊 Estatísticas":     _logic_statistics,
    "📤 Enviar Comando":   _logic_send_command,
    "📞 Contatar Proprietário":  _logic_contact_owner,
    "💳 Assinaturas":  _logic_subscriptions_panel,
    "📢 Transmissão":      _logic_broadcast_init,
    "🔒 Bloquear Bot":       _logic_toggle_lock_bot,
    "🔓 Desbloquear Bot":    _logic_toggle_lock_bot,
    "🟢 Rodar Todos os Scripts":_logic_run_all_scripts,
    "👑 Painel Admin":    _logic_admin_panel,
}

# ═══════════════════════════════════════════════════════
#  COMMAND & TEXT HANDLERS
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message): _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def cmd_status(message): _logic_statistics(message)

@bot.message_handler(commands=['ping'])
def cmd_ping(message):
    t0  = time.time()
    msg = bot.reply_to(message, "🏓 Pong!")
    lat = round((time.time() - t0) * 1000, 2)
    bot.edit_message_text(f"🏓 Pong! `{lat} ms`", message.chat.id, msg.message_id, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text in BUTTON_MAP)
def handle_buttons(message):
    fn = BUTTON_MAP.get(message.text)
    if fn: fn(message)

@bot.message_handler(commands=['uploadfile'])
def cmd_upload(m): _logic_upload_file(m)
@bot.message_handler(commands=['checkfiles'])
def cmd_check(m):  _logic_check_files(m)
@bot.message_handler(commands=['speed'])
def cmd_speed(m):  _logic_bot_speed(m)
@bot.message_handler(commands=['stats'])
def cmd_stats(m):  _logic_statistics(m)
@bot.message_handler(commands=['sendcommand'])
def cmd_sendcmd(m): _logic_send_command(m)
@bot.message_handler(commands=['contact'])
def cmd_contact(m): _logic_contact_owner(m)
@bot.message_handler(commands=['lock'])
def cmd_lock(m):   _logic_toggle_lock_bot(m)
@bot.message_handler(commands=['runall'])
def cmd_runall(m): _logic_run_all_scripts(m)
@bot.message_handler(commands=['admin'])
def cmd_admin(m):  _logic_admin_panel(m)

# ═══════════════════════════════════════════════════════
#  DOCUMENT (FILE UPLOAD) HANDLER
# ═══════════════════════════════════════════════════════
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    doc     = message.document

    if not is_member(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Entrar no Canal",
            url=f"https://t.me/{FORCE_JOIN_CHANNEL.lstrip('@')}"))
        markup.add(types.InlineKeyboardButton("🔄 Já entrei — Verificar", callback_data='verify_join'))
        bot.reply_to(message, f"⚠️ Entre no canal {FORCE_JOIN_CHANNEL} primeiro!",
                     reply_markup=markup); return

    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot bloqueado."); return

    limit = get_user_file_limit(user_id)
    count = get_user_file_count(user_id)
    if count >= limit:
        ls = str(limit) if limit != float('inf') else "∞"
        bot.reply_to(message, f"⚠️ Limite de arquivos ({count}/{ls}) atingido."); return

    fname = doc.file_name
    if not fname:
        bot.reply_to(message, "⚠️ O arquivo não tem nome."); return
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Apenas `.py`, `.js`, `.zip` são permitidos."); return
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "⚠️ Arquivo muito grande (máx 20 MB)."); return

    try:
        try:
            bot.forward_message(OWNER_ID, message.chat.id, message.message_id)
            bot.send_message(OWNER_ID,
                f"📁 Arquivo `{fname}` de {message.from_user.first_name} (`{user_id}`)",
                parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not forward to owner: {e}")

        wait = bot.reply_to(message, f"⏳ Baixando `{fname}`...", parse_mode='Markdown')
        finfo   = bot.get_file(doc.file_id)
        content = bot.download_file(finfo.file_path)

        bot.edit_message_text(f"✅ Baixado `{fname}`. Processando...",
                              message.chat.id, wait.message_id, parse_mode='Markdown')
        user_folder = get_user_folder(user_id)

        if ext == '.zip':
            handle_zip_file(content, fname, message)
        else:
            fpath = os.path.join(user_folder, fname)
            with open(fpath, 'wb') as f: f.write(content)
            if ext == '.js': handle_js_file(fpath, user_id, user_folder, fname, message)
            else:            handle_py_file(fpath, user_id, user_folder, fname, message)

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API error for {user_id}: {e}")
        bot.reply_to(message, f"❌ Erro na API do Telegram: {e}")
    except Exception as e:
        logger.error(f"File upload error for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Erro inesperado: {e}")

# ═══════════════════════════════════════════════════════
#  CALLBACK QUERY ROUTER
# ═══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data    = call.data

    # Force-join verify
    if data == 'verify_join':
        if is_member(user_id):
            bot.answer_callback_query(call.id, "✅ Verificado! Use /start para continuar.")
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            _logic_send_welcome(call.message, call.from_user)
        else:
            bot.answer_callback_query(call.id,
                f"❌ Você ainda não entrou no canal {FORCE_JOIN_CHANNEL}!", show_alert=True)
        return

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main','speed','stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot bloqueado.", show_alert=True); return

    try:
        if   data.startswith('f:'):     _dispatch_short_file_callback(call)
        elif data.startswith('l:'):      _dispatch_short_log_callback(call)
        elif data.startswith('s:'):      _dispatch_short_send_command_callback(call)
        elif data == 'upload':           upload_callback(call)
        elif data == 'check_files':      check_files_callback(call)
        elif data.startswith('file_'):   file_control_callback(call)
        elif data.startswith('start_'):  start_bot_callback(call)
        elif data.startswith('stop_'):   stop_bot_callback(call)
        elif data.startswith('restart_'):restart_bot_callback(call)
        elif data.startswith('delete_'): delete_bot_callback(call)
        elif data.startswith('logs_'):   logs_bot_callback(call)
        elif data == 'speed':            speed_callback(call)
        elif data == 'back_to_main':     back_to_main_callback(call)
        elif data == 'send_command':     send_command_callback(call)
        elif data == 'send_to_process':  send_to_process_callback(call)
        elif data.startswith('sendcmd_select_'): sendcmd_select_callback(call)
        elif data == 'view_all_logs':    view_all_logs_callback(call)
        elif data.startswith('viewlog_'):viewlog_callback(call)
        elif data == 'subscription':     _admin_cb(call, subscription_management_callback)
        elif data == 'stats':            stats_callback(call)
        elif data == 'lock_bot':         _admin_cb(call, lock_bot_callback)
        elif data == 'unlock_bot':       _admin_cb(call, unlock_bot_callback)
        elif data == 'run_all_scripts':  _admin_cb(call, run_all_scripts_callback)
        elif data == 'broadcast':        _admin_cb(call, broadcast_init_callback)
        elif data == 'admin_panel':      _admin_cb(call, admin_panel_callback)
        elif data == 'add_admin':        _owner_cb(call, add_admin_init_callback)
        elif data == 'remove_admin':     _owner_cb(call, remove_admin_init_callback)
        elif data == 'list_admins':      _admin_cb(call, list_admins_callback)
        elif data == 'add_subscription': _admin_cb(call, add_subscription_init_callback)
        elif data == 'remove_subscription': _admin_cb(call, remove_subscription_init_callback)
        elif data == 'check_subscription':  _admin_cb(call, check_subscription_init_callback)
        elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast': handle_cancel_broadcast(call)
        else:
            bot.answer_callback_query(call.id, "Ação desconhecida.")
    except Exception as e:
        logger.error(f"Callback error '{data}' for {user_id}: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Erro ao processar.", show_alert=True)
        except: pass

def _admin_cb(call, fn):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Apenas Admin.", show_alert=True); return
    fn(call)

def _owner_cb(call, fn):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Apenas Dono.", show_alert=True); return
    fn(call)

# ═══════════════════════════════════════════════════════
#  CALLBACK IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════
def update_callback_message(call, text, reply_markup=None, parse_mode=None):
    """Edit callback screens correctly whether the original menu is text or a photo caption."""
    message = call.message
    chat_id, message_id = message.chat.id, message.message_id
    is_photo = bool(getattr(message, 'photo', None))
    try:
        if is_photo and len(text) <= 1000:
            return bot.edit_message_caption(
                chat_id=chat_id, message_id=message_id, caption=text,
                reply_markup=reply_markup, parse_mode=parse_mode)
        if not is_photo:
            return bot.edit_message_text(
                text, chat_id, message_id, reply_markup=reply_markup, parse_mode=parse_mode)
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' in str(e).lower():
            return None
        logger.warning(f"Não foi possível editar a tela do callback: {e}")
    # Captions têm limite menor que mensagens de texto; também recupera mensagens que não podem ser editadas.
    try:
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
    except Exception:
        pass
    return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

def _dispatch_short_file_callback(call):
    try:
        _, action, owner_text, digest = call.data.split(':', 3)
        owner_id = int(owner_text)
        if action not in {'open', 'start', 'stop', 'restart', 'delete', 'logs'}:
            raise ValueError('ação inválida')
        file_name = next((fn for fn, _ in user_files.get(owner_id, [])
                          if _short_callback_id(fn) == digest), None)
        if file_name is None:
            bot.answer_callback_query(call.id, 'Arquivo não encontrado; atualize a lista.', show_alert=True)
            return
        legacy_action = {'open': 'file'}.get(action, action)
        call.data = f"{legacy_action}_{owner_id}_{file_name}"
        {'open': file_control_callback, 'start': start_bot_callback, 'stop': stop_bot_callback,
         'restart': restart_bot_callback, 'delete': delete_bot_callback, 'logs': logs_bot_callback}[action](call)
    except Exception as e:
        logger.error(f"Callback curto de arquivo inválido: {e}", exc_info=True)
        bot.answer_callback_query(call.id, 'Não foi possível abrir esse arquivo.', show_alert=True)

def _dispatch_short_log_callback(call):
    try:
        _, owner_text, digest = call.data.split(':', 2)
        owner_id = int(owner_text)
        folder = get_user_folder(owner_id)
        log_name = next((name for name in os.listdir(folder)
                         if name.endswith('.log') and _short_callback_id(name) == digest), None)
        if log_name is None:
            bot.answer_callback_query(call.id, 'Log não encontrado; atualize a lista.', show_alert=True)
            return
        call.data = f"viewlog_{owner_id}_{log_name}"
        viewlog_callback(call)
    except Exception as e:
        logger.error(f"Callback curto de log inválido: {e}", exc_info=True)
        bot.answer_callback_query(call.id, 'Não foi possível abrir esse log.', show_alert=True)

def _dispatch_short_send_command_callback(call):
    digest = call.data.split(':', 1)[1]
    key = next((candidate for candidate in bot_scripts
                if _short_callback_id(candidate) == digest), None)
    if key is None:
        bot.answer_callback_query(call.id, 'Esse processo não está mais disponível.', show_alert=True)
        return
    call.data = f"sendcmd_select_{key}"
    sendcmd_select_callback(call)

def upload_callback(call):
    user_id = call.from_user.id
    limit = get_user_file_limit(user_id); count = get_user_file_count(user_id)
    if count >= limit:
        ls = str(limit) if limit != float('inf') else "∞"
        bot.answer_callback_query(call.id, f"⚠️ Limite de arquivos ({count}/{ls}) atingido.", show_alert=True); return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📤 Envie seu arquivo `.py`, `.js`, ou `.zip`.", parse_mode='Markdown')

def check_files_callback(call):
    user_id = call.from_user.id
    files   = user_files.get(user_id, [])
    if not files:
        bot.answer_callback_query(call.id, "⚠️ Nenhum arquivo enviado.", show_alert=True)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data='back_to_main'))
        update_callback_message(call, "📂 Sem arquivos ainda.", reply_markup=markup)
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(files):
        icon = "🟢" if is_bot_running(user_id, fn) else "🔴"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn} [{ft}]", callback_data=file_callback_data('open', user_id, fn)))
    markup.add(types.InlineKeyboardButton("🔙 Voltar", callback_data='back_to_main'))
    update_callback_message(call, "📂 *Seus Arquivos*:", reply_markup=markup, parse_mode='Markdown')

def file_control_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        files = user_files.get(oid, [])
        if not any(f[0] == fname for f in files):
            bot.answer_callback_query(call.id, "⚠️ Arquivo não encontrado.", show_alert=True); return
        bot.answer_callback_query(call.id)
        running = is_bot_running(oid, fname)
        ft = next((f[1] for f in files if f[0] == fname), '?')
        status = "🟢 Rodando" if running else "🔴 Parado"
        update_callback_message(
            call, f"⚙️ *{fname}* `[{ft}]`\nDono: `{oid}` | Status: {status}",
            reply_markup=create_control_buttons(oid, fname, running), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"file_control_callback: {e}")
        bot.answer_callback_query(call.id, "Erro.", show_alert=True)

def start_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        files = user_files.get(oid, [])
        fi = next((f for f in files if f[0] == fname), None)
        if not fi:
            bot.answer_callback_query(call.id, "⚠️ Arquivo não encontrado.", show_alert=True); return
        ft = fi[1]; folder = get_user_folder(oid); fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            bot.answer_callback_query(call.id, f"⚠️ Arquivo ausente. Reenvie.", show_alert=True)
            remove_user_file_db(oid, fname); return
        if is_bot_running(oid, fname):
            bot.answer_callback_query(call.id, "⚠️ Já está rodando.", show_alert=True); return
        bot.answer_callback_query(call.id, f"▶️ Iniciando {fname}...")
        fn = run_script if ft == 'py' else run_js_script
        threading.Thread(target=fn, args=(fpath, oid, folder, fname, call.message)).start()
        time.sleep(1.5)
        running = is_bot_running(oid, fname)
        status  = "🟢 Rodando" if running else "🟡 Iniciando..."
        update_callback_message(call, f"⚙️ *{fname}* `[{ft}]`\nStatus: {status}",
            reply_markup=create_control_buttons(oid, fname, running), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"start_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Erro ao iniciar.", show_alert=True)

def stop_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        files = user_files.get(oid, [])
        fi = next((f for f in files if f[0] == fname), None)
        if not fi:
            bot.answer_callback_query(call.id, "⚠️ Arquivo não encontrado.", show_alert=True); return
        ft = fi[1]; key = f"{oid}_{fname}"
        if not is_bot_running(oid, fname):
            bot.answer_callback_query(call.id, "⚠️ Não está rodando.", show_alert=True); return
        bot.answer_callback_query(call.id, f"⏹️ Parando {fname}...")
        info = bot_scripts.get(key)
        if info: kill_process_tree(info)
        bot_scripts.pop(key, None)
        update_callback_message(call, f"⚙️ *{fname}* `[{ft}]`\nStatus: 🔴 Parado",
            reply_markup=create_control_buttons(oid, fname, False), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"stop_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Erro ao parar.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        files = user_files.get(oid, [])
        fi = next((f for f in files if f[0] == fname), None)
        if not fi:
            bot.answer_callback_query(call.id, "⚠️ Arquivo não encontrado.", show_alert=True); return
        ft = fi[1]; folder = get_user_folder(oid); fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            bot.answer_callback_query(call.id, "⚠️ Arquivo ausente. Reenvie.", show_alert=True)
            remove_user_file_db(oid, fname); return
        bot.answer_callback_query(call.id, f"🔄 Reiniciando {fname}...")
        key = f"{oid}_{fname}"
        if is_bot_running(oid, fname):
            info = bot_scripts.get(key)
            if info: kill_process_tree(info)
            bot_scripts.pop(key, None)
            time.sleep(1.5)
        fn = run_script if ft == 'py' else run_js_script
        threading.Thread(target=fn, args=(fpath, oid, folder, fname, call.message)).start()
        time.sleep(1.5)
        running = is_bot_running(oid, fname)
        status  = "🟢 Rodando" if running else "🟡 Iniciando..."
        update_callback_message(call, f"⚙️ *{fname}* `[{ft}]`\nStatus: {status}",
            reply_markup=create_control_buttons(oid, fname, running), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"restart_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Erro ao reiniciar.", show_alert=True)

def delete_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        if not any(f[0] == fname for f in user_files.get(oid, [])):
            bot.answer_callback_query(call.id, "⚠️ Arquivo não encontrado.", show_alert=True); return
        bot.answer_callback_query(call.id, f"🗑️ Excluindo {fname}...")
        key = f"{oid}_{fname}"
        if is_bot_running(oid, fname):
            info = bot_scripts.get(key)
            if info: kill_process_tree(info)
            bot_scripts.pop(key, None)
        folder = get_user_folder(oid)
        for p in [os.path.join(folder, fname),
                  os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")]:
            try:
                if os.path.exists(p): os.remove(p)
            except OSError as e: logger.error(f"Delete error {p}: {e}")
        remove_user_file_db(oid, fname)
        update_callback_message(call, f"🗑️ `{fname}` excluído com sucesso!", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"delete_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Erro ao excluir.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        if not any(f[0] == fname for f in user_files.get(oid, [])):
            bot.answer_callback_query(call.id, "⚠️ Arquivo não encontrado.", show_alert=True); return
        log_path = os.path.join(get_user_folder(oid), f"{os.path.splitext(fname)[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, "⚠️ Sem logs ainda.", show_alert=True); return
        bot.answer_callback_query(call.id)
        size = os.path.getsize(log_path)
        if size == 0: content = "(Log está vazio)"
        elif size > 100 * 1024:
            with open(log_path, 'rb') as f:
                f.seek(-100*1024, os.SEEK_END); raw = f.read()
            content = "(Últimos 100 KB)\n...\n" + raw.decode('utf-8', errors='ignore')
        else:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        if len(content) > 4000: content = "...\n" + content[-3900:]
        if not content.strip(): content = "(Vazio)"
        bot.send_message(call.message.chat.id,
            f"📜 *Logs* — `{fname}`:\n```\n{content}\n```", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"logs_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Erro ao buscar logs.", show_alert=True)

def speed_callback(call):
    uid = call.from_user.id; cid = call.message.chat.id
    t0  = time.time()
    try:
        bot.send_chat_action(cid, 'typing')
        ms = round((time.time() - t0) * 1000, 2)
        if uid == OWNER_ID:    lvl = "👑 Dono"
        elif uid in admin_ids: lvl = "🛡️ Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            lvl = "⭐ Premium"
        else: lvl = "🆓 Grátis"
        text = (f"⚡ *Relatório de Velocidade*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📶 Ping: `{ms} ms`\n"
                f"🚦 Bot: {'🔒 Bloqueado' if bot_locked else '🟢 Online'}\n"
                f"👤 Você: {lvl}\n"
                f"━━━━━━━━━━━━━━━")
        bot.answer_callback_query(call.id)
        show_reply_main_menu(cid, uid, text, source_message=call.message)
    except Exception as e:
        bot.answer_callback_query(call.id, "Erro.", show_alert=True)

def back_to_main_callback(call):
    uid = call.from_user.id
    limit = get_user_file_limit(uid); count = get_user_file_count(uid)
    ls = str(limit) if limit != float('inf') else "∞"
    if uid == OWNER_ID:    st = "👑 Dono"
    elif uid in admin_ids: st = "🛡️ Admin"
    elif uid in user_subscriptions:
        exp = user_subscriptions[uid].get('expiry')
        st  = "⭐ Premium" if exp and exp > datetime.now() else "🆓 Grátis"
    else: st = "🆓 Grátis"
    text = (f"💀 *{BOT_NAME}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👋 {call.from_user.first_name}\n"
            f"🆔 `{uid}` | 🔰 {st}\n"
            f"📁 Arquivos: {count}/{ls}\n"
            f"━━━━━━━━━━━━━━━")
    bot.answer_callback_query(call.id)
    show_reply_main_menu(call.message.chat.id, uid, text, source_message=call.message)

def send_command_callback(call):
    bot.answer_callback_query(call.id)
    update_callback_message(call, "📤 *Enviar Comando*",
        reply_markup=create_send_command_menu(), parse_mode='Markdown')

def send_to_process_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📝 Digite seu comando:")
    bot.register_next_step_handler(msg, send_to_process_init)

def sendcmd_select_callback(call):
    key = call.data.replace('sendcmd_select_', '')
    info = bot_scripts.get(key)
    if not info or not (call.from_user.id == info.get('script_owner_id') or call.from_user.id in admin_ids):
        bot.answer_callback_query(call.id, "⚠️ Processo indisponível ou sem permissão.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"📝 Digite o comando para `{info['file_name']}`:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, lambda m: process_send_command(m, key))

def view_all_logs_callback(call):
    bot.answer_callback_query(call.id)
    view_all_logs(call.message, call.from_user.id)

def viewlog_callback(call):
    try:
        _, uid_str, lf = call.data.split('_', 2)
        uid = int(uid_str); req = call.from_user.id
        if not (req == uid or req in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permissão negada.", show_alert=True); return
        lpath = os.path.join(get_user_folder(uid), lf)
        if not os.path.exists(lpath):
            bot.answer_callback_query(call.id, "❌ Log não encontrado.", show_alert=True); return
        bot.answer_callback_query(call.id, "📜 Enviando...")
        send_log_file(call.message, lpath, lf)
    except Exception as e:
        logger.error(f"viewlog_callback: {e}")
        bot.answer_callback_query(call.id, "Erro.", show_alert=True)

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message, call.from_user.id)

def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    update_callback_message(call, "💳 *Gerenciador de Assinaturas*",
        reply_markup=create_subscription_menu(), parse_mode='Markdown')

def lock_bot_callback(call):
    global bot_locked; bot_locked = True
    bot.answer_callback_query(call.id, "🔒 Bot bloqueado.")
    show_reply_main_menu(call.message.chat.id, call.from_user.id,
                         "🤖 O bot agora está: *🔒 Bloqueado*", source_message=call.message)

def unlock_bot_callback(call):
    global bot_locked; bot_locked = False
    bot.answer_callback_query(call.id, "🟢 Bot desbloqueado.")
    show_reply_main_menu(call.message.chat.id, call.from_user.id,
                         "🤖 O bot agora está: *🔓 Desbloqueado*", source_message=call.message)

def run_all_scripts_callback(call):
    bot.answer_callback_query(call.id)
    _logic_run_all_scripts(call)
def broadcast_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Envie mensagem de transmissão. /cancel para abortar.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def admin_panel_callback(call):
    bot.answer_callback_query(call.id)
    update_callback_message(call, "👑 *Painel Admin*",
        reply_markup=create_admin_panel(), parse_mode='Markdown')

def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Digite o ID do Usuário para promover. /cancel para abortar.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Apenas Dono."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelado."); return
    try:
        nid = int(message.text.strip())
        if nid == OWNER_ID: bot.reply_to(message, "⚠️ Já é o dono."); return
        if nid in admin_ids: bot.reply_to(message, f"⚠️ `{nid}` já é admin."); return
        add_admin_db(nid)
        bot.reply_to(message, f"✅ Usuário `{nid}` agora é Admin.", parse_mode='Markdown')
        try: bot.send_message(nid, "🎉 Você agora é um Admin!")
        except: pass
    except ValueError:
        msg = bot.reply_to(message, "⚠️ ID inválido. Tente novamente ou /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Digite o ID do Admin para remover. /cancel para abortar.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Apenas Dono."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelado."); return
    try:
        rid = int(message.text.strip())
        if rid == OWNER_ID: bot.reply_to(message, "⚠️ Não é possível remover o dono."); return
        if rid not in admin_ids: bot.reply_to(message, f"⚠️ `{rid}` não é um admin."); return
        if remove_admin_db(rid):
            bot.reply_to(message, f"✅ Admin `{rid}` removido.", parse_mode='Markdown')
            try: bot.send_message(rid, "ℹ️ Você não é mais um Admin.")
            except: pass
        else:
            bot.reply_to(message, f"❌ Erro ao remover admin `{rid}`.")
    except ValueError:
        msg = bot.reply_to(message, "⚠️ ID inválido. Tente novamente ou /cancel.")
        bot.register_next_step_handler(msg, process_remove_admin_id)

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    lines = "\n".join(f"• `{a}` {'👑' if a == OWNER_ID else ''}" for a in sorted(admin_ids))
    update_callback_message(call, f"👑 *Lista de Admins*:\n\n{lines or '(nenhum)'}",
        reply_markup=create_admin_panel(), parse_mode='Markdown')

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Digite: `USER_ID DIAS`\n/cancel para abortar.", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_add_subscription)

def process_add_subscription(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelado."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError
        uid = int(parts[0])
        days = int(parts[1])
        expiry = datetime.now() + timedelta(days=days)
        save_subscription(uid, expiry)
        bot.reply_to(message, f"✅ Sub adicionada para `{uid}` por {days} dias.\nExpira em: `{expiry.strftime('%d/%m/%Y %H:%M')}`", parse_mode='Markdown')
        try: bot.send_message(uid, f"🎉 Sua assinatura Premium foi ativada por {days} dias!")
        except: pass
    except ValueError:
        msg = bot.reply_to(message, "⚠️ Formato inválido. Use: `USER_ID DIAS` ou /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription)

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Digite o ID do Usuário para remover a sub. /cancel para abortar.")
    bot.register_next_step_handler(msg, process_remove_subscription)

def process_remove_subscription(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelado."); return
    try:
        uid = int(message.text.strip())
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ Sub removida para `{uid}`.", parse_mode='Markdown')
        try: bot.send_message(uid, "ℹ️ Sua assinatura Premium expirou ou foi removida.")
        except: pass
    except ValueError:
        msg = bot.reply_to(message, "⚠️ ID inválido. Tente novamente ou /cancel.")
        bot.register_next_step_handler(msg, process_remove_subscription)

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🔍 Digite o ID do Usuário para verificar.")
    bot.register_next_step_handler(msg, process_check_subscription)

def process_check_subscription(message):
    if message.from_user.id not in admin_ids: return
    try:
        uid = int(message.text.strip())
        sub = user_subscriptions.get(uid)
        if sub:
            exp = sub['expiry']
            rem = exp - datetime.now()
            bot.reply_to(message, f"👤 Usuário: `{uid}`\n📅 Expira em: `{exp.strftime('%d/%m/%Y %H:%M')}`\n⏳ Restam: `{rem.days}` dias.", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"👤 Usuário `{uid}` não tem sub ativa.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ ID inválido.")

# ═══════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════
if __name__ == '__main__':
    keep_alive()
    logger.info(f"Bot {BOT_NAME} is starting...")
    retry_delay = 3
    while True:
        try:
            logger.info("Iniciando polling do Telegram...")
            bot.polling(none_stop=True, interval=3, timeout=60, long_polling_timeout=60)
            # O polling não deveria retornar normalmente; se retornar, inicia novamente.
            logger.warning("Polling terminou inesperadamente; será reiniciado.")
            retry_delay = 3
        except KeyboardInterrupt:
            logger.info("Encerramento solicitado pelo usuário.")
            break
        except Exception:
            logger.exception("Falha no polling do Telegram; nova tentativa em %s s.", retry_delay)
        finally:
            try:
                bot.stop_polling()
            except Exception:
                logger.debug("stop_polling falhou durante recuperação.", exc_info=True)
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)
