import os
import random
import string
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8560832618:AAFxHDrVvAEHDR1zKUtK1glQq0RWMsYrWXk"
ADMIN_PASSWORD = "jash@2310"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

authorized_admins = set()
visitor_codes = {}
monitored_chats = set()
user_states = {}

def main_menu_keyboard(chat_id):
    markup = InlineKeyboardMarkup()
    if chat_id in authorized_admins:
        markup.add(InlineKeyboardButton("🛠️ Admin", callback_data="menu_admin"))
    markup.add(InlineKeyboardButton("👤 Visitor", callback_data="menu_visitor"))
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
    markup.add(InlineKeyboardButton("📹 Device (Gir Forest Live)", url="https://highway-animle-sfaty.vercel.app/"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_monitoring"))
    return markup

def highway_dept_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Monitoring (Animal Detection Alerts)", callback_data="view_animal_alerts"))
    markup.add(InlineKeyboardButton("📹 Device (RoadGuardian AI Dashboard)", url="https://highway-animle-sfaty.vercel.app/"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_monitoring"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    chat_id = message.chat.id
    bot.send_message(
        chat_id, 
        "🏠 *Main Menu*\n\nPlease select an option below:", 
        parse_mode="Markdown", 
        reply_markup=main_menu_keyboard(chat_id)
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    if call.data == "menu_main":
        bot.edit_message_text("🏠 *Main Menu*", chat_id, message_id, parse_mode="Markdown", reply_markup=main_menu_keyboard(chat_id))

    elif call.data == "menu_admin":
        if chat_id not in authorized_admins:
            bot.answer_callback_query(call.id, "🔒 Enter admin password in chat first!")
            user_states[chat_id] = "awaiting_admin_password"
            bot.send_message(chat_id, "🔐 Please enter the **Admin Password**:")
        else:
            bot.edit_message_text("🛠️ *Admin Panel*", chat_id, message_id, parse_mode="Markdown", reply_markup=admin_menu_keyboard())

    elif call.data == "admin_make_code":
        bot.edit_message_text("🔑 *Make Visitor Pass Code*\nSelect Pass Duration:", chat_id, message_id, parse_mode="Markdown", reply_markup=duration_keyboard())

    elif call.data.startswith("dur_"):
        duration = call.data.split("_")[1]
        user_states[chat_id] = {"action": "awaiting_phone", "duration": duration}
        bot.send_message(chat_id, f"📱 Selected duration: *{duration}*\nNow please type the Visitor's Phone Number:")

    elif call.data == "admin_monitoring":
        bot.edit_message_text("📡 *Monitoring System*", chat_id, message_id, parse_mode="Markdown", reply_markup=monitoring_keyboard())

    elif call.data == "mon_forest":
        bot.edit_message_text("🌲 *Forest Department*", chat_id, message_id, parse_mode="Markdown", reply_markup=forest_dept_keyboard())

    elif call.data == "mon_highway":
        bot.edit_message_text("🛣️ *Highway Department*", chat_id, message_id, parse_mode="Markdown", reply_markup=highway_dept_keyboard())

    elif call.data == "menu_visitor":
        user_states[chat_id] = "awaiting_visitor_code"
        bot.send_message(chat_id, "🎟️ *Visitor Access*\nPlease enter your Pass Code:")

    elif call.data in ["view_gunshots", "view_animal_alerts"]:
        monitored_chats.add(chat_id)
        bot.answer_callback_query(call.id, "✅ Subscribed to real-time alerts!")
        bot.send_message(chat_id, "📡 *Real-time Alerts Active!* You will receive immediate photo notifications when animals/gunshots are detected.")

@bot.message_handler(func=lambda message: True)
def handle_text_inputs(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states.get(chat_id)

    if text == ADMIN_PASSWORD:
        authorized_admins.add(chat_id)
        monitored_chats.add(chat_id)
        bot.reply_to(message, "🎉 *Admin Access Granted!*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
        user_states.pop(chat_id, None)
        return

    if isinstance(state, dict) and state.get("action") == "awaiting_phone":
        duration = state.get("duration")
        phone = text
        code = "PASS-" + ''.join(random.choices(string.digits, k=6))
        
        visitor_codes[code] = {"duration": duration, "phone": phone}
        bot.reply_to(message, f"✅ *Visitor Code Created!*\n\n🎟️ Code: `{code}`\n📱 Phone: {phone}\n⏱️ Duration: {duration}", parse_mode="Markdown")
        user_states.pop(chat_id, None)

    elif state == "awaiting_visitor_code":
        if text in visitor_codes:
            monitored_chats.add(chat_id)
            info = visitor_codes[text]
            bot.reply_to(message, f"🎉 *Visitor Code Verified!*\nWelcome! You will receive live highway alerts.\nDuration: {info['duration']}", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Invalid Pass Code!")
        user_states.pop(chat_id, None)

@app.route('/api/webhook', methods=['POST'])
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Bad Request', 400

@app.route('/api/alert', methods=['POST'])
@app.route('/alert', methods=['POST'])
def receive_alert_from_web():
    if 'photo' not in request.files or 'animal' not in request.form:
        return jsonify({"error": "Missing photo or animal name"}), 400

    animal = request.form['animal']
    photo_file = request.files['photo']

    recipients = authorized_admins.union(monitored_chats)

    if not recipients:
        return jsonify({"status": "No active recipients"}), 200

    caption = f"🚨 *ROADGUARDIAN ALERT*\n\n🐾 *Animal Detected:* {animal}\n📍 *Location:* Rajkot-Gondal Highway\n⚠️ *Drive with caution!*"

    success_count = 0
    for cid in list(recipients):
        try:
            photo_file.seek(0)
            bot.send_photo(cid, photo_file, caption=caption, parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            print(f"Error sending to {cid}: {e}")

    return jsonify({"status": "Alert sent", "sent_to": success_count}), 200

@app.route('/api', methods=['GET'])
def health():
    return "🚀 RoadGuardian Active!", 200
