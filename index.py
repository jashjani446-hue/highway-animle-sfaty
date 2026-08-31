import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot

# Telegram Credentials
BOT_TOKEN = "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk"
ADMIN_PASSWORD = "jash@2310"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

# Authorized Telegram Users List
authorized_users = set()

# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    if chat_id in authorized_users:
        bot.reply_to(message, "✅ You are authorized to receive RoadGuardian alerts!")
    else:
        bot.reply_to(message, "🔒 Welcome to RoadGuardian AI!\nPlease enter the admin password to get access:")

@bot.message_handler(func=lambda message: True)
def check_password(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if chat_id in authorized_users:
        bot.reply_to(message, "ℹ️ You are active. Detection photo alerts will arrive automatically.")
        return

    if text == ADMIN_PASSWORD:
        authorized_users.add(chat_id)
        bot.reply_to(message, "🎉 Access Granted! You will now receive automatic photo alerts.")
    else:
        bot.reply_to(message, "❌ Incorrect password! Please try again.")

# --- VERCEL ENDPOINTS ---

# Telegram Webhook Receiver
@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Bad Request', 400

# Web Camera Photo Alert Receiver
@app.route('/api/alert', methods=['POST'])
def receive_alert_from_web():
    if 'photo' not in request.files or 'animal' not in request.form:
        return jsonify({"error": "Missing photo or animal name"}), 400

    animal = request.form['animal']
    photo_file = request.files['photo']

    if not authorized_users:
        return jsonify({"status": "No authorized users registered yet"}), 200

    caption = f"🚨 *ROADGUARDIAN ALERT*\n\n🐾 *Animal Detected:* {animal}\n📍 *Location:* Rajkot-Gondal Highway\n⚠️ *Drive with caution!*"

    success_count = 0
    for chat_id in list(authorized_users):
        try:
            photo_file.seek(0)
            bot.send_photo(chat_id, photo_file, caption=caption, parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            print(f"Error sending to {chat_id}: {e}")

    return jsonify({"status": "Alert sent", "sent_to": success_count}), 200

@app.route('/api', methods=['GET'])
@app.route('/', methods=['GET'])
def health_check():
    return "🚀 RoadGuardian Vercel Python Server Active!", 200