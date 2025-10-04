from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
CHAT_ID = int(os.getenv("CHAT_ID", "123456789"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/habits_db")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Almaty")
