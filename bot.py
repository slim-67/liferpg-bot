import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import aiosqlite

# Токен бота (вставьте свой)
BOT_TOKEN = "8687517789:AAF6BKOzgsrX2fG_WgqD7zr1BTsZk18lAiE"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния для добавления целей
class DailyStates(StatesGroup):
    waiting_for_count = State()
    waiting_for_tasks = State()

# ----- Работа с базой данных -----
async def init_db():
    async with aiosqlite.connect("game_bot.db") as db:
        # Таблица пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                hp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                bronze INTEGER DEFAULT 0,
                silver INTEGER DEFAULT 0,
                gold INTEGER DEFAULT 0
            )
        ''')
        # Таблица задач
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                difficulty TEXT,
                completed BOOLEAN DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        # Таблица скиллов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS skills (
                user_id INTEGER,
                skill_name TEXT,
                PRIMARY KEY (user_id, skill_name),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            return (user_id, 0, 1, 0, 0, 0)  # hp, level, bronze, silver, gold
        return user

async def update_user_hp_and_coins(user_id: int, hp_add: int, bronze_add: int, silver_add: int, gold_add: int):
    async with aiosqlite.connect("game_bot.db") as db:
        await db.execute(
            "UPDATE users SET hp = hp + ?, bronze = bronze + ?, silver = silver + ?, gold = gold + ?, "
            "level = (hp + ?) // 100 + 1 WHERE user_id = ?",
            (hp_add, bronze_add, silver_add, gold_add, hp_add, user_id)
        )
        await db.commit()

async def add_task(user_id: int, title: str, difficulty: str):
    async with aiosqlite.connect("game_bot.db") as db:
        await db.execute(
            "INSERT INTO tasks (user_id, title, difficulty) VALUES (?, ?, ?)",
            (user_id, title, difficulty)
        )
        await db.commit()

async def get_active_tasks(user_id: int):
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute(
            "SELECT id, title, difficulty FROM tasks WHERE user_id = ? AND completed = 0",
            (user_id,)
        )
        return await cursor.fetchall()

async def complete_task(task_id: int):
    async with aiosqlite.connect("game_bot.db") as db:
        # Получаем информацию о задании
        cursor = await db.execute("SELECT user_id, difficulty FROM tasks WHERE id = ?", (task_id,))
        task = await cursor.fetchone()
        if not task:
            return None
        user_id, difficulty = task
        # Помечаем как выполненное
        await db.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
        await db.commit()
        # Начисляем награду
        if difficulty == "bronze":
            hp, b, s, g = 10, 1, 0, 0
        elif difficulty == "silver":
            hp, b, s, g = 20, 0, 1, 0
        elif difficulty == "gold":
            hp, b, s, g = 30, 0, 0, 1
        else:
            hp, b, s, g = 0, 0, 0, 0
        await update_user_hp_and_coins(user_id, hp, b, s, g)
        return user_id, hp, b, s, g

async def get_user_skills(user_id: int):
    async with aiosqlite.connect("game_bot.db") as db:
        cursor = await db.execute("SELECT skill_name FROM skills WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def buy_skill(user_id: int, skill_name: str, cost_bronze: int, cost_silver: int, cost_gold: int):
    async with aiosqlite.connect("game_bot.db") as db:
        # Проверяем текущие монеты
        cursor = await db.execute(
            "SELECT bronze, silver, gold FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        bronze, silver, gold = row
        if bronze < cost_bronze or silver < cost_silver or gold < cost_gold:
            return False
        # Списываем монеты
        await db.execute(
            "UPDATE users SET bronze = bronze - ?, silver = silver - ?, gold = gold - ? WHERE user_id = ?",
            (cost_bronze, cost_silver, cost_gold, user_id)
        )
        # Добавляем скилл
        await db.execute(
            "INSERT INTO skills (user_id, skill_name) VALUES (?, ?)",
            (user_id, skill_name)
        )
        await db.commit()
        return True

# ----- Клавиатуры -----
def difficulty_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🟤 Бронзовая", callback_data="diff_bronze")],
        [InlineKeyboardButton(text="⚪ Серебряная", callback_data="diff_silver")],
        [InlineKeyboardButton(text="🟡 Золотая", callback_data="diff_gold")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def tasks_keyboard(tasks):
    buttons = []
    for task_id, title, diff in tasks:
        emoji = "🟤" if diff == "bronze" else "⚪" if diff == "silver" else "🟡"
        buttons.append([InlineKeyboardButton(text=f"{emoji} {title}", callback_data=f"complete_{task_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def shop_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🔮 Логика (50б 30с 10з)", callback_data="buy_logic")],
        [InlineKeyboardButton(text="🧠 Память (30б 20с 5з)", callback_data="buy_memory")],
        [InlineKeyboardButton(text="✨ Креативность (20б 10с 15з)", callback_data="buy_creativity")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ----- Хендлеры -----
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await get_user(user_id)  # создаст запись, если нет
    await message.answer(
        "🌟 Добро пожаловать в **LifeGame**!\n\n"
        "Преврати свою жизнь в увлекательную RPG!\n"
        "Ставь цели, получай опыт и монеты, покупай скиллы и становись лучше.\n\n"
        "Команды:\n"
        "/profile — твой профиль\n"
        "/daily — добавить цели на день\n"
        "/tasks — текущие задачи\n"
        "/shop — магазин скиллов\n"
        "/inventory — твои скиллы\n"
        "/help — помощь",
        parse_mode="Markdown"
    )

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    _, hp, level, bronze, silver, gold = user
    await message.answer(
        f"👤 **Твой профиль**\n\n"
        f"❤️ HP: {hp}\n"
        f"📊 Уровень: {level}\n\n"
        f"🪙 Монеты:\n"
        f"🟤 Бронза: {bronze}\n"
        f"⚪ Серебро: {silver}\n"
        f"🟡 Золото: {gold}",
        parse_mode="Markdown"
    )

@dp.message(Command("daily"))
async def cmd_daily(message: types.Message, state: FSMContext):
    await message.answer("Сколько целей ты хочешь добавить сегодня? (введи число)")
    await state.set_state(DailyStates.waiting_for_count)

@dp.message(DailyStates.waiting_for_count, F.text.isdigit())
async def process_count(message: types.Message, state: FSMContext):
    count = int(message.text)
    if count <= 0:
        await message.answer("Число должно быть положительным. Попробуй ещё раз.")
        return
    await state.update_data(task_count=count, tasks=[], current_task=0)
    await message.answer(
        f"Хорошо, нужно добавить {count} целей.\n"
        "Введи название первой цели:"
    )
    await state.set_state(DailyStates.waiting_for_tasks)

@dp.message(DailyStates.waiting_for_tasks, F.text)
async def process_task_title(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tasks = data.get("tasks", [])
    current = data.get("current_task", 0)
    tasks.append({"title": message.text, "difficulty": None})
    await state.update_data(tasks=tasks, current_task=current+1)
    # Спрашиваем сложность для этой цели
    await message.answer(
        f"Цель {current+1}: «{message.text}»\nВыбери сложность:",
        reply_markup=difficulty_keyboard()
    )
    # Переходим в режим ожидания нажатия кнопки, но состояние остаётся waiting_for_tasks
    # Мы просто будем обрабатывать callback

@dp.callback_query(StateFilter(DailyStates.waiting_for_tasks), F.data.startswith("diff_"))
async def process_difficulty(callback: types.CallbackQuery, state: FSMContext):
    diff = callback.data.split("_")[1]  # bronze, silver, gold
    data = await state.get_data()
    tasks = data["tasks"]
    current = data["current_task"]
    # Устанавливаем сложность для последней добавленной задачи
    tasks[-1]["difficulty"] = diff
    await state.update_data(tasks=tasks)
    await callback.answer()
    if current >= data["task_count"]:
        # Все цели добавлены
        user_id = callback.from_user.id
        for task in tasks:
            await add_task(user_id, task["title"], task["difficulty"])
        await state.clear()
        await callback.message.edit_text(
            f"✅ Все {data['task_count']} целей сохранены!\n"
            "Можешь посмотреть их в /tasks и отмечать выполнение."
        )
    else:
        # Просим следующую цель
        await callback.message.edit_text(
            f"Введи название цели №{current+1}:"
        )

@dp.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    user_id = message.from_user.id
    tasks = await get_active_tasks(user_id)
    if not tasks:
        await message.answer("У тебя нет активных задач. Добавь через /daily")
        return
    await message.answer(
        "📋 **Твои текущие задачи**\n"
        "Нажми на задачу, чтобы отметить её выполненной:",
        reply_markup=tasks_keyboard(tasks),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("complete_"))
async def complete_task_callback(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    result = await complete_task(task_id)
    if result is None:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    user_id, hp, b, s, g = result
    await callback.answer("Задача выполнена! 🎉", show_alert=False)
    # Обновляем клавиатуру (убираем выполненную задачу)
    tasks = await get_active_tasks(user_id)
    if tasks:
        await callback.message.edit_reply_markup(reply_markup=tasks_keyboard(tasks))
    else:
        await callback.message.edit_text("Все задачи выполнены! Молодец!")
    # Отправляем уведомление о награде
    await callback.bot.send_message(
        user_id,
        f"🏅 Ты получил:\n"
        f"❤️ +{hp} HP\n"
        f"🟤 +{b} бронзы\n⚪ +{s} серебра\n🟡 +{g} золота"
    )

@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    await message.answer(
        "🛒 **Магазин скиллов**\n\n"
        "Купи способность и прокачай себя!\n\n"
        "🔮 Логика — 50🟤 30⚪ 10🟡\n"
        "🧠 Память — 30🟤 20⚪ 5🟡\n"
        "✨ Креативность — 20🟤 10⚪ 15🟡\n\n"
        "Нажми на кнопку, чтобы купить:",
        reply_markup=shop_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    skill_map = {
        "logic": ("Логика", 50, 30, 10),
        "memory": ("Память", 30, 20, 5),
        "creativity": ("Креативность", 20, 10, 15)
    }
    key = callback.data.split("_")[1]
    if key not in skill_map:
        await callback.answer("Неизвестный скилл")
        return
    skill_name, cost_b, cost_s, cost_g = skill_map[key]
    user_id = callback.from_user.id
    success = await buy_skill(user_id, skill_name, cost_b, cost_s, cost_g)
    if success:
        await callback.answer(f"✅ Ты купил скилл «{skill_name}»!", show_alert=True)
    else:
        await callback.answer("❌ Недостаточно монет!", show_alert=True)
    await callback.message.delete()  # убираем магазин, чтобы не нажимали повторно

@dp.message(Command("inventory"))
async def cmd_inventory(message: types.Message):
    user_id = message.from_user.id
    skills = await get_user_skills(user_id)
    if not skills:
        await message.answer("У тебя пока нет купленных скиллов. Загляни в /shop")
        return
    skills_list = "\n".join([f"• {s}" for s in skills])
    await message.answer(f"📦 **Твои скиллы:**\n{skills_list}", parse_mode="Markdown")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🔍 **Справка по командам**\n\n"
        "/start — начало игры\n"
        "/profile — твой профиль\n"
        "/daily — добавить цели на день\n"
        "/tasks — посмотреть текущие задачи\n"
        "/complete — отметить выполнение (через кнопки)\n"
        "/shop — магазин скиллов\n"
        "/inventory — твои скиллы\n"
        "/help — эта справка\n\n"
        "🎯 Как играть:\n"
        "1. Каждый день ставь цели через /daily\n"
        "2. Выполняй их и получай опыт и монеты\n"
        "3. Повышай уровень и покупай скиллы\n"
        "4. Становись лучше!",
        parse_mode="Markdown"
    )

# ----- Запуск бота -----
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())