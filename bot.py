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
        supabase.table('quest_players').insert({'user_id': user_id, 'faction': 'Нейтрал', 'hp': 100, 'max_hp': 100, 'defense': 10}).execute()
        q_res = supabase.table('quest_players').select('*').eq('user_id', user_id).execute()
    return user_id, q_res.data[0]

def get_main_keyboard(tg_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('👤 Профиль'), types.KeyboardButton('⚔️ Напасть'))
    markup.add(types.KeyboardButton('🎒 Инвентарь'), types.KeyboardButton('📜 Миссия'))
    markup.add(types.KeyboardButton('🛡 Фракции'), types.KeyboardButton('🌍 Мир'))
    if tg_id == MASTER_TG_ID:
        markup.add(types.KeyboardButton('👑 Мастер'))
    return markup

def log_event(text):
    res = supabase.table('quest_settings').select('value').eq('key', 'log_chat_id').execute()
    if res.data and res.data[0]['value']:
        try: bot.send_message(res.data[0]['value'], text, parse_mode='Markdown')
        except: pass

def get_player_stats(user_id):
    """Возвращает силу и пробитие брони с учетом экипировки"""
    p = supabase.table('quest_players').select('strength').eq('user_id', user_id).execute().data[0]
    inv = supabase.table('quest_inventory').select('*, quest_items(*)').eq('user_id', user_id).eq('is_equipped', True).execute()
    
    total_str = p['strength']
    total_pierce = 0
    for item in inv.data:
        total_str += item['quest_items']['attack_bonus']
        total_pierce += item['quest_items'].get('armor_pierce', 0)
    return total_str, total_pierce

# --- ПРОФИЛИ И МИР ---
@bot.message_handler(commands=['start'])
def start(message):
    get_or_create_player(message.from_user)
    bot.send_message(message.chat.id, f"Добро пожаловать в квест, {message.from_user.first_name}!", reply_markup=get_main_keyboard(message.from_user.id))

@bot.message_handler(func=lambda message: message.text == '👤 Профиль')
def profile(message):
    user_id, player = get_or_create_player(message.from_user)
    att_bonus, pierce = get_player_stats(user_id)
    
    status_emoji = '💀' if player['status'] == 'dead' else ('🩸' if player['status'] == 'wounded' else '🟢')
    hp_bar = f"❤️ {player['hp']}/{player['max_hp']}"
    
    text = (f"👤 *{message.from_user.first_name}*\nФракция: {player['faction']}\nСтатус: {status_emoji} {player['status']}\n\n"
            f"❤️ Здоровье: {hp_bar}\n🛡 Броня: {player['defense']}\n"
            f"⚔️ Сила: {att_bonus} (Пробой брони: {pierce})\n"
            f"💰 Талеры: {player['star_thalers']}\n\n📜 История: {player['history'] or 'Пока пусто...'}")
            
    if player.get('avatar_id'):
        try: bot.send_photo(message.chat.id, player['avatar_id'], caption=text, parse_mode='Markdown')
        except: bot.send_message(message.chat.id, text, parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '🌍 Мир')
def world_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    players = supabase.table('quest_players').select('user_id, status, faction, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for p in players.data:
        status_icon = '💀' if p['status'] == 'dead' else ('🩸' if p['status'] == 'wounded' else '🟢')
        markup.add(types.InlineKeyboardButton(f"{status_icon} {p['users']['name']} [{p['faction']}]", callback_data=f"view_{p['user_id']}"))
    bot.send_message(message.chat.id, "🌍 *Жители мира:*", parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_'))
def view_profile(call):
    target_id = call.data.split('_')[1]
    player = supabase.table('quest_players').select('*, users(name)').eq('user_id', target_id).execute().data[0]
    name = player['users']['name']
    
    status_emoji = '💀' if player['status'] == 'dead' else ('🩸' if player['status'] == 'wounded' else '🟢')
    text = (f"👤 *{name}*\nФракция: {player['faction']}\nСтатус: {status_emoji} {player['status']}\n"
            f"❤️ HP: {player['hp']}/{player['max_hp']}\n🛡 Броня: {player['defense']}\n"
            f"📜 История: {player['history'] or 'Скрыто'}")
            
    if player.get('avatar_id'):
        try: bot.send_photo(call.message.chat.id, player['avatar_id'], caption=text, parse_mode='Markdown')
        except: bot.send_message(call.message.chat.id, text)
    else:
        bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)

# --- НАПАДЕНИЯ ---
@bot.message_handler(func=lambda message: message.text == '⚔️ Напасть')
def attack_menu(message):
    user_id, player = get_or_create_player(message.from_user)
    if player['status'] != 'alive': return bot.send_message(message.chat.id, "Ты не можешь нападать.")
    
    targets = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).eq('status', 'alive').execute()
    markup = types.InlineKeyboardMarkup()
    for p in targets.data: markup.add(types.InlineKeyboardButton(f"⚔️ {p['users']['name']}", callback_data=f"atk_{p['user_id']}"))
    if targets.data: bot.send_message(message.chat.id, "Выбери цель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('atk_'))
def perform_attack(call):
    attacker_id, _ = get_or_create_player(call.from_user)
    defender_id = call.data.split('_')[1]
    
    atk_str, atk_pierce = get_player_stats(attacker_id)
    defender = supabase.table('quest_players').select('*, users(name)').eq('user_id', defender_id).execute().data[0]
    
    # Формула: (Сила - (Броня - Пробой)) = Урон
    effective_armor = max(0, defender['defense'] - atk_pierce)
    damage = max(0, atk_str - effective_armor)
    new_hp = max(0, defender['hp'] - damage)
    
    new_status = 'dead' if new_hp <= 0 else ('wounded' if new_hp < 30 else 'alive')
    
    supabase.table('quest_players').update({'hp': new_hp, 'status': new_status}).eq('user_id', defender_id).execute()
    supabase.table('quest_attacks').insert({'attacker_id': attacker_id, 'defender_id': defender_id, 'damage': damage}).execute()
    
    bot.answer_callback_query(call.id, "Атака проведена!")
    bot.send_message(call.message.chat.id, f"Ты напал на {defender['users']['name']}!\nПробито брони: {atk_pierce}\nУрон: {damage}\nОстаток HP: {new_hp}.")
    log_event(f"🩸 *{call.from_user.first_name}* атаковал *{defender['users']['name']}* на {damage} урона!")

# --- ФРАКЦИИ (Бывшие Союзы) ---
@bot.message_handler(func=lambda message: message.text == '🛡 Фракции')
def faction_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    # Получаем фракции, в которых состоит игрок
    res = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name, leader_id)').eq('user_id', user_id).eq('status', 'accepted').execute()
    
    markup = types.InlineKeyboardMarkup()
    text = "🛡 *Твои фракции:*\n\n"
    
    seen_ids = set() # Защита от дублей
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
            else:
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
    bot.send_message(call.message.chat.id, "Введи название фракции:")
    bot.register_next_step_handler(call.message, save_faction)

def save_faction(message):
    user_id, _ = get_or_create_player(message.from_user)
    a_res = supabase.table('quest_alliances').insert({'name': message.text, 'leader_id': user_id}).execute()
    supabase.table('quest_alliance_members').insert({'alliance_id': a_res.data[0]['id'], 'user_id': user_id, 'status': 'accepted'}).execute()
    # Обновляем фракцию в профиле игрока
    supabase.table('quest_players').update({'faction': message.text}).eq('user_id', user_id).execute()
    bot.send_message(message.chat.id, f"Фракция *{message.text}* создана!", parse_mode='Markdown', reply_markup=get_main_keyboard(message.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_leave_'))
def leave_faction(call):
    faction_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', user_id).execute()
    bot.answer_callback_query(call.id, "Ты покинул фракцию.")
    bot.edit_message_text("Ты вышел из фракции.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_manage_'))
def manage_faction(call):
    faction_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Пригласить", callback_data=f"fac_invite_{faction_id}"))
    markup.add(types.InlineKeyboardButton("👢 Выгнать", callback_data=f"fac_kick_menu_{faction_id}"))
    bot.edit_message_text("Управление фракцией:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_invite_'))
def faction_invite_menu(call):
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
    parts = call.data.split('_')
    faction_id, idx = parts[1], int(parts[2])
    user_id, _ = get_or_create_player(call.from_user)
    
    existing = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', faction_id).execute()
    exclude_ids = [m['user_id'] for m in existing.data]
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    targets = [p for p in players.data if p['user_id'] not in exclude_ids]
    
    if idx >= len(targets): return bot.answer_callback_query(call.id, "Не найден.", show_alert=True)
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
    bot.answer_callback_query(call.id, "Приглашение отправлено!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_kick_menu_'))
def kick_menu(call):
    faction_id = call.data.split('_')[3]
    user_id, _ = get_or_create_player(call.from_user)
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', faction_id).eq('status', 'accepted').neq('user_id', user_id).execute()
    if not members.data: return bot.answer_callback_query(call.id, "Некого выгонять.", show_alert=True)
    markup = types.InlineKeyboardMarkup()
    for idx, m in enumerate(members.data): markup.add(types.InlineKeyboardButton(f"{m['users']['name']}", callback_data=f"kick_{faction_id}_{idx}"))
    bot.edit_message_text("Кого выгнать?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('kick_'))
def do_kick(call):
    parts = call.data.split('_')
    faction_id, idx = parts[1], int(parts[2])
    user_id, _ = get_or_create_player(call.from_user)
    members = supabase.table('quest_alliance_members').select('user_id, users(name)').eq('alliance_id', faction_id).eq('status', 'accepted').neq('user_id', user_id).execute()
    if idx < len(members.data):
        target = members.data[idx]
        supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', target['user_id']).execute()
        bot.answer_callback_query(call.id, "Выгнан!")
        bot.edit_message_text(f"Игрок {target['users']['name']} исключен.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_fac_'))
def accept_invite(call):
    faction_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').update({'status': 'accepted'}).eq('alliance_id', faction_id).eq('user_id', user_id).execute()
    fac_name = supabase.table('quest_alliances').select('name').eq('id', faction_id).execute().data[0]['name']
    supabase.table('quest_players').update({'faction': fac_name}).eq('user_id', user_id).execute()
    bot.answer_callback_query(call.id, "Ты в фракции!")
    bot.edit_message_text(f"Ты вступил во фракцию *{fac_name}*!", call.message.chat.id, call.message.message_id, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('decline_fac_'))
def decline_invite(call):
    faction_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    supabase.table('quest_alliance_members').delete().eq('alliance_id', faction_id).eq('user_id', user_id).execute()
    bot.edit_message_text("Ты отклонил приглашение.", call.message.chat.id, call.message.message_id)

# --- КОЛЛЕКТИВНАЯ АТАКА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('fac_atk_'))
def col_atk_menu(call):
    faction_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup()
    factions = supabase.table('quest_alliances').select('id, name').neq('id', faction_id).execute()
    for a in factions.data: markup.add(types.InlineKeyboardButton(f"🏰 {a['name']}", callback_data=f"colatk_ally_{faction_id}_{a['id']}"))
    markup.add(types.InlineKeyboardButton("👤 Одиночный игрок", callback_data=f"colatk_solo_{faction_id}"))
    bot.edit_message_text("Выбери цель для атаки фракции:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_ally_'))
def col_atk_init_ally(call):
    parts = call.data.split('_')
    atk_fac, target_fac = parts[2], parts[3]
    user_id, _ = get_or_create_player(call.from_user)
    target_name = supabase.table('quest_alliances').select('name').eq('id', target_fac).execute().data[0]['name']
    
    atk_id = supabase.table('quest_collective_attacks').insert({'alliance_id': atk_fac, 'target_id': target_fac, 'initiator_id': user_id}).execute().data[0]['id']
    threading.Timer(60.0, execute_collective_attack, args=[atk_id, True]).start()
    
    members = supabase.table('quest_alliance_members').select('user_id, users(telegram_id)').eq('alliance_id', atk_fac).eq('status', 'accepted').execute()
    for m in members.data:
        if m['users']['telegram_id']:
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_{atk_id}"))
                bot.send_message(m['users']['telegram_id'], f"⚔️ Атака на фракцию *{target_name}*! Жми!", parse_mode='Markdown', reply_markup=markup)
            except: pass
    bot.answer_callback_query(call.id, "Атака начата!")
    bot.edit_message_text(f"Ожидаем удары по {target_name} (60 сек)...", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_solo_'))
def col_atk_init_solo(call):
    faction_id = call.data.split('_')[2]
    players = supabase.table('quest_players').select('user_id, users(name)').eq('status', 'alive').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): markup.add(types.InlineKeyboardButton(f"{p['users']['name']}", callback_data=f"colatk_target_{faction_id}_{idx}"))
    bot.edit_message_text("Выбери цель:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_target_'))
def col_atk_init_target(call):
    parts = call.data.split('_')
    faction_id, idx = parts[2], int(parts[3])
    user_id, _ = get_or_create_player(call.from_user)
    players = supabase.table('quest_players').select('user_id').eq('status', 'alive').execute()
    if idx >= len(players.data): return
    target_id = players.data[idx]['user_id']
    
    atk_id = supabase.table('quest_collective_attacks').insert({'alliance_id': faction_id, 'target_id': target_id, 'initiator_id': user_id}).execute().data[0]['id']
    threading.Timer(60.0, execute_collective_attack, args=[atk_id, False]).start()
    
    members = supabase.table('quest_alliance_members').select('user_id, users(telegram_id)').eq('alliance_id', faction_id).eq('status', 'accepted').execute()
    for m in members.data:
        if m['users']['telegram_id']:
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_{atk_id}"))
                bot.send_message(m['users']['telegram_id'], f"⚔️ Твоя фракция объявила атаку! 1 минута на подтверждение.", reply_markup=markup)
            except: pass
    bot.answer_callback_query(call.id, "Атака начата!")
    bot.edit_message_text("Ожидаем удары (60 сек)...", call.message.chat.id, call.message.message_id)

def execute_collective_attack(attack_id, is_alliance_target):
    atk = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute().data
    if not atk: return 
    attack = atk[0]
    supabase.table('quest_collective_attacks').delete().eq('id', attack_id).execute()
    
    votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()
    if not votes.data: return
        
    voter_ids = [v['user_id'] for v in votes.data]
    
    # Суммируем общую силу и пробитие атакующих
    total_damage = 0
    total_pierce = 0
    for vid in voter_ids:
        s, p = get_player_stats(vid)
        total_damage += s
        total_pierce += p
        
    if is_alliance_target:
        def_members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['target_id']).execute()
        defenders = supabase.table('quest_players').select('user_id, defense, hp, max_hp').in_('user_id', [m['user_id'] for m in def_members.data]).execute()
        total_defense = sum(d['defense'] for d in defenders.data)
        
        effective_armor = max(0, total_defense - total_pierce)
        net_damage = max(0, total_damage - effective_armor)
        dmg_per_player = math.ceil(net_damage / len(defenders.data)) if defenders.data else 0
        
        if dmg_per_player > 0:
            for d in defenders.data:
                new_hp = max(0, d['hp'] - dmg_per_player)
                new_stat = 'dead' if new_hp <= 0 else ('wounded' if new_hp < 30 else 'alive')
                supabase.table('quest_players').update({'hp': new_hp, 'status': new_stat}).eq('user_id', d['user_id']).execute()
        log_event(f"🔥 *ВОЙНА ФРАКЦИЙ!* Суммарный урон: {total_damage}. Пробито брони: {total_pierce}. Урон по HP: {dmg_per_player} каждому.")
    else:
        defender = supabase.table('quest_players').select('*').eq('user_id', attack['target_id']).execute().data[0]
        effective_armor = max(0, defender['defense'] - total_pierce)
        damage = max(0, total_damage - effective_armor)
        new_hp = max(0, defender['hp'] - damage)
        new_stat = 'dead' if new_hp <= 0 else ('wounded' if new_hp < 30 else 'alive')
        supabase.table('quest_players').update({'hp': new_hp, 'status': new_stat}).eq('user_id', attack['target_id']).execute()
        log_event(f"🔥 Коллективная атака на игрока! Урон: {damage}.")
        
    supabase.table('quest_collective_votes').delete().eq('attack_id', attack_id).execute()

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def col_atk_vote(call):
    attack_id = call.data.split('_')[1]
    user_id, _ = get_or_create_player(call.from_user)
    
    try: supabase.table('quest_collective_votes').insert({'attack_id': attack_id, 'user_id': user_id}).execute()
    except: return bot.answer_callback_query(call.id, "Уже подтвердил.", show_alert=True)

    atk = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute().data
    if not atk: return bot.answer_callback_query(call.id, "Атака завершена!", show_alert=True)
    attack = atk[0]
    members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['alliance_id']).eq('status', 'accepted').execute()
    votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()

    if len(votes.data) >= len(members.data):
        is_ally = supabase.table('quest_alliances').select('id').eq('id', attack['target_id']).execute().data
        execute_collective_attack(attack_id, bool(is_ally))
        bot.edit_message_text("Все собрались! Удар нанесен.", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Ждем остальных...")
        bot.edit_message_text("Ждем остальных...", call.message.chat.id, call.message.message_id)

# --- ПАНЕЛЬ МАСТЕРА ---
@bot.message_handler(func=lambda message: message.text == '👑 Мастер' and message.from_user.id == MASTER_TG_ID)
def master_panel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💀 Убить", callback_data="master_kill"))
    markup.add(types.InlineKeyboardButton("❤️ Воскресить всех", callback_data="master_revive_all"))
    markup.add(types.InlineKeyboardButton("🎁 Выдать предмет", callback_data="master_give"))
    markup.add(types.InlineKeyboardButton("🖼 Установить аватар", callback_data="master_set_avatar"))
    markup.add(types.InlineKeyboardButton("📜 Установить историю", callback_data="master_set_history"))
    markup.add(types.InlineKeyboardButton("⚙️ Лог-Чат", callback_data="master_set_log"))
    bot.send_message(message.chat.id, "Панель Мастера:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'master_revive_all' and call.from_user.id == MASTER_TG_ID)
def master_revive(call):
    supabase.table('quest_players').update({'status': 'alive', 'hp': 100, 'defense': 10}).neq('user_id', '').execute()
    bot.answer_callback_query(call.id, "Все воскрешены!")
    bot.send_message(call.message.chat.id, "Все игроки воскрешены с 100 HP!")

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_history' and call.from_user.id == MASTER_TG_ID)
def master_history_start(call):
    bot.send_message(call.message.chat.id, "Напиши текст истории для персонажа:")
    bot.register_next_step_handler(call.message, master_history_save)

def master_history_save(message):
    history_text = message.text
    players = supabase.table('quest_players').select('user_id, users(name)').execute()
    markup = types.InlineKeyboardMarkup()
    for idx, p in enumerate(players.data): 
        # Сохраняем текст истории во временный словарь (по индексу)
        temp_avatars[f"hist_{idx}"] = history_text
        markup.add(types.InlineKeyboardButton(f"Кому: {p['users']['name']}", callback_data=f"sethist_{idx}"))
    bot.send_message(message.chat.id, "Кому установить эту историю?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sethist_') and call.from_user.id == MASTER_TG_ID)
def master_history_apply(call):
    idx = int(call.data.split('_')[1])
    hist_text = temp_avatars.get(f"hist_{idx}")
    players = supabase.table('quest_players').select('user_id').execute()
    if idx < len(players.data) and hist_text:
        supabase.table('quest_players').update({'history': hist_text}).eq('user_id', players.data[idx]['user_id']).execute()
        bot.answer_callback_query(call.id, "История установлена!")
        bot.edit_message_text("История успешно обновлена.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_kill' and call.from_user.id == MASTER_TG_ID)
def master_kill_menu(call):
    all_players = supabase.table('quest_players').select('user_id, users(name)').neq('status', 'dead').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Убить {p['users']['name']}", callback_data=f"mkill_{p['user_id']}"))
    bot.send_message(call.message.chat.id, "Кого казнить?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('mkill_') and call.from_user.id == MASTER_TG_ID)
def master_do_kill(call):
    uid = call.data.split('_')[1]
    supabase.table('quest_players').update({'status': 'dead', 'hp': 0}).eq('user_id', uid).execute()
    bot.answer_callback_query(call.id, "Казнен!")
    bot.send_message(call.message.chat.id, "Игрок отправлен к праотцам.")

@bot.callback_query_handler(func=lambda call: call.data == 'master_give' and call.from_user.id == MASTER_TG_ID)
def master_give_menu(call):
    items = supabase.table('quest_items').select('*').execute()
    if not items.data: return bot.answer_callback_query(call.id, "Сначала создай предмет!", show_alert=True)
    markup = types.InlineKeyboardMarkup()
    for idx, it in enumerate(items.data): markup.add(types.InlineKeyboardButton(f"{it['name']}", callback_data=f"giveitem_{idx}"))
    bot.send_message(call.message.chat.id, "Какой предмет выдать?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('giveitem_') and call.from_user.id == MASTER_TG_ID)
def master_give_choose_player(call):
    idx = int(call.data.split('_')[1])
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
        bot.answer_callback_query(call.id, "Выдан!")
        bot.send_message(call.message.chat.id, "Предмет в инвентаре.")

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_avatar' and call.from_user.id == MASTER_TG_ID)
def master_avatar_start(call):
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
    idx = int(call.data.split('_')[1])
    file_id = temp_avatars.get(call.message.chat.id)
    players = supabase.table('quest_players').select('user_id').execute()
    if idx < len(players.data) and file_id:
        supabase.table('quest_players').update({'avatar_id': file_id}).eq('user_id', players.data[idx]['user_id']).execute()
        bot.answer_callback_query(call.id, "Аватар установлен!")
        bot.edit_message_text("Аватар обновлен.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'master_set_log' and call.from_user.id == MASTER_TG_ID)
def master_log_setup(call):
    bot.send_message(call.message.chat.id, "Отправь ID чата для логов.")
    bot.register_next_step_handler(call.message, master_log_save)

def master_log_save(message):
    supabase.table('quest_settings').update({'value': message.text.strip()}).eq('key', 'log_chat_id').execute()
    bot.send_message(message.chat.id, "Лог-чат настроен!")

# --- ИНВЕНТАРЬ И МИССИИ ---
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
        text += f"▪️ {it['name']} {eq}\n"
        if not item['is_equipped']: markup.add(types.InlineKeyboardButton(f"Надеть {it['name']}", callback_data=f"equip_{item['id']}"))
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('equip_'))
def equip_item(call):
    inv_id = call.data.split('_')[1]
    supabase.table('quest_inventory').update({'is_equipped': True}).eq('id', inv_id).execute()
    bot.answer_callback_query(call.id, "Надето!")
    bot.send_message(call.message.chat.id, "Предмет надет.")

@bot.message_handler(func=lambda message: message.text == '📜 Миссия')
def mission(message):
    user_id, player = get_or_create_player(message.from_user)
    bot.send_message(message.chat.id, f"📜 *Миссия:*\n\n{player['mission'] or 'Мастер пока не выдал миссию.'}", parse_mode='Markdown')

# --- ВЕБ-СЕРВЕР ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is alive")
    def do_HEAD(self): self.send_response(200); self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), DummyHandler).serve_forever()

threading.Thread(target=run_server, daemon=True).start()

print("Бот запущен...")
bot.infinity_polling()
