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
    res = supabase.table('users').select('*').eq('telegram_id', tg_id).execute()
    if not res.data:
        new_id = str(uuid.uuid4())
        supabase.table('users').insert({'id': new_id, 'name': name, 'telegram_id': tg_id}).execute()
        user_id = new_id
    else:
        user_id = res.data[0]['id']
    
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
    damage = max(0, atk_str - effective_armor) # Убрали минимальный урон
    
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

# (Функции Миссий и Фракций остаются без изменений, вставляем их сюда)
# ... [вставь сюда блоки МИССИИ, ФРАКЦИИ, КОЛЛЕКТИВНАЯ АТАКА из предыдущего кода] ...
# ВАЖНО: в функции execute_collective_attack тоже нужно поменять damage на max(0, ...)

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
                    net_damage = max(0, total_damage - effective_armor) # Убрали минимальный
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
                damage = max(0, total_damage - effective_armor) # Убрали минимальный
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
    # Ищем всех, кто зарегался (есть telegram_id)
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
    
    # Ищем свободных NPC (telegram_id is null)
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
        # Получаем telegram_id реального игрока
        u_res = supabase.table('users').select('telegram_id').eq('id', target_user_id).execute()
        if not u_res.data: return
        tg_id = u_res.data[0]['telegram_id']
        
        # Привязываем: обновляем telegram_id у NPC, а старого юзера удаляем
        supabase.table('users').update({'telegram_id': tg_id}).eq('id', npc_id).execute()
        supabase.table('users').delete().eq('id', target_user_id).execute()
        
        bot.edit_message_text(f"✅ Успешно привязано! Игрок теперь играет за персонажа.", call.message.chat.id, call.message.message_id)
    else:
        bot.edit_message_text("Ошибка привязки.", call.message.chat.id, call.message.message_id)

# (Остальные функции Мастера - kill, revive, give, mission, stats, avatar, log - остаются без изменений)
# (Вставь их сюда, если они не сохранились)

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
