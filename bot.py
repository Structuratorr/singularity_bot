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

# Временное хранилище для аватарок (чтобы обойти лимит кнопок Telegram)
temp_avatars = {}

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
        except Exception as e:
            print(f"Ошибка лога: {e}")

# --- ПРОФИЛИ И МИР ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id, player = get_or_create_player(message.from_user)
    bot.send_message(message.chat.id, f"Добро пожаловать в квест, {message.from_user.first_name}!", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda message: message.text == '🌍 Мир')
def world_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    players = supabase.table('quest_players').select('user_id, status, users(name)').execute()
    
    markup = types.InlineKeyboardMarkup()
    # Telegram ограничивает кол-во кнопок, но для 60 игроков это сработает (максимум 100)
    for p in players.data:
        status_icon = '💀' if p['status'] == 'dead' else ('🩸' if p['status'] == 'wounded' else '🟢')
        markup.add(types.InlineKeyboardButton(f"{status_icon} {p['users']['name']}", callback_data=f"view_{p['user_id']}"))
        
    bot.send_message(message.chat.id, "🌍 *Жители мира:*\nВыбери игрока, чтобы посмотреть профиль.", parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_profile(call):
    target_id = call.data.split('_')[1]
    p_res = supabase.table('quest_players').select('*, users(name)').eq('user_id', target_id).execute()
    if not p_res.data: return bot.answer_callback_query(call.id, "Не найден.")
    player = p_res.data[0]
    name = player['users']['name']
    
    status_emoji = '💀' if player['status'] == 'dead' else ('🩸' if player['status'] == 'wounded' else '🟢')
    text = (f"👤 *{name}*\nФракция: {player['faction']}\n"
            f"Статус: {status_emoji} {player['status']}\n⚔️ Сила: {player['strength']}\n"
            f"🛡 Защита: {player['defense']}\n💰 Талеры: {player['star_thalers']}\n\n"
            f"📜 История: {player['history'] or 'Скрыто'}")
            
    if player.get('avatar_id'):
        try:
            bot.send_photo(call.message.chat.id, player['avatar_id'], caption=text, parse_mode='Markdown')
        except:
            bot.send_message(call.message.chat.id, text + "\n\n(Ошибка загрузки аватара)", parse_mode='Markdown')
    else:
        bot.send_message(call.message.chat.id, text + "\n\n(Нет аватара)", parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '👤 Профиль')
def profile(message):
    user_id, player = get_or_create_player(message.from_user)
    inv = supabase.table('quest_inventory').select('*, quest_items(*)').eq('user_id', user_id).eq('is_equipped', True).execute()
    att_bonus = sum(i['quest_items']['attack_bonus'] for i in inv.data) if inv.data else 0
    def_bonus = sum(i['quest_items']['defense_bonus'] for i in inv.data) if inv.data else 0
    status_emoji = '💀' if player['status'] == 'dead' else ('🩸' if player['status'] == 'wounded' else '🟢')
    
    text = (f"👤 *{message.from_user.first_name}*\nФракция: {player['faction']}\nСтатус: {status_emoji} {player['status']}\n\n"
            f"⚔️ Сила: {player['strength']} (+{att_bonus})\n🛡 Защита: {player['defense']} (+{def_bonus})\n"
            f"💰 Талеры: {player['star_thalers']}\n\n📜 История: {player['history'] or 'Пока пусто...'}")
            
    if player.get('avatar_id'):
        try:
            bot.send_photo(message.chat.id, player['avatar_id'], caption=text, parse_mode='Markdown')
        except:
            bot.send_message(message.chat.id, text, parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, text, parse_mode='Markdown')

# --- НАПАДЕНИЯ ---
@bot.message_handler(func=lambda message: message.text == '⚔️ Напасть')
def attack_menu(message):
    user_id, player = get_or_create_player(message.from_user)
    if player['status'] != 'alive': return bot.send_message(message.chat.id, "Ты не можешь нападать в текущем статусе.")
    
    # Показываем ВСЕХ, кроме себя (можно бить даже союзников)
    targets = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).eq('status', 'alive').execute()
    
    markup = types.InlineKeyboardMarkup()
    for p in targets.data: 
        markup.add(types.InlineKeyboardButton(f"⚔️ {p['users']['name']}", callback_data=f"atk_{p['user_id']}"))
    
    if targets.data: bot.send_message(message.chat.id, "Выбери цель:", reply_markup=markup)
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

# --- СОЮЗЫ ---
@bot.message_handler(func=lambda message: message.text == '🤝 Союз')
def alliance_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    res = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name, leader_id)').eq('user_id', user_id).eq('status', 'accepted').execute()
    
    markup = types.InlineKeyboardMarkup()
    text = "🤝 *Твои союзы:*\n\n"
    
    if res.data:
        for item in res.data:
            alliance = item['quest_alliances']
            is_leader = (alliance['leader_id'] == user_id)
            text += f"🛡 *{alliance['name']}* {'(Лидер)' if is_leader else ''}\n"
            
            if is_leader:
                markup.add(types.InlineKeyboardButton(f"⚙️ Управление: {alliance['name']}", callback_data=f"ally_manage_{alliance['id']}"))
            else:
                markup.add(types.InlineKeyboardButton(f"🚪 Выйти из {alliance['name']}", callback_data=f"ally_leave_{alliance['id']}"))
    else:
        text = "У тебя пока нет союзов."
        
    markup.add(types.InlineKeyboardButton("➕ Создать союз", callback_data="create_alliance"))
    
    invites = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name)').eq('user_id', user_id).eq('status', 'pending').execute()
    if invites.data:
        text += "\n\n📩 *У тебя есть приглашения:*"
        for inv in invites.data:
            markup.add(types.InlineKeyboardButton(f"✅ Принять: {inv['quest_alliances']['name']}", callback_data=f"join_alliance_{inv['alliance_id']}"))
            markup.add(types.InlineKeyboardButton(f"❌ Отклонить: {inv['quest_alliances']['name']}", callback_data=f"decline_alliance_{inv['alliance_id']}"))

    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'create_alliance')
def create_alliance(call):
    bot.send_message(call.message.chat.id, "Введи название союза:")
    bot.register_next_step_handler(call.message, save_alliance)

def save_alliance(message):
    user_id, _ = get_or_create_player(message.from_user)
    name = message.text
    a_res = supabase.table('quest_alliances').insert({'name': name, 'leader_id': user_id}).execute()
    supabase.table('quest_alliance_members').insert({'alliance_id': a_res.data[0]['id'], 'user_id': user_id, 'status': 'accepted'}).execute()
    bot.send_message(message.chat.id, f"Союз *{name}* создан!", parse_mode='Markdown', reply_markup=get_main_keyboard(message.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data.startswith('ally_leave_'))
def leave_alliance(call):
    alliance_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').delete().eq('alliance_id', alliance_id).eq('user_id', user_id).execute()
    bot.answer_callback_query(call.id, "Ты покинул союз.")
    bot.edit_message_text("Ты вышел из союза.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ally_manage_'))
def manage_alliance(call):
    alliance_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Пригласить игрока", callback_data=f"ally_invite_{alliance_id}"))
    markup.add(types.InlineKeyboardButton("⚔️ Коллективная атака", callback_data=f"ally_col_atk_{alliance_id}"))
    markup.add(types.InlineKeyboardButton("👢 Выгнать участника", callback_data=f"ally_kick_menu_{alliance_id}"))
    
    bot.edit_message_text("Управление союзом:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ally_invite_'))
def alliance_invite_menu(call):
    alliance_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    
    # Приглашаем только тех, кого нет в этом конкретном союзе
    existing_members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', alliance_id).execute()
    exclude_ids = [m['user_id'] for m in existing_members.data]
    
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    targets = [p for p in players.data if p['user_id'] not in exclude_ids]
    
    if not targets: return bot.answer_callback_query(call.id, "Нет игроков для приглашения.", show_alert=True)
    
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(targets):
        markup.add(types.InlineKeyboardButton(f"Пригласить {p['users']['name']}", callback_data=f"inv_{alliance_id}_{idx}"))
        
    bot.edit_message_text("Кого пригласить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('inv_'))
def send_invite(call):
    parts = call.data.split('_')
    alliance_id, idx = parts[1], int(parts[2])
    user_id, _ = get_or_create_player(call.from_user)
    
    existing_members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', alliance_id).execute()
    exclude_ids = [m['user_id'] for m in existing_members.data]
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    targets = [p for p in players.data if p['user_id'] not in exclude_ids]
    
    if idx >= len(targets): return bot.answer_callback_query(call.id, "Игрок не найден.", show_alert=True)
        
    target_player = targets[idx]
    target_user_id = target_player['user_id']
    
    u_res = supabase.table('users').select('telegram_id').eq('id', target_user_id).execute()
    target_tg_id = u_res.data[0]['telegram_id'] if u_res.data else None
    
    existing = supabase.table('quest_alliance_members').select('*').eq('alliance_id', alliance_id).eq('user_id', target_user_id).execute()
    if not existing.data:
        supabase.table('quest_alliance_members').insert({'alliance_id': alliance_id, 'user_id': target_user_id, 'status': 'pending'}).execute()
        
    if target_tg_id:
        alliance_name = supabase.table('quest_alliances').select('name').eq('id', alliance_id).execute().data[0]['name']
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"join_alliance_{alliance_id}"))
        markup.add(types.InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_alliance_{alliance_id}"))
        try:
            bot.send_message(target_tg_id, f"🤝 Вас приглашают в союз *{alliance_name}*!", parse_mode='Markdown', reply_markup=markup)
        except: pass
            
    bot.answer_callback_query(call.id, "Приглашение отправлено!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ally_kick_menu_'))
def kick_menu(call):
    alliance_id = call.data.split('_')[3]
    user_id, _ = get_or_create_player(call.from_user)
    
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', alliance_id).eq('status', 'accepted').neq('user_id', user_id).execute()
    if not members.data: return bot.answer_callback_query(call.id, "В союзе нет других участников.", show_alert=True)
    
    markup = types.InlineKeyboardMarkup()
    for idx, m in enumerate(members.data):
        markup.add(types.InlineKeyboardButton(f"Выгнать {m['users']['name']}", callback_data=f"kick_{alliance_id}_{idx}"))
    
    bot.edit_message_text("Кого выгнать?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('kick_'))
def do_kick(call):
    parts = call.data.split('_')
    alliance_id, idx = parts[1], int(parts[2])
    user_id, _ = get_or_create_player(call.from_user)
    
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', alliance_id).eq('status', 'accepted').neq('user_id', user_id).execute()
    if idx >= len(members.data): return bot.answer_callback_query(call.id, "Ошибка.", show_alert=True)
    
    target = members.data[idx]
    supabase.table('quest_alliance_members').delete().eq('alliance_id', alliance_id).eq('user_id', target['user_id']).execute()
    
    bot.answer_callback_query(call.id, "Игрок выгнан!")
    bot.edit_message_text(f"Игрок {target['users']['name']} исключен из союза.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_alliance_'))
def accept_invite(call):
    alliance_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').update({'status': 'accepted'}).eq('alliance_id', alliance_id).eq('user_id', user_id).execute()
    bot.answer_callback_query(call.id, "Ты в союзе!")
    bot.edit_message_text("Ты вступил в союз!", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('decline_alliance_'))
def decline_invite(call):
    alliance_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').delete().eq('alliance_id', alliance_id).eq('user_id', user_id).execute()
    bot.edit_message_text("Ты отклонил приглашение.", call.message.chat.id, call.message.message_id)

# --- КОЛЛЕКТИВНАЯ АТАКА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('ally_col_atk_'))
def col_atk_menu(call):
    alliance_id = call.data.split('_')[3]
    markup = types.InlineKeyboardMarkup()
    
    # 1. Нападение на союз
    alliances = supabase.table('quest_alliances').select('id, name').neq('id', alliance_id).execute()
    for a in alliances.data:
        markup.add(types.InlineKeyboardButton(f"🏰 Атаковать союз: {a['name']}", callback_data=f"colatk_ally_{alliance_id}_{a['id']}"))
        
    # 2. Нападение на одиночку
    markup.add(types.InlineKeyboardButton("👤 Атаковать игрока", callback_data=f"colatk_solo_{alliance_id}"))
    
    bot.edit_message_text("Выбери, на кого напасть:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_ally_'))
def col_atk_init_ally(call):
    parts = call.data.split('_')
    attacker_alliance_id = parts[2]
    target_alliance_id = parts[3]
    user_id, _ = get_or_create_player(call.from_user)
    
    target_alliance = supabase.table('quest_alliances').select('name').eq('id', target_alliance_id).execute().data[0]
    
    atk_res = supabase.table('quest_collective_attacks').insert({
        'alliance_id': attacker_alliance_id, 
        'target_id': target_alliance_id,
        'initiator_id': user_id
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_solo_'))
def col_atk_init_solo(call):
    alliance_id = call.data.split('_')[2]
    players = supabase.table('quest_players').select('user_id, users(name)').eq('status', 'alive').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): 
        markup.add(types.InlineKeyboardButton(f"Напасть на {p['users']['name']}", callback_data=f"colatk_target_{alliance_id}_{idx}"))
    bot.edit_message_text("Выбери цель-игрока:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_target_'))
def col_atk_init_target(call):
    parts = call.data.split('_')
    alliance_id, idx = parts[2], int(parts[3])
    user_id, _ = get_or_create_player(call.from_user)
    
    players = supabase.table('quest_players').select('user_id, users(name)').eq('status', 'alive').execute()
    if idx >= len(players.data): return bot.answer_callback_query(call.id, "Не найден.")
    target_id = players.data[idx]['user_id']
    
    atk_res = supabase.table('quest_collective_attacks').insert({'alliance_id': alliance_id, 'target_id': target_id, 'initiator_id': user_id}).execute()
    attack_id = atk_res.data[0]['id']
    
    timer = threading.Timer(60.0, execute_collective_attack, args=[attack_id, False])
    timer.start()
    
    members = supabase.table('quest_alliance_members').select('user_id, users(telegram_id)').eq('alliance_id', alliance_id).eq('status', 'accepted').execute()
    for m in members.data:
        tg_id = m['users']['telegram_id']
        if tg_id:
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_{attack_id}"))
                bot.send_message(tg_id, f"⚔️ Твой союз объявил атаку! У тебя 1 минута, чтобы нажать кнопку.", reply_markup=markup)
            except: pass
            
    bot.answer_callback_query(call.id, "Атака инициирована!")
    bot.edit_message_text("Ожидаем удары (60 секунд)...", call.message.chat.id, call.message.message_id)

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
        
        defenders = supabase.table('quest_players').select('user_id, defense').in_('user_id', [m['user_id'] for m in def_members.data]).execute()
        total_defense = sum(d['defense'] for d in defenders.data)
        
        net_damage = max(0, total_damage - total_defense)
        dmg_per_player = math.ceil(net_damage / len(defenders.data)) if defenders.data else 0
        
        if dmg_per_player > 0:
            for d in defenders.data:
                new_def = max(0, d['defense'] - dmg_per_player)
                new_stat = 'wounded' if new_def <= 0 else 'alive'
                supabase.table('quest_players').update({'defense': new_def, 'status': new_stat}).eq('user_id', d['user_id']).execute()
                
        log_event(f"🔥 *ВОЙНА!* Союз нанес удар! Суммарный урон: {total_damage}, Защита врага: {total_defense}. Пробито: {net_damage} урона (по {dmg_per_player} каждому).")
        
    else:
        # Атака на игрока
        defender = supabase.table('quest_players').select('*').eq('user_id', attack['target_id']).execute().data[0]
        new_defense = max(0, defender['defense'] - total_damage)
        new_status = 'wounded' if new_defense <= 0 else defender['status']
        supabase.table('quest_players').update({'defense': new_defense, 'status': new_status}).eq('user_id', attack['target_id']).execute()
        log_event(f"🔥 Коллективная атака на игрока! Урон: {total_damage}.")
        
    supabase.table('quest_collective_votes').delete().eq('attack_id', attack_id).execute()

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def col_atk_vote(call):
    attack_id = call.data.split('_')[1]
    user_id, _ = get_or_create_player(call.from_user)
    
    try: 
        supabase.table('quest_collective_votes').insert({'attack_id': attack_id, 'user_id': user_id}).execute()
    except: 
        return bot.answer_callback_query(call.id, "Ты уже подтвердил.", show_alert=True)

    atk_res = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute()
    if not atk_res.data: return bot.answer_callback_query(call.id, "Время вышло, атака завершена!", show_alert=True)
    attack = atk_res.data[0]

    members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['alliance_id']).eq('status', 'accepted').execute()
    votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()

    if len(votes.data) >= len(members.data):
        # Если все нажали, определяем тип цели (союз или игрок)
        is_ally = supabase.table('quest_alliances').select('id').eq('id', attack['target_id']).execute().data
        execute_collective_attack(attack_id, bool(is_ally))
        bot.edit_message_text("Ты подтвердил. Все собрались! Удар нанесен.", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Голос учтен! Ждем остальных...")
        bot.edit_message_text("Ты подтвердил. Ждем остальных...", call.message.chat.id, call.message.message_id)

# --- ПАНЕЛЬ МАСТЕРА ---
@bot.message_handler(func=lambda message: message.text == '👑 Мастер' and message.from_user.id == MASTER_TG_ID)
def master_panel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💀 Убить", callback_data="master_kill"))
    markup.add(types.InlineKeyboardButton("🎁 Выдать предмет", callback_data="master_give"))
    markup.add(types.InlineKeyboardButton("🖼 Установить аватар", callback_data="master_set_avatar"))
    markup.add(types.InlineKeyboardButton("⚙️ Настроить Лог-Чат", callback_data="master_set_log"))
    bot.send_message(message.chat.id, "Панель Мастера:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'master_kill' and call.from_user.id == MASTER_TG_ID)
def master_kill_menu(call):
    all_players = supabase.table('quest_players').select('user_id, users(name)').neq('status', 'dead').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Убить {p['users']['name']}", callback_data=f"mkill_{p['user_id']}"))
    bot.send_message(call.message.chat.id, "Кого казнить?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mkill_') and call.from_user.id == MASTER_TG_ID)
def master_do_kill(call):
    uid = call.data.split('_')[1]
    supabase.table('quest_players').update({'status': 'dead', 'defense': 0}).eq('user_id', uid).execute()
    bot.answer_callback_query(call.id, "Игрок казнен!")
    bot.send_message(call.message.chat.id, "Игрок отправлен к праотцам.")
    log_event(f"💀 *{call.from_user.first_name}* (Мастер) убил игрока.")

@bot.callback_query_handler(func=lambda call: call.data == 'master_give' and call.from_user.id == MASTER_TG_ID)
def master_give_menu(call):
    items = supabase.table('quest_items').select('*').execute()
    if not items.data: return bot.answer_callback_query(call.id, "Сначала создай предмет в базе!", show_alert=True)
    markup = types.InlineKeyboardMarkup()
    for idx, it in enumerate(items.data): markup.add(types.InlineKeyboardButton(f"Выдать: {it['name']}", callback_data=f"giveitem_{idx}"))
    bot.send_message(call.message.chat.id, "Какой предмет выдать?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('giveitem_') and call.from_user.id == MASTER_TG_ID)
def master_give_choose_player(call):
    idx = int(call.data.split('_')[1])
    items = supabase.table('quest_items').select('*').execute().data
    all_players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"giveplayer_{idx}_{p['user_id']}"))
    bot.send_message(call.message.chat.id, "Кому выдать?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('giveplayer_') and call.from_user.id == MASTER_TG_ID)
def master_give_do(call):
    parts = call.data.split('_')
    idx, user_id = int(parts[1]), parts[2]
    items = supabase.table('quest_items').select('*').execute().data
    if idx < len(items):
        supabase.table('quest_inventory').insert({'user_id': user_id, 'item_id': items[idx]['id']}).execute()
        bot.answer_callback_query(call.id, "Предмет выдан!")
        bot.send_message(call.message.chat.id, "Предмет добавлен в инвентарь.")

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_avatar' and call.from_user.id == MASTER_TG_ID)
def master_avatar_start(call):
    bot.send_message(call.message.chat.id, "Отправь мне картинку (фото) для персонажа.")
    bot.register_next_step_handler(call.message, master_avatar_get_photo)

def master_avatar_get_photo(message):
    if not message.photo: return bot.send_message(message.chat.id, "Это не фото.")
    file_id = message.photo[-1].file_id
    temp_avatars[message.chat.id] = file_id
    
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): 
        markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"setav_{idx}"))
    bot.send_message(message.chat.id, "Кому установить этот аватар?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('setav_') and call.from_user.id == MASTER_TG_ID)
def master_avatar_save(call):
    idx = int(call.data.split('_')[1])
    file_id = temp_avatars.get(call.message.chat.id)
    if not file_id: return bot.answer_callback_query(call.id, "Ошибка: фото не найдено.", show_alert=True)
    
    players = supabase.table('quest_players').select('user_id').execute()
    if idx >= len(players.data): return bot.answer_callback_query(call.id, "Ошибка.")
    target_id = players.data[idx]['user_id']
    
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
        eq = "✅ (надет)" if item['is_equipped'] else ""
        text += f"▪️ {it['name']} {eq}\n"
        if not item['is_equipped']: markup.add(types.InlineKeyboardButton(f"Надеть {it['name']}", callback_data=f"equip_{item['id']}"))
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('equip_'))
def equip_item(call):
    inv_id = call.data.split('_')[1]
    supabase.table('quest_inventory').update({'is_equipped': True}).eq('id', inv_id).execute()
    bot.answer_callback_query(call.id, "Предмет надет!")
    bot.send_message(call.message.chat.id, "Предмет надет.")

# --- МИССИЯ ---
@bot.message_handler(func=lambda message: message.text == '📜 Миссия')
def mission(message):
    user_id, player = get_or_create_player(message.from_user)
    bot.send_message(message.chat.id, f"📜 *Миссия:*\n\n{player['mission'] or 'Мастер пока не выдал миссию.'}", parse_mode='Markdown')

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
