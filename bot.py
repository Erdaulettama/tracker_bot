# bot.py
import asyncio
from datetime import datetime, date
import logging

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import db
from states import AddHabitFlow, ScheduleFlow, NoteFlow

logging.basicConfig(level=logging.INFO)

# Bot with default HTML parse mode
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# ---------------- Utility ----------------
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

def schedule_days_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=DAYS_RU[i], callback_data=f"schedule_day:{i}") for i in range(4)],
        [InlineKeyboardButton(text=DAYS_RU[i], callback_data=f"schedule_day:{i}") for i in range(4,7)]
    ])
    return kb

def habits_keyboard_with_actions(habits):
    # returns InlineKeyboardMarkup: each row has two buttons: Done and Delete
    rows = []
    for h in habits:
        done_btn = InlineKeyboardButton(text="✅ Сделано", callback_data=f"done:{h['id']}")
        del_btn = InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{h['id']}")
        rows.append([done_btn, del_btn])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def notes_with_delete_keyboard(notes):
    kb_rows = []
    for n in notes:
        kb_rows.append([InlineKeyboardButton(text=f"Удалить #{n['id']}", callback_data=f"delnote:{n['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

# ---------------- Handlers ----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        "Привет! Я твой личный трекер привычек и расписание уроков.\n\n"
        "Команды:\n"
        "/addhabit — добавить привычку\n"
        "/listhabits — список привычек\n"
        "/delhabit &lt;id&gt; — удалить привычку\n"
        "/stats &lt;id&gt; — статистика по привычке\n\n"
        "/editschedule — добавить/изменить расписание уроков (выбери день)\n"
        "/viewschedule — посмотреть все расписания\n"
        "/delschedule — удалить расписание для дня (выбери день)\n\n"
        "/addnote — добавить заметку\n"
        "/listnotes — список заметок\n\n"
    )
    await message.answer(text)

# -------- Habits --------
@dp.message(Command("addhabit"))
async def cmd_addhabit(message: types.Message, state: FSMContext):
    await message.answer("✍️ Введи название новой привычки (коротко):")
    await state.set_state(AddHabitFlow.waiting_name)

@dp.message(AddHabitFlow.waiting_name)
async def process_habit_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым, попробуй ещё раз.")
        return
    hid = await db.add_habit(name)
    await message.answer(f"✅ Привычка <b>{name}</b> добавлена (id={hid}).")
    await state.clear()

@dp.message(Command("listhabits"))
async def cmd_listhabits(message: types.Message):
    habits = await db.list_habits()
    if not habits:
        await message.answer("У тебя пока нет привычек. Добавь через /addhabit")
        return

    # Build rich list with stats
    lines = ["<b>📋 Твои привычки:</b>\n"]
    for h in habits:
        st = await db.habit_stats(h["id"])
        lines.append(f"<b>{h['id']}. {h['name']}</b>\nВсего: {st['total']} • Серия: {st['streak']}\n")
    text = "\n".join(lines)
    await message.answer(text, reply_markup=habits_keyboard_with_actions(habits))

@dp.callback_query(F.data.startswith("done:"))
async def cb_done(callback: types.CallbackQuery):
    hid = int(callback.data.split(":",1)[1])
    ok = await db.mark_done(hid)
    if ok:
        await callback.answer("Отмечено ✅", show_alert=False)
        # respond without HTML issues (we don't use raw < >)
        await callback.message.answer(f"Привычка <b>{hid}</b> отмечена за сегодня.")
    else:
        await callback.answer("Уже отмечено сегодня.", show_alert=True)

@dp.callback_query(F.data.startswith("del:"))
async def cb_delete_habit(callback: types.CallbackQuery):
    hid = int(callback.data.split(":",1)[1])
    ok = await db.delete_habit(hid)
    if ok:
        await callback.answer("Привычка удалена.", show_alert=False)
        await callback.message.answer(f"🗑 Привычка <b>{hid}</b> удалена.")
        # optionally update the message with keyboard removal
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except:
            pass
    else:
        await callback.answer("Не нашёл привычку.", show_alert=True)

@dp.message(Command("delhabit"))
async def cmd_delhabit(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Используй: /delhabit &lt;id&gt;")
        return
    try:
        hid = int(parts[1])
    except:
        await message.answer("Неверный id.")
        return
    ok = await db.delete_habit(hid)
    if ok:
        await message.answer(f"🗑 Привычка #{hid} удалена.")
    else:
        await message.answer("Не нашёл такую привычку.")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Используй: /stats &lt;id&gt;")
        return
    try:
        hid = int(parts[1])
    except:
        await message.answer("Неверный id.")
        return
    st = await db.habit_stats(hid)
    text = (
        f"<b>Статистика по привычке #{hid}</b>\n\n"
        f"Всего выполнено: {st['total']}\n"
        f"Последний раз: {st['last_done'] or 'никогда'}\n"
        f"Текущая серия (streak): {st['streak']}"
    )
    await message.answer(text)

# -------- Schedule (расписание уроков) --------
@dp.message(Command("editschedule"))
async def cmd_editschedule(message: types.Message):
    await message.answer("Выбери день недели, для которого хочешь добавить/изменить расписание:", reply_markup=schedule_days_keyboard())

@dp.callback_query(F.data.startswith("schedule_day:"))
async def cb_schedule_day(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":",1)[1])
    await state.update_data(schedule_day=idx)
    await state.set_state(ScheduleFlow.waiting_text)
    await callback.message.answer(f"Отправь расписание для дня <b>{DAYS_RU[idx]}</b>.\nМожно вставить несколько строк (например: 1) Алгебра — 8:30).")
    await callback.answer()

@dp.message(ScheduleFlow.waiting_text)
async def process_schedule_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    day_idx = data.get("schedule_day")
    text = message.text.strip()
    if not text:
        await message.answer("Текст пустой — попробуй снова.")
        return
    await db.set_schedule_for_day(day_idx, text)
    await message.answer(f"✅ Расписание для <b>{DAYS_RU[day_idx]}</b> сохранено.")
    await state.clear()

@dp.message(Command("viewschedule"))
async def cmd_viewschedule(message: types.Message):
    rows = await db.list_all_schedules()
    if not rows:
        await message.answer("Расписаний пока нет. Добавь через /editschedule")
        return
    lines = []
    for r in rows:
        lines.append(f"<b>{DAYS_RU[r['day_of_week']]}</b>:\n{r['text']}\n")
    await message.answer("\n".join(lines))

@dp.message(Command("delschedule"))
async def cmd_delschedule(message: types.Message):
    await message.answer("Выбери день, расписание которого хочешь удалить:", reply_markup=schedule_days_keyboard())

@dp.callback_query(F.data.startswith("schedule_day:"))
async def cb_delschedule_and_edit(callback: types.CallbackQuery, state: FSMContext):
    # This handler is already used for editschedule flow; we need to distinguish context.
    # We'll check FSM state: if user is not in ScheduleFlow.waiting_text, then we assume delete operation.
    cur_state = await state.get_state()
    idx = int(callback.data.split(":",1)[1])
    if cur_state == ScheduleFlow.waiting_text.state:
        # handled by editschedule flow above
        return
    # Otherwise treat as delete request
    ok = await db.delete_schedule_for_day(idx)
    if ok:
        await callback.answer(f"Расписание для {DAYS_RU[idx]} удалено.", show_alert=False)
        await callback.message.answer(f"🗑 Расписание для <b>{DAYS_RU[idx]}</b> удалено.")
    else:
        await callback.answer("Не нашёл расписание для этого дня.", show_alert=True)

# -------- Notes (заметки) --------
@dp.message(Command("addnote"))
async def cmd_addnote(message: types.Message):
    await message.answer("✍️ Введи текст заметки:")
    await dp.current_state(user=message.from_user.id).set_state(NoteFlow.waiting_text)

@dp.message(NoteFlow.waiting_text)
async def process_note_text(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Заметка не может быть пустой.")
        return
    nid = await db.add_note(text)
    await message.answer(f"✅ Заметка сохранена (#{nid}). Я буду напоминать её в 15:00, 18:00 и 21:00 по Астане.")
    await state.clear()

@dp.message(Command("listnotes"))
async def cmd_listnotes(message: types.Message):
    notes = await db.list_notes()
    if not notes:
        await message.answer("У тебя пока нет заметок. Добавь /addnote")
        return
    text = "<b>Заметки:</b>\n\n" + "\n".join([f"#{n['id']}: {n['content']}" for n in notes])
    kb = notes_with_delete_keyboard(notes)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("delnote:"))
async def cb_delnote(callback: types.CallbackQuery):
    nid = int(callback.data.split(":",1)[1])
    ok = await db.delete_note(nid)
    if ok:
        await callback.answer("Заметка удалена.", show_alert=False)
        await callback.message.answer(f"Заметка #{nid} удалена.")
    else:
        await callback.answer("Не нашёл такую заметку.", show_alert=True)

# ---------------- Scheduled jobs ----------------
async def send_morning_digest():
    today_idx = date.today().weekday()
    schedule_text = await db.get_schedule_for_day(today_idx)
    habits = await db.list_habits()

    parts = []
    parts.append("🌅 <b>Доброе утро!</b>\n")
    if schedule_text:
        parts.append(f"<b>Расписание на сегодня ({DAYS_RU[today_idx]}):</b>\n{schedule_text}\n")
    else:
        parts.append(f"<b>Расписание на сегодня ({DAYS_RU[today_idx]}):</b>\n— пусто. /editschedule чтобы добавить\n")

    if habits:
        parts.append("<b>Привычки на сегодня:</b>\n" + "\n".join([f"{h['id']}. {h['name']}" for h in habits]))
    else:
        parts.append("У тебя пока нет привычек. /addhabit чтобы добавить.")

    text = "\n".join(parts)
    try:
        if habits:
            await bot.send_message(config.CHAT_ID, text, reply_markup=habits_keyboard_with_actions(habits))
        else:
            await bot.send_message(config.CHAT_ID, text)
    except Exception as e:
        logging.exception("Ошибка при отправке утреннего сообщения: %s", e)

async def send_notes_reminder():
    notes = await db.get_all_notes_texts()
    if not notes:
        return
    lines = ["⏰ <b>Напоминания / Заметки</b>\n"]
    for n in notes:
        lines.append(f"#{n['id']}: {n['content']}")
    text = "\n\n".join(lines)
    try:
        await bot.send_message(config.CHAT_ID, text)
    except Exception as e:
        logging.exception("Ошибка при отправке заметок: %s", e)

async def daily_cleanup_notes_job():
    removed = await db.cleanup_old_notes(3)
    if removed:
        logging.info("Cleanup: удалено заметок старше 3 дней: %d", removed)

# ---------------- Startup / Scheduler ----------------
async def main():
    await db.init_db_pool()
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    # Утро — 07:00
    scheduler.add_job(send_morning_digest, "cron", hour=7, minute=0)
    # Заметки — 15:00, 18:00, 21:00
    scheduler.add_job(send_notes_reminder, "cron", hour=15, minute=0)
    scheduler.add_job(send_notes_reminder, "cron", hour=18, minute=0)
    scheduler.add_job(send_notes_reminder, "cron", hour=21, minute=0)
    # Cleanup notes once a day (00:05)
    scheduler.add_job(daily_cleanup_notes_job, "cron", hour=0, minute=5)
    scheduler.start()
    try:
        logging.info("Bot started")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
