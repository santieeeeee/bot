import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ========== КОНФИГ ==========
BOT_TOKEN = "8790098998:AAHGmlM7MQjtJN6llZaxNNq-6GlR8_qDpUE"
ADMIN_IDS = [1065221609, 1404008993]  # список ID старост (можно несколько)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== БД ==========
def init_db():
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS absences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            date_start TEXT,
            date_end TEXT,
            pairs TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_absence(user_id, username, full_name, date_start, date_end, pairs, reason):
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO absences (user_id, username, full_name, date_start, date_end, pairs, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, full_name, date_start, date_end, pairs, reason))
    conn.commit()
    conn.close()
    return cur.lastrowid

def get_absence_by_id(abs_id):
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('SELECT * FROM absences WHERE id = ?', (abs_id,))
    row = cur.fetchone()
    conn.close()
    return row

def update_absence(abs_id, date_start, date_end, pairs, reason):
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('''
        UPDATE absences
        SET date_start = ?, date_end = ?, pairs = ?, reason = ?
        WHERE id = ?
    ''', (date_start, date_end, pairs, reason, abs_id))
    conn.commit()
    conn.close()

def delete_absence(abs_id):
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM absences WHERE id = ?', (abs_id,))
    conn.commit()
    conn.close()

def set_absence_status(abs_id, status):
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('UPDATE absences SET status = ? WHERE id = ?', (status, abs_id))
    conn.commit()
    conn.close()

def get_user_absences(user_id):
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, date_start, date_end, pairs, reason, status, created_at
        FROM absences WHERE user_id = ? ORDER BY created_at DESC
    ''', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_all_absences():
    conn = sqlite3.connect('absences.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, user_id, username, full_name, date_start, date_end, pairs, reason, status, created_at
        FROM absences ORDER BY created_at DESC
    ''')
    rows = cur.fetchall()
    conn.close()
    return rows

# ========== FSM ==========
class AbsenceForm(StatesGroup):
    choose_type = State()
    single_date = State()
    period_start = State()
    period_end = State()
    pairs = State()
    reason = State()
    # для редактирования
    edit_date = State()
    edit_pairs = State()
    edit_reason = State()

# ========== КЛАВИАТУРЫ ==========
def get_type_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Одна дата 📅"))
    kb.add(KeyboardButton(text="Период 📆"))
    kb.add(KeyboardButton(text="Отмена"))
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)

def get_reason_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="уваж"))
    kb.add(KeyboardButton(text="неуваж"))
    kb.add(KeyboardButton(text="болезнь"))
    kb.add(KeyboardButton(text="Отмена"))
    kb.adjust(3, 1)
    return kb.as_markup(resize_keyboard=True)

def get_cancel_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Отмена"))
    return kb.as_markup(resize_keyboard=True)

def get_edit_skip_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оставить без изменений", callback_data="skip_edit")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_dialog")]
    ])
    return kb

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_date(date_str):
    try:
        datetime.strptime(date_str, '%d.%m.%Y')
        return True
    except ValueError:
        return False

def format_absence_for_student(row):
    # row: (id, date_start, date_end, pairs, reason, status, created_at)
    abs_id, date_start, date_end, pairs, reason, status, created = row
    period = f"{date_start} – {date_end}" if date_end else date_start
    text = f"📅 {period}\nПары: {pairs}\nПричина: {reason}\nСтатус: {status}"
    return text, abs_id

def format_absence_for_admin(row):
    # row: (id, user_id, username, full_name, date_start, date_end, pairs, reason, status, created_at)
    abs_id, user_id, username, full_name, date_start, date_end, pairs, reason, status, created = row
    who = full_name or username or str(user_id)
    period = f"{date_start} – {date_end}" if date_end else date_start
    text = f"👤 {who} (ID: {user_id})\n📅 {period}\nПары: {pairs}\nПричина: {reason}\nСтатус: {status}"
    return text, abs_id, user_id

# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для учёта пропусков.\n\n"
        "Команды:\n"
        "/new – подать заявку на пропуск\n"
        "/my – посмотреть свои заявки (можно редактировать/удалять)\n"
        "/admin – (для старосты) все заявки (можно подтвердить/отклонить)"
    )

@dp.message(Command("new"))
async def cmd_new(message: types.Message, state: FSMContext):
    await state.set_state(AbsenceForm.choose_type)
    await message.answer(
        "Выберите тип пропуска:",
        reply_markup=get_type_keyboard()
    )

@dp.message(StateFilter("*"), F.text == "Отмена")
async def cancel_dialog(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Диалог отменён.",
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.callback_query(F.data == "cancel_dialog")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Диалог отменён.")
    await callback.answer("Отменено.")

@dp.message(Command("my"))
async def cmd_my(message: types.Message):
    rows = get_user_absences(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет заявок.")
        return
    for row in rows:
        text, abs_id = format_absence_for_student(row)
        # Кнопки "Редактировать" и "Удалить" только для pending
        if row[5] == 'pending':  # status
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{abs_id}"),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{abs_id}")
                ]
            ])
        else:
            keyboard = None
        await message.answer(text, reply_markup=keyboard)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Эта команда только для старосты.")
        return
    rows = get_all_absences()
    if not rows:
        await message.answer("Заявок пока нет.")
        return
    for row in rows:
        text, abs_id, user_id = format_absence_for_admin(row)
        # Кнопки подтвердить/отклонить только для pending
        if row[8] == 'pending':  # status
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{abs_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{abs_id}"),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{abs_id}")
                ]
            ])
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{abs_id}")]
            ])
        await message.answer(text, reply_markup=keyboard)

# ========== ОБРАБОТКА СОЗДАНИЯ ЗАЯВКИ (FSM) ==========
@dp.message(AbsenceForm.choose_type)
async def process_type(message: types.Message, state: FSMContext):
    choice = message.text
    if choice == "Одна дата 📅":
        await state.update_data(type="single")
        await state.set_state(AbsenceForm.single_date)
        await message.answer(
            "Введите дату в формате ДД.ММ.ГГГГ (например, 05.09.2026):",
            reply_markup=get_cancel_keyboard()
        )
    elif choice == "Период 📆":
        await state.update_data(type="period")
        await state.set_state(AbsenceForm.period_start)
        await message.answer(
            "Введите начальную дату периода в формате ДД.ММ.ГГГГ:",
            reply_markup=get_cancel_keyboard()
        )
    else:
        await message.answer("Пожалуйста, используйте кнопки.")

@dp.message(AbsenceForm.single_date)
async def process_single_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    if not validate_date(date_str):
        await message.answer("Неверный формат. Попробуйте ещё раз (ДД.ММ.ГГГГ):")
        return
    await state.update_data(date_start=date_str, date_end=None)
    await state.set_state(AbsenceForm.pairs)
    await message.answer(
        "Введите номера или названия пар, которые пропускаете.\n"
        "Примеры: 1,3,5  или  1-4  или  Математика, Физика",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(AbsenceForm.period_start)
async def process_period_start(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    if not validate_date(date_str):
        await message.answer("Неверный формат. Попробуйте ещё раз (ДД.ММ.ГГГГ):")
        return
    await state.update_data(date_start=date_str)
    await state.set_state(AbsenceForm.period_end)
    await message.answer(
        "Введите конечную дату периода (ДД.ММ.ГГГГ):",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(AbsenceForm.period_end)
async def process_period_end(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    if not validate_date(date_str):
        await message.answer("Неверный формат. Попробуйте ещё раз (ДД.ММ.ГГГГ):")
        return
    data = await state.get_data()
    start = datetime.strptime(data['date_start'], '%d.%m.%Y')
    end = datetime.strptime(date_str, '%d.%m.%Y')
    if end < start:
        await message.answer("Конечная дата не может быть раньше начальной. Введите снова:")
        return
    await state.update_data(date_end=date_str)
    await state.set_state(AbsenceForm.pairs)
    await message.answer(
        "Введите номера или названия пар, которые пропускаете (для всех дней периода).\n"
        "Примеры: 1,3,5  или  1-4  или  Математика, Физика",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(AbsenceForm.pairs)
async def process_pairs(message: types.Message, state: FSMContext):
    pairs = message.text.strip()
    if not pairs:
        await message.answer("Пожалуйста, введите хотя бы одну пару.")
        return
    await state.update_data(pairs=pairs)
    await state.set_state(AbsenceForm.reason)
    await message.answer(
        "Выберите причину пропуска:",
        reply_markup=get_reason_keyboard()
    )

@dp.message(AbsenceForm.reason)
async def process_reason(message: types.Message, state: FSMContext):
    reason = message.text.lower()
    if reason not in ["уваж", "неуваж", "болезнь"]:
        await message.answer("Пожалуйста, выберите одну из кнопок.")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = (message.from_user.first_name or "") + (" " + message.from_user.last_name if message.from_user.last_name else "")
    save_absence(
        user_id=user_id,
        username=username,
        full_name=full_name.strip(),
        date_start=data['date_start'],
        date_end=data.get('date_end'),
        pairs=data['pairs'],
        reason=reason
    )
    await state.clear()
    await message.answer(
        "✅ Заявка сохранена! Староста будет оповещён (если захочет).\n"
        "Вы можете посмотреть свои заявки командой /my.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# ========== РЕДАКТИРОВАНИЕ (FSM) ==========
# Callback для кнопки "Редактировать"
@dp.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery, state: FSMContext):
    abs_id = int(callback.data.split("_")[1])
    # Проверяем, что заявка принадлежит этому пользователю и статус pending
    row = get_absence_by_id(abs_id)
    if not row:
        await callback.answer("Заявка не найдена.")
        return
    if row[1] != callback.from_user.id:
        await callback.answer("Это не ваша заявка.")
        return
    if row[8] != 'pending':
        await callback.answer("Нельзя редактировать уже обработанную заявку.")
        return
    # Сохраняем id заявки в состояние
    await state.update_data(edit_id=abs_id)
    # Начинаем диалог редактирования с даты
    await state.set_state(AbsenceForm.edit_date)
    await callback.message.edit_text(
        f"Редактирование заявки #{abs_id}\n\n"
        "Введите новую дату (или период) в формате ДД.ММ.ГГГГ (одна дата) или ДД.ММ.ГГГГ-ДД.ММ.ГГГГ (период).\n"
        "Если хотите оставить как есть, нажмите кнопку ниже.",
        reply_markup=get_edit_skip_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "skip_edit", StateFilter(AbsenceForm.edit_date))
async def skip_edit_date(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(new_date_start=None, new_date_end=None)
    await state.set_state(AbsenceForm.edit_pairs)
    await callback.message.edit_text(
        "Дата оставлена без изменений.\n"
        "Теперь введите новые пары (или нажмите 'Оставить без изменений').",
        reply_markup=get_edit_skip_keyboard()
    )
    await callback.answer()

@dp.message(AbsenceForm.edit_date)
async def process_edit_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    # Проверяем, может быть это период через дефис
    if '-' in text:
        parts = text.split('-')
        if len(parts) == 2:
            d1, d2 = parts[0].strip(), parts[1].strip()
            if validate_date(d1) and validate_date(d2):
                start = datetime.strptime(d1, '%d.%m.%Y')
                end = datetime.strptime(d2, '%d.%m.%Y')
                if end >= start:
                    await state.update_data(new_date_start=d1, new_date_end=d2)
                    await state.set_state(AbsenceForm.edit_pairs)
                    await message.answer(
                        "Период обновлён. Теперь введите новые пары (или нажмите 'Оставить без изменений').",
                        reply_markup=get_edit_skip_keyboard()
                    )
                    return
    # Иначе пробуем как одну дату
    if validate_date(text):
        await state.update_data(new_date_start=text, new_date_end=None)
        await state.set_state(AbsenceForm.edit_pairs)
        await message.answer(
            "Дата обновлена. Теперь введите новые пары (или нажмите 'Оставить без изменений').",
            reply_markup=get_edit_skip_keyboard()
        )
        return
    await message.answer("Неверный формат. Введите ДД.ММ.ГГГГ или ДД.ММ.ГГГГ-ДД.ММ.ГГГГ, или нажмите кнопку.")

@dp.callback_query(F.data == "skip_edit", StateFilter(AbsenceForm.edit_pairs))
async def skip_edit_pairs(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(new_pairs=None)
    await state.set_state(AbsenceForm.edit_reason)
    await callback.message.edit_text(
        "Пары оставлены без изменений.\n"
        "Теперь выберите новую причину (или нажмите 'Оставить').",
        reply_markup=get_reason_keyboard()  # используем обычную клавиатуру с кнопками причин, но добавим кнопку "Оставить"
    )
    # Добавим отдельную кнопку "Оставить" в виде инлайн? Но у нас reply-клавиатура, смешивать неудобно.
    # Лучше сделать кнопку "Оставить" как отдельную команду или текст. Модифицируем: добавим в reply-клавиатуру кнопку "Оставить".
    # Для простоты, сделаем так: если пользователь пришлёт текст "оставить" (или любую другую команду), то пропускаем.
    # Но проще создать отдельную инлайн-кнопку, но у нас уже есть reply. Я добавлю отдельную кнопку "Оставить" в reply-клавиатуру.
    # Переделаем: в процессе редактирования причины будем использовать reply-клавиатуру с вариантами причин + кнопка "Оставить".
    # Переопределим функцию get_reason_keyboard с дополнительной кнопкой.
    await callback.answer()

# Создадим клавиатуру для редактирования причины с кнопкой "Оставить"
def get_reason_with_skip_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="уваж"))
    kb.add(KeyboardButton(text="неуваж"))
    kb.add(KeyboardButton(text="болезнь"))
    kb.add(KeyboardButton(text="Оставить"))
    kb.add(KeyboardButton(text="Отмена"))
    kb.adjust(3, 1, 1)
    return kb.as_markup(resize_keyboard=True)

# Для удобства, используем эту клавиатуру в процессе редактирования причины.
# Нужно модифицировать предыдущий шаг: после ввода пар переходим к причине с этой клавиатурой.

# Перепишем обработчик edit_pairs, чтобы после получения пар переходил к причине с нашей клавиатурой.
@dp.message(AbsenceForm.edit_pairs)
async def process_edit_pairs(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == "оставить" or text == "":
        await state.update_data(new_pairs=None)
    else:
        await state.update_data(new_pairs=text)
    await state.set_state(AbsenceForm.edit_reason)
    await message.answer(
        "Теперь выберите новую причину (или нажмите 'Оставить'):",
        reply_markup=get_reason_with_skip_keyboard()
    )

# Обработчик для причины (с учетом возможности оставить)
@dp.message(AbsenceForm.edit_reason)
async def process_edit_reason(message: types.Message, state: FSMContext):
    reason = message.text.lower()
    data = await state.get_data()
    abs_id = data['edit_id']
    old_row = get_absence_by_id(abs_id)
    if not old_row:
        await message.answer("Ошибка: заявка не найдена.")
        await state.clear()
        return
    # Определяем новые значения
    new_date_start = data.get('new_date_start') if data.get('new_date_start') is not None else old_row[3]  # date_start
    new_date_end = data.get('new_date_end') if data.get('new_date_end') is not None else old_row[4]       # date_end
    new_pairs = data.get('new_pairs') if data.get('new_pairs') is not None else old_row[5]               # pairs
    if reason == "оставить":
        new_reason = old_row[6]  # reason
    elif reason in ["уваж", "неуваж", "болезнь"]:
        new_reason = reason
    else:
        await message.answer("Пожалуйста, выберите одну из кнопок или 'Оставить'.")
        return
    # Обновляем
    update_absence(abs_id, new_date_start, new_date_end, new_pairs, new_reason)
    await state.clear()
    await message.answer(
        "✅ Заявка обновлена!",
        reply_markup=types.ReplyKeyboardRemove()
    )

# ========== УДАЛЕНИЕ ЗАЯВКИ ==========
@dp.callback_query(F.data.startswith("delete_"))
async def delete_callback(callback: types.CallbackQuery):
    abs_id = int(callback.data.split("_")[1])
    row = get_absence_by_id(abs_id)
    if not row:
        await callback.answer("Заявка не найдена.")
        return
    if row[1] != callback.from_user.id:
        await callback.answer("Это не ваша заявка.")
        return
    if row[8] != 'pending':
        await callback.answer("Нельзя удалить уже обработанную заявку.")
        return
    delete_absence(abs_id)
    await callback.message.edit_text("🗑 Заявка удалена.")
    await callback.answer("Удалено.")

@dp.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete_callback(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Только для старосты.")
        return
    abs_id = int(callback.data.split("_")[2])
    row = get_absence_by_id(abs_id)
    if not row:
        await callback.answer("Заявка не найдена.")
        return
    delete_absence(abs_id)
    await callback.message.edit_text("🗑 Заявка удалена администратором.")
    await callback.answer("Удалено.")

# ========== ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ (староста) ==========
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_callback(callback: types.CallbackQuery):
    abs_id = int(callback.data.split("_")[1])
    row = get_absence_by_id(abs_id)
    if not row:
        await callback.answer("Заявка не найдена.")
        return
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Только для старосты.")
        return
    if row[8] != 'pending':
        await callback.answer("Заявка уже обработана.")
        return
    set_absence_status(abs_id, 'confirmed')
    # Уведомляем студента
    user_id = row[1]
    try:
        await bot.send_message(user_id, f"✅ Ваша заявка #{abs_id} подтверждена старостой.")
    except:
        pass
    await callback.message.edit_text(callback.message.text + "\n\n✅ Статус: подтверждена")
    await callback.answer("Подтверждено.")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_callback(callback: types.CallbackQuery):
    abs_id = int(callback.data.split("_")[1])
    row = get_absence_by_id(abs_id)
    if not row:
        await callback.answer("Заявка не найдена.")
        return
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Только для старосты.")
        return
    if row[8] != 'pending':
        await callback.answer("Заявка уже обработана.")
        return
    set_absence_status(abs_id, 'rejected')
    user_id = row[1]
    try:
        await bot.send_message(user_id, f"❌ Ваша заявка #{abs_id} отклонена старостой.")
    except:
        pass
    await callback.message.edit_text(callback.message.text + "\n\n❌ Статус: отклонена")
    await callback.answer("Отклонено.")

# ========== ЗАПУСК ==========
async def main():
    init_db()
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())