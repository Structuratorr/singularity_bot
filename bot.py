import telebot
from telebot import types
from supabase import create_client, Client
import uuid
import os
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
MASTER_TG_ID = 329435071

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_or_create_player(tg_user):
    tg_id = tg_user.id
    name = tg_user.first_name
    res = supabase.table('users').select('*').eq('telegram_id', tg_id).execute()
    if not res.data:
        new_id = str(uuid.uuid4())
        supabase.table('users').insert({'id': new_id, 'name': name, 'telegram_id': tg_id}).execute()
        user_id = new_id
    else:
        user_id = res.data[0]['id']
    
    q_res = supabase.table('quest_players').select('*').eq('user_id', user_id).execute()
    if not q_res.data:
        supabase.table('quest_players').insert({'user_id': user_id, 'faction': 'Нейтрал'}).execute()
        q_res = supabase.table('quest_players').select('*').eq('user_id', user_id).execute()
    return user_id, q_res.data[0]

def get_main_keyboard(tg_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('👤 Профиль'), types.KeyboardButton('⚔️ Напасть'))
    markup.add(types.KeyboardButton('🎒 Инвентарь'), types.KeyboardButton('📜 Миссия'))
    markup.add(types.KeyboardButton('🤝 Союз'), types.KeyboardButton('🌍 Мир'))
    if tg_id == MASTER_TG_ID:
        markup.add(types.KeyboardButton('👑 Мастер'))
    return markup

def log_event(text):
    """Отправляет сообщение в глобальный чат, если он настроен"""
    res = supabase.table('quest_settings').select('value').eq('key', 'log_chat_id').execute()
    if res.data and res.data[0]['value']:
        try:
            bot.send_message(res.data[0]['value'], text, parse_mode='Markdown')
        except:
            pass

# --- ПРОФИЛИ И МИР ---
@bot.message_handler(func=lambda message: message.text == '🌍 Мир')
def world_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    players = supabase.table('quest_players').select('user_id, status, users(name)').execute()
    
    markup = types.InlineKeyboardMarkup()
    for p in players.data:
        status_icon = '💀' if p['status'] == 'dead' else ('🩸' if p['status'] == 'wounded' else '🟢')
        markup.add(types.InlineKeyboardButton(f"{status_icon} {p['users']['name']}", callback_data=f"view_{p['user_id']}"))
        
    bot.send_message(message.chat.id, "🌍 *Жители мира:*", parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_profile(call):
    target_id = call.data.split('_')[1]
    p_res = supabase.table('quest_players').select('*, users(name)').eq('user_id', target_id).execute()
    if not p_res.data: return bot.answer_callback_query(call.id, "Не найден.")
    player = p_res.data[0]
    name = player['users']['name']
    
    text = (f"👤 *{name}*\nФракция: {player['faction']}\n"
            f"Статус: {player['status']}\n⚔️ Сила: {player['strength']}\n"
            f"🛡 Защита: {player['defense']}\n💰 Талеры: {player['star_thalers']}\n\n"
            f"📜 История: {player['history'] or 'Скрыто'}")
            
    if player.get('avatar_id'):
        bot.send_photo(call.message.chat.id, player['avatar_id'], caption=text, parse_mode='Markdown')
    else:
        bot.send_message(call.message.chat.id, text + "\n\n(Нет аватара)", parse_mode='Markdown')
    bot.answer_callback_query(call.id)

# --- НАПАДЕНИЯ ---
@bot.message_handler(func=lambda message: message.text == '⚔️ Напасть')
def attack_menu(message):
    user_id, player = get_or_create_player(message.from_user)
    if player['status'] != 'alive': return bot.send_message(message.chat.id, "Ты не можешь нападать.")
    
    # Теперь показываем ВСЕХ, кроме себя
    targets = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).eq('status', 'alive').execute()
    
    markup = types.InlineKeyboardMarkup()
    for p in targets.data: 
        markup.add(types.InlineKeyboardButton(f"⚔️ {p['users']['name']}", callback_data=f"atk_{p['user_id']}"))
    
    if targets.data: bot.send_message(message.chat.id, "Выбери цель (можно бить даже своих):", reply_markup=markup)
    else: bot.send_message(message.chat.id, "Нет доступных целей.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('atk_'))
def perform_attack(call):
    attacker_id, attacker = get_or_create_player(call.from_user)
    defender_id = call.data.split('_')[1]
    defender = supabase.table('quest_players').select('*, users(name)').eq('user_id', defender_id).execute().data[0]
    
    damage = attacker['strength']
    new_defense = max(0, defender['defense'] - damage)
    new_status = 'wounded' if new_defense <= 0 else defender['status']
    
    supabase.table('quest_players').update({'defense': new_defense, 'status': new_status}).eq('user_id', defender_id).execute()
    supabase.table('quest_attacks').insert({'attacker_id': attacker_id, 'defender_id': defender_id, 'damage': damage}).execute()
    
    bot.answer_callback_query(call.id, "Атака проведена!")
    bot.send_message(call.message.chat.id, f"Ты напал на {defender['users']['name']}! Урон: {damage}. Остаток защиты: {new_defense}.")
    log_event(f"🩸 *{call.from_user.first_name}* напал на *{defender['users']['name']}*! Урон: {damage}.")

# --- КОЛЛЕКТИВНАЯ АТАКА (СОЮЗ НА СОЮЗ) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('ally_col_atk_'))
def col_atk_menu(call):
    alliance_id = call.data.split('_')[3]
    user_id, _ = get_or_create_player(call.from_user)
    
    markup = types.InlineKeyboardMarkup()
    
    # 1. Список других союзов
    alliances = supabase.table('quest_alliances').select('id, name').neq('id', alliance_id).execute()
    for a in alliances.data:
        markup.add(types.InlineKeyboardButton(f"🏰 Союз: {a['name']}", callback_data=f"colatk_ally_{alliance_id}_{a['id']}"))
        
    # 2. Список игроков вне союзов
    markup.add(types.InlineKeyboardButton("👤 Одиночные игроки", callback_data=f"colatk_solo_{alliance_id}"))
    
    bot.edit_message_text("Выбери, на кого напасть:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_ally_'))
def col_atk_target_ally(call):
    parts = call.data.split('_')
    attacker_alliance_id = parts[2]
    target_alliance_id = parts[3]
    
    target_alliance = supabase.table('quest_alliances').select('name').eq('id', target_alliance_id).execute().data[0]
    
    atk_res = supabase.table('quest_collective_attacks').insert({
        'alliance_id': attacker_alliance_id, 
        'target_id': target_alliance_id, # Тут храним ID союза-цели
        'initiator_id': get_or_create_player(call.from_user)[0]
    }).execute()
    attack_id = atk_res.data[0]['id']
    
    timer = threading.Timer(60.0, execute_collective_attack, args=[attack_id, True])
    timer.start()
    
    members = supabase.table('quest_alliance_members').select('user_id, users(telegram_id)').eq('alliance_id', attacker_alliance_id).eq('status', 'accepted').execute()
    for m in members.data:
        tg_id = m['users']['telegram_id']
        if tg_id:
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_{attack_id}"))
                bot.send_message(tg_id, f"⚔️ Твой союз объявил атаку на союз *{target_alliance['name']}*! Жми кнопку!", parse_mode='Markdown', reply_markup=markup)
            except: pass
            
    bot.answer_callback_query(call.id, "Атака инициирована!")
    bot.edit_message_text(f"Ожидаем удары по союзу {target_alliance['name']} (60 сек)...", call.message.chat.id, call.message.message_id)

def execute_collective_attack(attack_id, is_alliance_target=False):
    atk_res = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute()
    if not atk_res.data: return 
    attack = atk_res.data[0]
    
    supabase.table('quest_collective_attacks').delete().eq('id', attack_id).execute()
    
    votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()
    if not votes.data: return
        
    voter_ids = [v['user_id'] for v in votes.data]
    attackers = supabase.table('quest_players').select('strength').in_('user_id', voter_ids).execute()
    total_damage = sum(a['strength'] for a in attackers.data)
    
    if is_alliance_target:
        # Атака на СОЮЗ
        def_members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['target_id']).execute()
        if not def_members.data: return
        
        # Суммарная защита союза
        defenders = supabase.table('quest_players').select('user_id, defense').in_('user_id', [m['user_id'] for m in def_members.data]).execute()
        total_defense = sum(d['defense'] for d in defenders.data)
        
        net_damage = max(0, total_damage - total_defense)
        dmg_per_player = math.ceil(net_damage / len(defenders.data)) if defenders.data else 0
        
        if dmg_per_player > 0:
            for d in defenders.data:
                new_def = max(0, d['defense'] - dmg_per_player)
                new_stat = 'wounded' if new_def <= 0 else 'alive'
                supabase.table('quest_players').update({'defense': new_def, 'status': new_stat}).eq('user_id', d['user_id']).execute()
                
        log_event(f"🔥 *ВОЙНА!* Союз нанес удар! Урон: {total_damage}, Защита врага: {total_defense}. Пробито: {net_damage} урона (по {dmg_per_player} каждому).")
        
    else:
        # Атака на игрока (старая логика)
        defender = supabase.table('quest_players').select('*').eq('user_id', attack['target_id']).execute().data[0]
        new_defense = max(0, defender['defense'] - total_damage)
        new_status = 'wounded' if new_defense <= 0 else defender['status']
        supabase.table('quest_players').update({'defense': new_defense, 'status': new_status}).eq('user_id', attack['target_id']).execute()
        log_event(f"🔥 Коллективная атака на игрока! Урон: {total_damage}.")
        
    supabase.table('quest_collective_votes').delete().eq('attack_id', attack_id).execute()

# --- ПАНЕЛЬ МАСТЕРА (ДОБАВЛЕНА УСТАНОВКА КАРТИНОК И ЧАТА) ---
@bot.message_handler(func=lambda message: message.text == '👑 Мастер' and message.from_user.id == MASTER_TG_ID)
def master_panel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💀 Убить", callback_data="master_kill"))
    markup.add(types.InlineKeyboardButton("🎁 Выдать предмет", callback_data="master_give"))
    markup.add(types.InlineKeyboardButton("🖼 Установить аватар", callback_data="master_set_avatar"))
    markup.add(types.InlineKeyboardButton("⚙️ Настроить Лог-Чат", callback_data="master_set_log"))
    bot.send_message(message.chat.id, "Панель Мастера:", reply_markup=markup)

# ... (ОСТАЛЬНЫЕ ФУНКЦИИ ПАНЕЛИ МАСТЕРА, ИНВЕНТАРЯ, СОЮЗОВ ОСТАВЛЯЕМ КАК БЫЛИ, но добавим новые обработчики)

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_avatar' and call.from_user.id == MASTER_TG_ID)
def master_avatar_start(call):
    bot.send_message(call.message.chat.id, "Отправь мне картинку (фото) для персонажа.")
    bot.register_next_step_handler(call.message, master_avatar_get_photo)

def master_avatar_get_photo(message):
    if not message.photo: return bot.send_message(message.chat.id, "Это не фото.")
    file_id = message.photo[-1].file_id
    
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for p in players.data: 
        markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"setav_{file_id}_{p['user_id']}"))
    bot.send_message(message.chat.id, "Кому установить этот аватар?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setav_') and call.from_user.id == MASTER_TG_ID)
def master_avatar_save(call):
    parts = call.data.split('_')
    file_id, target_id = parts[1], parts[2]
    supabase.table('quest_players').update({'avatar_id': file_id}).eq('user_id', target_id).execute()
    bot.answer_callback_query(call.id, "Аватар установлен!")
    bot.edit_message_text("Аватар успешно установлен.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_log' and call.from_user.id == MASTER_TG_ID)
def master_log_setup(call):
    bot.send_message(call.message.chat.id, "Отправь мне ID чата (например, -100123456789), куда бот будет писать логи. Бот должен быть админом в этом чате.")
    bot.register_next_step_handler(call.message, master_log_save)

def master_log_save(message):
    chat_id = message.text.strip()
    supabase.table('quest_settings').update({'value': chat_id}).eq('key', 'log_chat_id').execute()
    bot.send_message(message.chat.id, f"Лог-чат настроен на {chat_id}!")

# --- ОСТАВШИЕСЯ ФУНКЦИИ (союзы, инвентарь и т.д.) ---
# (ВСТАВЬ СЮДА СТАРЫЕ ФУНКЦИИ СОЮЗОВ, ИНВЕНТАРЯ, МИССИЙ И ВЕБ-СЕРВЕРА)
# Я оставил их для краткости, так как они уже написаны выше, но в коде они должны быть.

# --- ВЕБ-СЕРВЕР ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is alive")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

print("Бот запущен...")
bot.infinity_polling()
