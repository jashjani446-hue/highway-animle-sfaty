import os
import random
import string
import time
import io
import urllib.parse
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import telebot
from telebot.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo, 
    ReplyKeyboardRemove
)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "jashjani")
FIREBASE_BASE_URL = os.getenv(
    "FIREBASE_BASE_URL", 
    "https://roadguardianai-a8d23-default-rtdb.asia-southeast1.firebasedatabase.app/RoadGuardian"
)
SERVER_URL = os.getenv("SERVER_URL", "https://highway-animle-sfaty.vercel.app")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

# --- DIRECT CAMERA QR SCANNER WEBAPP HTML ---
SCANNER_HTML = """
<!DOCTYPE html>
<html lang="gu">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>રોડગાર્ડિયન QR સ્કેનર</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://unpkg.com/html5-qrcode"></script>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: white;
      margin: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 15px;
      box-sizing: border-box;
    }
    .scanner-card {
      width: 100%;
      max-width: 360px;
      background: #1e293b;
      border-radius: 20px;
      padding: 20px;
      text-align: center;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    #reader {
      width: 100%;
      border-radius: 15px;
      overflow: hidden;
      border: 2px solid #38bdf8;
      margin-top: 15px;
    }
    .status {
      margin-top: 15px;
      font-size: 14px;
      color: #38bdf8;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="scanner-card">
    <h3 style="margin:0;">📷 મુલાકાતી પાસ સ્કેન કરો</h3>
    <p style="color: #94a3b8; font-size: 12px; margin-top: 5px;">સુરક્ષા એક્સેસ મેળવવા QR સ્કેન કરો</p>
    <div id="reader"></div>
    <div class="status" id="status-text">કેમેરા શરૂ થઈ રહ્યો છે...</div>
  </div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    let isProcessing = false;

    function onScanSuccess(decodedText) {
      if (isProcessing) return;
      isProcessing = true;

      document.getElementById('status-text').innerHTML = `<span style="color:#4ade80;">✅ પાસ સ્કેન થયો! ચકાસણી થઈ રહી છે...</span>`;

      try {
        tg.sendData(decodedText);
      } catch (e) {
        document.getElementById('status-text').innerHTML = `<span style="color:#ef4444;">❌ ટેલિગ્રામ બ્રિજ ભૂલ</span>`;
      }
    }

    let html5QrcodeScanner = new Html5QrcodeScanner(
      "reader", 
      { fps: 15, qrbox: { width: 220, height: 220 }, facingMode: "environment" }, 
      false
    );
    html5QrcodeScanner.render(onScanSuccess);
  </script>
</body>
</html>
"""

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

def get_qr_api_url(data_text):
    encoded_text = urllib.parse.quote(data_text)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_text}"

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
    if isinstance(root_data, dict):
        admins = root_data.get("admins", {})
        if isinstance(admins, dict):
            for admin_id in admins.keys():
                try:
                    recipients.add(str(admin_id))
                except Exception:
                    pass

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


# --- TELEGRAM BOT UI & KEYBOARDS ---

def main_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛠️ એડમિન પેનલ", callback_data="menu_admin"))
    markup.add(InlineKeyboardButton("👤 મુલાકાતી એક્સેસ વિકલ્પો", callback_data="menu_visitor"))
    return markup

def visitor_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    scanner_url = f"{SERVER_URL}/scanner"
    markup.add(KeyboardButton("📷 QR કેમેરા સ્કેનર ખોલો", web_app=WebAppInfo(url=scanner_url)))
    return markup

def admin_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔑 મુલાકાતી માટે કોડ બનાવો", callback_data="admin_make_code"))
    markup.add(InlineKeyboardButton("📡 મોનિટરિંગ કંટ્રોલ", callback_data="admin_monitoring"))
    markup.add(InlineKeyboardButton("🔙 મુખ્ય મેનુ પર પાછા જાઓ", callback_data="menu_main"))
    return markup

def duration_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("10 મિનિટ", callback_data="dur_10m"),
        InlineKeyboardButton("1 કલાક", callback_data="dur_1h"),
        InlineKeyboardButton("5 કલાક", callback_data="dur_5h"),
        InlineKeyboardButton("10 કલાક", callback_data="dur_10h"),
        InlineKeyboardButton("24 કલાક", callback_data="dur_24h"),
        InlineKeyboardButton("હંમેશા માટે", callback_data="dur_always")
    )
    markup.add(InlineKeyboardButton("🔙 પાછા જાઓ", callback_data="menu_admin"))
    return markup

def monitoring_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌲 ગીર જંગલ વિભાગ ડેશબોર્ડ", url="https://gir-forest-guardian.vercel.app/"))
    markup.add(InlineKeyboardButton("🛣️ હાઇવે સુરક્ષા ડેશબોર્ડ", url="https://highway-animle-sfaty.vercel.app/"))
    markup.add(InlineKeyboardButton("🔙 પાછા જાઓ", callback_data="menu_admin"))
    return markup


# --- TELEGRAM BOT HANDLERS ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    chat_id = message.chat.id
    try:
        bot.send_message(
            chat_id, 
            "🏠 *રોડગાર્ડિયન સુરક્ષા કંટ્રોલ સિસ્ટમ*\n\nકૃપા કરીને એક વિકલ્પ પસંદ કરો:", 
            parse_mode="Markdown", 
            reply_markup=main_menu_keyboard()
        )
    except Exception as e:
        print(f"Error in send_welcome: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    try:
        if call.data == "menu_main":
            bot.edit_message_text("🏠 *મુખ્ય મેનુ*", chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())

        elif call.data == "menu_visitor":
            bot.send_message(
                chat_id, 
                "📲 કેમેરા ખોલવા માટે નીચે આપેલા **QR કેમેરા સ્કેનર ખોલો** બટન પર ટેપ કરો, અથવા ફક્ત તમારો પાસ કોડ લખીને મોકલો:", 
                parse_mode="Markdown", 
                reply_markup=visitor_keyboard()
            )

        elif call.data == "menu_admin":
            if not is_admin(chat_id):
                bot.answer_callback_query(call.id, "🔒 પહેલા ચેટમાં એડમિન પાસવર્ડ દાખલ કરો!")
                set_user_state(chat_id, "awaiting_admin_password")
                bot.send_message(chat_id, "🔐 કૃપા કરીને **એડમિન પાસવર્ડ** ટાઇપ કરો:")
            else:
                bot.edit_message_text("🛠️ *એડમિન પેનલ*", chat_id, message_id, parse_mode="Markdown", reply_markup=admin_menu_keyboard())

        elif call.data == "admin_make_code":
            bot.edit_message_text("🔑 *મુલાકાતી પાસ કોડ બનાવો*\nપાસની સમયમર્યાદા પસંદ કરો:", chat_id, message_id, parse_mode="Markdown", reply_markup=duration_keyboard())

        elif call.data.startswith("dur_"):
            duration = call.data.split("_")[1]
            set_user_state(chat_id, {"action": "awaiting_phone", "duration": duration})
            bot.send_message(chat_id, f"📱 પસંદ કરેલ મર્યાદા: *{duration}*\nહવે મુલાકાતીનો મોબાઈલ નંબર લખો:")

        elif call.data == "admin_monitoring":
            bot.edit_message_text("📡 *મોનિટરિંગ સિસ્ટમ*", chat_id, message_id, parse_mode="Markdown", reply_markup=monitoring_keyboard())

    except Exception as e:
        print(f"Error in callback: {e}")

# Catches data sent from ReplyKeyboardButton WebApps
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    chat_id = message.chat.id
    scanned_code = message.web_app_data.data.strip()

    success, duration = verify_and_register_visitor(chat_id, scanned_code)
    if success:
        bot.reply_to(
            message, 
            f"🎉 *પ્રવેશ સ્વીકૃત! તમે અધિકૃત છો.*\n\n"
            f"તમારી ચેટ ID `{chat_id}` ફાઉન્ડેશનમાં સેવ થઈ ગઈ છે!\n"
            f"⏱️ સક્રિય સમયમર્યાદા: *{duration}*", 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        bot.reply_to(
            message, 
            "❌ અમાન્ય અથવા મુદત પૂરી થયેલ પાસ કોડ! પ્રવેશ અસ્વીકૃત.",
            reply_markup=ReplyKeyboardRemove()
        )
    clear_user_state(chat_id)

@bot.message_handler(func=lambda message: True)
def handle_text_inputs(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = get_user_state(chat_id)

    try:
        if text == ADMIN_PASSWORD:
            add_admin(chat_id)
            bot.reply_to(message, "🎉 *એડમિન એક્સેસ મંજૂર કરવામાં આવ્યો!*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
            clear_user_state(chat_id)
            return

        if state == "awaiting_admin_password":
            bot.reply_to(message, "❌ ખોટો પાસવર્ડ!")
            clear_user_state(chat_id)
            return

        if isinstance(state, dict) and state.get("action") == "awaiting_phone":
            duration = state.get("duration")
            phone = text
            code = "PASS-" + ''.join(random.choices(string.digits, k=6))

            save_visitor_code(code, phone, duration)
            qr_url = get_qr_api_url(code)

            caption = (
                f"✅ *મુલાકાતી પાસ તૈયાર છે!*\n\n"
                f"🎟️ પાસ કોડ: `{code}`\n"
                f"📱 ફોન નંબર: {phone}\n"
                f"⏱️ સમયમર્યાદા: {duration}\n\n"
                f"📲 *ઓટોમેટિક રજીસ્ટ્રેશન માટે આ QR કોડ 'મુલાકાતી એક્સેસ' દ્વારા સ્કેન કરો.*"
            )
            bot.send_photo(chat_id, photo=qr_url, caption=caption, parse_mode="Markdown")
            clear_user_state(chat_id)
            return

        if text.startswith("PASS-"):
            success, duration = verify_and_register_visitor(chat_id, text)
            if success:
                bot.reply_to(
                    message, 
                    f"🎉 *પ્રવેશ સ્વીકૃત! તમે અધિકૃત છો.*\n\n"
                    f"તમારી ચેટ ID `{chat_id}` ફાઉન્ડેશનમાં સેવ થઈ ગઈ છે!\n"
                    f"⏱️ સક્રિય સમયમર્યાદા: *{duration}*", 
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                bot.reply_to(
                    message, 
                    "❌ અમાન્ય અથવા મુદત પૂરી થયેલ પાસ કોડ! પ્રવેશ અસ્વીકૃત.",
                    reply_markup=ReplyKeyboardRemove()
                )
            clear_user_state(chat_id)
            return

    except Exception as e:
        print(f"Error handling text input: {e}")


# --- FLASK SERVER & WEBHOOK ROUTES ---

@app.route('/scanner', methods=['GET'])
def serve_scanner():
    return render_template_string(SCANNER_HTML)

@app.route('/api/alert', methods=['POST'])
@app.route('/alert', methods=['POST'])
def receive_alert_from_web():
    if 'photo' not in request.files or 'animal' not in request.form:
        return jsonify({"error": "Missing photo or animal name"}), 400

    recipients = get_active_recipients()
    if not recipients:
        return jsonify({"status": "Ignored", "message": "No granted users found in Firebase."}), 200

    animal = request.form['animal']
    photo_file = request.files['photo']
    photo_bytes = photo_file.read()

    caption = f"🚨 *રોડગાર્ડિયન હાઇવે એલર્ટ*\n\n🐾 *પ્રાણી જોવા મળ્યું:* {animal}\n📍 *સ્થળ:* રાજકોટ-ગોંડલ હાઇવે\n⚠️ *સાવચેતીપૂર્વક વાહન ચલાવો!*"

    success_count = 0
    for cid in recipients:
        try:
            photo_stream = io.BytesIO(photo_bytes)
            photo_stream.name = 'alert.jpg'
            bot.send_photo(chat_id=cid, photo=photo_stream, caption=caption, parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            print(f"Failed sending alert to {cid}: {e}")

    return jsonify({"status": "Highway Alert sent", "sent_to_granted_count": success_count}), 200


@app.route('/api/forest-alert', methods=['POST'])
@app.route('/forest-alert', methods=['POST'])
def receive_forest_alert():
    if 'photo' not in request.files:
        return jsonify({"error": "Missing photo file"}), 400

    recipients = get_active_recipients()
    if not recipients:
        return jsonify({"status": "Ignored", "message": "No granted users found in Firebase."}), 200

    sound_label = request.form.get('label', 'બંદૂકની ગોળીનો અવાજ શોધો')
    photo_file = request.files['photo']
    photo_bytes = photo_file.read()

    caption = (
        f"🚨 *ગીર જંગલ વિભાગ કટોકટીની ચેતવણી*\n\n"
        f"💥 *ખતરો શોધાયો:* {sound_label}\n"
        f"📍 *સ્થળ:* ગીર જંગલ ઝોન-૧\n"
        f"⚠️ *તાત્કાલિક પગલાં જરૂરી! વન અધિકારીને જાણ કરવામાં આવી છે.*"
    )

    success_count = 0
    for cid in recipients:
        try:
            photo_stream = io.BytesIO(photo_bytes)
            photo_stream.name = 'forest_alert.jpg'
            bot.send_photo(chat_id=cid, photo=photo_stream, caption=caption, parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            print(f"Failed sending alert to {cid}: {e}")

    return jsonify({"status": "Forest Alert sent", "sent_to_granted_count": success_count}), 200


@app.route('/api/webhook', methods=['POST', 'GET'])
@app.route('/webhook', methods=['POST', 'GET'])
def telegram_webhook():
    if request.method == 'GET':
        return "Webhook Endpoint Ready!", 200

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
    return "🚀 Road Guardian Backend Active", 200

app_instance = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
