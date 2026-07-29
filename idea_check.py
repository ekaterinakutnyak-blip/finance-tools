# idea_check.py — эндпоинт «Проверка идеи» (Оптимист против пессимиста).
# Подключаемый роутер: main.py трогать не режем, только добавим 2 строки в конец.
# САМОДОСТАТОЧНЫЙ: подписку проверяет через существующий /api/check,
# счётчик — в своём файле idea_usage.db (основную базу не трогает).
# Модель — Alice (дёшево, ~1₽/разбор). Лимит 15 разборов/месяц на PRO.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3, datetime, requests
from yandex_ai import call_model, _load, MODEL_IDEA

router = APIRouter()

PROMPT_IDEA = _load("/opt/finance-api/prompts/optimist_pessimist.txt")
IDEA_DB = "/opt/finance-api/idea_usage.db"
CHECK_URL = "https://investtools.pro/api/check"
MONTHLY_LIMIT = 15
MAX_INPUT_CHARS = 4000


class IdeaIn(BaseModel):
    token: str
    text: str


def _token_valid(token: str) -> bool:
    try:
        r = requests.get(CHECK_URL, params={"token": token}, timeout=10)
        return bool(r.json().get("valid"))
    except Exception:
        return False


def _month():
    return datetime.date.today().strftime("%Y-%m")


def _used(token):
    con = sqlite3.connect(IDEA_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS idea_usage
                   (token TEXT, month TEXT, cnt INTEGER, PRIMARY KEY(token, month))""")
    row = con.execute("SELECT cnt FROM idea_usage WHERE token=? AND month=?",
                      (token, _month())).fetchone()
    con.close()
    return row[0] if row else 0


def _bump(token):
    con = sqlite3.connect(IDEA_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS idea_usage
                   (token TEXT, month TEXT, cnt INTEGER, PRIMARY KEY(token, month))""")
    con.execute("""INSERT INTO idea_usage(token, month, cnt) VALUES(?,?,1)
                   ON CONFLICT(token, month) DO UPDATE SET cnt = cnt + 1""",
                (token, _month()))
    con.commit(); con.close()


@router.post("/api/idea-check")
async def idea_check(payload: IdeaIn):
    token = (payload.token or "").strip().upper()
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Опишите идею")
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]

    if not _token_valid(token):
        raise HTTPException(status_code=403, detail="Проверка своей идеи доступна по подписке")

    used = _used(token)
    if used >= MONTHLY_LIMIT:
        raise HTTPException(status_code=402,
                            detail=f"Лимит {MONTHLY_LIMIT} разборов в этом месяце исчерпан")

    try:
        result = call_model(PROMPT_IDEA, text, model=MODEL_IDEA, max_output_tokens=3000)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Модель недоступна: {e}")

    _bump(token)
    return {"analysis": result, "left_this_month": max(0, MONTHLY_LIMIT - (used + 1))}
