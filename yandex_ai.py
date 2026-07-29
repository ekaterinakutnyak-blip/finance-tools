# yandex_ai.py — вызов моделей Яндекса через OpenAI-совместимый Responses API.
# Снято из «Посмотреть код» в AI Studio. Живёт рядом с main.py (/opt/finance-api).
#
#   pip install requests
#   export YANDEX_API_KEY="AQV...ключ..."   (только на сервере, НЕ во фронте!)
#
# Лимит 7000 токенов — это был дефолт ассистента, НЕ модели. Через Responses API
# доступен полный контекст. Проверка идей идёт на дешёвой модели, разбор эмитента — на Qwen.

import os
import requests

YANDEX_FOLDER = "b1gqud4dcqb3vrvb50gi"
YANDEX_URL = "https://ai.api.cloud.yandex.net/v1/responses"

# Модели под продукты:
MODEL_IDEA = "aliceai-llm-flash/latest"       # «Проверка идей» — проверена на этой задаче, ~1₽/разбор (вход 0,1 / выход 0,2)
MODEL_REPORT = "qwen3-235b-a22b-fp8/latest"   # «Разбор эмитента» — большой отчёт, нужен сильный+длинный контекст
# (DeepSeek v4 flash — резервный вариант, если захочется более «живого» голоса; ~3₽/разбор)


def call_model(instructions: str, user_input: str, model: str = MODEL_IDEA,
               max_output_tokens: int = 3000, temperature: float = 0.3, timeout: int = 120) -> str:
    """instructions = системный промт продукта; user_input = текст пользователя/снапшот/отчёт."""
    api_key = os.environ["YANDEX_API_KEY"]
    body = {
        "model": f"gpt://{YANDEX_FOLDER}/{model}",
        "temperature": temperature,
        "instructions": instructions,
        "input": user_input,
        "max_output_tokens": max_output_tokens,
    }
    r = requests.post(
        YANDEX_URL,
        headers={"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"},
        json=body, timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()  # {"output": [{"content": [{"text": "..."}]}]}
    for out in data.get("output", []):
        content = out.get("content", [])
        if content and content[0].get("text"):
            return content[0]["text"]
    raise RuntimeError(f"Пустой ответ модели: {data}")


def _load(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()
