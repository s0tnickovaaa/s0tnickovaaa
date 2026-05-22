import os
import glob
from sentence_transformers import SentenceTransformer
import chromadb
from config import CHROMA_DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL

print("Загрузка модели эмбеддингов...")
embedder = SentenceTransformer(EMBEDDING_MODEL)

client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

try:
    client.delete_collection(COLLECTION_NAME)
except:
    pass
collection = client.create_collection(name=COLLECTION_NAME)

def parse_qa_blocks(file_content):
    blocks = []
    current_block = []
    for line in file_content.splitlines():
        if line.strip() == "" and current_block:
            blocks.append("\n".join(current_block).strip())
            current_block = []
        elif line.strip():
            current_block.append(line.strip())
    if current_block:
        blocks.append("\n".join(current_block).strip())
    return blocks

data_files = glob.glob("data/*.txt")
all_chunks = []
all_metadatas = []
all_ids = []

chunk_id = 0
for file_path in data_files:
    filename = os.path.basename(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    blocks = parse_qa_blocks(text)
    for i, block in enumerate(blocks):
        all_chunks.append(block)
        all_metadatas.append({"source": filename, "block": i})
        all_ids.append(f"{filename}_{i}")
        chunk_id += 1

print(f"Всего чанков (блоков): {len(all_chunks)}")

batch_size = 64
for i in range(0, len(all_chunks), batch_size):
    batch_chunks = all_chunks[i:i+batch_size]
    batch_ids = all_ids[i:i+batch_size]
    batch_metadatas = all_metadatas[i:i+batch_size]
    print(f"Обработка батча {i//batch_size + 1}/{(len(all_chunks)-1)//batch_size + 1}")
    embeddings = embedder.encode(batch_chunks).tolist()
    collection.add(
        embeddings=embeddings,
        documents=batch_chunks,
        metadatas=batch_metadatas,
        ids=batch_ids
    )

print("База знаний успешно загружена в ChromaDB")