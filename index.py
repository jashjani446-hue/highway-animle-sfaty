import os
import random
import string
import requests  # Firebase સાથે કનેક્ટ કરવા માટે
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk"
FIREBASE_USERS_URL = "https://roadguardianai-a8d23-default-rtdb.asia-southeast1.firebasedatabase.app/RoadGuardian/active_users.json"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

# Firebase માંથી બધા સક્રિય યુઝર્સ મેળવવાનું ફંક્શન
def get_all_monitored_chats():
    try:
        res = requests.get(FIREBASE_USERS_URL, timeout=3)
        if res.ok and res.json():
            return list(res.json().keys())
    except Exception as e:
        print(f"Error fetching users: {e}")
    return []

# નવા યુઝરનો Chat ID Firebase માં સેવ કરવાનું ફંક્શન
def add_monitored_chat(chat_id):
    try:
        url = f"https://roadguardianai-a8d23-default-rtdb.asia-southeast1.firebasedatabase.app/RoadGuardian/active_users/{chat_id}.json"
        requests.put(url, json=True, timeout=3)
    except Exception as e:
        print(f"Error adding user: {e}")

# --- ટેલિગ્રામ બોટ લોજિક ---

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📡 Start Receiving Alerts", callback_data="view_animal_alerts"))
    bot.send_message(
        chat_id, 
        "🏠 *RoadGuardian AI માં સ્વાગત છે!*\n\nનીચે આપેલા બટન પર ક્લિક કરીને લાઈવ હાઈવે એલર્ટ્સ ચાલુ કરો:", 
        parse_mode="Markdown", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id

    if call.data == "view_animal_alerts":
        # યુઝરનો ID Firebase ડેટાબેઝમાં સેવ થશે
        add_monitored_chat(chat_id)
        bot.answer_callback_query(call.id, "✅ Alerts Subscribed!")
        bot.send_message(chat_id, "📡 *Real-time Alerts Active!*\n\nહવે તમને હાઈવે પર પ્રાણી દેખાતા જ લાઈવ એલર્ટ અને ફોટો મોકલવામાં આવશે.")

# --- API નોટિફિકેશન એન્ડપોઈન્ટ ---

@app.route('/api/alert', methods=['POST'])
@app.route('/alert', methods=['POST'])
def receive_alert_from_web():
    if 'photo' not in request.files or 'animal' not in request.form:
        return jsonify({"error": "Missing photo or animal name"}), 400

    animal = request.form['animal']
    photo_file = request.files['photo']
    
    # ફોટો બાઈટ્સમાં રીડ કરવો
    photo_bytes = photo_file.read()

    # Firebase માંથી બધા જ યુઝર્સના ID એકસાથે મેળવવા
    recipients = get_all_monitored_chats()

    if not recipients:
        print("⚠️ કોઈ યુઝર સબ્સ્ક્રાઇબ થયેલ નથી.")
        return jsonify({"status": "No active recipients found", "sent_to": 0}), 200

    caption = f"🚨 *ROADGUARDIAN ALERT*\n\n🐾 *Animal Detected:* {animal}\n📍 *Location:* Rajkot-Gondal Highway\n⚠️ *Drive with caution!*"

    success_count = 0
    # દરેક યુઝરને અલગથી ફોટો મોકલવો
    for cid in recipients:
        try:
            bot.send_photo(
                chat_id=cid, 
                photo=('alert.jpg', photo_bytes, 'image/jpeg'), 
                caption=caption, 
                parse_mode="Markdown"
            )
            success_count += 1
        except Exception as e:
            print(f"❌ Error sending to {cid}: {e}")

    return jsonify({"status": "Alert sent", "sent_to": success_count}), 200

@app.route('/api/webhook', methods=['POST'])
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Bad Request', 400
