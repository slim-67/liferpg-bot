import asyncio
import logging
import random
from datetime import datetime, time, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
import os

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUR_USER_ID = 1484297802  # ← ТВОЙ ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== БАЗА ДАННЫХ ==========
async def init_db():
    async with aiosqlite.connect("game_bot.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                hp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                bronze INTEGER DEFAULT 0,
                silver INTEGER DEFAULT 0,
                gold INTEGER DEFAULT 0,
                total_tasks INTEGER DEFAULT 0,
                last_daily TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                difficulty TEXT,
                completed BOOLEAN DEFAULT 0,
                date TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS skills (
                user_id INTEGER,
                skill_name TEXT,
                PRIMARY KEY (user_id, skill_name)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                user_id INTEGER,
                achievement_name TEXT,
                achieved_date TEXT,
                PRIMARY KEY (user_id, achievement_name)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS daily_quests (
                user_id INTEGER,
                quest_text TEXT,
                completed BOOLEAN DEFAULT 0,
                date TEXT,
                reward_hp INTEGER,
                reward_bronze INTEGER,
                reward_silver INTEGER,
                reward_gold INTEGER
            )
        ''')
        await db.commit()

# ========== КНОПКИ ==========
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Игра"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="📋 Квесты"), KeyboardButton(text="🏆 Достижения")],
            [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🤖 AI Помощник")]
        ],
        resize_keyboard=True
    )

def game_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить цель"), KeyboardButton(text="📋 Мои цели")],
            [KeyboardButton(text="✅ Выполнить цель"), KeyboardButton(text="◀ Назад")]
        ],
        resize_keyboard=True
    )

# ========== AI ПОМОЩНИК ==========
async def get_ai_advice(user_id):
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT hp, level, total_tasks FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
    if not user:
        return "🌟 Начни игру! Добавь первую цель."
    hp, level, total_tasks = user
    advices = [
        "💪 Маленькие шаги каждый день приводят к большим результатам!",
        "🎯 Разбей большую цель на маленькие задачи — так легче начать.",
        "🌟 Каждая выполненная цель делает тебя сильнее!",
        "📚 Учись новому каждый день — это прокачивает мозг.",
        f"🏆 Ты уже выполнил {total_tasks} задач! Так держать!",
        "⚡ Самое сложное — начать. Сделай первый шаг прямо сейчас!",
        "🎮 Отдых тоже важен. Не забывай про перерывы.",
        "🌈 Верь в себя — у тебя всё получится!"
    ]
    return random.choice(advices)# ========== ДОСТИЖЕНИЯ ==========
async def check_achievements(user_id):
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT hp, level, total_tasks FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            return []
        hp, level, total_tasks = user
        achievements_to_check = [
            ("💪 Новичок", "Выполнить первую задачу", total_tasks >= 1, 50, 5, 0, 0),
            ("🔥 Труженик", "Выполнить 10 задач", total_tasks >= 10, 100, 10, 5, 0),
            ("🏆 Мастер", "Выполнить 50 задач", total_tasks >= 50, 300, 20, 10, 5),
            ("⭐ Легенда", "Выполнить 100 задач", total_tasks >= 100, 500, 50, 25, 10),
            ("📈 Уровень 5", "Достичь 5 уровня", level >= 5, 100, 10, 5, 1),
            ("📈 Уровень 10", "Достичь 10 уровня", level >= 10, 200, 20, 10, 3),
            ("❤️ 1000 HP", "Накопить 1000 опыта", hp >= 1000, 300, 30, 15, 5),
        ]
        new_achievements = []
        for name, desc, condition, hp_r, b_r, s_r, g_r in achievements_to_check:
            if condition:
                cursor = await db.execute("SELECT * FROM achievements WHERE user_id = ? AND achievement_name = ?", (user_id, name))
                existing = await cursor.fetchone()
                if not existing:
                    await db.execute("INSERT INTO achievements (user_id, achievement_name, achieved_date) VALUES (?, ?, ?)", (user_id, name, datetime.now().isoformat()))
                    await db.execute("UPDATE users SET hp = hp + ?, bronze = bronze + ?, silver = silver + ?, gold = gold + ? WHERE user_id = ?", (hp_r, b_r, s_r, g_r, user_id))
                    new_achievements.append((name, desc, hp_r, b_r, s_r, g_r))
        await db.commit()
        return new_achievements

# ========== ЕЖЕДНЕВНЫЕ КВЕСТЫ ==========
async def generate_daily_quests(user_id):
    today = datetime.now().date().isoformat()
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT * FROM daily_quests WHERE user_id = ? AND date = ?", (user_id, today))
        existing = await cursor.fetchall()
        if not existing:
            quests = [
                ("📚 Прочитать 10 страниц книги", 20, 2, 1, 0),
                ("🏃 Сделать зарядку", 15, 1, 1, 0),
                ("💧 Выпить 2 литра воды", 10, 3, 0, 0),
                ("🧠 Выучить 5 новых слов", 25, 0, 2, 1),
                ("🧹 Убраться в комнате", 30, 2, 2, 0),
                ("📝 Написать планы на завтра", 15, 2, 1, 0),
                ("🎨 Позаниматься творчеством", 25, 1, 2, 1),
                ("🧘 Помедитировать 10 минут", 20, 2, 2, 0),
            ]
            selected = random.sample(quests, 3)
            for quest_text, hp, b, s, g in selected:
                await db.execute("INSERT INTO daily_quests (user_id, quest_text, date, reward_hp, reward_bronze, reward_silver, reward_gold) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, quest_text, today, hp, b, s, g))
            await db.commit()

async def get_daily_quests(user_id):
    today = datetime.now().date().isoformat()
    await generate_daily_quests(user_id)
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT quest_text, completed, reward_hp, reward_bronze, reward_silver, reward_gold FROM daily_quests WHERE user_id = ? AND date = ?", (user_id, today))
        return await cursor.fetchall()

async def complete_daily_quest(user_id, quest_index):
    today = datetime.now().date().isoformat()
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT rowid, quest_text, completed, reward_hp, reward_bronze, reward_silver, reward_gold FROM daily_quests WHERE user_id = ? AND date = ?", (user_id, today))
        quests = await cursor.fetchall()
        if 0 <= quest_index < len(quests) and not quests[quest_index][2]:
            quest = quests[quest_index]
            await db.execute("UPDATE daily_quests SET completed = 1 WHERE rowid = ?", (quest[0],))
            await db.execute("UPDATE users SET hp = hp + ?, bronze = bronze + ?, silver = silver + ?, gold = gold + ? WHERE user_id = ?", (quest[3], quest[4], quest[5], quest[6], user_id))
            await db.commit()
            return quest[3], quest[4], quest[5], quest[6]
    return None

# ========== СТАРТ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("game_bot.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
    await message.answer("🌟 Добро пожаловать в **LifeRPG**!\n\nПреврати свою жизнь в игру!", parse_mode="Markdown", reply_markup=main_keyboard())# ========== ПРОФИЛЬ ==========
@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT hp, level, bronze, silver, gold, total_tasks FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        cursor = await db.execute("SELECT skill_name FROM skills WHERE user_id = ?", (user_id,))
        skills = await cursor.fetchall()
        cursor = await db.execute("SELECT achievement_name FROM achievements WHERE user_id = ?", (user_id,))
        achievements = await cursor.fetchall()
    if user:
        hp, level, bronze, silver, gold, total_tasks = user
        skills_list = ", ".join([s[0] for s in skills]) if skills else "Нет"
        achievements_count = len(achievements)
        await message.answer(
            f"👤 **Твой профиль**\n\n❤️ HP: {hp}\n📊 Уровень: {level}\n🎯 Выполнено задач: {total_tasks}\n🏆 Достижений: {achievements_count}\n\n🪙 Монеты:\n🟤 Бронза: {bronze}\n⚪ Серебро: {silver}\n🟡 Золото: {gold}\n\n🧠 Навыки: {skills_list}",
            parse_mode="Markdown", reply_markup=main_keyboard())

# ========== ИГРА ==========
@dp.message(F.text == "🎮 Игра")
async def game_menu(message: types.Message):
    await message.answer("🎮 Меню игры", reply_markup=game_keyboard())

@dp.message(F.text == "◀ Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_keyboard())

@dp.message(F.text == "➕ Добавить цель")
async def add_goal_prompt(message: types.Message):
    await message.answer("✍ Напиши цель в формате:\nНазвание | сложность\n\nСложность: 1 (легко), 2 (средне), 3 (сложно)")

@dp.message(F.text == "📋 Мои цели")
async def show_goals(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT id, title, difficulty FROM tasks WHERE user_id = ? AND completed = 0", (user_id,))
        tasks = await cursor.fetchall()
    if not tasks:
        await message.answer("📭 У тебя нет активных целей")
        return
    text = "📋 **Твои цели:**\n\n"
    for i, (task_id, title, diff) in enumerate(tasks):
        emoji = "🟤" if diff == "1" else "⚪" if diff == "2" else "🟡"
        text += f"{i+1}. {emoji} {title}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "✅ Выполнить цель")
async def complete_goal_prompt(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT id, title, difficulty FROM tasks WHERE user_id = ? AND completed = 0", (user_id,))
        tasks = await cursor.fetchall()
    if not tasks:
        await message.answer("📭 Нет целей для выполнения")
        return
    buttons = []
    for task_id, title, diff in tasks:
        emoji = "🟤" if diff == "1" else "⚪" if diff == "2" else "🟡"
        buttons.append([InlineKeyboardButton(text=f"{emoji} {title}", callback_data=f"complete_{task_id}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("✅ Какую цель выполнил?", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("complete_"))
async def complete_task(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT difficulty FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        task = await cursor.fetchone()
        if task:
            diff = int(task[0])
            if diff == 1:
                hp, b, s, g = 10, 2, 0, 0
            elif diff == 2:
                hp, b, s, g = 20, 0, 2, 0
            else:
                hp, b, s, g = 30, 0, 0, 1
            await db.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            await db.execute("UPDATE users SET hp = hp + ?, bronze = bronze + ?, silver = silver + ?, gold = gold + ?, total_tasks = total_tasks + 1 WHERE user_id = ?", (hp, b, s, g, user_id))
            await db.commit()
            await callback.answer("✅ Цель выполнена!")
            await callback.message.edit_text(f"🎉 Ты получил:\n❤️ +{hp} HP\n🟤 +{b} бронзы\n⚪ +{s} серебра\n🟡 +{g} золота")
            new_achievements = await check_achievements(user_id)
            if new_achievements:
                text = "🏆 **Новые достижения!**\n\n"
                for name, desc, hp_r, b_r, s_r, g_r in new_achievements:
                    text += f"✨ {name}: {desc}\nНаграда: +{hp_r} HP, +{b_r}🟤 +{s_r}⚪ +{g_r}🟡\n\n"
                await callback.message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📋 Квесты")
async def show_quests(message: types.Message):
    user_id = message.from_user.id
    quests = await get_daily_quests(user_id)
    if not quests:
        await message.answer("📋 Сегодня нет квестов")
        return
    text = "📋 **Ежедневные квесты:**\n\n"
    buttons = []
    for i, (quest_text, completed, hp, b, s, g) in enumerate(quests):
        status = "✅" if completed else "❌"
        text += f"{i+1}. {quest_text} {status}\nНаграда: +{hp}❤️ +{b}🟤 +{s}⚪ +{g}🟡\n\n"
        if not completed:
            buttons.append([InlineKeyboardButton(text=f"✅ Квест {i+1}", callback_data=f"quest_{i}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("quest_"))
async def complete_quest(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    quest_index = int(callback.data.split("_")[1])
    result = await complete_daily_quest(user_id, quest_index)
    if result:
        hp, b, s, g = result
        await callback.answer("✅ Квест выполнен!")
        await callback.message.edit_text(f"🎉 Квест выполнен!\nНаграда: +{hp}❤️ +{b}🟤 +{s}⚪ +{g}🟡")
        new_achievements = await check_achievements(user_id)
        if new_achievements:
            text = "🏆 **Новые достижения!**\n\n"
            for name, desc, hp_r, b_r, s_r, g_r in new_achievements:
                text += f"✨ {name}: {desc}\nНаграда: +{hp_r} HP, +{b_r}🟤 +{s_r}⚪ +{g_r}🟡\n\n"
            await callback.message.answer(text, parse_mode="Markdown")
    else:
        await callback.answer("❌ Квест уже выполнен или не найден")

@dp.message(F.text == "🏆 Достижения")
async def show_achievements(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT achievement_name, achieved_date FROM achievements WHERE user_id = ?", (user_id,))
        achievements = await cursor.fetchall()
    if not achievements:
        await message.answer("🏆 У тебя пока нет достижений. Выполняй цели и получай их!")
        return
    text = "🏆 **Твои достижения:**\n\n"
    for name, date in achievements:
        date_obj = datetime.fromisoformat(date)
        text += f"✨ {name} — {date_obj.strftime('%d.%m.%Y')}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🤖 AI Помощник")
async def ai_helper(message: types.Message):
    user_id = message.from_user.id
    advice = await get_ai_advice(user_id)
    await message.answer(f"🤖 **AI Помощник:**\n\n{advice}", parse_mode="Markdown")

@dp.message(F.text == "🛒 Магазин")
async def shop(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Логика (50🟤 30⚪ 10🟡)", callback_data="buy_logic")],
        [InlineKeyboardButton(text="🧠 Память (30🟤 20⚪ 5🟡)", callback_data="buy_memory")],
        [InlineKeyboardButton(text="✨ Креативность (20🟤 10⚪ 15🟡)", callback_data="buy_creativity")]
    ])
    await message.answer(
        "🛒 **Магазин навыков**\n\n🔮 Логика — 50🟤 30⚪ 10🟡\n🧠 Память — 30🟤 20⚪ 5🟡\n✨ Креативность — 20🟤 10⚪ 15🟡",
        parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_skill(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    skills = {
        "logic": ("🔮 Логика", 50, 30, 10),
        "memory": ("🧠 Память", 30, 20, 5),
        "creativity": ("✨ Креативность", 20, 10, 15)
    }
    skill_key = callback.data.split("_")[1]
    skill_name, cost_b, cost_s, cost_g = skills[skill_key]
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT bronze, silver, gold FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        if user and user[0] >= cost_b and user[1] >= cost_s and user[2] >= cost_g:
            await db.execute("UPDATE users SET bronze = bronze - ?, silver = silver - ?, gold = gold - ? WHERE user_id = ?", (cost_b, cost_s, cost_g, user_id))
            await db.execute("INSERT OR IGNORE INTO skills (user_id, skill_name) VALUES (?, ?)", (user_id, skill_name))
            await db.commit()
            await callback.answer(f"✅ Навык {skill_name} куплен!")
            await callback.message.edit_text(f"🎉 Ты купил навык {skill_name}!")
        else:
            await callback.answer("❌ Недостаточно монет!")

@dp.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if "|" in message.text:
        try:
            title, difficulty = message.text.split("|")
            difficulty = int(difficulty.strip())
            title = title.strip()
            if difficulty not in [1, 2, 3]:
                await message.answer("❌ Сложность должна быть 1, 2 или 3")
                return
            async with aiosqlite.connect("game_bot.db") as db:
                await db.execute("INSERT INTO tasks (user_id, title, difficulty) VALUES (?, ?, ?)", (user_id, title, difficulty))
                await db.commit()
            diff_emoji = "🟤" if difficulty == 1 else "⚪" if difficulty == 2 else "🟡"
            await message.answer(f"✅ Цель добавлена: {diff_emoji} {title}")
        except ValueError:
            await message.answer("❌ Ошибка формата. Используй: Название | сложность (1, 2 или 3)")
    else:
        await message.answer("Используй кнопки для навигации", reply_markup=main_keyboard())

# ========== УВЕДОМЛЕНИЯ ПО РАСПИСАНИЮ ==========
async def send_startup_notification():
    await asyncio.sleep(5)
    await bot.send_message(YOUR_USER_ID, "🔔 Бот запущен и готов к работе!")

async def scheduled_notifications():
    while True:
        now = datetime.now().time()
        week_day = datetime.now().weekday()
        if now.hour == 7 and now.minute == 0:
            await bot.send_message(YOUR_USER_ID, "🌅 Доброе утро!\nНе бери телефон первые 10 минут.\nТы справишься сегодня 💪")
            await asyncio.sleep(60)
        if now.hour == 15 and now.minute == 30 and week_day < 4:
            await bot.send_message(YOUR_USER_ID, "📚 Время делать домашку! Убери телефон.")
        if now.hour == 17 and now.minute == 30 and week_day < 4:
            await bot.send_message(YOUR_USER_ID, "💻 Время программировать! 30 минут кода.")
        if now.hour == 19 and now.minute == 0:
            await bot.send_message(YOUR_USER_ID, "🎮 Отдыхай! Ты сегодня молодец.")
        if now.hour == 16 and now.minute == 0 and week_day == 4:
            await bot.send_message(YOUR_USER_ID, "🧠 Через 30 минут репетитор! Не опоздай.")
        if now.hour == 11 and now.minute == 0 and week_day >= 5:
            await bot.send_message(YOUR_USER_ID, "🌿 Выходной, но час физики/математики не помешает.")
        await asyncio.sleep(60)
@dp.message(Command("test_notify"))
async def test_notify(message: types.Message):
    await message.answer("🔔 Тестовое уведомление (команда)")
# ========== ЗАПУСК ==========
async def main():
    await init_db()
    asyncio.create_task(scheduled_notifications())
    asyncio.create_task(send_startup_notification())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
