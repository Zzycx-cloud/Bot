import os
import sqlite3
from contextlib import closing
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
DB_NAME = os.getenv("DB_NAME", "bot.db")


def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(owner_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                role TEXT DEFAULT 'user',
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT DEFAULT '',
                is_whitelisted INTEGER DEFAULT 0,
                referred_by INTEGER,
                discount INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                service TEXT,
                service_code TEXT,
                need TEXT,
                deadline TEXT,
                budget TEXT,
                status TEXT DEFAULT 'active',
                admin_chat_id INTEGER,
                admin_message_id INTEGER,
                referrals INTEGER DEFAULT 0,
                discount INTEGER DEFAULT 0,
                reject_reason TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                invited_id INTEGER PRIMARY KEY,
                inviter_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL,
                target_id INTEGER,
                action TEXT NOT NULL,
                extra TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                admin_id INTEGER PRIMARY KEY,
                action_type TEXT NOT NULL,
                target_user_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        cur.execute(
            "INSERT OR IGNORE INTO users (user_id, role, full_name) VALUES (?, 'owner', 'Owner')",
            (owner_id,),
        )

        conn.commit()


# ---------------- users ----------------
def register_user(user_id: int, username: str = "", full_name: str = ""):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
            """,
            (user_id, username or "", full_name or ""),
        )
        conn.commit()


def get_user(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone()


def get_all_user_ids(active_only: bool = False):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        if active_only:
            cur.execute("SELECT user_id FROM users WHERE is_banned = 0")
        else:
            cur.execute("SELECT user_id FROM users")
        return [row["user_id"] for row in cur.fetchall()]




def get_all_users():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, full_name, role, is_banned, created_at FROM users ORDER BY created_at DESC, user_id DESC")
        return cur.fetchall()

def set_role(user_id: int, role: str):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()


def delete_admin_role(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET role = 'user' WHERE user_id = ?", (user_id,))
        conn.commit()


def get_admin_role(user_id: int) -> Optional[str]:
    row = get_user(user_id)
    return row["role"] if row else None


def is_staff(user_id: int) -> bool:
    role = get_admin_role(user_id)
    return role in ("owner", "superadmin", "admin")


def is_superadmin(user_id: int) -> bool:
    role = get_admin_role(user_id)
    return role in ("owner", "superadmin")


def get_admins():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, role FROM users WHERE role IN ('admin', 'superadmin', 'owner') ORDER BY user_id")
        return cur.fetchall()


def ban_user(user_id: int, reason: str):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?",
            (reason, user_id),
        )
        conn.commit()


def unban_user(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_banned = 0, ban_reason = '' WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def is_banned_user(user_id: int) -> bool:
    row = get_user(user_id)
    return bool(row and row["is_banned"] == 1)


def get_ban_reason(user_id: int) -> str:
    row = get_user(user_id)
    return row["ban_reason"] if row and row["ban_reason"] else "Sabab ko‘rsatilmagan"


def get_banned_users():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, ban_reason FROM users WHERE is_banned = 1 ORDER BY user_id")
        return cur.fetchall()


def add_whitelist(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_whitelisted = 1 WHERE user_id = ?", (user_id,))
        conn.commit()


def remove_whitelist(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_whitelisted = 0 WHERE user_id = ?", (user_id,))
        conn.commit()


def is_whitelisted(user_id: int) -> bool:
    row = get_user(user_id)
    return bool(row and row["is_whitelisted"] == 1)


def get_whitelist_users():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE is_whitelisted = 1 ORDER BY user_id")
        return [row["user_id"] for row in cur.fetchall()]


def get_user_order_count(user_id: int) -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM orders WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row["total"] if row else 0


def top_users(limit: int = 10):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, COUNT(*) AS total
            FROM orders
            GROUP BY user_id
            ORDER BY total DESC, user_id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


def get_user_stats(user_id: int):
    row = get_user(user_id)
    if not row:
        return None
    return {
        "user_id": user_id,
        "orders": get_user_order_count(user_id),
        "referrals": get_referral_count(user_id),
        "discount": row["discount"],
        "is_banned": row["is_banned"],
        "role": row["role"],
    }


# ---------------- referrals ----------------
def add_referral(inviter_id: int, invited_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM referrals WHERE invited_id = ?", (invited_id,))
        exists = cur.fetchone()
        if exists:
            return False

        cur.execute(
            "INSERT INTO referrals (invited_id, inviter_id) VALUES (?, ?)",
            (invited_id, inviter_id),
        )
        cur.execute(
            "UPDATE users SET referred_by = ? WHERE user_id = ? AND (referred_by IS NULL OR referred_by = '')",
            (inviter_id, invited_id),
        )
        conn.commit()
        return True


def get_referral_count(user_id: int) -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM referrals WHERE inviter_id = ?", (user_id,))
        row = cur.fetchone()
        return row["total"] if row else 0


def recalc_discount(user_id: int) -> int:
    count = get_referral_count(user_id)
    if count >= 150:
        discount = 50
    elif count >= 100:
        discount = 40
    elif count >= 50:
        discount = 30
    elif count >= 25:
        discount = 20
    elif count >= 10:
        discount = 10
    else:
        discount = 0

    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET discount = ? WHERE user_id = ?", (discount, user_id))
        conn.commit()

    return discount


def get_discount(user_id: int) -> int:
    row = get_user(user_id)
    return row["discount"] if row else 0


# ---------------- orders ----------------
def create_order(
    order_id: int,
    user_id: int,
    service: str,
    service_code: str,
    need: str,
    deadline: str,
    budget: str,
    admin_chat_id: int,
    admin_message_id: int,
    referrals: int,
    discount: int,
):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO orders (
                order_id, user_id, service, service_code, need, deadline, budget,
                status, admin_chat_id, admin_message_id, referrals, discount
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                order_id,
                user_id,
                service,
                service_code,
                need,
                deadline,
                budget,
                admin_chat_id,
                admin_message_id,
                referrals,
                discount,
            ),
        )
        conn.commit()


def get_order(order_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        return cur.fetchone()


def get_user_orders(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return cur.fetchall()


def update_order_status(order_id: int, status: str, reject_reason: str = ""):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE orders SET status = ?, reject_reason = ? WHERE order_id = ?",
            (status, reject_reason, order_id),
        )
        conn.commit()


def get_orders_by_status(status: str):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", (status,))
        return cur.fetchall()


def get_finished_orders():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE status IN ('accepted', 'rejected', 'banned', 'unbanned') ORDER BY created_at DESC"
        )
        return cur.fetchall()


def get_orders_by_service(service_code: str):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE status = 'active' AND service_code = ? ORDER BY created_at DESC",
            (service_code,),
        )
        return cur.fetchall()


def count_all_orders() -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM orders")
        row = cur.fetchone()
        return row["total"] if row else 0


# ---------------- logs ----------------
def add_log(action: str, actor_id: int, target_id: int | None = None, extra: str = ""):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO admin_logs (actor_id, target_id, action, extra) VALUES (?, ?, ?, ?)",
            (actor_id, target_id, action, extra),
        )
        conn.commit()


def get_recent_logs(limit: int = 20):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()


def get_admin_action_counts():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT actor_id, COUNT(*) AS total FROM admin_logs GROUP BY actor_id ORDER BY total DESC, actor_id ASC"
        )
        return cur.fetchall()


# ---------------- pending actions ----------------
def save_pending_action(admin_id: int, action_type: str, target_user_id: int, order_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_actions (admin_id, action_type, target_user_id, order_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(admin_id) DO UPDATE SET
                action_type = excluded.action_type,
                target_user_id = excluded.target_user_id,
                order_id = excluded.order_id
            """,
            (admin_id, action_type, target_user_id, order_id),
        )
        conn.commit()


def get_pending_action(admin_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM pending_actions WHERE admin_id = ?", (admin_id,))
        return cur.fetchone()


def delete_pending_action(admin_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM pending_actions WHERE admin_id = ?", (admin_id,))
        conn.commit()


# ---------------- stats ----------------
def total_users_count() -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM users")
        row = cur.fetchone()
        return row["total"] if row else 0


def banned_users_count() -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM users WHERE is_banned = 1")
        row = cur.fetchone()
        return row["total"] if row else 0


def admins_count() -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM users WHERE role IN ('owner', 'superadmin', 'admin')")
        row = cur.fetchone()
        return row["total"] if row else 0
