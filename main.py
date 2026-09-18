import os
import random
import string
import time
import urllib.parse
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "jashjani")
FIREBASE_BASE_URL = os.getenv(
    "FIREBASE_BASE_URL", 
    "https://roadguardianai-a8d23-default-rtdb.asia-southeast1.firebasedatabase.app/RoadGuardian"
)

# તમારું Vercel / Deployment URL અહીં ઉમેરો
SERVER_URL = os.getenv("SERVER_URL", "https://highway-animle-sfaty.vercel.app")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

# --- GOOGLE LENS STYLE CAMERA SCANNER (HTML) ---
SCANNER_HTML = """
<!DOCTYPE html>
<html lang="gu">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Google Lens Style Scanner</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://unpkg.com/html5-qrcode"></script>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: #0f172a;
      color: white;
      margin: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .scanner-card {
      width: 88%;
      max-width: 380px;
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
      border: 3px solid #38bdf8;
    }
    .status {
      margin-top: 15px;
      font-size: 15px;
      color: #38bdf8;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="scanner-card">
    <h2>📷 Live Camera Scanner</h2>
    <p style="color: #94a3b8; font-size: 13px;">QR કોડ સામે કેમેરો રાખો, સીધું જ ઓટો-કનેક્ટ થઈ જશે.</p>
    <div id="reader"></div>
    <div class="status" id="status-text">Scanning Live...</div>
  </div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    function onScanSuccess(decodedText) {
      document.getElementById('status-text').innerHTML = `<span style="color:#4ade80;">✅ Verified: ${decodedText}</span>`;
      if (tg.sendData) {
        tg.sendData(decodedText);
      } else {
        alert("Scanned Code: " + decodedText);
      }
    }

    let html5QrcodeScanner = new Html5QrcodeScanner(
      "reader", 
      { fps: 15, qrbox: { width: 230, height: 230 }, facingMode: "environment" }, 
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
        requests.put(f"{FIREBASE_BASE_URL}/{path}.json", json=data, timeout=5)
    except Exception as e:
        print(f"Firebase Set Error: {e}")

def get_firebase_data(path):
    try:
        res = requests.get(f"{FIREBASE_BASE_URL}/{path}.json", timeout=5)
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

def generate_random_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def get_qr_api_url(data_text):
    encoded_text = urllib.parse.quote(data_text)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_text}"

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

# --- UI KEYBOARDS ---
def main_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛠️ Admin Panel", callback_data="menu_admin"))
    scanner_url = f"{SERVER_URL}/scanner"
    markup.add(InlineKeyboardButton("📷 Direct Camera QR Scanner", web_app=WebAppInfo(url=scanner_url)))
    return markup

def admin_panel_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ 1 Hour Pass", callback_data="gen_1h"))
    markup.add(InlineKeyboardButton("➕ 1 Day Pass", callback_data="gen_1d"))
    markup.add(InlineKeyboardButton("📋 Active Codes", callback_data="list_codes"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main"))
    return markup

# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    bot.send_message(
        message.chat.id, 
        "🏠 *RoadGuardian Safety System*\n\nસ્વાગત છે! સ્કેન કરવા નીચે આપેલું Direct Camera Scanner બટન વાપરો:", 
        parse_mode="Markdown", 
        reply_markup=main_menu_keyboard()
    )

@bot.message_handler(commands=['admin'])
def admin_login(message):
    chat_id = message.chat.id
    if is_admin(chat_id):
        bot.send_message(chat_id, "🛠️ *Admin Panel Active*", parse_mode="Markdown", reply_markup=admin_panel_keyboard())
    else:
        msg = bot.send_message(chat_id, "🔑 એડમિન પાસવર્ડ દાખલ કરો:")
        bot.register_next_step_handler(msg, process_admin_password)

def process_admin_password(message):
    chat_id = message.chat.id
    if message.text == ADMIN_PASSWORD:
        add_admin(chat_id)
        bot.send_message(chat_id, "✅ *તમે Admin તરીકે સફળતાપૂર્વક લોગિન થઈ ગયા છો.*", parse_mode="Markdown", reply_markup=admin_panel_keyboard())
    else:
        bot.send_message(chat_id, "❌ ખોટો પાસવર્ડ!")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == "menu_main":
        bot.edit_message_text("🏠 *RoadGuardian Main Menu*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif data == "menu_admin":
        if is_admin(chat_id):
            bot.edit_message_text("🛠️ *Admin Panel*", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=admin_panel_keyboard())
        else:
            bot.answer_callback_query(call.id, "❌ ફક્ત Admin જ વાપરી શકે છે!")
    elif data in ["gen_1h", "gen_1d"]:
        if not is_admin(chat_id): return
        dur_sec = 3600 if data == "gen_1h" else 86400
        dur_str = "1 કલાક" if data == "gen_1h" else "1 દિવસ"
        code = generate_random_code()
        
        set_firebase_data(f"codes/{code}", {"dur_sec": dur_sec, "duration_str": dur_str, "created_at": time.time()})
        qr_url = get_qr_api_url(code)
        
        bot.send_photo(
            chat_id, 
            photo=qr_url, 
            caption=f"🎟️ *નવો QR Pass તૈયાર છે!*\n\n👉 Code: `{code}`\n⏱️ Duration: *{dur_str}*", 
            parse_mode="Markdown"
        )
    elif data == "list_codes":
        if not is_admin(chat_id): return
        codes = get_firebase_data("codes")
        if isinstance(codes, dict) and codes:
            msg_text = "📋 *સક્રિય QR કોડ્સ:*\n\n"
            for c, val in codes.items():
                msg_text += f"• `{c}` - {val.get('duration_str', 'N/A')}\n"
            bot.send_message(chat_id, msg_text, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "ℹ️ કોઈ સક્રિય કોડ મળ્યો નથી.")

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    chat_id = message.chat.id
    scanned_code = message.web_app_data.data.strip()

    success, duration = verify_and_register_visitor(chat_id, scanned_code)
    if success:
        bot.reply_to(
            message, 
            f"🎉 *QR Verified Successfully!*\n\n🎟️ Code: `{scanned_code}`\n⏱️ Duration: *{duration}*\n\nતમારું એકાઉન્ટ ઓટો-કનેક્ટ થઈ ગયું છે.", 
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(message, f"❌ અમાન્ય QR Code: `{scanned_code}`", parse_mode="Markdown")

# --- FLASK ROUTES ---
@app.route('/scanner', methods=['GET'])
def serve_scanner():
    return render_template_string(SCANNER_HTML)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return jsonify({"status": "error"}), 400

@app.route('/', methods=['GET'])
def index():
    return "Highway Animal Safety Engine Active!", 200

# Vercel Deployment Handler
app_instance = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
