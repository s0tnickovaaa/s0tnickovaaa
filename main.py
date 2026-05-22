import os
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import chromadb
from sentence_transformers import SentenceTransformer
import openai
import requests
from config import (
    CHROMA_DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    LLM_TYPE
)
import torch
import sounddevice as sd
import numpy as np
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Создаем пул потоков для TTS, чтобы не блокировать основной цикл
executor = ThreadPoolExecutor(max_workers=1)

def speak_with_silero(text):
    # Загружаем компактную русскую модель
    device = torch.device('cpu')
    model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models',
                               model='silero_tts',
                               language='ru',
                               speaker='v5_4_ru',
                               trust_repo=True)
    model.to(device)
    
    # Генерируем аудио
    audio = model.apply_tts(text=text, speaker='kseniya', sample_rate=48000)
    
    # Воспроизводим
    sd.play(audio, 48000)
    sd.wait()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация FastAPI
app = FastAPI(title="Virtual Anthropomorphic Guide")

# Подключаем статические файлы (фронтенд)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Инициализация векторной БД и модели эмбеддингов
logger.info("Подключение к ChromaDB...")
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_collection(COLLECTION_NAME)
logger.info("Загрузка модели эмбеддингов...")
embedder = SentenceTransformer(EMBEDDING_MODEL)

# Настройка OpenAI, если используется
if LLM_TYPE == "openai" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    logger.info("OpenAI API настроен")
elif LLM_TYPE == "ollama":
    logger.info(f"Будет использоваться локальная LLM через Ollama: {OLLAMA_MODEL}")
else:
    logger.info("Режим заглушки (dummy) — ответы будут браться из базы знаний без генерации")

# Модели запроса/ответа
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    animation: str

# Хранилище истории диалогов (по IP-адресу)
conversations = {}

def get_session_id(request: Request) -> str:
    """Получаем идентификатор сессии по IP"""
    if request.client:
        return request.client.host
    return "default"

def get_conversation_history(session_id: str, limit: int = 7):
    """Возвращает последние limit сообщений в формате для OpenAI"""
    if session_id not in conversations:
        conversations[session_id] = []
    # Возвращаем последние limit сообщений
    return conversations[session_id][-limit:]

def add_to_conversation(session_id: str, role: str, content: str):
    """Добавляет сообщение в историю"""
    if session_id not in conversations:
        conversations[session_id] = []
    conversations[session_id].append({"role": role, "content": content})
    # Храним только последние 50, чтобы не переполнять память
    if len(conversations[session_id]) > 50:
        conversations[session_id] = conversations[session_id][-50:]

def simple_web_search(query: str) -> str:
    """Очень простой поиск по ключевым словам"""
    q = query.lower()
    
    answers = {
        "сайт": "Официальный сайт Московского Политеха: https://mospolytech.ru",
        "официальный сайт": "https://mospolytech.ru",
        "адрес": "Москва, ул. Большая Семёновская, 38",
        "где находитесь": "Москва, ул. Большая Семёновская, 38",
        "как добраться": "Москва, ул. Большая Семёновская, 38. Ближайшее метро — Электрозаводская",
        "приёмная комиссия": "https://mospolytech.ru/abiturient/priemnaya-komissiya/",
        "расписание": "https://mospolytech.ru/students/raspisanie/",
        "телефон": "Приёмная комиссия: +7 (495) 123-45-67",
        "почта": "E-mail: priem@mospolytech.ru"
    }
    
    for keyword, answer in answers.items():
        if keyword in q:
            return answer
    return None

# Эндпоинт для конфига анимаций
@app.get("/animations")
async def get_animations():
    return {"idle": "idle.png", "talking": "talking.png"}

# Эндпоинт для чата
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    user_message = request.message
    logger.info(f"Получено сообщение: {user_message}")
    
    # Получаем ID сессии
    session_id = get_session_id(http_request)
    
    # Добавляем сообщение пользователя в историю
    add_to_conversation(session_id, "user", user_message)

    # 1. Сначала пробуем простой поиск по сайту
    quick_answer = simple_web_search(user_message)
    if quick_answer:
        reply = quick_answer
    else:
        # 2. Пробуем найти в ChromaDB
        documents = []
        try:
            query_embedding = embedder.encode(user_message).tolist()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=2,
                include=["documents"]
            )
            documents = results["documents"][0] if results["documents"] else []
        except Exception as e:
            logger.warning(f"Ошибка ChromaDB: {e}")

        # 3. Формируем системный промпт для более естественных ответов
        if documents:
            context = "\n".join(documents)
            system_prompt = f"""Ты — дружелюбный и живой гид по Московскому Политеху. 
Говори ТЕПЛО, ЕСТЕСТВЕННО и с энтузиазмом, как настоящий человек.

База знаний: {context}

Важные правила для ЕСТЕСТВЕННОЙ речи:
- Используй разговорные фразы и вводные слова ("ну", "знаете", "кстати", "вообще")
- Добавляй эмоциональные междометия ("ого!", "здорово!", "представляете?")
- Используй эмодзи умеренно, но для эмоций
- Не будь сухим и официальным - ты живой человек!
- Отвечай как в реальном разговоре, с теплотой
- Если не знаешь - скажи мягко и предложи помощь с другим вопросом
- Можешь иногда переспрашивать для уточнения"""
        else:
            system_prompt = """Ты — дружелюбный и живой гид по Московскому Политеху.
Говори ТЕПЛО, ЕСТЕСТВЕННО и с энтузиазмом, как настоящий человек.

Важные правила для ЕСТЕСТВЕННОЙ речи:
- Используй разговорные фразы и вводные слова ("ну", "знаете", "кстати", "вообще")
- Добавляй эмоциональные междометия ("ого!", "здорово!", "представляете?")
- Используй эмодзи умеренно, но для эмоций
- Не будь сухим и официальным - ты живой человек!
- Отвечай как в реальном разговоре, с теплотой
- Если не знаешь - скажи мягко и предложи помощь с другим вопросом
- Можешь иногда переспрашивать для уточнения"""

        # 4. Получаем историю последних 7 сообщений
        history = get_conversation_history(session_id, limit=7)
        
        # 5. Формируем полный список сообщений для модели
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)  # добавляем историю диалога
        
        # 6. Запрос к Groq
        try:
            groq_openai = openai
            groq_openai.api_key = OPENAI_API_KEY
            groq_openai.api_base = "https://api.groq.com/openai/v1"
            
            response = await groq_openai.ChatCompletion.acreate(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.8,  # повысили для большей живости и естественности
                max_tokens=200    # увеличили для более полных ответов
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            reply = "Ой, что-то пошло не так 😕 Попробуй ещё раз!"

    # Добавляем ответ бота в историю
    add_to_conversation(session_id, "assistant", reply)
    
    # Запускаем озвучку асинхронно, чтобы не блокировать ответ
    # Но с небольшой задержкой, чтобы сообщение появилось раньше
    async def delayed_speak():
        await asyncio.sleep(0.3)  # 300ms задержка перед озвучкой
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, speak_with_silero, reply)
    
    # Запускаем озвучку в фоне
    asyncio.create_task(delayed_speak())

    return ChatResponse(reply=reply, animation="talking")

# Корневой эндпоинт: отдаём index.html
@app.get("/")
async def root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)