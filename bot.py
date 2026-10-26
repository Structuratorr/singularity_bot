import telebot
from telebot import types
from supabase import create_client, Client
import uuid
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv('BOT_TOKEN', '8990623005:AAHe8v1pY-Q4QIU2rmGfGSHPM33yANbw_O4')
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://irtixigmkwbzkitzhjvf.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'sb_publishable_kTNliJzwfjPMacV1JBeLdw_C0wzbLg8')
MASTER_TG_ID = 329435071  # Твой Telegram ID

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
    markup.add(types.KeyboardButton('🤝 Союз'))
    if tg_id == MASTER_TG_ID:
        markup.add(types.KeyboardButton('👑 Мастер'))
    return markup

# --- ЛОГИКА КОЛЛЕКТИВНОЙ АТАКИ (ТАЙМЕР) ---
def execute_collective_attack(attack_id):
    atk_res = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute()
    if not atk_res.data: return 
    attack = atk_res.data[0]
    
    # Удаляем атаку из базы (чтобы таймер не сработал дважды)
    supabase.table('quest_collective_attacks').delete().eq('id', attack_id).execute()
    
    # Собираем голоса тех, кто успел нажать
    votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()
    if not votes.data: 
        supabase.table('quest_collective_votes').delete().eq('attack_id', attack_id).execute()
        return # Никто не нажал, атака отменяется
        
    voter_ids = [v['user_id'] for v in votes.data]
    attackers = supabase.table('quest_players').select('strength').in_('user_id', voter_ids).execute()
    total_damage = sum(a['strength'] for a in attackers.data)
    
    # Наносим урон
    defender = supabase.table('quest_players').select('*').eq('user_id', attack['target_id']).execute().data[0]
    new_defense = max(0, defender['defense'] - total_damage)
    new_status = 'wounded' if new_defense <= 0 else defender['status']
    
    supabase.table('quest_players').update({'defense': new_defense, 'status': new_status}).eq('user_id', attack['target_id']).execute()
    supabase.table('quest_attacks').insert({'attacker_id': voter_ids[0], 'defender_id': attack['target_id'], 'damage': total_damage}).execute()
    
    # Уведомляем тех, кто успел нажать
    for vid in voter_ids:
        u_data = supabase.table('users').select('telegram_id').eq('id', vid).execute()
        if u_data.data and u_data.data[0]['telegram_id']:
            try: bot.send_message(u_data.data[0]['telegram_id'], f"🔥 Время вышло! Коллективная атака завершена.\nСуммарный урон: {total_damage}.\nЗащита врага: {new_defense}.")
            except: pass
            
    # Чистим голоса
    supabase.table('quest_collective_votes').delete().eq('attack_id', attack_id).execute()


# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id, player = get_or_create_player(message.from_user)
    bot.send_message(message.chat.id, f"Добро пожаловать в квест, {message.from_user.first_name}!", reply_markup=get_main_keyboard(message.from_user.id))

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
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '⚔️ Напасть')
def attack_menu(message):
    user_id, player = get_or_create_player(message.from_user)
    if player['status'] != 'alive': return bot.send_message(message.chat.id, "Ты не можешь нападать.")
    all_players = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).eq('status', 'alive').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Напасть на {p['users']['name']}", callback_data=f"atk_{p['user_id']}"))
    if all_players.data: bot.send_message(message.chat.id, "Выбери цель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('atk_'))
def perform_attack(call):
    attacker_id, attacker = get_or_create_player(call.from_user)
    defender_id = call.data.split('_')[1]
    defender = supabase.table('quest_players').select('*').eq('user_id', defender_id).execute().data[0]
    damage = attacker['strength']
    new_defense = max(0, defender['defense'] - damage)
    new_status = 'wounded' if new_defense <= 0 else defender['status']
    supabase.table('quest_players').update({'defense': new_defense, 'status': new_status}).eq('user_id', defender_id).execute()
    supabase.table('quest_attacks').insert({'attacker_id': attacker_id, 'defender_id': defender_id, 'damage': damage}).execute()
    bot.answer_callback_query(call.id, "Атака проведена!")
    bot.send_message(call.message.chat.id, f"Ты напал! Урон: {damage}. Защита врага: {new_defense}.")

# --- СОЮЗЫ ---
@bot.message_handler(func=lambda message: message.text == '🤝 Союз')
def alliance_menu(message):
    user_id, _ = get_or_create_player(message.from_user)
    res = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name, leader_id)').eq('user_id', user_id).eq('status', 'accepted').execute()
    
    if res.data:
        alliance = res.data[0]['quest_alliances']
        is_leader = (alliance['leader_id'] == user_id)
        members = supabase.table('quest_alliance_members').select('users(name)').eq('alliance_id', alliance['id']).eq('status', 'accepted').execute()
        members_list = ", ".join([m['users']['name'] for m in members.data])
        
        markup = types.InlineKeyboardMarkup()
        if is_leader:
            markup.add(types.InlineKeyboardButton("Пригласить игрока", callback_data="alliance_invite"))
            markup.add(types.InlineKeyboardButton("⚔️ Коллективная атака", callback_data="alliance_col_atk"))
        text = f"🛡 *Союз: {alliance['name']}*\n\nУчастники: {members_list}"
        bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)
        return

    invites = supabase.table('quest_alliance_members').select('*, quest_alliances(id, name)').eq('user_id', user_id).eq('status', 'pending').execute()
    if invites.data:
        markup = types.InlineKeyboardMarkup()
        for inv in invites.data:
            markup.add(types.InlineKeyboardButton(f"Принять: {inv['quest_alliances']['name']}", callback_data=f"join_alliance_{inv['alliance_id']}"))
            markup.add(types.InlineKeyboardButton(f"Отклонить", callback_data=f"decline_alliance_{inv['alliance_id']}"))
        bot.send_message(message.chat.id, "У тебя есть приглашения:", reply_markup=markup)
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Создать союз", callback_data="create_alliance"))
    bot.send_message(message.chat.id, "У тебя пока нет союза.", reply_markup=markup)

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

@bot.callback_query_handler(func=lambda call: call.data == 'alliance_invite')
def alliance_invite_menu(call):
    try:
        user_id, _ = get_or_create_player(call.from_user)
        res = supabase.table('quest_alliance_members').select('alliance_id').eq('user_id', user_id).eq('status', 'accepted').execute()
        if not res.data: return bot.answer_callback_query(call.id, "Ошибка: ты не в союзе.")
        
        alliance_id = res.data[0]['alliance_id']
        all_players = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).execute()
        
        markup = types.InlineKeyboardMarkup()
        for idx, p in enumerate(all_players.data):
            # Передаем ИНДЕКС игрока вместо длинного UUID
            markup.add(types.InlineKeyboardButton(f"Пригласить {p['users']['name']}", callback_data=f"inv_{alliance_id}_{idx}"))
            
        bot.edit_message_text("Кого пригласить?", call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('inv_'))
def send_invite(call):
    try:
        parts = call.data.split('_')
        alliance_id = parts[1]
        idx = int(parts[2])
        
        user_id, _ = get_or_create_player(call.from_user)
        all_players = supabase.table('quest_players').select('user_id').neq('user_id', user_id).execute()
        
        if idx >= len(all_players.data):
            return bot.answer_callback_query(call.id, "Игрок не найден.", show_alert=True)
            
        target_user_id = all_players.data[idx]['user_id']
        
        existing = supabase.table('quest_alliance_members').select('*').eq('alliance_id', alliance_id).eq('user_id', target_user_id).execute()
        if existing.data: 
            return bot.answer_callback_query(call.id, "Уже в союзе или приглашен.", show_alert=True)
            
        supabase.table('quest_alliance_members').insert({'alliance_id': alliance_id, 'user_id': target_user_id, 'status': 'pending'}).execute()
        bot.answer_callback_query(call.id, "Приглашение отправлено!")
        bot.send_message(call.message.chat.id, "Приглашение успешно отправлено игроку.")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

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
@bot.callback_query_handler(func=lambda call: call.data == 'alliance_col_atk')
def col_atk_menu(call):
    user_id, _ = get_or_create_player(call.from_user)
    all_players = supabase.table('quest_players').select('user_id, users(name)').neq('user_id', user_id).eq('status', 'alive').execute()
    markup = types.InlineKeyboardMarkup()
    for p in all_players.data: markup.add(types.InlineKeyboardButton(f"Напасть на {p['users']['name']}", callback_data=f"colatk_target_{p['user_id']}"))
    bot.edit_message_text("Выбери цель для коллективной атаки:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('colatk_target_'))
def col_atk_init(call):
    target_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    alliance_id = supabase.table('quest_alliance_members').select('alliance_id').eq('user_id', user_id).eq('status', 'accepted').execute().data[0]['alliance_id']
    
    atk_res = supabase.table('quest_collective_attacks').insert({'alliance_id': alliance_id, 'target_id': target_id, 'initiator_id': user_id}).execute()
    attack_id = atk_res.data[0]['id']
    
    # Запускаем таймер на 60 секунд
    timer = threading.Timer(60.0, execute_collective_attack, args=[attack_id])
    timer.start()
    
    members = supabase.table('quest_alliance_members').select('user_id, users(telegram_id)').eq('alliance_id', alliance_id).eq('status', 'accepted').execute()
    for m in members.data:
        tg_id = m['users']['telegram_id']
        if tg_id:
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("Подтвердить удар", callback_data=f"vote_colatk_{attack_id}"))
                bot.send_message(tg_id, f"⚔️ Твой союз объявил атаку! У тебя есть 1 минута, чтобы нажать кнопку. Опоздавшие не наносят урон.", reply_markup=markup)
            except: pass
            
    bot.answer_callback_query(call.id, "Атака инициирована! Таймер пошел (60 сек).")
    bot.edit_message_text("Ожидаем удары (60 секунд)...", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_colatk_'))
def col_atk_vote(call):
    attack_id = call.data.split('_')[2]
    user_id, _ = get_or_create_player(call.from_user)
    
    try: 
        supabase.table('quest_collective_votes').insert({'attack_id': attack_id, 'user_id': user_id}).execute()
    except: 
        return bot.answer_callback_query(call.id, "Ты уже подтвердил.", show_alert=True)

    atk_res = supabase.table('quest_collective_attacks').select('*').eq('id', attack_id).execute()
    if not atk_res.data: return bot.answer_callback_query(call.id, "Время вышло, атака уже завершена!", show_alert=True)
    attack = atk_res.data[0]

    members = supabase.table('quest_alliance_members').select('user_id').eq('alliance_id', attack['alliance_id']).eq('status', 'accepted').execute()
    votes = supabase.table('quest_collective_votes').select('user_id').eq('attack_id', attack_id).execute()

    if len(votes.data) >= len(members.data):
        execute_collective_attack(attack_id)
        bot.edit_message_text("Ты подтвердил. Все собрались! Удар нанесен.", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Голос учтен! Ждем остальных...")
        bot.edit_message_text("Ты подтвердил. Ждем остальных...", call.message.chat.id, call.message.message_id)

# --- ПАНЕЛЬ МАСТЕРА ---
@bot.message_handler(func=lambda message: message.text == '👑 Мастер' and message.from_user.id == MASTER_TG_ID)
def master_panel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💀 Убить игрока", callback_data="master_kill"))
    markup.add(types.InlineKeyboardButton("🎁 Выдать предмет", callback_data="master_give"))
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
