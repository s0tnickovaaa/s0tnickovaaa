import os

# Путь к директории с векторной БД
CHROMA_DB_PATH = "./chroma_db"

# Имя коллекции в Chroma
COLLECTION_NAME = "university_knowledge"

# Модель для эмбеддингов (локальная, sentence-transformers)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Настройки OpenAI (если используется)
OPENAI_API_KEY = "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"
OPENAI_MODEL = "llama-3.3-70b-versatile"

# Настройки локальной LLM (Ollama)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "mistral"  # или "llama2", "gemma" и т.д.

# Выбор типа LLM: "openai", "ollama" или "dummy"
LLM_TYPE = "openai"  # dummy - заглушка