import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/uniproagency")
PORTFOLIO_LINK = os.getenv("PORTFOLIO_LINK", "https://Uniproagency.netlify.app")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@upagencyadmin")
ADMIN_REVIEW_CHAT_ID = int(os.getenv("ADMIN_REVIEW_CHAT_ID", "0"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
