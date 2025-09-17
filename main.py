import os
import json
import logging
import telebot
from telebot import types
import requests

TOKEN = "8083296880:AAHgw_w73FC7smTQA3l47DvC9ISyXca3nMQ"
GROUP_ID = -1003095262397
MAP_FILE = "forward_map.json"
ADMIN_FILE = "admin_data.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

bot = telebot.TeleBot(TOKEN)

# Главный админ
MAIN_ADMIN = 1478525032

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
        admin_data = {"admins": [MAIN_ADMIN], "channels": [], "banned_users": []}
else:
    admin_data = {"admins": [MAIN_ADMIN], "channels": [], "banned_users": []}

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

def is_admin(user_id):
    return user_id in admin_data["admins"]

def is_banned(user_id):
    return user_id in admin_data["banned_users"]

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

def check_bot_in_group():
    """Проверка: бот состоит в группе и является админом."""
    try:
        me = bot.get_me()
        member = bot.get_chat_member(GROUP_ID, me.id)
        status = member.status if hasattr(member, "status") else str(member)
        is_admin = status in ("administrator", "creator")
        logging.info("Bot status in group %s: %s", GROUP_ID, status)
        return True, is_admin, status
    except Exception as e:
        logging.exception("check_bot_in_group error: %s", e)
        return False, False, str(e)

# Вывод результата проверки при старте
exists, is_admin_bot, status = check_bot_in_group()
if not exists:
    logging.error("Не удалось получить информацию о группе. Проверь GROUP_ID и доступ в интернет.")
elif not is_admin_bot:
    logging.warning("Бот НЕ админ в группе. Для пересылки/ответа он должен быть админом (или иметь права писать).")

# Состояния для ожидания ввода
user_states = {}

# Админ команда
@bot.message_handler(commands=["admin"], func=lambda m: m.chat and m.chat.type == "private")
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("📝 Добавить канал", callback_data="add_channel")
    btn2 = types.InlineKeyboardButton("❌ Удалить канал", callback_data="remove_channel")
    btn3 = types.InlineKeyboardButton("👤 Добавить админа", callback_data="add_admin")
    btn4 = types.InlineKeyboardButton("🗑 Удалить админа", callback_data="remove_admin")
    btn5 = types.InlineKeyboardButton("🚫 Забанить пользователя", callback_data="ban_user")
    btn6 = types.InlineKeyboardButton("✅ Разбанить пользователя", callback_data="unban_user")
    btn7 = types.InlineKeyboardButton("📋 Список каналов", callback_data="list_channels")
    btn8 = types.InlineKeyboardButton("👥 Список админов", callback_data="list_admins")
    btn9 = types.InlineKeyboardButton("🚫 Список банов", callback_data="list_bans")
    
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn5, btn6)
    markup.add(btn7, btn8, btn9)
    
    bot.send_message(message.chat.id, "🔧 Админ-панель", reply_markup=markup)

# Обработка кнопок админ-панели
@bot.callback_query_handler(func=lambda call: True)
def handle_admin_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "check_subscription":
        # Проверка подписки
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
    
    if call.data == "add_channel":
        bot.send_message(call.message.chat.id, "📝 Введите ссылку на канал (например: https://t.me/channel_name):")
        user_states[user_id] = "waiting_channel_add"
        
    elif call.data == "remove_channel":
        if not admin_data["channels"]:
            bot.send_message(call.message.chat.id, "❌ Список каналов пуст")
            return
        channels_text = "\n".join([f"{i+1}. {ch}" for i, ch in enumerate(admin_data["channels"])])
        bot.send_message(call.message.chat.id, f"Введите номер канала для удаления:\n{channels_text}")
        user_states[user_id] = "waiting_channel_remove"
        
    elif call.data == "add_admin":
        bot.send_message(call.message.chat.id, "👤 Введите ID пользователя для добавления в админы:")
        user_states[user_id] = "waiting_admin_add"
        
    elif call.data == "remove_admin":
        admins_list = [str(admin_id) for admin_id in admin_data["admins"] if admin_id != MAIN_ADMIN]
        if not admins_list:
            bot.send_message(call.message.chat.id, "❌ Нет админов для удаления")
            return
        admins_text = "\n".join([f"{i+1}. {admin_id}" for i, admin_id in enumerate(admins_list)])
        bot.send_message(call.message.chat.id, f"Введите номер админа для удаления:\n{admins_text}")
        user_states[user_id] = "waiting_admin_remove"
        
    elif call.data == "ban_user":
        bot.send_message(call.message.chat.id, "🚫 Введите ID пользователя для бана:")
        user_states[user_id] = "waiting_user_ban"
        
    elif call.data == "unban_user":
        if not admin_data["banned_users"]:
            bot.send_message(call.message.chat.id, "❌ Список банов пуст")
            return
        bans_text = "\n".join([f"{i+1}. {user_id}" for i, user_id in enumerate(admin_data["banned_users"])])
        bot.send_message(call.message.chat.id, f"Введите номер пользователя для разбана:\n{bans_text}")
        user_states[user_id] = "waiting_user_unban"
        
    elif call.data == "list_channels":
        if admin_data["channels"]:
            channels_text = "\n".join([f"• {ch}" for ch in admin_data["channels"]])
            bot.send_message(call.message.chat.id, f"📋 Обязательные каналы:\n{channels_text}")
        else:
            bot.send_message(call.message.chat.id, "📋 Список каналов пуст")
            
    elif call.data == "list_admins":
        admins_text = "\n".join([f"• {admin_id}" for admin_id in admin_data["admins"]])
        bot.send_message(call.message.chat.id, f"👥 Список админов:\n{admins_text}")
        
    elif call.data == "list_bans":
        if admin_data["banned_users"]:
            bans_text = "\n".join([f"• {user_id}" for user_id in admin_data["banned_users"]])
            bot.send_message(call.message.chat.id, f"🚫 Заблокированные пользователи:\n{bans_text}")
        else:
            bot.send_message(call.message.chat.id, "🚫 Список банов пуст")

# Обработка состояний админ-панели
@bot.message_handler(func=lambda m: m.chat and m.chat.type == "private" and m.from_user.id in user_states)
def handle_admin_states(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    
    if state == "waiting_channel_add":
        channel_url = message.text.strip()
        if "t.me/" not in channel_url and not channel_url.startswith('@'):
            bot.send_message(message.chat.id, "❌ Введите корректную ссылку (https://t.me/channel_name) или @username")
            return
        if channel_url not in admin_data["channels"]:
            admin_data["channels"].append(channel_url)
            save_admin_data()
            bot.send_message(message.chat.id, f"✅ Канал добавлен: {channel_url}")
        else:
            bot.send_message(message.chat.id, f"❌ Канал уже в списке: {channel_url}")
        del user_states[user_id]
        
    elif state == "waiting_channel_remove":
        try:
            index = int(message.text.strip()) - 1
            if 0 <= index < len(admin_data["channels"]):
                removed_channel = admin_data["channels"].pop(index)
                save_admin_data()
                bot.send_message(message.chat.id, f"✅ Канал {removed_channel} удален")
            else:
                bot.send_message(message.chat.id, "❌ Неверный номер")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите число")
        del user_states[user_id]
        
    elif state == "waiting_admin_add":
        try:
            new_admin_id = int(message.text.strip())
            if new_admin_id not in admin_data["admins"]:
                admin_data["admins"].append(new_admin_id)
                save_admin_data()
                bot.send_message(message.chat.id, f"✅ Пользователь {new_admin_id} добавлен в админы")
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь {new_admin_id} уже админ")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректный ID")
        del user_states[user_id]
        
    elif state == "waiting_admin_remove":
        try:
            admins_list = [admin_id for admin_id in admin_data["admins"] if admin_id != MAIN_ADMIN]
            index = int(message.text.strip()) - 1
            if 0 <= index < len(admins_list):
                removed_admin = admins_list[index]
                admin_data["admins"].remove(removed_admin)
                save_admin_data()
                bot.send_message(message.chat.id, f"✅ Админ {removed_admin} удален")
            else:
                bot.send_message(message.chat.id, "❌ Неверный номер")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите число")
        del user_states[user_id]
        
    elif state == "waiting_user_ban":
        try:
            ban_user_id = int(message.text.strip())
            if ban_user_id not in admin_data["banned_users"]:
                admin_data["banned_users"].append(ban_user_id)
                save_admin_data()
                bot.send_message(message.chat.id, f"✅ Пользователь {ban_user_id} заблокирован")
            else:
                bot.send_message(message.chat.id, f"❌ Пользователь {ban_user_id} уже заблокирован")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректный ID")
        del user_states[user_id]
        
    elif state == "waiting_user_unban":
        try:
            index = int(message.text.strip()) - 1
            if 0 <= index < len(admin_data["banned_users"]):
                unbanned_user = admin_data["banned_users"].pop(index)
                save_admin_data()
                bot.send_message(message.chat.id, f"✅ Пользователь {unbanned_user} разблокирован")
            else:
                bot.send_message(message.chat.id, "❌ Неверный номер")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите число")
        del user_states[user_id]

# Обработчик приватных сообщений
@bot.message_handler(
    func=lambda m: m.chat and m.chat.type == "private",
    content_types=['text', 'photo', 'voice']
)
def handle_private(message):
    user_id = message.from_user.id
    
    # Проверка на бан
    if is_banned(user_id):
        bot.send_message(message.chat.id, "🚫 Вы заблокированы и не можете отправлять сообщения")
        return
    
    try:
        # Ответ на команды /start и др.
        if message.entities:
            for ent in message.entities:
                if ent.type == "bot_command":
                    # Проверка подписки при /start
                    if message.text == "/start" and admin_data["channels"]:
                        if not check_user_subscription(user_id):
                            markup = types.InlineKeyboardMarkup()
                            btn = types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")
                            markup.add(btn)
                            channels_text = "\n".join(admin_data["channels"])
                            bot.send_message(message.chat.id, 
                                f"👋 Привет! Для использования бота подпишитесь на каналы:\n{channels_text}\n\nПосле подписки нажмите кнопку ниже:", 
                                reply_markup=markup)
                            return
                    
                    bot.send_message(
                        message.chat.id,
                        "ʜѧπџɯџϯє ʜѧʍ џ ӌєʌѳʙєκ ѳϯʙєϯџϯ ʙѧʍ"
                    )
                    return
                    
        # Проверка подписки перед пересылкой
        if admin_data["channels"] and not check_user_subscription(user_id):
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")
            markup.add(btn)
            channels_text = "\n".join(admin_data["channels"])
            bot.send_message(message.chat.id, 
                f"❌ Для отправки сообщений подпишитесь на каналы:\n{channels_text}", 
                reply_markup=markup)
            return
        
        # Пересылка в группу по типу
        if message.photo:
            logging.info("Принято фото из приватного чата")
            sent_msg = bot.send_photo(GROUP_ID, message.photo[-1].file_id, caption=message.caption)
            forward_map[str(sent_msg.message_id)] = {
                "chat_id": message.chat.id,
                "orig_id": message.message_id
            }
            save_map()
        elif message.voice:
            logging.info("Принят голосовой из приватного чата")
            sent_msg = bot.send_voice(GROUP_ID, message.voice.file_id)
            forward_map[str(sent_msg.message_id)] = {
                "chat_id": message.chat.id,
                "orig_id": message.message_id
            }
            save_map()
        else:
            logging.info("Текстовое сообщение из приватного чата")
            forwarded = bot.forward_message(GROUP_ID, message.chat.id, message.message_id)
            forward_map[str(forwarded.message_id)] = {
                "chat_id": message.chat.id,
                "orig_id": message.message_id
            }
            save_map()
    except Exception as e:
        logging.exception("handle_private error: %s", e)

# Обработчик ответов на сообщения (для группы)
@bot.message_handler(
    func=lambda m: m.chat and m.chat.id == GROUP_ID and m.reply_to_message is not None,
    content_types=['text', 'photo', 'voice']
)
def handle_group_reply(message):
    try:
        key = str(message.reply_to_message.message_id)
        data = forward_map.get(key)
        if not data:
            return
        target_chat = data["chat_id"]
        
        # Проверка на бан перед отправкой ответа
        if is_banned(target_chat):
            bot.send_message(GROUP_ID, "🚫 Пользователь заблокирован", reply_to_message_id=message.message_id)
            return
        
        # Ответ пользователю по типу
        if message.photo:
            logging.info("Ответ фото отправлен пользователю")
            bot.send_photo(target_chat, message.photo[-1].file_id, caption=message.caption)
        elif message.voice:
            logging.info("Ответ голосовым отправлен пользователю")
            bot.send_voice(target_chat, message.voice.file_id)
        else:
            logging.info("Ответ текстом отправлен пользователю")
            bot.send_message(target_chat, message.text)
        # После ответа — удаляем из мапы
        forward_map.pop(key)
        save_map()
    except Exception as e:
        logging.exception("handle_group_reply error: %s", e)

# Обработчик /start в группе
@bot.message_handler(commands=["start"], func=lambda m: m.chat and m.chat.id == GROUP_ID)
def handle_group_start(message):
    username = getattr(message.from_user, "username", None)
    if username:
        usertag = f"@{username}"
    else:
        usertag = message.from_user.first_name or "Пользователь"
    bot.send_message(
        GROUP_ID,
        f"{usertag} запустил бота",
        reply_to_message_id=message.message_id
    )

# Команда для проверки состояния (приват)
@bot.message_handler(commands=["status"], func=lambda m: m.chat and m.chat.type == "private")
def cmd_status(message):
    ok, is_admin_bot, status = check_bot_in_group()
    out = (
        f"Group access: {'ok' if ok else 'error'}\n"
        f"Bot admin: {'yes' if is_admin_bot else 'no'}\n"
        f"Status: {status}"
    )
    bot.send_message(message.chat.id, out)

if __name__ == "__main__":
    logging.info("Starting bot polling...")
    bot.infinity_polling()
