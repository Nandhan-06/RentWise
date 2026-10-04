"""
build_kb_index.py — Module 5: offline knowledge-base indexing step

Run this ONCE (and again any time you edit files in knowledge_base/):

    python build_kb_index.py

This is deliberately a separate, manually-run script rather than
something that runs at server startup — per the SRS architecture
(Section 7.3.1): "documents are chunked and embedded offline, ahead of
runtime." Embedding on every server restart would be slow and would
burn API quota for no reason, since the knowledge base rarely changes.

What it does:
  1. Reads every .md file in knowledge_base/
  2. Splits each on "## " headings into one chunk per section
  3. Calls the Gemini embedding API (task_type=RETRIEVAL_DOCUMENT) for
     each chunk
  4. Saves everything to kb_index.json, which ai_service.py loads at
     runtime for semantic search — no embedding calls happen per chat
     message, only one call to embed the user's question.

Requires GEMINI_API_KEY to be set (same key as Module 4).
"""

import json
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge_base")
INDEX_PATH = os.path.join(os.path.dirname(__file__), "kb_index.json")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBED_DIMENSIONS = 768  # Google's recommended balance of quality vs. storage size


def chunk_markdown(text: str, source: str) -> list[dict]:
    """Split on '## ' headings; each section becomes one retrievable chunk."""
    sections = re.split(r"\n(?=## )", text.strip())
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or section.startswith("# "):
            # Skip the top-level "# Title" line if it ends up alone
            if "\n" not in section:
                continue
        heading_match = re.match(r"##\s*(.+)", section)
        heading = heading_match.group(1).strip() if heading_match else source
        chunks.append({"source": source, "heading": heading, "text": section})
    return chunks


def load_all_chunks() -> list[dict]:
    chunks = []
    if not os.path.isdir(KB_DIR):
        print(f"No knowledge_base/ folder found at {KB_DIR}")
        return chunks

    for filename in sorted(os.listdir(KB_DIR)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(KB_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        chunks.extend(chunk_markdown(text, source=filename))
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set. Add it to .env and try again.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    indexed = []

    for i, chunk in enumerate(chunks, start=1):
        print(f"Embedding chunk {i}/{len(chunks)}: {chunk['source']} — {chunk['heading']}")
        response = client.models.embed_content(
            model=EMBED_MODEL,
            contents=chunk["text"],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBED_DIMENSIONS,
                title=chunk["heading"],
            ),
        )
        vector = response.embeddings[0].values
        indexed.append({**chunk, "embedding": vector})

    return indexed


def main():
    chunks = load_all_chunks()
    if not chunks:
        print("No chunks found — check that knowledge_base/*.md files exist.")
        return

    print(f"Found {len(chunks)} chunks across the knowledge base.")
    indexed = embed_chunks(chunks)

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump({"model": EMBED_MODEL, "dimensions": EMBED_DIMENSIONS, "chunks": indexed}, f)

    print(f"\nWrote {len(indexed)} embedded chunks to {INDEX_PATH}")
    print("Restart uvicorn so ai_service.py picks up the new index.")


if __name__ == "__main__":
    main()
