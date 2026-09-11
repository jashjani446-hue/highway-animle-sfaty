import os
import random
import string
import time
import io
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Environment variables
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
    if isinstance(admins, dict):
        return str(chat_id) in admins
    return False

def add_admin(chat_id):
    set_firebase_data(f"admins/{str(chat_id)}", True)

def set_user_state(chat_id, state):
    set_firebase_data(f"user_states/{str(chat_id)}", state)

def get_user_state(chat_id):
    return get_firebase_data(f"user_states/{str(chat_id)}")

def clear_user_state(chat_id):
    try:
        url = f"{FIREBASE_BASE_URL}/user_states/{str(chat_id)}.json"
        requests.delete(url, timeout=5)
    except Exception as e:
        print(f"Firebase Delete Error: {e}")

def save_visitor_code(code, phone, duration_str):
    seconds_map = {
        "10m": 10 * 60,
        "1h": 3600,
        "5h": 5 * 3600,
        "10h": 10 * 3600,
        "24h": 24 * 3600,
        "always": 100 * 365 * 86400
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
        dur_sec = c_data.get("dur_sec", 3600)
        expire_timestamp = time.time() + dur_sec

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
    if not isinstance(root_data, dict):
        return []

    # 1. Add Admins
    admins = root_data.get("admins", {})
    if isinstance(admins, dict):
        for admin_id in admins.keys():
            try:
                recipients.add(str(admin_id))
            except Exception:
                pass

    # 2. Add Valid Visitors
    subscribers = root_data.get("subscribers", {})
    if isinstance(subscribers, dict):
        for cid, sdata in subscribers.items():
            if isinstance(sdata, dict):
                expire_at = sdata.get("expire_at", 0)
                if expire_at > now:
                    try:
                        recipients.add(str(cid))
                    except Exception:
                        pass

    return list(recipients)


# --- KEYBOARDS (UI) ---

def main_menu_keyboard(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛠️ Admin Panel", callback_data="menu_admin"))
    markup.add(InlineKeyboardButton("👤 Visitor Access", callback_data="menu_visitor"))
    return markup

def admin_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔑 Make Code of Visitor", callback_data="admin_make_code"))
    markup.add(InlineKeyboardButton("📡 Monitoring", callback_data="admin_monitoring"))
    markup.add(InlineKeyboardButton("🔙 Back to Main", callback_data="menu_main"))
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
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="menu_admin"))
    return markup

def monitoring_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌲 Forest Department", callback_data="mon_forest"))
    markup.add(InlineKeyboardButton("🛣️ Highway Department", callback_data="mon_highway"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="menu_admin"))
    return markup

def forest_dept_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Monitoring (Gunshot Alerts)", callback_data="view_gunshots"))
    markup.add(InlineKeyboardButton("📹 Device (Gir Forest Live)", url="https://gir-forest-guardian.vercel.app/"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_monitoring"))
    return markup

def highway_dept_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Monitoring (Animal Detection Alerts)", callback_data="view_animal_alerts"))
    markup.add(InlineKeyboardButton("📹 Device (RoadGuardian AI Dashboard)", url="https://highway-animle-sfaty.vercel.app/"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_monitoring"))
    return markup


# --- TELEGRAM BOT HANDLERS ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    chat_id = message.chat.id
    try:
        bot.send_message(
            chat_id, 
            "🏠 *Main Menu*\n\nPlease select an option below:", 
            parse_mode="Markdown", 
            reply_markup=main_menu_keyboard(chat_id)
        )
    except Exception as e:
        print(f"Error in send_welcome: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    try:
        if call.data == "menu_main":
            bot.edit_message_text("🏠 *Main Menu*", chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard(chat_id))

        elif call.data == "menu_admin":
            if not is_admin(chat_id):
                bot.answer_callback_query(call.id, "🔒 Enter admin password in chat first!")
                set_user_state(chat_id, "awaiting_admin_password")
                bot.send_message(chat_id, "🔐 Please enter the **Admin Password**:")
            else:
                bot.edit_message_text("🛠️ *Admin Panel*", chat_id, message_id, parse_mode="Markdown", reply_markup=admin_menu_keyboard())

        elif call.data == "admin_make_code":
            bot.edit_message_text("🔑 *Make Visitor Pass Code*\nSelect Pass Duration:", chat_id, message_id, parse_mode="Markdown", reply_markup=duration_keyboard())

        elif call.data.startswith("dur_"):
            duration = call.data.split("_")[1]
            set_user_state(chat_id, {"action": "awaiting_phone", "duration": duration})
            bot.send_message(chat_id, f"📱 Selected duration: *{duration}*\nNow please type the Visitor's Phone Number:")

        elif call.data == "admin_monitoring":
            bot.edit_message_text("📡 *Monitoring System*", chat_id, message_id, parse_mode="Markdown", reply_markup=monitoring_keyboard())

        elif call.data == "mon_forest":
            bot.edit_message_text("🌲 *Forest Department*", chat_id, message_id, parse_mode="Markdown", reply_markup=forest_dept_keyboard())

        elif call.data == "mon_highway":
            bot.edit_message_text("🛣️ *Highway Department*", chat_id, message_id, parse_mode="Markdown", reply_markup=highway_dept_keyboard())

        elif call.data == "menu_visitor":
            set_user_state(chat_id, "awaiting_visitor_code")
            bot.send_message(chat_id, "🎟️ *Visitor Access*\nPlease enter your Pass Code:")

        elif call.data in ["view_gunshots", "view_animal_alerts"]:
            bot.answer_callback_query(call.id, "✅ Subscribed to real-time alerts!")
            bot.send_message(chat_id, "📡 *Real-time Alerts Active!* You will receive immediate photo notifications when alerts/gunshots are detected.")
    except Exception as e:
        print(f"Error in callback: {e}")

@bot.message_handler(func=lambda message: True)
def handle_text_inputs(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = get_user_state(chat_id)

    try:
        if text == ADMIN_PASSWORD:
            add_admin(chat_id)
            bot.reply_to(message, "🎉 *Admin Access Granted!*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
            clear_user_state(chat_id)
            return

        if state == "awaiting_admin_password":
            bot.reply_to(message, "❌ Incorrect Password!")
            clear_user_state(chat_id)
            return

        if isinstance(state, dict) and state.get("action") == "awaiting_phone":
            duration = state.get("duration")
            phone = text
            code = "PASS-" + ''.join(random.choices(string.digits, k=6))

            save_visitor_code(code, phone, duration)
            bot.reply_to(message, f"✅ *Visitor Code Created!*\n\n🎟️ Code: `{code}`\n📱 Phone: {phone}\n⏱️ Duration: {duration}", parse_mode="Markdown")
            clear_user_state(chat_id)
            return

        if state == "awaiting_visitor_code":
            success, duration = verify_and_register_visitor(chat_id, text)
            if success:
                bot.reply_to(message, f"🎉 *Visitor Code Verified!*\n\nWelcome! Your Chat ID has been saved.\n⏱️ Access Duration: *{duration}*\n\nYou will now receive live alert photos!", parse_mode="Markdown")
            else:
                bot.reply_to(message, "❌ Invalid or Expired Pass Code!")
            clear_user_state(chat_id)
            return
    except Exception as e:
        print(f"Error handling message: {e}")


# --- API ROUTES FOR ALERTS ---

@app.route('/api/alert', methods=['POST'])
@app.route('/alert', methods=['POST'])
def receive_alert_from_web():
    if 'photo' not in request.files or 'animal' not in request.form:
        return jsonify({"error": "Missing photo or animal name"}), 400

    animal = request.form['animal']
    photo_file = request.files['photo']
    photo_bytes = photo_file.read()

    recipients = get_active_recipients()
    if not recipients:
        return jsonify({"status": "No active recipients found", "sent_to": 0}), 200

    caption = f"🚨 *ROADGUARDIAN HIGHWAY ALERT*\n\n🐾 *Animal Detected:* {animal}\n📍 *Location:* Rajkot-Gondal Highway\n⚠️ *Drive with caution!*"

    success_count = 0
    for cid in recipients:
        try:
            photo_stream = io.BytesIO(photo_bytes)
            photo_stream.name = 'alert.jpg'
            bot.send_photo(chat_id=cid, photo=photo_stream, caption=caption, parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            print(f"Failed to send photo to {cid}: {e}")

    return jsonify({"status": "Highway Alert sent", "sent_to": success_count}), 200


@app.route('/api/forest-alert', methods=['POST'])
@app.route('/forest-alert', methods=['POST'])
def receive_forest_alert():
    if 'photo' not in request.files:
        return jsonify({"error": "Missing photo file"}), 400

    sound_label = request.form.get('label', 'GUNSHOT DETECTED')
    photo_file = request.files['photo']
    photo_bytes = photo_file.read()

    recipients = get_active_recipients()
    if not recipients:
        return jsonify({"status": "No active recipients found", "sent_to": 0}), 200

    caption = (
        f"🚨 *GIR FOREST DEPARTMENT CRITICAL ALERT*\n\n"
        f"💥 *Threat Detected:* {sound_label}\n"
        f"📍 *Location:* Gir Forest Zone-1\n"
        f"⚠️ *Immediate Action Required! Forest Range Officer Alerted.*"
    )

    success_count = 0
    for cid in recipients:
        try:
            photo_stream = io.BytesIO(photo_bytes)
            photo_stream.name = 'forest_alert.jpg'
            bot.send_photo(chat_id=cid, photo=photo_stream, caption=caption, parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            print(f"Failed to send photo to {cid}: {e}")

    return jsonify({"status": "Forest Gunshot Alert sent", "sent_to": success_count}), 200


@app.route('/api/webhook', methods=['POST', 'GET'])
@app.route('/webhook', methods=['POST', 'GET'])
def telegram_webhook():
    if request.method == 'GET':
        return "Webhook is active!", 200

    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            print(f"Webhook processing error: {e}")
            return 'Error', 500
    return 'Bad Request', 400


@app.route('/', methods=['GET'])
def index_check():
    return "🚀 RoadGuardian & Gir Forest Vercel Backend Active!", 200
