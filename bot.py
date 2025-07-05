import logging
import re
import aiosqlite
from datetime import datetime
import asyncio
from aiogram.exceptions import TelegramAPIError
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from get_wb_price import get_wb_product

BOT_TOKEN = "7928665092:AAGfExLKRs1lOtsPYx0CO4WUt000tMOuw-s"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/start"), KeyboardButton(text="/track")],
        [KeyboardButton(text="/find"), KeyboardButton(text="/promo")],
        [KeyboardButton(text="/daily"), KeyboardButton(text="/my"), KeyboardButton(text="/refer")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

class TrackStates(StatesGroup):
    waiting_for_article = State()

# --- Работа с базой ---

DB_PATH = "tracked_products.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                article TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                added_at TEXT NOT NULL,
                last_notified_price REAL
            )
        """)
        await db.commit()

async def add_tracked_product(user_id: int, article: str, name: str, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO tracked_products (user_id, article, name, price, last_notified_price, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, article, name, price, price, datetime.utcnow().isoformat()))
        await db.commit()

async def get_tracked_products(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT article, name, price, added_at FROM tracked_products WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        return rows

async def get_all_tracked_products():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id, user_id, article, name, price, last_notified_price FROM tracked_products")
        rows = await cursor.fetchall()
        return rows

async def update_tracked_product_price(product_id: int, new_price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE tracked_products
            SET price = ?, last_notified_price = ?
            WHERE id = ?
        """, (new_price, new_price, product_id))
        await db.commit()

# --- Хендлеры ---

@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я помогу тебе отслеживать цены на Wildberries.\nВыбери нужную команду ниже 👇 \n\n"
        "/start — Приветствие, выбор маркетплейса\n"
        "/track — Добавить товар на слежение\n"
        "/find — Поиск товаров по ключевым словам\n"
        "/promo — Получить актуальные промокоды\n"
        "/daily — Подписка на ежедневные подборки\n"
        "/my — Избранные товары\n"
        "/refer — Реферальная система\n",
        reply_markup=main_keyboard
    )

@dp.message(Command("track"))
async def track_handler(message: Message, state: FSMContext):
    await message.answer("Введите артикул товара Wildberries:")
    await state.set_state(TrackStates.waiting_for_article)

@dp.message(TrackStates.waiting_for_article)
async def process_article(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.search(r"\d{6,10}", text)
    if not match:
        await message.answer("❗ Введите корректный артикул (от 6 до 10 цифр).")
        return

    article = match.group(0)
    product = get_wb_product(article)

    if "error" in product:
        await message.answer(product["error"])
        await state.clear()
        return

    price_str = product.get("price_str", "❗ Цена недоступна.")
    name = product.get("name", "Название не найдено")

    msg = f"🛍️ <b>{name}</b>\n💰 Цена: {price_str}"

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить в отслеживание", callback_data=f"add_{article}")]
    ])

    await message.answer(msg, reply_markup=inline_kb)
    await state.clear()

@dp.callback_query(lambda c: c.data and c.data.startswith("add_"))
async def add_product_callback(callback: CallbackQuery):
    article = callback.data[4:]  # убираем 'add_'
    user_id = callback.from_user.id
    product = get_wb_product(article)

    if "error" in product:
        await callback.message.answer("Ошибка при добавлении товара.")
        await callback.answer()
        return

    price_value = product.get("price_value")
    if price_value is None:
        price_value = 0.0

    await add_tracked_product(user_id, article, product['name'], price_value)
    await callback.message.answer(f"✅ Товар <b>{product['name']}</b> добавлен в отслеживание.")
    await callback.answer()

@dp.message(Command("find"))
async def find_handler(message: Message):
    await message.answer("🔍 Команда /find пока в разработке.")

@dp.message(Command("promo"))
async def promo_handler(message: Message):
    await message.answer("🎁 Команда /promo пока в разработке.")

@dp.message(Command("daily"))
async def daily_handler(message: Message):
    await message.answer("📅 Команда /daily пока в разработке.")

@dp.message(Command("my"))
async def my_handler(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT article, name, price FROM tracked_products WHERE user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("У вас пока нет отслеживаемых товаров.")
        return

    msg_lines = ["Ваши отслеживаемые товары:"]
    for article, name, price in rows:
        msg_lines.append(f"• <b>{name}</b>\n  Артикул: {article}\n  Цена: {price}")

    msg = "\n\n".join(msg_lines)
    await message.answer(msg)

@dp.message(Command("refer"))
async def refer_handler(message: Message):
    await message.answer("👥 Команда /refer пока в разработке.")

# --- Фоновая задача для проверки изменения цен и отправки уведомлений ---

async def check_price_changes_and_notify():
    while True:
        products = await get_all_tracked_products()
        for product in products:
            product_id, user_id, article, name, old_price, last_notified_price = product

            wb_product = get_wb_product(article)  # Если асинхронная, то: await get_wb_product(article)
            if "error" in wb_product:
                continue

            new_price = wb_product.get("price_value")
            if new_price is None:
                continue

            if last_notified_price is None or abs(new_price - last_notified_price) > 0.01:
                try:
                    msg = (
                        f"📢 <b>Обновление цены!</b>\n\n"
                        f"🛍️ <b>{name}</b>\n"
                        f"Артикул: <code>{article}</code>\n\n"
                        f"💸 Старая цена: <s>{old_price} ₽</s>\n"
                        f"🆕 Новая цена: <b>{new_price} ₽</b>\n\n"
                        f"Проверь товар на Wildberries: https://www.wildberries.ru/catalog/{article}/detail.aspx"
                    )
                    await bot.send_message(user_id, msg)
                    await update_tracked_product_price(product_id, new_price)
                except TelegramAPIError as e:
                    if "bot was blocked by the user" in str(e).lower():
                        logging.info(f"Пользователь {user_id} заблокировал бота. Уведомление не отправлено.")
                    else:
                        logging.error(f"Ошибка при отправке уведомления: {e}")
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления: {e}")

            await asyncio.sleep(1)  # чтобы не перегружать Telegram API
        await asyncio.sleep(60)  # ждать 8 часов перед следующей проверкой



# --- Запуск бота ---

if __name__ == "__main__":
    import asyncio

    async def main():
        await init_db()
        # запуск задач и polling
        asyncio.create_task(check_price_changes_and_notify())
        await dp.start_polling(bot)

    asyncio.run(main())