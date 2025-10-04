from aiogram.fsm.state import StatesGroup, State

class AddHabitFlow(StatesGroup):
    waiting_name = State()

class ScheduleFlow(StatesGroup):
    waiting_text = State()  # after selecting day via callback, store day in FSM data

class NoteFlow(StatesGroup):
    waiting_text = State()
