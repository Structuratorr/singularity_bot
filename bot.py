import telebot
from telebot import types
from supabase import create_client, Client
import uuid
import os
import math
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
MASTER_TG_ID = 329435071

bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

temp_avatars = {}
temp_master_data = {}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_status_ru(status):
    return {'alive': 'жив', 'wounded': 'ранен', 'dead': 'мертв'}.get(status, status)

def is_attacks_enabled():
    res = supabase.table('quest_settings').select('value').eq('key', 'attacks_enabled').execute()
    return res.data[0]['value'] == 'true' if res.data else True

def get_or_create_player(tg_user):
    tg_id = tg_user.id
    name = tg_user.first_name
    
    # 1. Ищем по Telegram ID (как обычно)
    res = supabase.table('users').select('*').eq('telegram_id', tg_id).execute()
    
    if not res.data:
        # 2. Если не нашли, ищем предзагруженного персонажа с таким же именем (и без Telegram ID)
        res_name = supabase.table('users').select('*').eq('name', name).is_('telegram_id', 'null').execute()
        
        if res_name.data:
            # Нашли! Привязываем Telegram ID к существующей анкете
            user_id = res_name.data[0]['id']
            supabase.table('users').update({'telegram_id': tg_id}).eq('id', user_id).execute()
        else:
            # 3. Если и по имени нет, создаем абсолютно нового
            new_id = str(uuid.uuid4())
            supabase.table('users').insert({'id': new_id, 'name': name, 'telegram_id': tg_id}).execute()
            user_id = new_id
            supabase.table('quest_players').insert({'user_id': user_id, 'hp': 10, 'max_hp': 10, 'defense': 2, 'strength': 2}).execute()
    else:
        user_id = res.data[0]['id']
    
    # Проверяем, есть ли запись в quest_players (на случай сбоя)
    q_res = supabase.table('quest_players').select('*').eq('user_id', user_id).execute()
    if not q_res.data:
        supabase.table('quest_players').insert({'user_id': user_id, 'hp': 10, 'max_hp': 10, 'defense': 2, 'strength': 2}).execute()
        q_res = supabase.table('quest_players').select('*').eq('user_id', user_id).execute()
        
    return user_id, q_res.data[0]

def get_player_factions(user_id):
    res = supabase.table('quest_alliance_members').select('quest_alliances(name)').eq('user_id', user_id).eq('status', 'accepted').execute()
    if not res.data: return "Нейтрал"
    return ", ".join([f['quest_alliances']['name'] for f in res.data])

def get_player_inventory(user_id):
    res = supabase.table('quest_inventory').select('*, quest_items(name)').eq('user_id', user_id).execute()
    if not res.data: return "Пусто"
    return ", ".join([item['quest_items']['name'] for item in res.data])

def get_main_keyboard(tg_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('⚔️ Напасть'), types.KeyboardButton('🌍 Мир'))
    markup.add(types.KeyboardButton('🎒 Инвентарь'), types.KeyboardButton('📜 Миссии'))
    markup.add(types.KeyboardButton('🛡 Фракции'), types.KeyboardButton('💸 Перевести деньги'))
    if tg_id == MASTER_TG_ID:
        markup.add(types.KeyboardButton('👑 Мастер'))
    return markup

def log_event(text):
    res = supabase.table('quest_settings').select('value').eq('key', 'log_chat_id').execute()
    if res.data and res.data[0]['value']:
        try: bot.send_message(res.data[0]['value'], text, parse_mode='Markdown')
        except: pass

def get_player_stats(user_id):
    p = supabase.table('quest_players').select('strength').eq('user_id', user_id).execute().data[0]
    inv = supabase.table('quest_inventory').select('*, quest_items(*)').eq('user_id', user_id).eq('is_equipped', True).execute()
    total_str = p['strength']
    total_pierce = 0
    for item in inv.data:
        total_str += item['quest_items']['attack_bonus']
        total_pierce += item['quest_items'].get('armor_pierce', 0)
    return total_str, total_pierce

def format_money(amount):
    return f"{amount} z₮"

# --- ПРОФИЛИ И МИР ---
@bot.message_handler(commands=['start'])
def start(message):
    get_or_create_player(message.from_user)
    bot.send_message(message.chat.id, f"Добро пожаловать в квест, {message.from_user.first_name}!", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda message: message.text == '🌍 Мир')
def world_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    players = supabase.table('quest_players').select('user_id, hp, users(name)').execute()
    
    markup = types.InlineKeyboardMarkup()
    for p in players.data:
        status_icon = '🩸' if p['hp'] <= 0 else ('🟡' if p['hp'] < 5 else '🟢')
        is_me = (p['user_id'] == user_id)
        me_tag = " (Вы)" if is_me else ""
        markup.add(types.InlineKeyboardButton(f"{status_icon} {p['users']['name']}{me_tag}", callback_data=f"view_{p['user_id']}"))
    bot.send_message(message.chat.id, "🌍 *Жители мира:*", parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_profile(call):
    bot.answer_callback_query(call.id)
    target_id = call.data.split('_')[1]
    current_id, _ = get_or_create_player(call.from_user)
    
    player = supabase.table('quest_players').select('*, users(name)').eq('user_id', target_id).execute().data[0]
    name = player['users']['name']
    factions = get_player_factions(target_id)
    inventory = get_player_inventory(target_id)
    att_bonus, pierce = get_player_stats(target_id)
    
    status_emoji = '🩸' if player['hp'] <= 0 else ('🟡' if player['hp'] < 5 else '🟢')
    status_text = get_status_ru(player['status'])
    
    money_text = f"\n💰 Талеры: {format_money(player['star_thalers'])}" if target_id == current_id else ""
    
    text = (f"👤 *{name}*\nФракции: {factions}\nСтатус: {status_emoji} {status_text}\n"
            f"❤️ HP: {player['hp']}/{player['max_hp']}\n🛡 Броня: {player['defense']}\n"
            f"⚔️ Сила: {att_bonus} (Пробой брони: {pierce}){money_text}\n"
            f"🎒 Инвентарь: {inventory}\n\n"
            f"📜 История: {player['history'] or 'Скрыто'}")
            
    if player.get('avatar_id'):
        try: bot.send_photo(call.message.chat.id, player['avatar_id'], caption=text, parse_mode='Markdown')
        except: bot.send_message(call.message.chat.id, text, parse_mode='Markdown')
    else:
        bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

# --- ДЕНЬГИ ---
@bot.message_handler(func=lambda message: message.text == '💸 Перевести деньги')
def pay_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    players = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).execute()
    markup = types.InlineKeyboardMarkup()
    for p in players.data:
        markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"payto_{p['user_id']}"))
    bot.send_message(message.chat.id, "Кому перевести талеры?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('payto_'))
def pay_amount(call):
    bot.answer_callback_query(call.id)
    target_id = call.data.split('_')[1]
    temp_master_data[f"pay_{call.from_user.id}"] = target_id
    msg = bot.send_message(call.message.chat.id, "Введи сумму для перевода (в z₮):")
    bot.register_next_step_handler(msg, pay_execute)

def pay_execute(message):
    try:
        amount = int(message.text)
        if amount <= 0: return bot.send_message(message.chat.id, "Сумма должна быть больше 0.")
        
        sender_id, sender = get_or_create_player(message.from_user)
        target_id = temp_master_data.get(f"pay_{message.from_user.id}")
        if not target_id: return bot.send_message(message.chat.id, "Ошибка перевода.")
        
        target = supabase.table('quest_players').select('*').eq('user_id', target_id).execute().data[0]
        
        if sender['star_thalers'] < amount:
            return bot.send_message(message.chat.id, "У тебя недостаточно талеров.")
            
        supabase.table('quest_players').update({'star_thalers': sender['star_thalers'] - amount}).eq('user_id', sender_id).execute()
        supabase.table('quest_players').update({'star_thalers': target['star_thalers'] + amount}).eq('user_id', target_id).execute()
        
        bot.send_message(message.chat.id, f"Успешно переведено {format_money(amount)}!", reply_markup=get_main_keyboard(message.from_user.id))
    except ValueError:
        bot.send_message(message.chat.id, "Введи число!", reply_markup=get_main_keyboard(message.from_user.id))

# --- НАПАДЕНИЯ ---
@bot.message_handler(func=lambda message: message.text == '⚔️ Напасть')
def attack_menu(message):
    if not is_attacks_enabled():
        return bot.send_message(message.chat.id, "🕊 Сейчас действует перемирие. Атаки запрещены Мастером.")
        
    user_id, player = get_or_create_player(message.from_user)
    if player['hp'] <= 0: return bot.send_message(message.chat.id, "Ты ранен и не можешь нападать.")
    
    if player.get('last_attack_time'):
        try:
            last_atk = datetime.fromisoformat(player['last_attack_time'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = timedelta(minutes=15) - (now - last_atk)
            if diff.total_seconds() > 0:
                mins = int(diff.total_seconds() // 60) + 1
                return bot.send_message(message.chat.id, f"⏳ Ты слишком устал. Подожди 15 минут перед следующей атакой, осталось {mins} минут.")
        except: pass

    targets = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).gt('hp', 0).execute()
    markup = types.InlineKeyboardMarkup()
    for p in targets.data: markup.add(types.InlineKeyboardButton(f"⚔️ {p['users']['name']}", callback_data=f"atk_{p['user_id']}"))
    if targets.data: bot.send_message(message.chat.id, "Выбери цель:", reply_markup=markup)
    else: bot.send_message(message.chat.id, "Нет доступных целей (все либо ранены, либо это ты).")

@bot.callback_query_handler(func=lambda call: call.data.startswith('atk_'))
def perform_attack(call):
    bot.answer_callback_query(call.id)
    if not is_attacks_enabled():
        return bot.send_message(call.message.chat.id, "🕊 Сейчас действует перемирие. Атаки запрещены Мастером.")

    attacker_id, attacker = get_or_create_player(call.from_user)
    defender_id = call.data.split('_')[1]
    
    defender = supabase.table('quest_players').select('*, users(name)').eq('user_id', defender_id).execute().data[0]
    if defender['hp'] <= 0:
        return bot.send_message(call.message.chat.id, "🩸 Он уже без сознания. Добивать раненых — дело Мастера.")

    atk_str, atk_pierce = get_player_stats(attacker_id)
    effective_armor = max(0, defender['defense'] - atk_pierce)
    damage = max(0, atk_str - effective_armor) 
    
    if damage == 0:
        supabase.table('quest_players').update({'last_attack_time': datetime.now(timezone.utc).isoformat()}).eq('user_id', attacker_id).execute()
        return bot.send_message(call.message.chat.id, f"🛡 Твой удар не пробил броню {defender['users']['name']}! Урона нет.")

    new_hp = max(0, defender['hp'] - damage)
    new_status = 'wounded' if new_hp <= 0 else 'alive'
    
    supabase.table('quest_players').update({'hp': new_hp, 'status': new_status, 'last_attack_time': datetime.now(timezone.utc).isoformat()}).eq('user_id', attacker_id).execute()
    supabase.table('quest_players').update({'hp': new_hp, 'status': new_status}).eq('user_id', defender_id).execute()
    supabase.table('quest_attacks').insert({'attacker_id': attacker_id, 'defender_id': defender_id, 'damage': damage}).execute()
    
    bot.send_message(call.message.chat.id, f"Ты напал на {defender['users']['name']}!\nПробито брони: {atk_pierce}\nУрон: {damage}\nОстаток HP: {new_hp}.")
    log_event(f"💥 *Вспышка ярости!* *{call.from_user.first_name}* наносит удар по *{defender['users']['name']}*! Урон: {damage}. Осталось HP: {new_hp}.")

# --- МИССИИ (ИГРОК) ---
@bot.message_handler(func=lambda message: message.text == '📜 Миссии')
def missions_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    res = supabase.table('quest_missions').select('*').eq('user_id', user_id).in_('status', ['active', 'review']).execute()
    
    if not res.data:
        return bot.send_message(message.chat.id, "У тебя нет активных миссий.")
        
    text = "📜 *Твои миссии:*\n\n"
    markup = types.InlineKeyboardMarkup()
    for m in res.data:
        status_icon = "🕒 (На проверке)" if m['status'] == 'review' else ""
        text += f"▪️ {m['text']} {status_icon}\n\n"
        if m['status'] == 'active':
            markup.add(types.InlineKeyboardButton(f"Сдать: {m['text'][:20]}...", callback_data=f"submit_m_{m['id']}"))
            
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('submit_m_'))
def submit_mission(call):
    bot.answer_callback_query(call.id)
    mission_id = call.data.split('_')[2]
    supabase.table('quest_missions').update({'status': 'review'}).eq('id', mission_id).execute()
    
    user_id, _ = get_or_create_player(call.from_user)
    mission = supabase.table('quest_missions').select('*').eq('id', mission_id).execute().data[0]
    
    try: 
        bot.send_message(MASTER_TG_ID, f"📜 Игрок {call.from_user.first_name} сдал миссию:\n{mission['text']}\n\nЗайди в 👑 Мастер -> ⚖️ Управление миссиями.")
    except Exception as e:
        print(f"Ошибка отправки Мастеру: {e}")
    
    bot.edit_message_text("Миссия отправлена Мастеру на проверку.", call.message.chat.id, call.message.message_id)

# --- ФРАКЦИИ ---
@bot.message_handler(func=lambda message: message.text == '🛡 Фракции')
def faction_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    res = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name, leader_id)').eq('user_id', user_id).eq('status', 'accepted').execute()
    markup = types.InlineKeyboardMarkup()
    text = "🛡 *Твои фракции:*\n\n"
    seen_ids = set()
    if res.data:
        for item in res.data:
            alliance = item['quest_alliances']
            if alliance['id'] in seen_ids: continue
            seen_ids.add(alliance['id'])
            is_leader = (alliance['leader_id'] == user_id)
            text += f"🏰 *{alliance['name']}* {'(Лидер)' if is_leader else ''}\n"
            markup.add(types.InlineKeyboardButton(f"⚔️ Атака: {alliance['name']}", callback_data=f"fac_atk_{alliance['id']}"))
            if is_leader:
                markup.add(types.InlineKeyboardButton(f"⚙️ Управление: {alliance['name']}", callback_data=f"fac_manage_{alliance['id']}"))
            markup.add(types.InlineKeyboardButton(f"🚪 Выйти из {alliance['name']}", callback_data=f"fac_leave_{alliance['id']}"))
    else:
        text = "Ты пока не состоишь во фракциях."
        
    markup.add(types.InlineKeyboardButton("➕ Создать фракцию", callback_data="create_faction"))
    invites = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name)').eq('user_id', user_id).eq('status', 'pending').execute()
    if invites.data:
        text += "\n\n📩 *Приглашения:*"
        for inv in invites.data:
            markup.add(types.InlineKeyboardButton(f"✅ Принять: {inv['quest_alliances']['name']}", callback_data=f"join_fac_{inv['alliance_id']}"))
            markup.add(types.InlineKeyboardButton(f"❌ Отклонить: {inv['quest_alliances']['name']}", callback_data=f"decline_fac_{inv['alliance_id']}"))
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'create_faction')
def create_faction(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Введи название фракции:")
    bot.register_next_step_handler(call.message, save_faction)

def save_faction(message):
    forbidden = ['👤 Профиль', '⚔️ Напасть', '🎒 Инвентарь', '📜 Миссии', '🛡 Фракции', '🌍 Мир', '💸 Перевести деньги', '👑 Мастер']
    if message.text in forbidden:
        return bot.send_message(message.chat.id, "Создание отменено.", reply_markup=get_main_keyboard(message.from_user.id))
    user_id, _ = get_or_create_player(message.from_user)
    a_res = supabase.table('quest_alliances').insert({'name': message.text, 'leader_id': user_id}).execute()
    supabase.table('quest_alliance_members').insert({'alliance_id': a_res.data[0]['id'], 'user_id': user_id, 'status': 'accepted'}).execute()
    bot.send_message(message.chat.id, f"Фракция *{message.text}* создана!", parse_mode='Markdown', reply_markup=get_main_keyboard(message.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_leave_'))
def leave_faction(call):
    bot.answer_callback_query(call.id)
    faction_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', user_id).execute()
    bot.edit_message_text("Ты вышел из фракции.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_manage_'))
def manage_faction(call):
    bot.answer_callback_query(call.id)
    faction_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Пригласить", callback_data=f"fac_invite_{faction_id}"))
    markup.add(types.InlineKeyboardButton("👢 Выгнать", callback_data=f"fac_kick_menu_{faction_id}"))
    bot.edit_message_text("Управление фракцией:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_invite_'))
def faction_invite_menu(call):
    bot.answer_callback_query(call.id)
    faction_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    existing = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', faction_id).execute()
    exclude_ids = [m['user_id'] for m in existing.data]
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    targets = [p for p in players.data if p['user_id'] not in exclude_ids]
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(targets): markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"inv_{faction_id}_{idx}"))
    bot.edit_message_text("Кого пригласить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('inv_'))
def send_invite(call):
    bot.answer_callback_query(call.id)
    try:
        parts = call.data.split('_')
        faction_id, idx = parts[1], int(parts[2])
        user_id, _ = get_or_create_player(call.from_user)
        existing = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', faction_id).execute()
        exclude_ids = [m['user_id'] for m in existing.data]
        players = supabase.table('quest_players').select('user_id, users(name)').execute()
        targets = [p for p in players.data if p['user_id'] not in exclude_ids]
        if idx >= len(targets): return bot.send_message(call.message.chat.id, "Игрок не найден.")
        target_user_id = targets[idx]['user_id']
        u_res = supabase.table('users').select('telegram_id').eq('id', target_user_id).execute()
        target_tg_id = u_res.data[0]['telegram_id'] if u_res.data else None
        existing = supabase.table('quest_alliance_members').select('*').eq('alliance_id', faction_id).eq('user_id', target_user_id).execute()
        if not existing.data:
            supabase.table('quest_alliance_members').insert({'alliance_id': faction_id, 'user_id': target_user_id, 'status': 'pending'}).execute()
        if target_tg_id:
            fac_name = supabase.table('quest_alliances').select('name').eq('id', faction_id).execute().data[0]['name']
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"join_fac_{faction_id}"))
            markup.add(types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_fac_{faction_id}"))
            try: bot.send_message(target_tg_id, f"🛡 Вас приглашают во фракцию *{fac_name}*!", parse_mode='Markdown', reply_markup=markup)
            except: pass
        bot.edit_message_text("Приглашение отправлено!", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_kick_menu_'))
def kick_menu(call):
    bot.answer_callback_query(call.id)
    faction_id = call.data.split('_')[3]
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', faction_id).eq('status', 'accepted').execute()
    if not members.data: return bot.send_message(call.message.chat.id, "Некого выгонять.")
    markup = types.InlineKeyboardMarkup()
    for idx, m in enumerate(members.data): 
        markup.add(types.InlineKeyboardButton(f"{m['users']['name']}", callback_data=f"kick_{faction_id}_{idx}"))
    bot.edit_message_text("Кого исключить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('kick_'))
def do_kick(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split('_')
    faction_id, idx = parts[1], int(parts[2])
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', faction_id).eq('status', 'accepted').execute()
    if idx < len(members.data):
        target = members.data[idx]
        supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', target['user_id']).execute()
        bot.edit_message_text(f"Игрок {target['users']['name']} исключен.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_fac_'))
def accept_invite(call):
    bot.answer_callback_query(call.id)
    try:
        faction_id = call.data.split('_')[2]
        user_id, _ = get_or_create_player(call.from_user)
        supabase.table('quest_alliance_members').update({'status': 'accepted'}).eq('alliance_id', faction_id).eq('user_id', user_id).execute()
        fac_name = supabase.table('quest_alliances').select('name').eq('id', faction_id).execute().data[0]['name']
        bot.edit_message_text(f"Ты вступил во фракцию *{fac_name}*!", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('decline_fac_'))
def decline_invite(call):
    bot.answer_callback_query(call.id)
    faction_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', user_id).execute()
    bot.edit_message_text("Ты отклонил приглашение.", call.message.chat.id, call.message.message_id)

# --- КОЛЛЕКТИВНАЯ АТАКА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_atk_'))
def col_atk_menu(call):
    bot.answer_callback_query(call.id)
    if not is_attacks_enabled(): return bot.send_message(call.message.chat.id, "🕊 Сейчас действует перемирие.")
    faction_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup()
    factions = supabase.table('quest_alliances').select('id, name').neq('id', faction_id).execute()
    for idx, a in enumerate(factions.data): 
        markup.add(types.InlineKeyboardButton(f"🏰 {a['name']}", callback_data=f"colatk_ally_{faction_id}_{idx}"))
    markup.add(types.InlineKeyboardButton("👤 Одиночный игрок", callback_data=f"colatk_solo_{faction_id}_0"))
    bot.edit_message_text("Выбери цель для атаки фракции:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_ally_'))
def col_atk_init_ally(call):
    bot.answer_callback_query(call.id)
    try:
        parts = call.data.split('_')
        atk_fac, idx = parts[2], int(parts[3])
        user_id, _ = get_or_create_player(call.from_user)
        
        factions = supabase.table('quest_alliances').select('id, name').neq('id', atk_fac).execute()
        if idx >= len(factions.data): return bot.send_message(call.message.chat.id, "Ошибка: фракция не найдена.")
        target_fac = factions.data[idx]['id']
        target_name = factions.data[idx]['name']
        
        atk_res = supabase.table('quest_collective_attacks').insert({'alliance_id': atk_fac, 'target_id': target_fac, 'initiator_id': user_id}).execute()
        atk_id = atk_res.data[0]['id']
        
        threading.Timer(60.0, execute_collective_attack, args=[atk_id, True]).start()
        
        members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', atk_fac).eq('status', 'accepted').execute()
        member_ids = [m['user_id'] for m in members.data]
        
        if len(member_ids) <= 1:
            supabase.table('quest_collective_votes').insert({'attack_id': atk_id, 'user_id': user_id}).execute()
            execute_collective_attack(atk_id, True)
            bot.edit_message_text(f"Ты в одиночку атаковал {target_name}!", call.message.chat.id, call.message.message_id)
            return

        users_data = supabase.table('users').select('id, telegram_id').in_('id', member_ids).execute()
        for u in users_data.data:
            if u.get('telegram_id'):
                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_{atk_id}"))
                    bot.send_message(u['telegram_id'], f"⚔️ Атака на фракцию *{target_name}*! Жми!", parse_mode='Markdown', reply_markup=markup)
                except: pass
        bot.edit_message_text(f"Ожидаем удары по {target_name} (60 сек)...", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_solo_'))
def col_atk_init_solo(call):
    bot.answer_callback_query(call.id)
    try:
        parts = call.data.split('_')
        faction_id, page = parts[2], int(parts[3])
        players = supabase.table('quest_players').select('user_id, users(name)').gt('hp', 0).execute()
        
        markup = types.InlineKeyboardMarkup()
        start, end = page * 10, (page * 10) + 10
        for idx, p in enumerate(players.data[start:end]):
            real_idx = start + idx
            markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"catk_s_{faction_id}_{real_idx}"))
            
        nav = []
        if page > 0: nav.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"colatk_solo_{faction_id}_{page-1}"))
        if end < len(players.data): nav.append(types.InlineKeyboardButton("Вперед ➡️", callback_data=f"colatk_solo_{faction_id}_{page+1}"))
        if nav: markup.add(*nav)
        
        bot.edit_message_text(f"Выбери цель (стр. {page+1}):", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка пагинации: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('catk_s_'))
def col_atk_init_target(call):
    bot.answer_callback_query(call.id)
    try:
        parts = call.data.split('_')
        faction_id, idx = parts[2], int(parts[3])
        user_id, _ = get_or_create_player(call.from_user)
        
        players = supabase.table('quest_players').select('user_id').gt('hp', 0).execute()
        if idx >= len(players.data): return bot.send_message(call.message.chat.id, "Ошибка: игрок не найден.")
        target_id = players.data[idx]['user_id']
        
        atk_res = supabase.table('quest_collective_attacks').insert({'alliance_id': faction_id, 'target_id': target_id, 'initiator_id': user_id}).execute()
        atk_id = atk_res.data[0]['id']
        
        threading.Timer(60.0, execute_collective_attack, args=[atk_id, False]).start()
        
        members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', faction_id).eq('status', 'accepted').execute()
        member_ids = [m['user_id'] for m in members.data]
        
        if len(member_ids) <= 1:
            supabase.table('quest_collective_votes').insert({'attack_id': atk_id, 'user_id': user_id}).execute()
            execute_collective_attack(atk_id, False)
            bot.edit_message_text("Ты в одиночку напал на игрока!", call.message.chat.id, call.message.message_id)
            return

        users_data = supabase.table('users').select('id, telegram_id').in_('id', member_ids).execute()
        for u in users_data.data:
            if u.get('telegram_id'):
                try:
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_{atk_id}"))
                    bot.send_message(u['telegram_id'], f"⚔️ Твоя фракция объявила атаку! 1 минута на подтверждение.", reply_markup=markup)
                except: pass
        bot.edit_message_text("Ожидаем удары (60 сек)...", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при выборе цели: {e}")

def execute_collective_attack(attack_id, is_alliance_target):
    try:
        atk = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute().data
        if not atk: return 
        attack = atk[0]
        
        votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()
        if not votes.data: 
            supabase.table('quest_collective_attacks').delete().eq('id', attack_id).execute()
            return
            
        voter_ids = [v['user_id'] for v in votes.data]
        total_damage = 0
        total_pierce = 0
        for vid in voter_ids:
            s, p = get_player_stats(vid)
            total_damage += s
            total_pierce += p
            
        if is_alliance_target:
            def_members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['target_id']).execute()
            if def_members.data:
                defenders = supabase.table('quest_players').select('user_id, defense, hp').in_('user_id', [m['user_id'] for m in def_members.data]).execute()
                if defenders.data:
                    total_defense = sum(d['defense'] for d in defenders.data)
                    effective_armor = max(0, total_defense - total_pierce)
                    net_damage = max(0, total_damage - effective_armor)
                    dmg_per_player = math.ceil(net_damage / len(defenders.data)) if net_damage > 0 else 0
                    
                    if dmg_per_player > 0:
                        for d in defenders.data:
                            new_hp = max(0, d['hp'] - dmg_per_player)
                            new_stat = 'wounded' if new_hp <= 0 else 'alive'
                            supabase.table('quest_players').update({'hp': new_hp, 'status': new_stat}).eq('user_id', d['user_id']).execute()
                        log_event(f"🔥 *ВОЙНА ФРАКЦИЙ!* Урон: {total_damage}. Пробито брони: {total_pierce}. Урон по HP: {dmg_per_player} каждому.")
                    else:
                        log_event(f"🛡 *Атака фракции провалилась!* Броня выдержала удар (Урон: {total_damage}, Броня: {total_defense}).")
        else:
            defender = supabase.table('quest_players').select('*').eq('user_id', attack['target_id']).execute().data
            if defender:
                defender = defender[0]
                effective_armor = max(0, defender['defense'] - total_pierce)
                damage = max(0, total_damage - effective_armor)
                if damage > 0:
                    new_hp = max(0, defender['hp'] - damage)
                    new_stat = 'wounded' if new_hp <= 0 else 'alive'
                    supabase.table('quest_players').update({'hp': new_hp, 'status': new_stat}).eq('user_id', attack['target_id']).execute()
                    log_event(f"🔥 *Сокрушительный удар фракции!* Игрок получил {damage} урона. Осталось HP: {new_hp}.")
                else:
                    log_event(f"🛡 *Атака фракции провалилась!* Броня игрока выдержала удар.")
        
        supabase.table('quest_collective_attacks').delete().eq('id', attack_id).execute()
    except Exception as e:
        print(f"Ошибка выполнения атаки: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def col_atk_vote(call):
    bot.answer_callback_query(call.id)
    try:
        attack_id = call.data.split('_')[1]
        user_id, _ = get_or_create_player(call.from_user)
        
        atk = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute().data
        if not atk: return bot.send_message(call.message.chat.id, "⏳ Время атаки истекло.")
        
        existing = supabase.table('quest_collective_votes').select('*').eq('attack_id', attack_id).eq('user_id', user_id).execute()
        if existing.data: return bot.send_message(call.message.chat.id, "Ты уже подтвердил удар.")

        try:
            supabase.table('quest_collective_votes').insert({'attack_id': attack_id, 'user_id': user_id}).execute()
        except Exception:
            return bot.send_message(call.message.chat.id, "Атака уже завершилась.")

        attack = atk[0]
        members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['alliance_id']).eq('status', 'accepted').execute()
        votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()

        if len(votes.data) >= len(members.data):
            is_ally = supabase.table('quest_alliances').select('id').eq('id', attack['target_id']).execute().data
            execute_collective_attack(attack_id, bool(is_ally))
            bot.edit_message_text("✅ Все собрались! Удар нанесен.", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text(f"⏳ Ждем остальных... ({len(votes.data)}/{len(members.data)})", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

# --- ПАНЕЛЬ МАСТЕРА ---
@bot.message_handler(func=lambda message: message.text == '👑 Мастер' and message.from_user.id == MASTER_TG_ID)
def master_panel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💀 Убить", callback_data="master_kill"))
    markup.add(types.InlineKeyboardButton("❤️ Воскресить", callback_data="master_revive"))
    markup.add(types.InlineKeyboardButton("⚖️ Управление миссиями", callback_data="master_missions_manage"))
    markup.add(types.InlineKeyboardButton("🎁 Выдать предмет", callback_data="master_give"))
    markup.add(types.InlineKeyboardButton("📜 Выдать миссию", callback_data="master_mission"))
    markup.add(types.InlineKeyboardButton("🛠 Изменить статы", callback_data="master_stats"))
    markup.add(types.InlineKeyboardButton("✏️ Изменить имя", callback_data="master_rename"))
    markup.add(types.InlineKeyboardButton("👤 Привязка ролей", callback_data="master_bind"))
    markup.add(types.InlineKeyboardButton("🕊 Перемирие", callback_data="master_peace"))
    markup.add(types.InlineKeyboardButton("🛡 Управление фракциями", callback_data="master_faction_manage"))
    markup.add(types.InlineKeyboardButton("🖼 Установить аватар", callback_data="master_set_avatar"))
    markup.add(types.InlineKeyboardButton("📜 Установить историю", callback_data="master_set_history"))
    markup.add(types.InlineKeyboardButton("⚙️ Лог-Чат", callback_data="master_set_log"))
    bot.send_message(message.chat.id, "Панель Мастера:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'master_peace' and call.from_user.id == MASTER_TG_ID)
def master_toggle_peace(call):
    bot.answer_callback_query(call.id)
    current = is_attacks_enabled()
    new_val = 'false' if current else 'true'
    supabase.table('quest_settings').update({'value': new_val}).eq('key', 'attacks_enabled').execute()
    
    status_text = "выключен (атаки разрешены)" if new_val == 'true' else "включен (атаки запрещены)"
    bot.edit_message_text(f"🕊 Режим перемирия {status_text}.", call.message.chat.id, call.message.message_id)
    if new_val == 'false':
        log_event(f"🕊 *Мастер объявил перемирие.* Атаки запрещены.")

@bot.callback_query_handler(func=lambda call: call.data == 'master_rename' and call.from_user.id == MASTER_TG_ID)
def master_rename_menu(call):
    bot.answer_callback_query(call.id)
    players = supabase.table('users').select('id, name').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): 
        markup.add(types.InlineKeyboardButton(f"{p['name']}", callback_data=f"ren_{idx}"))
    temp_master_data['rename_list'] = [p['id'] for p in players.data]
    bot.edit_message_text("Кому изменить имя?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ren_') and call.from_user.id == MASTER_TG_ID)
def master_rename_ask(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    targets = temp_master_data.get('rename_list', [])
    if idx < len(targets):
        temp_master_data['rename_target'] = targets[idx]
        msg = bot.send_message(call.message.chat.id, "Введи новое имя:")
        bot.register_next_step_handler(msg, master_rename_save)

def master_rename_save(message):
    target_id = temp_master_data.get('rename_target')
    if target_id:
        supabase.table('users').update({'name': message.text}).eq('id', target_id).execute()
        bot.send_message(message.chat.id, "Имя обновлено!", reply_markup=get_main_keyboard(message.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data == 'master_bind' and call.from_user.id == MASTER_TG_ID)
def master_bind_menu(call):
    bot.answer_callback_query(call.id)
    users = supabase.table('users').select('id, name, telegram_id').not_.is_('telegram_id', 'null').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, u in enumerate(users.data):
        markup.add(types.InlineKeyboardButton(f"{u['name']} (TG)", callback_data=f"binduser_{idx}"))
    temp_master_data['bind_users'] = [u['id'] for u in users.data]
    bot.edit_message_text("Выбери аккаунт Telegram:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('binduser_') and call.from_user.id == MASTER_TG_ID)
def master_bind_choose_npc(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    users = temp_master_data.get('bind_users', [])
    if idx >= len(users): return
    temp_master_data['bind_target_user'] = users[idx]
    
    npcs = supabase.table('users').select('id, name').is_('telegram_id', 'null').execute()
    if not npcs.data: return bot.edit_message_text("Нет свободных персонажей.", call.message.chat.id, call.message.message_id)
    
    markup = types.InlineKeyboardMarkup()
    for i, n in enumerate(npcs.data):
        markup.add(types.InlineKeyboardButton(f"{n['name']}", callback_data=f"bindnpc_{i}"))
    temp_master_data['bind_npcs'] = [n['id'] for n in npcs.data]
    bot.edit_message_text("Выбери персонажа:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('bindnpc_') and call.from_user.id == MASTER_TG_ID)
def master_bind_do(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    target_user_id = temp_master_data.get('bind_target_user')
    npcs = temp_master_data.get('bind_npcs', [])
    
    if idx < len(npcs) and target_user_id:
        npc_id = npcs[idx]
        u_res = supabase.table('users').select('telegram_id').eq('id', target_user_id).execute()
        if not u_res.data: return bot.edit_message_text("Ошибка: игрок не найден.", call.message.chat.id, call.message.message_id)
        tg_id = u_res.data[0]['telegram_id']
        
        try:
            # 1. Обнуляем лидерство, чтобы фракции не удалились каскадно
            supabase.table('quest_alliances').update({'leader_id': None}).eq('leader_id', target_user_id).execute()
            
            # 2. Удаляем старый профиль (освобождаем telegram_id)
            supabase.table('users').delete().eq('id', target_user_id).execute()
            
            # 3. Привязываем telegram_id к новому NPC
            supabase.table('users').update({'telegram_id': tg_id}).eq('id', npc_id).execute()
            
            bot.edit_message_text(f"✅ Успешно! Игрок теперь управляет персонажем. Нажми /start", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка привязки: {e}", call.message.chat.id, call.message.message_id)
    else:
        bot.edit_message_text("Ошибка: данные устарели, попробуй заново.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_kill' and call.from_user.id == MASTER_TG_ID)
def master_kill_menu(call):
    bot.answer_callback_query(call.id)
    all_players = supabase.table('quest_players').select('user_id, users(name)').neq('status', 'dead').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Убить {p['users']['name']}", callback_data=f"mkill_{p['user_id']}"))
    bot.edit_message_text("Кого казнить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mkill_') and call.from_user.id == MASTER_TG_ID)
def master_do_kill(call):
    bot.answer_callback_query(call.id)
    uid = call.data.split('_')[1]
    supabase.table('quest_players').update({'status': 'dead', 'hp': 0}).eq('user_id', uid).execute()
    bot.edit_message_text("Игрок казнен.", call.message.chat.id, call.message.message_id)
    log_event(f"💀 *Мастер* вынес смертный приговор.")

@bot.callback_query_handler(func=lambda call: call.data == 'master_revive' and call.from_user.id == MASTER_TG_ID)
def master_revive_menu(call):
    bot.answer_callback_query(call.id)
    players = supabase.table('quest_players').select('user_id, users(name)').in_('status', ['dead', 'wounded']).execute()
    if not players.data: return bot.edit_message_text("Некого воскрешать.", call.message.chat.id, call.message.message_id)
    markup = types.InlineKeyboardMarkup()
    for p in players.data: markup.add(types.InlineKeyboardButton(f"Воскресить {p['users']['name']}", callback_data=f"mrev_{p['user_id']}"))
    bot.edit_message_text("Кого воскресить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mrev_') and call.from_user.id == MASTER_TG_ID)
def master_do_revive(call):
    bot.answer_callback_query(call.id)
    uid = call.data.split('_')[1]
    supabase.table('quest_players').update({'status': 'alive', 'hp': 10}).eq('user_id', uid).execute()
    bot.edit_message_text("Игрок исцелен (10 HP).", call.message.chat.id, call.message.message_id)
    log_event(f"✨ *Мастер* даровал исцеление!")

@bot.callback_query_handler(func=lambda call: call.data == 'master_stats' and call.from_user.id == MASTER_TG_ID)
def master_stats_menu(call):
    bot.answer_callback_query(call.id)
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for p in players.data: markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"mstat_{p['user_id']}"))
    bot.edit_message_text("Кому изменить характеристики?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mstat_') and call.from_user.id == MASTER_TG_ID)
def master_stats_choose(call):
    bot.answer_callback_query(call.id)
    target_id = call.data.split('_')[1]
    temp_master_data['stat_target'] = target_id
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("HP", callback_data="chstat_hp"), types.InlineKeyboardButton("Сила", callback_data="chstat_str"))
    markup.add(types.InlineKeyboardButton("Броня", callback_data="chstat_def"), types.InlineKeyboardButton("Талеры", callback_data="chstat_mon"))
    bot.edit_message_text("Какой параметр изменить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('chstat_') and call.from_user.id == MASTER_TG_ID)
def master_stats_ask(call):
    bot.answer_callback_query(call.id)
    stat = call.data.split('_')[1]
    temp_master_data['stat_type'] = stat
    msg = bot.send_message(call.message.chat.id, "Введи новое значение (целое число):")
    bot.register_next_step_handler(msg, master_stats_apply)

def master_stats_apply(message):
    try:
        val = int(message.text)
        target_id = temp_master_data.get('stat_target')
        stat = temp_master_data.get('stat_type')
        if not target_id or not stat: return bot.send_message(message.chat.id, "Ошибка.")
        field = {'hp': 'hp', 'str': 'strength', 'def': 'defense', 'mon': 'star_thalers'}.get(stat)
        if field:
            supabase.table('quest_players').update({field: val}).eq('user_id', target_id).execute()
            bot.send_message(message.chat.id, f"Параметр {field} обновлен на {val}.", reply_markup=get_main_keyboard(message.from_user.id))
    except ValueError:
        bot.send_message(message.chat.id, "Введи число!", reply_markup=get_main_keyboard(message.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data == 'master_faction_manage' and call.from_user.id == MASTER_TG_ID)
def master_faction_menu(call):
    bot.answer_callback_query(call.id)
    factions = supabase.table('quest_alliances').select('id, name').execute()
    markup = types.InlineKeyboardMarkup()
    for f in factions.data: markup.add(types.InlineKeyboardButton(f"{f['name']}", callback_data=f"mfac_{f['id']}"))
    bot.edit_message_text("Выбери фракцию:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mfac_') and call.from_user.id == MASTER_TG_ID)
def master_faction_action(call):
    bot.answer_callback_query(call.id)
    faction_id = call.data.split('_')[1]
    temp_master_data['faction_id'] = faction_id
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Добавить игрока", callback_data="mfa_add"))
    markup.add(types.InlineKeyboardButton("Удалить игрока", callback_data="mfr_rem"))
    bot.edit_message_text("Действие с фракцией:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'mfa_add' and call.from_user.id == MASTER_TG_ID)
def master_faction_add_menu(call):
    bot.answer_callback_query(call.id)
    faction_id = temp_master_data.get('faction_id')
    if not faction_id: return bot.send_message(call.message.chat.id, "Ошибка: фракция не выбрана.")
    existing = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', faction_id).execute()
    exclude_ids = [m['user_id'] for m in existing.data]
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    targets = [p for p in players.data if p['user_id'] not in exclude_ids]
    temp_master_data['mf_targets'] = [p['user_id'] for p in targets]
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(targets): markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"mfadd_{idx}"))
    bot.edit_message_text("Кого добавить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mfadd_') and call.from_user.id == MASTER_TG_ID)
def master_faction_add_do(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    targets = temp_master_data.get('mf_targets', [])
    faction_id = temp_master_data.get('faction_id')
    if idx < len(targets) and faction_id:
        try:
            supabase.table('quest_alliance_members').insert({'alliance_id': faction_id, 'user_id': targets[idx], 'status': 'accepted'}).execute()
            bot.edit_message_text("✅ Игрок добавлен.", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка добавления: {e}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'mfr_rem' and call.from_user.id == MASTER_TG_ID)
def master_faction_rem_menu(call):
    bot.answer_callback_query(call.id)
    faction_id = temp_master_data.get('faction_id')
    if not faction_id: return bot.send_message(call.message.chat.id, "Ошибка: фракция не выбрана.")
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', faction_id).execute()
    temp_master_data['mf_members'] = [m['user_id'] for m in members.data]
    markup = types.InlineKeyboardMarkup()
    for idx, m in enumerate(members.data): markup.add(types.InlineKeyboardButton(f"{m['users']['name']}", callback_data=f"mfrem_{idx}"))
    bot.edit_message_text("Кого удалить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mfrem_') and call.from_user.id == MASTER_TG_ID)
def master_faction_rem_do(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    members = temp_master_data.get('mf_members', [])
    faction_id = temp_master_data.get('faction_id')
    if idx < len(members) and faction_id:
        try:
            supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', members[idx]).execute()
            bot.edit_message_text("✅ Игрок удален.", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Ошибка удаления: {e}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_mission' and call.from_user.id == MASTER_TG_ID)
def master_mission_menu(call):
    bot.answer_callback_query(call.id)
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for p in players.data: markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"mmiss_{p['user_id']}"))
    bot.edit_message_text("Кому выдать миссию?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mmiss_') and call.from_user.id == MASTER_TG_ID)
def master_mission_ask(call):
    bot.answer_callback_query(call.id)
    target_id = call.data.split('_')[1]
    temp_master_data['mission_target'] = target_id
    msg = bot.send_message(call.message.chat.id, "Напиши текст миссии:")
    bot.register_next_step_handler(msg, master_mission_save)

def master_mission_save(message):
    target_id = temp_master_data.get('mission_target')
    if target_id:
        supabase.table('quest_missions').insert({'user_id': target_id, 'text': message.text}).execute()
        bot.send_message(message.chat.id, "Миссия выдана!", reply_markup=get_main_keyboard(message.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data == 'master_missions_manage' and call.from_user.id == MASTER_TG_ID)
def master_missions_manage(call):
    bot.answer_callback_query(call.id)
    res = supabase.table('quest_missions').select('*, users(name)').eq('status', 'review').execute()
    if not res.data: return bot.edit_message_text("Нет миссий на проверке.", call.message.chat.id, call.message.message_id)
    
    temp_master_data['m_manage_list'] = [m['id'] for m in res.data]
    
    markup = types.InlineKeyboardMarkup()
    for idx, m in enumerate(res.data):
        name = m['users']['name']
        text = m['text'][:20] + "..." if len(m['text']) > 20 else m['text']
        markup.add(types.InlineKeyboardButton(f"{name}: {text}", callback_data=f"m_chk_{idx}"))
    bot.edit_message_text("Выбери миссию для проверки:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('m_chk_') and call.from_user.id == MASTER_TG_ID)
def master_mission_check(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[2])
    missions = temp_master_data.get('m_manage_list', [])
    if idx >= len(missions): return bot.send_message(call.message.chat.id, "Ошибка: миссия не найдена.")
    
    mission_id = missions[idx]
    mission = supabase.table('quest_missions').select('*, users(name)').eq('id', mission_id).execute().data[0]
    
    text = f"📜 Миссия игрока *{mission['users']['name']}*:\n\n_{mission['text']}_"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"m_acc_{idx}"))
    markup.add(types.InlineKeyboardButton("❌ Отклонить", callback_data=f"m_rej_{idx}"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('m_acc_') and call.from_user.id == MASTER_TG_ID)
def master_mission_accept(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[2])
    missions = temp_master_data.get('m_manage_list', [])
    if idx >= len(missions): return bot.send_message(call.message.chat.id, "Ошибка.")
    
    mission_id = missions[idx]
    mission = supabase.table('quest_missions').select('user_id').eq('id', mission_id).execute().data[0]
    supabase.table('quest_missions').update({'status': 'completed'}).eq('id', mission_id).execute()
    
    u_res = supabase.table('users').select('telegram_id').eq('id', mission['user_id']).execute()
    if u_res.data and u_res.data[0]['telegram_id']:
        try: bot.send_message(u_res.data[0]['telegram_id'], "✅ Мастер принял твою миссию!")
        except: pass
    bot.edit_message_text("Миссия принята.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('m_rej_') and call.from_user.id == MASTER_TG_ID)
def master_mission_reject(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[2])
    missions = temp_master_data.get('m_manage_list', [])
    if idx >= len(missions): return bot.send_message(call.message.chat.id, "Ошибка.")
    
    mission_id = missions[idx]
    supabase.table('quest_missions').update({'status': 'active'}).eq('id', mission_id).execute()
    bot.edit_message_text("Миссия отклонена (возвращена игроку).", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_give' and call.from_user.id == MASTER_TG_ID)
def master_give_menu(call):
    bot.answer_callback_query(call.id)
    items = supabase.table('quest_items').select('*').execute()
    if not items.data: return bot.send_message(call.message.chat.id, "Сначала создай предмет!")
    markup = types.InlineKeyboardMarkup()
    for idx, it in enumerate(items.data): markup.add(types.InlineKeyboardButton(f"{it['name']}", callback_data=f"giveitem_{idx}"))
    bot.edit_message_text("Какой предмет выдать?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('giveitem_') and call.from_user.id == MASTER_TG_ID)
def master_give_choose_player(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    all_players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"giveplayer_{idx}_{p['user_id']}"))
    bot.edit_message_text("Кому выдать?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('giveplayer_') and call.from_user.id == MASTER_TG_ID)
def master_give_do(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split('_')
    idx, user_id = int(parts[1]), parts[2]
    items = supabase.table('quest_items').select('*').execute().data
    if idx < len(items):
        supabase.table('quest_inventory').insert({'user_id': user_id, 'item_id': items[idx]['id']}).execute()
        bot.edit_message_text("Предмет в инвентаре.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_avatar' and call.from_user.id == MASTER_TG_ID)
def master_avatar_start(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Отправь мне картинку (фото).")
    bot.register_next_step_handler(call.message, master_avatar_get_photo)

def master_avatar_get_photo(message):
    if not message.photo: return bot.send_message(message.chat.id, "Это не фото.")
    file_id = message.photo[-1].file_id
    temp_avatars[message.chat.id] = file_id
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"setav_{idx}"))
    bot.send_message(message.chat.id, "Кому установить?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setav_') and call.from_user.id == MASTER_TG_ID)
def master_avatar_save(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    file_id = temp_avatars.get(call.message.chat.id)
    players = supabase.table('quest_players').select('user_id').execute()
    if idx < len(players.data) and file_id:
        supabase.table('quest_players').update({'avatar_id': file_id}).eq('user_id', players.data[idx]['user_id']).execute()
        bot.edit_message_text("Аватар обновлен.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_history' and call.from_user.id == MASTER_TG_ID)
def master_history_start(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Напиши текст истории для персонажа:")
    bot.register_next_step_handler(call.message, master_history_save)

def master_history_save(message):
    history_text = message.text
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): 
        temp_avatars[f"hist_{idx}"] = history_text
        markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"sethist_{idx}"))
    bot.send_message(message.chat.id, "Кому установить эту историю?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sethist_') and call.from_user.id == MASTER_TG_ID)
def master_history_apply(call):
    bot.answer_callback_query(call.id)
    idx = int(call.data.split('_')[1])
    hist_text = temp_avatars.get(f"hist_{idx}")
    players = supabase.table('quest_players').select('user_id').execute()
    if idx < len(players.data) and hist_text:
        supabase.table('quest_players').update({'history': hist_text}).eq('user_id', players.data[idx]['user_id']).execute()
        bot.edit_message_text("История успешно обновлена.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_log' and call.from_user.id == MASTER_TG_ID)
def master_log_setup(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Отправь ID чата для логов.")
    bot.register_next_step_handler(call.message, master_log_save)

def master_log_save(message):
    supabase.table('quest_settings').update({'value': message.text.strip()}).eq('key', 'log_chat_id').execute()
    bot.send_message(message.chat.id, "Лог-чат настроен!")

# --- ИНВЕНТАРЬ ---
@bot.message_handler(func=lambda message: message.text == '🎒 Инвентарь')
def inventory(message):
    user_id, _ = get_or_create_player(message.from_user)
    res = supabase.table('quest_inventory').select('*, quest_items(*)').eq('user_id', user_id).execute()
    if not res.data: return bot.send_message(message.chat.id, "Инвентарь пуст.")
    text = "🎒 *Твой инвентарь:*\n\n"
    markup = types.InlineKeyboardMarkup()
    for item in res.data:
        it = item['quest_items']
        eq = "✅" if item['is_equipped'] else ""
        
        bonuses = []
        if it.get('attack_bonus'): bonuses.append(f"⚔️+{it['attack_bonus']} Сила")
        if it.get('defense_bonus'): bonuses.append(f"🛡+{it['defense_bonus']} Броня")
        if it.get('armor_pierce'): bonuses.append(f"🩸Пробитие {it['armor_pierce']}")
        
        bonus_text = ", ".join(bonuses) if bonuses else "Без бонусов"
        text += f"▪️ *{it['name']}* {eq}\n_{it.get('description') or 'Без описания'}_\n({bonus_text})\n\n"
        
        if not item['is_equipped']: 
            markup.add(types.InlineKeyboardButton(f"Надеть {it['name']}", callback_data=f"equip_{item['id']}"))
            
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('equip_'))
def equip_item(call):
    bot.answer_callback_query(call.id)
    inv_id = call.data.split('_')[1]
    supabase.table('quest_inventory').update({'is_equipped': True}).eq('id', inv_id).execute()
    bot.edit_message_text("Предмет надет.", call.message.chat.id, call.message.message_id)

# --- ВЕБ-СЕРВЕР ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is alive")
    def do_HEAD(self): self.send_response(200); self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), DummyHandler).serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# --- ЗАПУСК С ЗАЩИТОЙ ОТ ПАДЕНИЙ ---
print("Бот запущен...")
while True:
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Критическая ошибка сети: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
