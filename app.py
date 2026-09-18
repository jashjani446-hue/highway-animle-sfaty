import os
import random
import string
import time
import io
import urllib.parse
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image

# Dynamic Import for In-Built Scanning Engine
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_AVAILABLE = True
except Exception:
    PYZBAR_AVAILABLE = False

BOT_TOKEN = os.getenv("BOT_TOKEN", "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "jashjani")
FIREBASE_BASE_URL = os.getenv(
    "FIREBASE_BASE_URL", 
    "https://roadguardianai-a8d23-default-rtdb.asia-southeast1.firebasedatabase.app/RoadGuardian"
)

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

# --- FIREBASE HELPER FUNCTIONS ---

def set_firebase_data(path, data):
    try:
        url = f"{FIREBASE_BASE_URL}/{path}.json"
        requests.put(url, json=data, timeout=5)
    except Exception as e:
        print(f"Firebase Set Error: {e}")

def get_firebase_data(path):
    try:
        url = f"{FIREBASE_BASE_URL}/{path}.json"
        res = requests.get(url, timeout=5)
        if res.ok and res.json() is not None:
            return res.json()
    except Exception as e:
        print(f"Firebase Get Error: {e}")
    return {}

def is_admin(chat_id):
    admins = get_firebase_data("admins")
    return isinstance(admins, dict) and str(chat_id) in admins

def add_admin(chat_id):
    set_firebase_data(f"admins/{str(chat_id)}", True)

def set_user_state(chat_id, state):
    set_firebase_data(f"user_states/{str(chat_id)}", state)

def get_user_state(chat_id):
    return get_firebase_data(f"user_states/{str(chat_id)}")

def clear_user_state(chat_id):
    try:
        requests.delete(f"{FIREBASE_BASE_URL}/user_states/{str(chat_id)}.json", timeout=5)
    except Exception as e:
        print(f"Delete State Error: {e}")

def save_visitor_code(code, phone, duration_str):
    seconds_map = {
        "10m": 600, "1h": 3600, "5h": 18000, 
        "10h": 36000, "24h": 86400, "always": 3153600000
    }
    dur_sec = seconds_map.get(str(duration_str).lower(), 3600)
    code_data = {
        "phone": phone,
        "duration_str": duration_str,
        "dur_sec": dur_sec,
        "created_at": time.time()
    }
    set_firebase_data(f"codes/{code}", code_data)

def verify_and_register_visitor(chat_id, code):
    codes = get_firebase_data("codes")
    if isinstance(codes, dict) and code in codes:
        c_data = codes[code]
        expire_timestamp = time.time() + c_data.get("dur_sec", 3600)
        subscriber_data = {
            "code": code,
            "phone": c_data.get("phone", ""),
            "duration": c_data.get("duration_str", ""),
            "expire_at": expire_timestamp
        }
        set_firebase_data(f"subscribers/{str(chat_id)}", subscriber_data)
        return True, c_data.get("duration_str", "")
    return False, None

def get_active_recipients():
    recipients = set()
    now = time.time()
    root_data = get_firebase_data("")
    if isinstance(root_data, dict):
        admins = root_data.get("admins", {})
        if isinstance(admins, dict):
            for aid in admins.keys(): recipients.add(str(aid))
        subscribers = root_data.get("subscribers", {})
        if isinstance(subscribers, dict):
            for cid, sdata in subscribers.items():
                if isinstance(sdata, dict) and sdata.get("expire_at", 0) > now:
                    recipients.add(str(cid))
    return list(recipients)

# --- IN-BUILT QR SCANNER ENGINE ---

def scan_qr_from_bytes(image_bytes):
    """Scans QR code directly in memory using PyZbar or fallback parser"""
    extracted_text = None
    
    # 1. Primary In-Built Pure Scanning Engine
    if PYZBAR_AVAILABLE:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            decoded_objs = pyzbar_decode(img)
            if decoded_objs:
                extracted_text = decoded_objs[0].data.decode('utf-8')
                return extracted_text
        except Exception as e:
            print(f"Pyzbar engine error: {e}")

    # 2. Direct API Fallback Engine (If C-Libraries are missing on serverless host)
    try:
        files = {'file': ('qr.jpg', image_bytes, 'image/jpeg')}
        res = requests.post("https://api.qrserver.com/v1/read-qr-code/", files=files, timeout=8).json()
        if res and len(res) > 0:
            symbol = res[0].get('symbol', [])
            if symbol and len(symbol) > 0:
                extracted_text = symbol[0].get('data')
    except Exception as e:
        print(f"Fallback scan engine error: {e}")

    return extracted_text

# --- TELEGRAM BOT KEYBOARDS ---

def main_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛠️ Admin Panel", callback_data="menu_admin"))
    markup.add(InlineKeyboardButton("📸 Direct QR Scanning / Access", callback_data="menu_visitor"))
    return markup

def admin_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔑 Generate Pass (QR Code)", callback_data="admin_make_code"))
    markup.add(InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main"))
    return markup

def duration_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("10m", callback_data="dur_10m"),
        InlineKeyboardButton("1h", callback_data="dur_1h"),
        InlineKeyboardButton("5h", callback_data="dur_5h"),
        InlineKeyboardButton("10h", callback_data="dur_10h"),
        InlineKeyboardButton("24h", callback_data="dur_24h"),
        InlineKeyboardButton("Always", callback_data="dur_always")
    )
    return markup

# --- TELEGRAM BOT HANDLERS ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    bot.send_message(message.chat.id, "🏠 *RoadGuardian Control System*", parse_mode="Markdown", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "menu_main":
        bot.edit_message_text("🏠 *Main Menu*", chat_id, msg_id, reply_markup=main_menu_keyboard())
    elif call.data == "menu_admin":
        if not is_admin(chat_id):
            set_user_state(chat_id, "awaiting_admin_password")
            bot.send_message(chat_id, "🔐 Enter Admin Password:")
        else:
            bot.edit_message_text("🛠️ *Admin Panel*", chat_id, msg_id, parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    elif call.data == "admin_make_code":
        bot.edit_message_text("🔑 Select Pass Duration:", chat_id, msg_id, reply_markup=duration_keyboard())
    elif call.data.startswith("dur_"):
        duration = call.data.split("_")[1]
        set_user_state(chat_id, {"action": "awaiting_phone", "duration": duration})
        bot.send_message(chat_id, f"📱 Selected Duration: *{duration}*\nNow enter Visitor's Phone Number:")
    elif call.data == "menu_visitor":
        set_user_state(chat_id, "awaiting_visitor_code")
        bot.send_message(chat_id, "📷 *Direct QR Scanner Active!*\n\nSend or scan the QR Code photo directly into this chat now:")

# --- IN-BUILT DIRECT SCANNING HANDLER ---

@bot.message_handler(content_types=['photo'])
def handle_direct_photo_scan(message):
    chat_id = message.chat.id
    state = get_user_state(chat_id)

    if state == "awaiting_visitor_code":
        bot.send_chat_action(chat_id, 'typing')
        try:
            # Fetch highest quality image from Telegram
            file_info = bot.get_file(message.photo[-1].file_id)
            file_bytes = bot.download_file(file_info.file_path)

            # Direct In-Built QR Scan
            scanned_code = scan_qr_from_bytes(file_bytes)

            if scanned_code:
                code_clean = scanned_code.strip()
                success, duration = verify_and_register_visitor(chat_id, code_clean)
                if success:
                    bot.reply_to(message, f"🎉 *QR Code Successfully Scanned & Verified!*\n\n🎟️ Code: `{code_clean}`\n⏱️ Duration Active: *{duration}*", parse_mode="Markdown")
                else:
                    bot.reply_to(message, f"❌ QR Code contains Invalid/Expired Pass Code: `{code_clean}`", parse_mode="Markdown")
            else:
                bot.reply_to(message, "🔍 Could not read QR Code in the image. Please make sure image is sharp and clear.")

            clear_user_state(chat_id)
        except Exception as e:
            print(f"Direct scan exception: {e}")
            bot.reply_to(message, "❌ Error scanning image. Please type the Pass Code manually.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = get_user_state(chat_id)

    if text == ADMIN_PASSWORD:
        add_admin(chat_id)
        bot.reply_to(message, "🎉 *Admin Granted!*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
        clear_user_state(chat_id)
        return

    if isinstance(state, dict) and state.get("action") == "awaiting_phone":
        duration = state.get("duration")
        code = "PASS-" + ''.join(random.choices(string.digits, k=6))
        save_visitor_code(code, text, duration)

        # Generating High Resolution Dynamic QR Code
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=500x500&data={urllib.parse.quote(code)}"

        caption = (
            f"✅ *DYNAMIC VISITOR PASS CREATED*\n\n"
            f"🎟️ Code: `{code}`\n"
            f"📱 Phone: {text}\n"
            f"⏱️ Duration: {duration}\n\n"
            f"📷 *Visitors can directly send a photo of this QR to scan & get access!*"
        )
        bot.send_photo(chat_id, photo=qr_url, caption=caption, parse_mode="Markdown")
        clear_user_state(chat_id)
        return

    if state == "awaiting_visitor_code":
        success, duration = verify_and_register_visitor(chat_id, text)
        if success:
            bot.reply_to(message, f"🎉 *Access Granted!*\n⏱️ Duration: *{duration}*", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Invalid Pass Code!")
        clear_user_state(chat_id)

# --- API ENDPOINTS FOR ALERTS ---

@app.route('/api/alert', methods=['POST'])
@app.route('/alert', methods=['POST'])
def highway_alert():
    if 'photo' not in request.files: return jsonify({"error": "No photo"}), 400
    recipients = get_active_recipients()
    photo_bytes = request.files['photo'].read()
    animal = request.form.get('animal', 'ANIMAL DETECTED')

    for cid in recipients:
        try:
            bot.send_photo(cid, photo=io.BytesIO(photo_bytes), caption=f"🚨 *HIGHWAY ALERT*\n🐾 Threat: {animal}", parse_mode="Markdown")
        except: pass
    return jsonify({"status": "Sent", "recipients": len(recipients)}), 200

@app.route('/api/forest-alert', methods=['POST'])
@app.route('/forest-alert', methods=['POST'])
def forest_alert():
    if 'photo' not in request.files: return jsonify({"error": "No photo"}), 400
    recipients = get_active_recipients()
    photo_bytes = request.files['photo'].read()
    label = request.form.get('label', 'GUNSHOT DETECTED')

    for cid in recipients:
        try:
            bot.send_photo(cid, photo=io.BytesIO(photo_bytes), caption=f"🚨 *GIR FOREST ALERT*\n💥 Threat: {label}", parse_mode="Markdown")
        except: pass
    return jsonify({"status": "Sent", "recipients": len(recipients)}), 200

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'POST':
        bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
        return 'OK', 200
    return 'OK', 200

@app.route('/', methods=['GET'])
def index(): return "RoadGuardian In-Built QR Backend Active!", 200

app_instance = app
