import asyncio
import html
import logging
import random
import os  # Қўшилди

from aiohttp import web  # Қўшилди
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

# Сизнинг конфиг ва база функцияларингиз
from config import TOKEN, CHANNEL_LINK, PORTFOLIO_LINK, ADMIN_USERNAME, ADMIN_REVIEW_CHAT_ID, OWNER_ID
from db import * 

# 1. МУҲИМ: Dispatcher ва Bot ни шу ерда, функциялардан ТАШҚАРИДА эълон қиламиз
storage = MemoryStorage()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# Шу ердан пастга қараб сизнинг @dp.message handler'ларингиз бошланади...

logging.basicConfig(level=logging.INFO)

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. .env faylga yozing.")
if not OWNER_ID:
    raise RuntimeError("OWNER_ID topilmadi. .env faylga yozing.")
if not ADMIN_REVIEW_CHAT_ID:
    raise RuntimeError("ADMIN_REVIEW_CHAT_ID topilmadi. .env faylga yozing.")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
broadcast_targets_mode: dict[int, str] = {}


class OrderForm(StatesGroup):
    need = State()
    deadline = State()
    budget = State()


class PanelForm(StatesGroup):
    add_admin_ids = State()
    remove_admin = State()
    search_order = State()
    search_user = State()
    user_orders = State()
    broadcast_text = State()


def esc(text):
    return html.escape(str(text)) if text is not None else "-"


def is_blank(text: str) -> bool:
    return not text or not str(text).strip()


def role_name(role: str | None) -> str:
    if role == "owner":
        return "Owner"
    if role == "superadmin":
        return "Katta admin"
    if role == "admin":
        return "Oddiy admin"
    return "User"


def register_from_telegram(user) -> None:
    register_user(user.id, user.username or "", user.full_name or "")


async def blocked_message(message: Message):
    reason = get_ban_reason(message.from_user.id)
    await message.answer(f"🚫 Siz bloklangansiz.\n📝 Sabab: {esc(reason)}")


async def blocked_callback(callback: CallbackQuery):
    reason = get_ban_reason(callback.from_user.id)
    await callback.answer(f"Bloklangansiz. Sabab: {reason}", show_alert=True)


def build_order_discount_note(user_id: int) -> str:
    return (
        f"\n<b>👥 Referal:</b> {get_referral_count(user_id)} ta"
        f"\n<b>🎁 Skidka:</b> {get_discount(user_id)}%"
    )


def main_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛠 Xizmatlar")],
        [KeyboardButton(text="👤 Profile")],
        [KeyboardButton(text="📢 Bizning kanalimiz")],
        [KeyboardButton(text="🖼 Portfolio")],
        [KeyboardButton(text="📞 Biz bilan bog‘lanish")],
    ]
    if is_staff(user_id):
        rows.append([KeyboardButton(text="⚙️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


services_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌐 Web-sahifa yaratish")],
        [KeyboardButton(text="🤖 Telegram bot yaratish")],
        [KeyboardButton(text="🎨 Dizayn xizmatlari")],
        [KeyboardButton(text="⬅️ Orqaga")],
    ],
    resize_keyboard=True,
)


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Referal system", callback_data="profile_ref")],
            [InlineKeyboardButton(text="📦 Mening orderlarim", callback_data="profile_orders")],
        ]
    )


def my_orders_kb(user_id: int) -> InlineKeyboardMarkup | None:
    rows = []
    for order in get_user_orders(user_id):
        rows.append([InlineKeyboardButton(text=f"📦 Order #{order['order_id']}", callback_data=f"myorder:{order['order_id']}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_order_kb(service_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📝 Buyurtma berish", callback_data=f"start:{service_code}")]]
    )


def review_kb(user_id: int, order_id: int, mode: str = "active") -> InlineKeyboardMarkup | None:
    if mode in ("accepted", "rejected", "unbanned"):
        return None
    if mode == "banned":
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="♻️ Ochish", callback_data=f"unban:{user_id}:{order_id}")]]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept:{user_id}:{order_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{user_id}:{order_id}"),
            ],
            [InlineKeyboardButton(text="🚫 Ban", callback_data=f"ban:{user_id}:{order_id}")],
        ]
    )


def panel_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Orderlar", callback_data="panel_orders")],
            [InlineKeyboardButton(text="👤 Userlar", callback_data="panel_users")],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="panel_broadcast")],
            [InlineKeyboardButton(text="⚙️ Admin sozlamalar", callback_data="panel_admin_settings")],
        ]
    )


def panel_orders_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Aktiv orderlar", callback_data="orders_active")],
            [InlineKeyboardButton(text="🕓 Qabul qilinmagan orderlar", callback_data="orders_unaccepted")],
            [InlineKeyboardButton(text="🔍 Order qidirish", callback_data="orders_search")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_panel_main")],
        ]
    )


def panel_users_kb(super_user: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👥 Hamma userlar", callback_data="users_all")],
        [InlineKeyboardButton(text="👤 User qidirish", callback_data="users_search")],
        [InlineKeyboardButton(text="🚫 Ban ro‘yxati", callback_data="users_banned")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_panel_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Hammaga", callback_data="broadcast_all")],
            [InlineKeyboardButton(text="📢 Faollarga", callback_data="broadcast_active")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_panel_main")],
        ]
    )


def panel_admin_settings_kb(super_user: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🧾 Admin log", callback_data="admin_logs")],
    ]
    if super_user:
        rows.append([InlineKeyboardButton(text="➕ Katta admin qo‘shish", callback_data="admin_add_super")])
        rows.append([InlineKeyboardButton(text="➕ Oddiy admin qo‘shish", callback_data="admin_add_normal")])
        rows.append([InlineKeyboardButton(text="➖ Admin olib tashlash", callback_data="admin_remove")])
        rows.append([InlineKeyboardButton(text="👮 Adminlar ro‘yxati", callback_data="admin_list")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_panel_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_service_card(service_code: str):
    data = {
        "web": {
            "name": "🌐 Web-sahifa yaratish",
            "card": (
                "🌐 <b>Web-sayt yaratish</b>\n\n"
                "• Landing page\n"
                "• Biznes sayt\n"
                "• Online shop\n\n"
                "⏱️ 3–7 kun\n"
                "💰 Narx: kelishiladi"
            ),
            "need_prompt": "✍️ Qanday <b>web-sayt</b> kerakligini to‘liq yozing:",
        },
        "bot": {
            "name": "🤖 Telegram bot yaratish",
            "card": (
                "🤖 <b>Telegram bot yaratish</b>\n\n"
                "• Biznes bot\n"
                "• Admin panel\n"
                "• SMM botlar\n\n"
                "⏱️ 3–10 kun\n"
                "💰 Narx: kelishiladi"
            ),
            "need_prompt": "✍️ Qanday <b>telegram bot</b> kerakligini to‘liq yozing:",
        },
        "design": {
            "name": "🎨 Dizayn xizmatlari",
            "card": (
                "🎨 <b>Dizayn xizmatlari</b>\n\n"
                "• Logo\n"
                "• Banner\n"
                "• Post dizayn\n\n"
                "⏱️ 1–3 kun\n"
                "💰 Narx: kelishiladi"
            ),
            "need_prompt": "✍️ Qanday <b>dizayn</b> kerakligini to‘liq yozing:",
        },
    }
    return data.get(service_code)


def build_order_text(order_id: int, service: str, need: str, deadline: str, budget: str, full_name: str, username: str, user_id: int) -> str:
    user_text = f"@{esc(username)}" if username else "Username yo‘q"
    return (
        f"<b>📥 YANGI BUYURTMA</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>🆔 Buyurtma:</b> <code>{order_id}</code>\n"
        f"<b>🛠 Xizmat:</b> {esc(service)}\n"
        f"<b>📋 Kerak:</b> {esc(need)}\n"
        f"<b>⏰ Muddat:</b> {esc(deadline)}\n"
        f"<b>💰 Budjet:</b> {esc(budget)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>👤 Ism:</b> {esc(full_name)}\n"
        f"<b>🔗 User:</b> {user_text}\n"
        f"<b>🆔 Telegram ID:</b> <code>{user_id}</code>"
    )


def build_status_only_text(title: str, user_text: str, user_id: int, admin_text: str, reason: str | None = None) -> str:
    text = (
        f"<b>{title}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>👤 User:</b> {user_text}\n"
        f"<b>🆔 User ID:</b> <code>{user_id}</code>\n"
        f"<b>👨‍💼 Admin:</b> {admin_text}"
    )
    if reason:
        text += f"\n<b>📝 Sabab:</b> {esc(reason)}"
    return text


def build_order_with_status_text(base_text: str, title: str, user_text: str, user_id: int, admin_text: str, reason: str | None = None) -> str:
    text = (
        f"{base_text}\n\n"
        f"<b>📌 STATUS</b>\n"
        f"<b>🔹 Holat:</b> {title}\n"
        f"<b>👤 User:</b> {user_text}\n"
        f"<b>🆔 User ID:</b> <code>{user_id}</code>\n"
        f"<b>👨‍💼 Admin:</b> {admin_text}"
    )
    if reason:
        text += f"\n<b>📝 Sabab:</b> {esc(reason)}"
    return text


def banned_users_text() -> str:
    rows = get_banned_users()
    if not rows:
        return "🚫 Ban olgan userlar yo‘q."
    return "🚫 <b>Ban olgan userlar:</b>\n" + "\n".join(
        [f"• <code>{row['user_id']}</code> — {esc(row['ban_reason'])}" for row in rows]
    )


def admins_text() -> str:
    rows = get_admins()
    if not rows:
        return "👮 Admin yo‘q."
    lines = ["👮 <b>Adminlar:</b>"]
    for row in rows:
        lines.append(f"• {role_name(row['role'])}: <code>{row['user_id']}</code>")
    return "\n".join(lines)


def stats_text() -> str:
    return (
        "📊 <b>Bot statistikasi</b>\n"
        f"👥 Jami foydalangan userlar: <b>{total_users_count()}</b>\n"
        f"📦 Jami orderlar: <b>{count_all_orders()}</b>\n"
        f"🚫 Ban olgan userlar: <b>{banned_users_count()}</b>\n"
        f"👮 Adminlar soni: <b>{admins_count()}</b>"
    )


def admin_stats_text() -> str:
    rows = get_admin_action_counts()
    if not rows:
        return "👮 <b>Admin bo‘yicha statistika</b>\nHali action yo‘q."
    return "👮 <b>Admin bo‘yicha statistika</b>\n" + "\n".join(
        [f"• <code>{row['actor_id']}</code> — <b>{row['total']}</b> ta action" for row in rows]
    )


def recent_logs_text() -> str:
    rows = get_recent_logs(20)
    if not rows:
        return "🧾 Log bo‘sh."
    lines = ["🧾 <b>So‘nggi loglar:</b>"]
    for row in rows:
        line = f"• {esc(row['action'])} | actor=<code>{row['actor_id']}</code>"
        if row['target_id'] is not None:
            line += f" | target=<code>{row['target_id']}</code>"
        if row['extra']:
            line += f" | {esc(row['extra'])}"
        lines.append(line)
    return "\n".join(lines)


def orders_list_text(status: str, title: str, empty_text: str) -> str:
    rows = get_orders_by_status(status)
    if not rows:
        return empty_text
    lines = [f"<b>{title}</b>"]
    for row in rows:
        lines.append(
            f"• <code>{row['order_id']}</code> — {esc(row['service'])} — <code>{row['user_id']}</code>"
        )
    return "\n".join(lines)


def all_orders_text() -> str:
    return orders_list_text("active", "Qabul qilinmagan orderlar:", "Qabul qilinmagan order yo‘q.")


def active_orders_text() -> str:
    return orders_list_text("accepted", "Aktiv orderlar:", "Aktiv order yo‘q.")


def order_info_text(order) -> str:
    return (
        f"<b>🆔 Buyurtma:</b> <code>{order['order_id']}</code>\n"
        f"<b>🛠 Xizmat:</b> {esc(order['service'])}\n"
        f"<b>👤 User ID:</b> <code>{order['user_id']}</code>\n"
        f"<b>📌 Status:</b> {esc(order['status'])}\n"
        f"<b>👥 Referal:</b> {order['referrals']} ta\n"
        f"<b>🎁 Skidka:</b> {order['discount']}%"
    )


def order_full_info_text(order) -> str:
    return (
        f"<b>📦 Order ma’lumoti</b>\n"
        f"<b>🆔 ID:</b> <code>{order['order_id']}</code>\n"
        f"<b>🛠 Xizmat:</b> {esc(order['service'])}\n"
        f"<b>📋 Kerak:</b> {esc(order['need'])}\n"
        f"<b>⏰ Muddat:</b> {esc(order['deadline'])}\n"
        f"<b>💰 Budjet:</b> {esc(order['budget'])}\n"
        f"<b>👤 User ID:</b> <code>{order['user_id']}</code>\n"
        f"<b>📌 Status:</b> {esc(order['status'])}\n"
        f"<b>👥 Referal:</b> {order['referrals']} ta\n"
        f"<b>🎁 Skidka:</b> {order['discount']}%"
    )


def all_users_text() -> str:
    rows = get_all_users()
    if not rows:
        return "Hali userlar yo‘q."
    lines = ["👥 <b>Botni ishlatgan hamma userlar:</b>"]
    for row in rows:
        username = f"@{esc(row['username'])}" if row['username'] else "username yo‘q"
        full_name = esc(row['full_name'] or '-')
        banned = " 🚫" if row['is_banned'] else ""
        lines.append(f"• <code>{row['user_id']}</code> — {full_name} — {username}{banned}")
    return "\n".join(lines)


def user_info_text(user_id: int) -> str:
    stats = get_user_stats(user_id)
    if not stats:
        return "User topilmadi."
    return (
        f"<b>👤 User ma’lumot</b>\n"
        f"<b>🆔 ID:</b> <code>{user_id}</code>\n"
        f"<b>📦 Orderlar soni:</b> {stats['orders']}\n"
        f"<b>👥 Referal:</b> {stats['referrals']} ta\n"
        f"<b>🎁 Skidka:</b> {stats['discount']}%\n"
        f"<b>🚫 Ban:</b> {'Ha' if stats['is_banned'] else 'Yo‘q'}\n"
        f"<b>👮 Roli:</b> {role_name(stats['role'])}"
    )


def user_orders_text(user_id: int) -> str:
    rows = get_user_orders(user_id)
    if not rows:
        return "Bu userda order yo‘q."
    return "<b>User orderlari:</b>\n" + "\n".join(
        [f"• <code>{row['order_id']}</code> — {esc(row['service'])} — <b>{row['status']}</b>" for row in rows]
    )


def top_users_text() -> str:
    rows = top_users(10)
    if not rows:
        return "Top userlar yo‘q."
    return "🏆 <b>Eng aktiv userlar</b>\n" + "\n".join(
        [f"• <code>{row['user_id']}</code> — <b>{row['total']}</b> ta order" for row in rows]
    )


@dp.message(CommandStart())
async def start_handler(message: Message):
    register_from_telegram(message.from_user)

    args = ""
    if message.text and len(message.text.split()) > 1:
        args = message.text.split(maxsplit=1)[1].strip()

    if args.startswith("ref_"):
        code = args.replace("ref_", "", 1)
        if code.isdigit():
            inviter_id = int(code)
            if inviter_id != message.from_user.id:
                added = add_referral(inviter_id, message.from_user.id)
                if added:
                    recalc_discount(inviter_id)

                    inviter = get_user(inviter_id)
                    inviter_name = None
                    if inviter:
                        if inviter["username"]:
                            inviter_name = f"@{inviter['username']}"
                        elif inviter["full_name"]:
                            inviter_name = inviter["full_name"]
                    if not inviter_name:
                        inviter_name = f"ID: {inviter_id}"

                    invited_name = (
                        f"@{message.from_user.username}"
                        if message.from_user.username
                        else (message.from_user.full_name or f"ID: {message.from_user.id}")
                    )
                    total_refs = get_referral_count(inviter_id)

                    await message.answer(
                        f"👤 Sizni {esc(inviter_name)} taklif qildi!"
                    )

                    try:
                        await bot.send_message(
                            inviter_id,
                            f"🎉 <b>+1 referal!</b>\n\n"
                            f"👤 {esc(invited_name)} sizning havolangiz orqali kirdi.\n"
                            f"👥 Jami referallar: <b>{total_refs} ta</b>"
                        )
                    except Exception as e:
                        logging.warning("Referral notification yuborilmadi: %s", e)

    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return

    await message.answer(
        "👋 <b>UNIPRO Agency</b> botiga xush kelibsiz.\n\nKerakli bo‘limni tanlang 👇",
        reply_markup=main_menu_kb(message.from_user.id),
    )


@dp.message(F.text == "👤 Profile")
async def profile_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return

    await message.answer(
        f"<b>👤 Profil</b>\n"
        f"<b>🆔 ID:</b> <code>{message.from_user.id}</code>\n"
        f"<b>👥 Referal:</b> {get_referral_count(message.from_user.id)} ta\n"
        f"<b>🎁 Skidka:</b> {get_discount(message.from_user.id)}%",
        reply_markup=profile_kb(),
    )


@dp.callback_query(F.data == "profile_ref")
async def profile_ref_handler(callback: CallbackQuery):
    register_from_telegram(callback.from_user)
    if is_banned_user(callback.from_user.id):
        await blocked_callback(callback)
        return

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{callback.from_user.id}"

    await callback.message.answer(
        f"<b>👥 Referal system</b>\n\n"
        f"<b>🔗 Sizning havolangiz:</b>\n<code>{ref_link}</code>\n\n"
        f"<b>👤 Qo‘shilgan odamlar:</b> {get_referral_count(callback.from_user.id)} ta\n"
        f"<b>🎁 Hozirgi skidka:</b> {get_discount(callback.from_user.id)}%\n\n"
        f"<b>Skidka darajalari:</b>\n"
        f"• 10 ta odam — 10%\n"
        f"• 25 ta odam — 20%\n"
        f"• 50 ta odam — 30%\n"
        f"• 100 ta odam — 40%\n"
        f"• 150 ta odam — 50%"
    )
    await callback.answer()


@dp.callback_query(F.data == "profile_orders")
async def profile_orders_handler(callback: CallbackQuery):
    register_from_telegram(callback.from_user)
    if is_banned_user(callback.from_user.id):
        await blocked_callback(callback)
        return

    kb = my_orders_kb(callback.from_user.id)
    if not kb:
        await callback.message.answer("Sizda hali order yo‘q.")
        await callback.answer()
        return

    await callback.message.answer("📦 Mening orderlarim:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("myorder:"))
async def myorder_handler(callback: CallbackQuery):
    register_from_telegram(callback.from_user)
    if is_banned_user(callback.from_user.id):
        await blocked_callback(callback)
        return

    order_id = int(callback.data.split(":")[1])
    order = get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Order topilmadi", show_alert=True)
        return

    await callback.message.answer(order_full_info_text(order))
    await callback.answer()


@dp.message(F.text == "⚙️ Admin panel")
@dp.message(Command("panel"))
async def panel_handler(message: Message, state: FSMContext):
    register_from_telegram(message.from_user)
    if not is_staff(message.from_user.id):
        await message.answer("Siz admin emassiz.")
        return
    await state.clear()
    await message.answer("⚙️ <b>Admin panel</b>", reply_markup=panel_main_kb())


@dp.callback_query(F.data == "panel_orders")
async def open_orders_panel(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.edit_text("📦 <b>Orderlar bo‘limi</b>", reply_markup=panel_orders_kb())
    await callback.answer()


@dp.callback_query(F.data == "panel_users")
async def open_users_panel(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.edit_text("👤 <b>Userlar bo‘limi</b>", reply_markup=panel_users_kb(is_superadmin(callback.from_user.id)))
    await callback.answer()


@dp.callback_query(F.data == "panel_broadcast")
async def open_broadcast_panel(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.edit_text("📢 <b>Broadcast bo‘limi</b>", reply_markup=panel_broadcast_kb())
    await callback.answer()


@dp.callback_query(F.data == "panel_admin_settings")
async def open_admin_settings_panel(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.edit_text("⚙️ <b>Admin sozlamalar</b>", reply_markup=panel_admin_settings_kb(is_superadmin(callback.from_user.id)))
    await callback.answer()


@dp.callback_query(F.data == "back_panel_main")
async def back_panel_main(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.edit_text("⚙️ <b>Admin panel</b>", reply_markup=panel_main_kb())
    await callback.answer()


@dp.callback_query(F.data == "orders_all")
async def orders_all(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(all_orders_text())
    await callback.answer()


@dp.callback_query(F.data == "orders_active")
async def orders_active(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(active_orders_text())
    await callback.answer()


@dp.callback_query(F.data == "orders_unaccepted")
async def orders_unaccepted(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(all_orders_text())
    await callback.answer()


@dp.callback_query(F.data == "orders_search")
async def orders_search(callback: CallbackQuery, state: FSMContext):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await state.set_state(PanelForm.search_order)
    await callback.message.answer("🔍 Order ID yuboring:")
    await callback.answer()


@dp.callback_query(F.data == "users_search")
async def users_search(callback: CallbackQuery, state: FSMContext):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await state.set_state(PanelForm.search_user)
    await callback.message.answer("👤 User ID yuboring:")
    await callback.answer()


@dp.callback_query(F.data == "users_all")
async def users_all(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(all_users_text())
    await callback.answer()


@dp.callback_query(F.data == "users_banned")
async def users_banned(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(banned_users_text())
    await callback.answer()


@dp.callback_query(F.data == "broadcast_all")
async def broadcast_all(callback: CallbackQuery, state: FSMContext):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    broadcast_targets_mode[callback.from_user.id] = "all"
    await state.set_state(PanelForm.broadcast_text)
    await callback.message.answer("📢 Hammaga yuboriladigan matnni yozing:")
    await callback.answer()


@dp.callback_query(F.data == "broadcast_active")
async def broadcast_active(callback: CallbackQuery, state: FSMContext):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    broadcast_targets_mode[callback.from_user.id] = "active"
    await state.set_state(PanelForm.broadcast_text)
    await callback.message.answer("📢 Faqat ban bo‘lmagan userlarga yuboriladigan matnni yozing:")
    await callback.answer()


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(stats_text() + "\n\n" + admin_stats_text() + "\n\n" + top_users_text())
    await callback.answer()


@dp.callback_query(F.data == "admin_logs")
async def admin_logs_handler(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return
    await callback.message.answer(recent_logs_text())
    await callback.answer()


@dp.callback_query(F.data == "admin_add_super")
async def admin_add_super(callback: CallbackQuery, state: FSMContext):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Faqat katta admin", show_alert=True)
        return
    await state.update_data(add_role="superadmin")
    await state.set_state(PanelForm.add_admin_ids)
    await callback.message.answer("🛡 Katta admin ID larini yuboring. Bir nechta bo‘lsa vergul yoki probel bilan yozing.")
    await callback.answer()


@dp.callback_query(F.data == "admin_add_normal")
async def admin_add_normal(callback: CallbackQuery, state: FSMContext):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Faqat katta admin", show_alert=True)
        return
    await state.update_data(add_role="admin")
    await state.set_state(PanelForm.add_admin_ids)
    await callback.message.answer("👮 Oddiy admin ID larini yuboring. Bir nechta bo‘lsa vergul yoki probel bilan yozing.")
    await callback.answer()


@dp.callback_query(F.data == "admin_remove")
async def admin_remove(callback: CallbackQuery, state: FSMContext):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Faqat katta admin", show_alert=True)
        return
    await state.set_state(PanelForm.remove_admin)
    await callback.message.answer("➖ Olib tashlamoqchi bo‘lgan admin ID ni yuboring:")
    await callback.answer()


@dp.callback_query(F.data == "admin_list")
async def admin_list(callback: CallbackQuery):
    if not is_superadmin(callback.from_user.id):
        await callback.answer("Faqat katta admin", show_alert=True)
        return
    await callback.message.answer(admins_text())
    await callback.answer()


@dp.message(PanelForm.add_admin_ids)
async def add_admin_state(message: Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer("Faqat katta admin.")
        await state.clear()
        return

    role = (await state.get_data()).get("add_role")
    parts = [x.strip() for x in (message.text or "").replace(",", " ").split() if x.strip()]
    if not parts:
        await message.answer("Kamida bitta ID yuboring.")
        return

    added = []
    skipped = []

    for part in parts:
        if not part.isdigit():
            skipped.append(f"{part} (xato)")
            continue
        uid = int(part)
        if uid == OWNER_ID:
            skipped.append(f"{uid} (owner)")
            continue

        register_user(uid, "", "")
        set_role(uid, role)
        add_log("ADMIN_ADDED", message.from_user.id, uid, role)
        added.append(uid)

        try:
            await bot.send_message(uid, "⚙️ Siz admin bo‘ldingiz!", reply_markup=main_menu_kb(uid))
            await bot.send_message(uid, "⚙️ <b>Admin panel</b>", reply_markup=panel_main_kb())
        except Exception:
            pass

    role_label = "Katta admin" if role == "superadmin" else "Oddiy admin"
    text = f"✅ <b>{role_label}</b> qo‘shish yakunlandi.\n\n"
    if added:
        text += "Qo‘shildi:\n" + "\n".join([f"• <code>{uid}</code>" for uid in added]) + "\n\n"
    if skipped:
        text += "O‘tkazib yuborildi:\n" + "\n".join([f"• {esc(x)}" for x in skipped])

    await message.answer(text)
    await state.clear()


@dp.message(PanelForm.remove_admin)
async def remove_admin_state(message: Message, state: FSMContext):
    if not is_superadmin(message.from_user.id):
        await message.answer("Faqat katta admin.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Faqat raqamli ID yuboring.")
        return

    uid = int(text)
    if uid == OWNER_ID:
        await message.answer("Ownerni o‘chirib bo‘lmaydi.")
        await state.clear()
        return

    if not is_staff(uid):
        await message.answer("Bu ID admin emas.")
        await state.clear()
        return

    delete_admin_role(uid)
    add_log("ADMIN_REMOVED", message.from_user.id, uid)

    try:
        await bot.send_message(uid, "❌ Siz adminlikdan olindingiz.", reply_markup=main_menu_kb(uid))
    except Exception:
        pass

    await message.answer(f"✅ Admin olib tashlandi: <code>{uid}</code>")
    await state.clear()


@dp.message(PanelForm.search_order)
async def search_order_state(message: Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        await message.answer("Faqat admin.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Faqat order ID yuboring.")
        return

    order = get_order(int(text))
    if not order:
        await message.answer("Order topilmadi.")
    else:
        await message.answer(order_info_text(order))
    await state.clear()


@dp.message(PanelForm.search_user)
async def search_user_state(message: Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        await message.answer("Faqat admin.")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Faqat user ID yuboring.")
        return

    await message.answer(user_info_text(int(text)))
    await state.clear()


@dp.message(F.text == "📢 Bizning kanalimiz")
async def channel_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Kanalga kirish", url=CHANNEL_LINK)]])
    await message.answer(f"📢 Kanal linki:\n{esc(CHANNEL_LINK)}", reply_markup=kb)


@dp.message(F.text == "🖼 Portfolio")
async def portfolio_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼 Portfolio", url=PORTFOLIO_LINK)]])
    await message.answer("🖼 Portfolio:", reply_markup=kb)


@dp.message(F.text == "📞 Biz bilan bog‘lanish")
async def contact_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📞 Admin bilan bog‘lanish", url="https://t.me/upagencyadmin")]])
    await message.answer("📞 Admin bilan bog‘lanish:", reply_markup=kb)


@dp.message(F.text == "🛠 Xizmatlar")
async def services_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    await message.answer("🛠 Xizmatlardan birini tanlang:", reply_markup=services_kb)


@dp.message(F.text == "⬅️ Orqaga")
async def back_handler(message: Message, state: FSMContext):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    await state.clear()
    await message.answer("🏠 Bosh menyu:", reply_markup=main_menu_kb(message.from_user.id))


@dp.message(F.text == "🌐 Web-sahifa yaratish")
async def web_service_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    item = build_service_card("web")
    await message.answer(item["card"], reply_markup=service_order_kb("web"))


@dp.message(F.text == "🤖 Telegram bot yaratish")
async def bot_service_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    item = build_service_card("bot")
    await message.answer(item["card"], reply_markup=service_order_kb("bot"))


@dp.message(F.text == "🎨 Dizayn xizmatlari")
async def design_service_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    item = build_service_card("design")
    await message.answer(item["card"], reply_markup=service_order_kb("design"))


@dp.callback_query(F.data.startswith("start:"))
async def start_order(callback: CallbackQuery, state: FSMContext):
    register_from_telegram(callback.from_user)
    if is_banned_user(callback.from_user.id):
        await blocked_callback(callback)
        return

    code = callback.data.split(":")[1]
    item = build_service_card(code)
    if not item:
        await callback.answer("Xizmat topilmadi", show_alert=True)
        return

    await state.clear()
    await state.update_data(service=item["name"], service_code=code)
    await state.set_state(OrderForm.need)
    await callback.message.answer(item["need_prompt"])
    await callback.answer()


@dp.message(OrderForm.need)
async def get_need(message: Message, state: FSMContext):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        await state.clear()
        return
    if is_blank(message.text):
        await message.answer("✍️ Iltimos, bu joyni bo‘sh qoldirmang.")
        return
    await state.update_data(need=message.text.strip())
    await state.set_state(OrderForm.deadline)
    await message.answer("⏰ Qachongacha tayyor bo‘lishi kerak?")


@dp.message(OrderForm.deadline)
async def get_deadline(message: Message, state: FSMContext):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        await state.clear()
        return
    if is_blank(message.text):
        await message.answer("⏰ Muddatni yozing.")
        return
    await state.update_data(deadline=message.text.strip())
    await state.set_state(OrderForm.budget)
    await message.answer("💰 Budjetingiz qancha?")


@dp.message(OrderForm.budget)
async def get_budget(message: Message, state: FSMContext):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        await state.clear()
        return
    if is_blank(message.text):
        await message.answer("💰 Budjetni to‘ldiring.")
        return

    await state.update_data(budget=message.text.strip())
    data = await state.get_data()

    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or "No name"
    order_id = random.randint(10000, 99999)
    while get_order(order_id):
        order_id = random.randint(10000, 99999)

    base_text = build_order_text(
        order_id=order_id,
        service=data.get("service", "-"),
        need=data.get("need", "-"),
        deadline=data.get("deadline", "-"),
        budget=message.text.strip(),
        full_name=full_name,
        username=username,
        user_id=user_id,
    ) + build_order_discount_note(user_id)

    try:
        sent = await bot.send_message(
            ADMIN_REVIEW_CHAT_ID,
            base_text,
            reply_markup=review_kb(user_id, order_id, "active"),
        )

        create_order(
            order_id=order_id,
            user_id=user_id,
            service=data.get("service", "-"),
            service_code=data.get("service_code", ""),
            need=data.get("need", "-"),
            deadline=data.get("deadline", "-"),
            budget=message.text.strip(),
            admin_chat_id=sent.chat.id,
            admin_message_id=sent.message_id,
            referrals=get_referral_count(user_id),
            discount=get_discount(user_id),
        )

        await message.answer(
            f"✅ Buyurtmangiz yuborildi!\n\n🆔 Buyurtma ID: <code>{order_id}</code>",
            reply_markup=main_menu_kb(message.from_user.id),
        )
    except Exception as e:
        logging.exception("Order send error: %s", e)
        await message.answer("❌ Buyurtmani yuborishda xatolik bo‘ldi.", reply_markup=main_menu_kb(message.from_user.id))

    await state.clear()


@dp.callback_query(F.data.startswith("accept:"))
async def accept_order(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return

    _, user_id_raw, order_id_raw = callback.data.split(":")
    user_id = int(user_id_raw)
    order_id = int(order_id_raw)
    order = get_order(order_id)

    if not order:
        await callback.answer("Buyurtma topilmadi", show_alert=True)
        return
    if order["status"] != "active":
        await callback.answer("Bu buyurtma allaqachon yakunlangan", show_alert=True)
        return

    admin_text = f"@{esc(callback.from_user.username)}" if callback.from_user.username else esc(callback.from_user.full_name or "Admin")
    update_order_status(order_id, "accepted")
    add_log("ORDER_ACCEPT", callback.from_user.id, user_id, f"order={order_id}")

    await callback.message.edit_text(
        build_order_with_status_text(
            build_order_text(order_id, order['service'], order['need'], order['deadline'], order['budget'], get_user(user_id)['full_name'] if get_user(user_id) else 'No name', get_user(user_id)['username'] if get_user(user_id) else '', user_id) + build_order_discount_note(user_id),
            "✅ Qabul qilindi",
            f"@{get_user(user_id)['username']}" if get_user(user_id) and get_user(user_id)['username'] else "Username yo‘q",
            user_id,
            admin_text,
        ),
        reply_markup=None,
    )
    await callback.answer("Buyurtma qabul qilindi")

    try:
        await bot.send_message(user_id, f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n<b>Buyurtma ID:</b> <code>{order_id}</code>\n<b>Admin:</b> {admin_text}")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("reject:"))
async def ask_reject_reason(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return

    _, user_id_raw, order_id_raw = callback.data.split(":")
    user_id = int(user_id_raw)
    order_id = int(order_id_raw)
    order = get_order(order_id)
    if not order or order["status"] != "active":
        await callback.answer("Buyurtma aktiv emas", show_alert=True)
        return

    save_pending_action(callback.from_user.id, "reject", user_id, order_id)
    await bot.send_message(callback.from_user.id, f"❌ <b>Rad etish sababi</b>ni yozing.\n<b>Buyurtma ID:</b> <code>{order_id}</code>")
    await callback.answer("Botga kiring va sabab yozing", show_alert=True)


@dp.callback_query(F.data.startswith("ban:"))
async def ask_ban_reason(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return

    _, user_id_raw, order_id_raw = callback.data.split(":")
    user_id = int(user_id_raw)
    order_id = int(order_id_raw)
    order = get_order(order_id)
    if not order or order["status"] != "active":
        await callback.answer("Buyurtma aktiv emas", show_alert=True)
        return
    if is_staff(user_id):
        await callback.answer("Adminni ban qilib bo‘lmaydi", show_alert=True)
        return
    save_pending_action(callback.from_user.id, "ban", user_id, order_id)
    await bot.send_message(callback.from_user.id, f"🚫 <b>Ban sababi</b>ni yozing.\n<b>Buyurtma ID:</b> <code>{order_id}</code>")
    await callback.answer("Botga kiring va sabab yozing", show_alert=True)


@dp.callback_query(F.data.startswith("unban:"))
async def unban_user_callback(callback: CallbackQuery):
    if not is_staff(callback.from_user.id):
        await callback.answer("Faqat admin", show_alert=True)
        return

    _, user_id_raw, order_id_raw = callback.data.split(":")
    user_id = int(user_id_raw)
    order_id = int(order_id_raw)
    order = get_order(order_id)
    if not order or order["status"] != "banned":
        await callback.answer("Bu user ban holatida emas", show_alert=True)
        return

    unban_user(user_id)
    update_order_status(order_id, "unbanned")
    admin_text = f"@{esc(callback.from_user.username)}" if callback.from_user.username else esc(callback.from_user.full_name or "Admin")
    add_log("UNBAN", callback.from_user.id, user_id, f"order={order_id}")

    user_row = get_user(user_id)
    user_text = f"@{user_row['username']}" if user_row and user_row['username'] else "Username yo‘q"
    await callback.message.edit_text(
        build_status_only_text("♻️ User ochildi", user_text, user_id, admin_text),
        reply_markup=None,
    )
    await callback.answer("User ochildi")

    try:
        await bot.send_message(user_id, "♻️ <b>Siz uchun blok olib tashlandi.</b>")
    except Exception:
        pass


@dp.message(F.chat.type == ChatType.PRIVATE)
async def process_private_messages(message: Message):
    register_from_telegram(message.from_user)

    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return

    pending = get_pending_action(message.from_user.id)
    if not pending:
        return

    if is_blank(message.text):
        await message.answer("Sababni bo‘sh qoldirmang.")
        return

    if not is_staff(message.from_user.id):
        delete_pending_action(message.from_user.id)
        return

    action_type = pending["action_type"]
    target_user_id = int(pending["target_user_id"])
    order_id = int(pending["order_id"])
    reason = message.text.strip()
    order = get_order(order_id)

    if not order or order["status"] != "active":
        await message.answer("Bu buyurtma aktiv emas.")
        delete_pending_action(message.from_user.id)
        return

    admin_text = f"@{esc(message.from_user.username)}" if message.from_user.username else esc(message.from_user.full_name or "Admin")
    target_user = get_user(target_user_id)
    target_user_text = f"@{target_user['username']}" if target_user and target_user['username'] else "Username yo‘q"
    base_text = build_order_text(order_id, order['service'], order['need'], order['deadline'], order['budget'], target_user['full_name'] if target_user else 'No name', target_user['username'] if target_user else '', target_user_id) + build_order_discount_note(target_user_id)

    if action_type == "reject":
        update_order_status(order_id, "rejected", reason)
        add_log("ORDER_REJECT", message.from_user.id, target_user_id, f"order={order_id}; reason={reason}")
        await bot.edit_message_text(
            chat_id=order["admin_chat_id"],
            message_id=order["admin_message_id"],
            text=build_order_with_status_text(base_text, "❌ Rad etildi", target_user_text, target_user_id, admin_text, reason),
            reply_markup=None,
        )
        try:
            await bot.send_message(target_user_id, f"❌ <b>Buyurtmangiz rad etildi.</b>\n\n<b>Buyurtma ID:</b> <code>{order_id}</code>\n<b>Admin:</b> {admin_text}\n<b>Sabab:</b> {esc(reason)}")
        except Exception:
            pass
        await message.answer("Rad etish sababi yuborildi.")

    elif action_type == "ban":
        if is_staff(target_user_id):
            delete_pending_action(message.from_user.id)
            await message.answer("Bu userni ban qilib bo‘lmaydi.")
            return

        ban_user(target_user_id, reason)
        update_order_status(order_id, "banned", reason)
        add_log("BAN", message.from_user.id, target_user_id, f"order={order_id}; reason={reason}")
        await bot.edit_message_text(
            chat_id=order["admin_chat_id"],
            message_id=order["admin_message_id"],
            text=build_status_only_text("🚫 Bu odam ban oldi", target_user_text, target_user_id, admin_text, reason),
            reply_markup=review_kb(target_user_id, order_id, "banned"),
        )
        try:
            await bot.send_message(target_user_id, f"🚫 <b>Siz botdan bloklandingiz.</b>\n\n<b>Buyurtma ID:</b> <code>{order_id}</code>\n<b>Admin:</b> {admin_text}\n<b>Sabab:</b> {esc(reason)}")
        except Exception:
            pass
        await message.answer("Ban sababi saqlandi va user bloklandi.")

    delete_pending_action(message.from_user.id)


@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    register_from_telegram(message.from_user)
    await state.clear()
    delete_pending_action(message.from_user.id)
    broadcast_targets_mode.pop(message.from_user.id, None)
    await message.answer("❌ Jarayon bekor qilindi.", reply_markup=main_menu_kb(message.from_user.id))


@dp.message()
async def fallback_handler(message: Message):
    register_from_telegram(message.from_user)
    if is_banned_user(message.from_user.id):
        await blocked_message(message)
        return
    await message.answer("Kerakli bo‘limni tugmalar orqali tanlang 👇", reply_markup=main_menu_kb(message.from_user.id))


async def main():
    init_db(OWNER_ID)
    await start_web_server() # Юқорида берган веб-сервер функциям
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
