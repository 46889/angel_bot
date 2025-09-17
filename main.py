import os
import json
import logging
import telebot
from telebot import types
import requests
import time
from datetime import datetime
import threading
import random

# Токены и ID из переменных окружения с вашими значениями по умолчанию
TOKEN         = os.environ.get('BOT_TOKEN',  '8083296880:AAHgw_w73FC7smTQA3l47DvC9ISyXca3nMQ')
GROUP_ID      = int(os.environ.get('GROUP_ID', '-1003095262397'))
MAIN_ADMIN    = int(os.environ.get('MAIN_ADMIN', '1478525032'))

# Имена файлов хранения данных
MAP_FILE       = "forward_map.json"
ADMIN_FILE     = "admin_data.json"
STATS_FILE     = "bot_stats.json"
AUTOMOD_FILE   = "automod_settings.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
bot = telebot.TeleBot(TOKEN)

# --- Загрузка/сохранение JSON ---
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logging.exception("Ошибка сохранения %s: %s", path, e)

forward_map      = load_json(MAP_FILE, {})
admin_data       = load_json(ADMIN_FILE, {
    "admins": [MAIN_ADMIN], "channels": [], "banned_users": [], "muted_users": [],
    "warnings": {}, "vip_users": [], "welcome_message": "Добро пожаловать!",
    "auto_replies": {}, "working_hours": {"enabled": False, "start": "09:00", "end": "18:00"},
    "flood_protection": {"enabled": True, "max_messages": 5, "time_window": 60}
})
bot_stats        = load_json(STATS_FILE, {"total_users": 0, "messages_today": 0, "last_reset": str(datetime.now().date())})
automod_settings = load_json(AUTOMOD_FILE, {"enabled": True, "banned_words": ["спам", "реклама"], "max_caps_percent": 80, "max_message_length": 4096, "auto_delete_links": False})

# --- Проверка прав ---
def is_admin(uid):   return uid in admin_data["admins"]
def is_banned(uid):  return uid in admin_data["banned_users"]
def is_muted(uid):   return uid in admin_data["muted_users"]
def is_vip(uid):     return uid in admin_data["vip_users"]

# --- Разметка главного меню ---
def main_menu_markup():
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("👥 Пользователи", callback_data="user_mgmt"),
        types.InlineKeyboardButton("📢 Каналы",     callback_data="chan_mgmt"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="statistics"),
        types.InlineKeyboardButton("🤖 Автомодер.", callback_data="automod")
    )
    return mk

@bot.message_handler(commands=["admin"], func=lambda m: m.chat.type=="private")
def cmd_admin(msg):
    if not is_admin(msg.from_user.id):
        return bot.send_message(msg.chat.id, "❌ Нет прав администратора")
    bot.send_message(msg.chat.id, "🔧 Админ-панель", reply_markup=main_menu_markup())

# --- Обработчик нажатий кнопок ---
@bot.callback_query_handler(func=lambda c: True)
def cb_handler(call):
    uid  = call.from_user.id
    data = call.data

    if data == "statistics":
        total = len(set([v["chat_id"] for v in forward_map.values()])) if forward_map else 0
        text = (
            f"📊 Статистика бота:\n"
            f"👥 Пользователей: {total}\n"
            f"📩 Сообщений сегодня: {bot_stats['messages_today']}\n"
            f"🚫 Забанено: {len(admin_data['banned_users'])}\n"
            f"⭐ VIP: {len(admin_data['vip_users'])}"
        )
        return bot.edit_message_text(text, call.message.chat.id, call.message.message_id)

    if not is_admin(uid):
        return bot.answer_callback_query(call.id, "❌ Нет прав")

    # Пользователи
    if data == "user_mgmt":
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin"),
            types.InlineKeyboardButton("➖ Убрать админа",   callback_data="rem_admin"),
            types.InlineKeyboardButton("🔨 Забанить",         callback_data="ban_user"),
            types.InlineKeyboardButton("⛔ Разбанить",       callback_data="unban_user"),
            types.InlineKeyboardButton("🔇 Выключить чат",   callback_data="mute_user"),
            types.InlineKeyboardButton("🔊 Включить чат",    callback_data="unmute_user"),
            types.InlineKeyboardButton("⬅️ Главное",         callback_data="back_main")
        )
        return bot.edit_message_text("👥 Управление пользователями:", call.message.chat.id, call.message.message_id, reply_markup=mk)

    # Каналы
    if data == "chan_mgmt":
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel"),
            types.InlineKeyboardButton("➖ Удалить канал",  callback_data="rem_channel"),
            types.InlineKeyboardButton("📋 Список каналов", callback_data="list_channels"),
            types.InlineKeyboardButton("⬅️ Главное",        callback_data="back_main")
        )
        return bot.edit_message_text("📢 Управление каналами:", call.message.chat.id, call.message.message_id, reply_markup=mk)

    # Автомодерация
    if data == "automod":
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(
            types.InlineKeyboardButton(
                f"🟢 {'Выкл' if automod_settings['enabled'] else 'Вкл'} модерацию",
                callback_data="toggle_automod"
            ),
            types.InlineKeyboardButton("✏️ Слова бан", callback_data="edit_banned_words"),
            types.InlineKeyboardButton("⬅️ Главное",    callback_data="back_main")
        )
        return bot.edit_message_text("🤖 Настройки автомодерации:", call.message.chat.id, call.message.message_id, reply_markup=mk)

    # Возврат в главное меню
    if data == "back_main":
        return bot.edit_message_text("🔧 Админ-панель", call.message.chat.id, call.message.message_id, reply_markup=main_menu_markup())

    # Остальные функции – в разработке
    bot.answer_callback_query(call.id, "Функция в разработке")

# (Здесь остальной код обработки сообщений, пересылки, автопроверок остается без изменений)

if __name__ == "__main__":
    logging.info("🚀 Bot starting...")
    bot.infinity_polling(none_stop=True)
