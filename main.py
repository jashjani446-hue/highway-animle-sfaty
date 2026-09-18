import os
import time
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk")
FIREBASE_BASE_URL = os.getenv(
    "FIREBASE_BASE_URL", 
    "https://roadguardianai-a8d23-default-rtdb.asia-southeast1.firebasedatabase.app/RoadGuardian"
)
# તમારી Vercel/Render ડબલ્યુઈબી સાઈટની Domain લિંક દર્શાવો
SERVER_URL = os.getenv("SERVER_URL", "https://your-domain.vercel.app") 

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

# --- GOOGLE LENS STYLE CAMERA SCANNER HTML (Embedded Directly) ---
SCANNER_HTML = """
<!DOCTYPE html>
<html lang="gu">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Google Lens QR Scanner</title>
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
    }
    .scanner-card {
      width: 88%;
      max-width: 380px;
      background: #1e293b;
      border-radius: 16px;
      padding: 16px;
      text-align: center;
      box-shadow: 0 8px 20px rgba(0,0,0,0.4);
    }
    #reader {
      width: 100%;
      border-radius: 12px;
      overflow: hidden;
      border: 2px solid #38bdf8;
    }
    .status {
      margin-top: 12px;
      font-size: 15px;
      color: #38bdf8;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="scanner-card">
    <h3>📷 Live QR Scanner</h3>
    <p style="color: #94a3b8; font-size: 13px;">QR કોડ સામે કેમેરો રાખો, સીધું જ ઓટો-કનેક્ટ થઈ જશે.</p>
    <div id="reader"></div>
    <div class="status" id="status-text">Scanning Live...</div>
  </div>

  <script>
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    function onScanSuccess(decodedText) {
      document.getElementById('status-text').innerHTML = `<span style="color:#4ade80;">✅ Code Found: ${decodedText}</span>`;
      
      if (tg.sendData) {
        tg.sendData(decodedText);
      } else {
        alert("Scanned Code: " + decodedText);
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

# --- FIREBASE HELPERS ---
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

# --- TELEGRAM BOT ROUTINGS ---
def main_menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛠️ Admin Panel", callback_data="menu_admin"))
    
    # Direct Google Lens Camera Scanner WebApp Button
    scanner_url = f"{SERVER_URL}/scanner"
    markup.add(InlineKeyboardButton("📷 Direct Camera QR Scanner", web_app=WebAppInfo(url=scanner_url)))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    bot.send_message(
        message.chat.id, 
        "🏠 *RoadGuardian Control System*\n\nવિઝિટર માટે સીધું જ સ્કેન કરવા નીચે આપેલ કેમેરા બટન દબાવો:", 
        parse_mode="Markdown", 
        reply_markup=main_menu_keyboard()
    )

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    chat_id = message.chat.id
    scanned_code = message.web_app_data.data.strip()

    success, duration = verify_and_register_visitor(chat_id, scanned_code)
    if success:
        bot.reply_to(
            message, 
            f"🎉 *QR Verified Automatically!*\n\n🎟️ Code: `{scanned_code}`\n⏱️ Duration Active: *{duration}*\n\nતમે સફળતાપૂર્વક કનેક્ટ થઈ ગયા છો. લાઈવ એલર્ટ્સ ચાલુ કરી દેવાયા છે.", 
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(message, f"❌ અમાન્ય અથવા એક્સપાયર થયેલ QR Code: `{scanned_code}`", parse_mode="Markdown")

# --- FLASK ROUTES ---
@app.route('/scanner', methods=['GET'])
def serve_scanner():
    # Direct HTML Camera View Render
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
    return "RoadGuardian Unified All-in-One Engine Active!", 200

# Server Instance
app_instance = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
