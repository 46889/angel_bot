import os
import json
import logging
import telebot
from telebot import types
import requests
import time
from datetime import datetime, timedelta
import threading
import random

# Получение токена из переменных окружения
TOKEN = os.environ.get('BOT_TOKEN', '8083296880:AAHgw_w73FC7smTQA3l47DvC9ISyXca3nMQ')
GROUP_ID = int(os.environ.get('GROUP_ID', '-1003095262397'))

MAP_FILE = "forward_map.json"
ADMIN_FILE = "admin_data.json"
STATS_FILE = "bot_stats.json"
AUTOMOD_FILE = "automod_settings.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

bot = telebot.TeleBot(TOKEN)

# Главный админ
MAIN_ADMIN = int(os.environ.get('MAIN_ADMIN', '1478525032'))

# Загрузка index map
if os.path.exists(MAP_FILE):
    try:
        with open(MAP_FILE, "r", encoding="utf-8") as f:
            forward_map = json.load(f)
    except Exception:
        forward_map = {}
else:
    forward_map = {}

# Загрузка данных админов
if os.path.exists(ADMIN_FILE):
    try:
        with open(ADMIN_FILE, "r", encoding="utf-8") as f:
            admin_data = json.load(f)
    except Exception:
        admin_data = {
            "admins": [MAIN_ADMIN], 
            "channels": [], 
            "banned_users": [],
            "muted_users": [],
            "warnings": {},
            "vip_users": [],
            "welcome_message": "Добро пожаловать! Напишите ваш вопрос.",
            "auto_replies": {},
            "working_hours": {"enabled": False, "start": "09:00", "end": "18:00"},
            "flood_protection": {"enabled": True, "max_messages": 5, "time_window": 60}
        }
else:
    admin_data = {
        "admins": [MAIN_ADMIN], 
        "channels": [], 
        "banned_users": [],
        "muted_users": [],
        "warnings": {},
        "vip_users": [],
        "welcome_message": "Добро пожаловать! Напишите ваш вопрос.",
        "auto_replies": {},
        "working_hours": {"enabled": False, "start": "09:00", "end": "18:00"},
        "flood_protection": {"enabled": True, "max_messages": 5, "time_window": 60}
    }

# Загрузка статистики
if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            bot_stats = json.load(f)
    except Exception:
        bot_stats = {"total_users": 0, "messages_today": 0, "last_reset": str(datetime.now().date())}
else:
    bot_stats = {"total_users": 0, "messages_today": 0, "last_reset": str(datetime.now().date())}

# Загрузка настроек автомодерации
if os.path.exists(AUTOMOD_FILE):
    try:
        with open(AUTOMOD_FILE, "r", encoding="utf-8") as f:
            automod_settings = json.load(f)
    except Exception:
        automod_settings = {
            "enabled": True,
            "banned_words": ["спам", "реклама"],
            "max_caps_percent": 80,
            "max_message_length": 4096,
            "auto_delete_links": False
        }
else:
    automod_settings = {
        "enabled": True,
        "banned_words": ["спам", "реклама"],
        "max_caps_percent": 80,
        "max_message_length": 4096,
        "auto_delete_links": False
    }

# Хранение данных для флуд-защиты
user_message_times = {}
user_states = {}
scheduled_messages = []

def save_map():
    try:
        with open(MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(forward_map, f, ensure_ascii=False)
    except Exception as e:
        logging.exception("save_map error: %s", e)

def save_admin_data():
    try:
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            json.dump(admin_data, f, ensure_ascii=False)
    except Exception as e:
        logging.exception("save_admin_data error: %s", e)

def save_stats():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(bot_stats, f, ensure_ascii=False)
    except Exception as e:
        logging.exception("save_stats error: %s", e)

def save_automod_settings():
    try:
        with open(AUTOMOD_FILE, "w", encoding="utf-8") as f:
            json.dump(automod_settings, f, ensure_ascii=False)
    except Exception as e:
        logging.exception("save_automod_settings error: %s", e)

def is_admin(user_id):
    return user_id in admin_data["admins"]

def is_banned(user_id):
    return user_id in admin_data["banned_users"]

def is_muted(user_id):
    return user_id in admin_data["muted_users"]

def is_vip(user_id):
    return user_id in admin_data["vip_users"]

def extract_channel_username(url):
    """Извлекает username канала из ссылки"""
    if "t.me/" in url:
        return "@" + url.split("t.me/")[-1]
    return url

def check_user_subscription(user_id):
    """Проверка подписки пользователя на все обязательные каналы"""
    for channel_url in admin_data["channels"]:
        channel_username = extract_channel_username(channel_url)
        url = f"https://api.telegram.org/bot{TOKEN}/getChatMember?chat_id={channel_username}&user_id={user_id}"
        try:
            response = requests.get(url)
            result = response.json()
            
            if result["ok"]:
                status = result["result"]["status"]
                if status not in ["member", "administrator", "creator"]:
                    return False
            else:
                return False
        except:
            return False
    return True

def check_flood_protection(user_id):
    """Проверка флуд-защиты"""
    if not admin_data["flood_protection"]["enabled"] or is_vip(user_id):
        return True
    
    now = time.time()
    if user_id not in user_message_times:
        user_message_times[user_id] = []
    
    # Очистка старых сообщений
    time_window = admin_data["flood_protection"]["time_window"]
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t < time_window]
    
    # Проверка лимита
    max_messages = admin_data["flood_protection"]["max_messages"]
    if len(user_message_times[user_id]) >= max_messages:
        return False
    
    user_message_times[user_id].append(now)
    return True

def moderate_message(text):
    """Проверка сообщения автомодератором"""
    if not automod_settings["enabled"]:
        return True, ""
    
    # Проверка запрещенных слов
    for word in automod_settings["banned_words"]:
        if word.lower() in text.lower():
            return False, f"Сообщение содержит запрещенное слово: {word}"
    
    # Проверка CAPS
    if len(text) > 10:
        caps_count = sum(1 for c in text if c.isupper())
        caps_percent = (caps_count / len(text)) * 100
        if caps_percent > automod_settings["max_caps_percent"]:
            return False, "Слишком много заглавных букв"
    
    # Проверка длины
    if len(text) > automod_settings["max_message_length"]:
        return False, "Сообщение слишком длинное"
    
    # Проверка ссылок
    if automod_settings["auto_delete_links"] and ("http" in text.lower() or "t.me" in text.lower()):
        return False, "Ссылки запрещены"
    
    return True, ""

def update_stats(user_id):
    """Обновление статистики"""
    # Сброс дневной статистики
    today = str(datetime.now().date())
    if bot_stats["last_reset"] != today:
        bot_stats["messages_today"] = 0
        bot_stats["last_reset"] = today
    
    bot_stats["messages_today"] += 1
    save_stats()

# Планировщик сообщений
def scheduler_thread():
    """Поток для отправки запланированных сообщений"""
    while True:
        try:
            now = datetime.now()
            for msg in scheduled_messages[:]:
                if now >= msg["time"]:
                    try:
                        bot.send_message(msg["chat_id"], msg["text"])
                        scheduled_messages.remove(msg)
                    except:
                        scheduled_messages.remove(msg)
            time.sleep(30)
        except:
            time.sleep(30)

# Запуск планировщика
threading.Thread(target=scheduler_thread, daemon=True).start()

# Админ команда
@bot.message_handler(commands=["admin"], func=lambda m: m.chat and m.chat.type == "private")
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("👥 Управление пользователями", callback_data="user_management")
    btn2 = types.InlineKeyboardButton("📢 Управление каналами", callback_data="channel_management")
    btn3 = types.InlineKeyboardButton("📊 Статистика", callback_data="statistics")
    btn4 = types.InlineKeyboardButton("🤖 Автомодерация", callback_data="automoderation")
    
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    
    bot.send_message(message.chat.id, "🔧 Админ-панель", reply_markup=markup)

# Обработка кнопок (упрощенная версия для Railway)
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "check_subscription":
        if not admin_data["channels"]:
            bot.send_message(call.message.chat.id, "✅ Добро пожаловать!")
            return
            
        if check_user_subscription(user_id):
            bot.send_message(call.message.chat.id, "✅ Спасибо за подписку!")
        else:
            channels_text = "\n".join(admin_data["channels"])
            bot.send_message(call.message.chat.id, f"❌ Пожалуйста, подпишитесь на все каналы:\n{channels_text}")
        return
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ У вас нет прав администратора")
        return
    
    # Базовая обработка админских команд
    if call.data == "statistics":
        total_users = len(set([data["chat_id"] for data in forward_map.values()])) if forward_map else 0
        stats_text = f"""📊 Статистика бота:
        
👥 Пользователей: {total_users}
📩 Сообщений сегодня: {bot_stats["messages_today"]}
🚫 Забанено: {len(admin_data["banned_users"])}
⭐ VIP: {len(admin_data["vip_users"])}"""
        
        bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id)

# Обработчик приватных сообщений
@bot.message_handler(func=lambda m: m.chat and m.chat.type == "private", content_types=['text', 'photo', 'voice', 'video', 'document', 'sticker'])
def handle_private(message):
    user_id = message.from_user.id
    
    # Проверки
    if is_banned(user_id):
        bot.send_message(message.chat.id, "🚫 Вы заблокированы")
        return
    
    if is_muted(user_id):
        bot.send_message(message.chat.id, "🔇 Вы заглушены")
        return
    
    if not check_flood_protection(user_id):
        bot.send_message(message.chat.id, "⚠️ Слишком много сообщений")
        return
    
    try:
        # Обработка команд
        if message.entities:
            for ent in message.entities:
                if ent.type == "bot_command":
                    if message.text == "/start" and admin_data["channels"]:
                        if not check_user_subscription(user_id):
                            markup = types.InlineKeyboardMarkup()
                            btn = types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")
                            markup.add(btn)
                            channels_text = "\n".join(admin_data["channels"])
                            bot.send_message(message.chat.id, 
                                f"👋 Подпишитесь на каналы:\n{channels_text}", 
                                reply_markup=markup)
                            return
                        else:
                            bot.send_message(message.chat.id, admin_data.get("welcome_message", "Добро пожаловать!"))
                            return
                    else:
                        bot.send_message(message.chat.id, "ʜѧπџɯџϯє ʜѧʍ џ ӌєʌѳʙєκ ѳϯʙєϯџϯ ʙѧʍ")
                        return
        
        # Проверка подписки
        if admin_data["channels"] and not check_user_subscription(user_id):
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")
            markup.add(btn)
            channels_text = "\n".join(admin_data["channels"])
            bot.send_message(message.chat.id, f"❌ Подпишитесь на каналы:\n{channels_text}", reply_markup=markup)
            return
        
        # Модерация
        if message.text:
            is_allowed, reason = moderate_message(message.text)
            if not is_allowed:
                bot.send_message(message.chat.id, f"❌ {reason}")
                return
        
        update_stats(user_id)
        
        # Информация о пользователе
        user_info = f"👤 ID: {user_id}"
        if message.from_user.username:
            user_info += f" | @{message.from_user.username}"
        if is_vip(user_id):
            user_info += " | ⭐ VIP"
        user_info += f" | {message.from_user.first_name or 'Без имени'}"
        
        # Пересылка в группу
        if message.photo:
            sent_msg = bot.send_photo(GROUP_ID, message.photo[-1].file_id, caption=f"{user_info}\n\n{message.caption or ''}")
        elif message.voice:
            sent_msg = bot.send_voice(GROUP_ID, message.voice.file_id, caption=user_info)
        elif message.video:
            sent_msg = bot.send_video(GROUP_ID, message.video.file_id, caption=f"{user_info}\n\n{message.caption or ''}")
        elif message.document:
            sent_msg = bot.send_document(GROUP_ID, message.document.file_id, caption=f"{user_info}\n\n{message.caption or ''}")
        elif message.sticker:
            sent_msg = bot.send_sticker(GROUP_ID, message.sticker.file_id)
            bot.send_message(GROUP_ID, user_info, reply_to_message_id=sent_msg.message_id)
        else:
            sent_msg = bot.send_message(GROUP_ID, f"{user_info}\n\n{message.text}")
        
        forward_map[str(sent_msg.message_id)] = {
            "chat_id": message.chat.id,
            "orig_id": message.message_id
        }
        save_map()
        
    except Exception as e:
        logging.exception("handle_private error: %s", e)

# Обработчик ответов из группы
@bot.message_handler(func=lambda m: m.chat and m.chat.id == GROUP_ID and m.reply_to_message is not None, content_types=['text', 'photo', 'voice', 'video', 'document', 'sticker'])
def handle_group_reply(message):
    try:
        key = str(message.reply_to_message.message_id)
        data = forward_map.get(key)
        if not data:
            return
        
        target_chat = data["chat_id"]
        
        if is_banned(target_chat):
            bot.send_message(GROUP_ID, "🚫 Пользователь заблокирован", reply_to_message_id=message.message_id)
            return
        
        # Ответ пользователю
        if message.photo:
            bot.send_photo(target_chat, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            bot.send_voice(target_chat, message.voice.file_id)
        elif message.video:
            bot.send_video(target_chat, message.video.file_id, caption=message.caption)
        elif message.document:
            bot.send_document(target_chat, message.document.file_id, caption=message.caption)
        elif message.sticker:
            bot.send_sticker(target_chat, message.sticker.file_id)
        else:
            bot.send_message(target_chat, message.text)
        
        forward_map.pop(key)
        save_map()
        
    except Exception as e:
        logging.exception("handle_group_reply error: %s", e)

if __name__ == "__main__":
    logging.info("🚀 Bot starting on Railway...")
    logging.info(f"Bot Token: {TOKEN[:10]}...")
    logging.info(f"Group ID: {GROUP_ID}")
    logging.info(f"Main Admin: {MAIN_ADMIN}")
    
    try:
        bot.infinity_polling(none_stop=True, interval=1)
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
        time.sleep(5)
        # Перезапуск при ошибке
        bot.infinity_polling(none_stop=True, interval=1)