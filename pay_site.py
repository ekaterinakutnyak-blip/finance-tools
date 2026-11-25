# -*- coding: utf-8 -*-
"""
Оплата PRO-доступа прямо на сайте investtools.pro.

Телеграм-бот (он на другом сервере) этим кодом не затрагивается: здесь делается
второй вход в ту же кассу ЮKassa и в ту же базу токенов.

Персональные данные сайт НЕ собирает: ни почты, ни имени. Человек выбирает срок
и уходит на страницу кассы — всё остальное происходит там.

Подключается в main.py двумя строками:
    from pay_site import router as pay_router
    app.include_router(pay_router)

Нужные переменные в /opt/finance-api/.env:
    YOOKASSA_SHOP_ID=...
    YOOKASSA_SECRET_KEY=...
"""

import os
import uuid
import sqlite3
import secrets
import string
import logging
from datetime import datetime, timedelta

import requests
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter()

DB_PATH = "/opt/finance-api/db.sqlite"
SITE = "https://investtools.pro"
YK_API = "https://api.yookassa.ru/v3/payments"

SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# Адрес для чека. Сайт почту у покупателя не спрашивает, поэтому здесь стоит
# ровно тот же служебный адрес, что уже много месяцев подставляет телеграм-бот.
# Так оплата с сайта и оплата из бота ведут себя в кассе одинаково.
RECEIPT_EMAIL = "noreply@privatemoney.org"

# ЕДИНСТВЕННЫЙ источник цен. Из браузера приходит только код тарифа:
# цена никогда не приходит от клиента, иначе год можно купить за рубль.
PLANS = {
    "m1": {"price": 700,  "days": 30,  "title": "PRO-доступ к investtools.pro, 1 месяц"},
    "m3": {"price": 1800, "days": 90,  "title": "PRO-доступ к investtools.pro, 3 месяца"},
    "m6": {"price": 3000, "days": 180, "title": "PRO-доступ к investtools.pro, 6 месяцев"},
    "y1": {"price": 5400, "days": 365, "title": "PRO-доступ к investtools.pro, 1 год"},
}


def _db():
    return sqlite3.connect(DB_PATH)


def _init():
    """Таблица заказов сайта: по своему номеру заказа находим платёж в кассе."""
    conn = _db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_orders (
            oid        TEXT PRIMARY KEY,
            payment_id TEXT NOT NULL,
            plan       TEXT NOT NULL,
            user_id    INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init()


def _new_token() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def _user_id_for(prev_token):
    """
    Покупателю с сайта нужен числовой user_id — такой же, как telegram id у бота,
    иначе сохранённые портфели не к чему привязать.

    Почты мы не спрашиваем, поэтому постоянство делается иначе: при продлении
    браузер присылает свой прежний токен, и мы берём его user_id. Тогда человек
    попадает в свою же учётную запись и ничего не теряет. Нет прежнего токена —
    выдаём новый случайный номер. Отрицательный, чтобы никогда не пересечься
    с настоящими telegram id.
    """
    if prev_token:
        t = str(prev_token).strip().upper()[:64]
        conn = _db()
        row = conn.execute("SELECT user_id FROM tokens WHERE token = ?", (t,)).fetchone()
        conn.close()
        if row and int(row[0]) < 0:
            return int(row[0])
    return -(secrets.randbelow(2_000_000_000) + 1)


# ---------------------------------------------------------------- шаг 1: создание платежа

@router.post("/api/site/pay")
async def site_pay(request: Request):
    body = await request.json()
    plan = str(body.get("plan", "")).strip()
    prev_token = body.get("prev_token")

    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Неизвестный тариф")
    if not SHOP_ID or not SECRET_KEY:
        logger.error("site pay: в .env нет YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY")
        raise HTTPException(status_code=500, detail="Оплата на сайте временно недоступна")

    p = PLANS[plan]
    oid = secrets.token_urlsafe(16)
    user_id = _user_id_for(prev_token)
    amount = f"{p['price']}.00"

    payload = {
        "amount": {"value": amount, "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"{SITE}/oplata-gotovo.html?o={oid}",
        },
        "description": p["title"],
        "metadata": {"user_id": str(user_id), "source": "site", "plan": plan, "oid": oid},
        "receipt": {
            "customer": {"email": RECEIPT_EMAIL},
            "items": [{
                "description": p["title"],
                "quantity": "1",
                "amount": {"value": amount, "currency": "RUB"},
                "vat_code": 1,
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }],
        },
    }

    try:
        r = requests.post(
            YK_API,
            auth=(SHOP_ID, SECRET_KEY),
            headers={"Idempotence-Key": str(uuid.uuid4()), "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        payment_id = data["id"]
        confirmation_url = data["confirmation"]["confirmation_url"]
    except Exception:
        logger.exception("site pay: касса не приняла платёж")
        raise HTTPException(status_code=502, detail="Касса не отвечает, попробуйте через минуту")

    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO site_orders (oid, payment_id, plan, user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (oid, payment_id, plan, user_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    logger.info("site pay: создан платёж %s, тариф %s, заказ %s", payment_id, plan, oid)
    return {"oid": oid, "confirmation_url": confirmation_url}


# ---------------------------------------------------------------- шаг 2: выдача токена

@router.get("/api/site/token")
def site_token(o: str):
    """
    Страница «оплата прошла» спрашивает сюда раз в пару секунд.

    Важное: возврат человека на страницу успеха НЕ считается подтверждением
    оплаты — этот адрес может открыть кто угодно. Статус спрашиваем у самой кассы
    своими ключами и сверяем сумму со своим прайсом. Сообщению вебхука не доверяем.
    """
    if not o or len(o) > 64:
        raise HTTPException(status_code=400, detail="Заказ не найден")

    conn = _db()
    row = conn.execute(
        "SELECT payment_id, plan, user_id FROM site_orders WHERE oid = ?", (o,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    payment_id, plan, user_id = row

    # Токен за этот платёж уже выдан — отдаём тот же самый.
    conn = _db()
    issued = conn.execute(
        "SELECT token, expires_at FROM tokens WHERE payment_id = ? ORDER BY created_at LIMIT 1",
        (payment_id,),
    ).fetchone()
    conn.close()
    if issued:
        return {"status": "succeeded", "token": issued[0], "expires_at": issued[1]}

    if not SHOP_ID or not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Оплата на сайте временно недоступна")

    try:
        r = requests.get(f"{YK_API}/{payment_id}", auth=(SHOP_ID, SECRET_KEY), timeout=20)
        r.raise_for_status()
        pay = r.json()
    except Exception:
        logger.exception("site pay: касса не ответила по платежу %s", payment_id)
        return {"status": "pending"}

    status = pay.get("status")
    if status != "succeeded":
        return {"status": status or "pending"}

    # Сверяем сумму с собственным прайсом — на случай подмены платежа.
    try:
        paid = round(float(pay["amount"]["value"]))
    except Exception:
        paid = -1
    if plan not in PLANS or paid != PLANS[plan]["price"]:
        logger.error("site pay: сумма не сходится, платёж %s, пришло %s", payment_id, paid)
        raise HTTPException(status_code=409, detail="Сумма платежа не совпадает с тарифом")

    now = datetime.utcnow()
    expires = now + timedelta(days=PLANS[plan]["days"])
    token = _new_token()

    conn = _db()
    cur = conn.cursor()
    # строка в payments — чтобы оплата с сайта была видна там же, где оплаты из бота
    cur.execute(
        "INSERT OR REPLACE INTO payments (payment_id, user_id, amount, status, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (payment_id, user_id, float(paid), "succeeded", now.isoformat()),
    )
    # ещё раз под замком базы: вдруг параллельный запрос успел выдать токен
    again = cur.execute(
        "SELECT token, expires_at FROM tokens WHERE payment_id = ? ORDER BY created_at LIMIT 1",
        (payment_id,),
    ).fetchone()
    if again:
        conn.commit()
        conn.close()
        return {"status": "succeeded", "token": again[0], "expires_at": again[1]}

    cur.execute(
        "INSERT INTO tokens (token, user_id, payment_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (token, user_id, payment_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()

    logger.info("site pay: выдан токен за платёж %s, тариф %s", payment_id, plan)
    return {"status": "succeeded", "token": token, "expires_at": expires.isoformat()}
