"""
ai_service.py — RentWise Modules 4 & 5: AI Property Finder + AI Chatbot (RAG)
Gemini edition — uses Google's free-tier-eligible Gemini API.

Module 4 (structured RAG):
  1. parse_query_to_filters() — turn free text into the same filter shape
     /properties/filter already accepts, using the LLM.
  2. generate_recommendation_summary() — write a short natural-language
     recommendation, but ONLY from the rows the database actually
     returned.

Module 5 (adds semantic RAG + the chatbot's intent routing — see the
"Chatbot" section below the Module 4 code):
  - semantic_search() retrieves from kb_index.json (built offline by
    build_kb_index.py), never at request time from the raw markdown.
  - classify_chat_intent() decides whether a chat message is a property
    search, a general question, or out of scope, and routes accordingly
    — see SRS Section 3.1.

If GEMINI_API_KEY isn't set, or any API call fails for any reason,
callers should catch the exception and fall back to plain keyword search
(SRS NFR-7). This module never fails silently — it raises so app.py can
decide the fallback behaviour.
"""

import json
import os
import re

import numpy as np
from google import genai
from google.genai import types

# gemini-3.1-flash-lite: stable (not preview), free-tier eligible, and —
# unlike gemini-2.5-flash — has no scheduled shutdown date as of this
# writing. gemini-2.5-flash is also free and works fine, but Google has
# it scheduled for shutdown on 16 October 2026; avoid it for anything
# you want running past that date. Re-check https://ai.google.dev/gemini-api/docs/models
# occasionally — Google's free-tier model lineup shifts every few months.
MODEL = os.getenv("AI_MODEL", "gemini-3.1-flash-lite")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

_api_key = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=_api_key) if _api_key else None

ALLOWED_PROPERTY_TYPES = {"Apartment", "Villa", "Independent House", "Studio", "PG"}
ALLOWED_FURNISHING = {"Furnished", "Semi-Furnished", "Unfurnished"}

FILTER_SYSTEM_PROMPT = """You convert a renter's natural-language housing request into a JSON \
object of search filters. Respond with ONLY a JSON object — no prose, no markdown fences.

Allowed keys (omit any that don't apply to the request):
  city            string
  property_type   one of: Apartment, Villa, Independent House, Studio, PG
  min_rent        number (monthly rent, in rupees)
  max_rent        number (monthly rent, in rupees)
  bedrooms        integer
  furnishing      one of: Furnished, Semi-Furnished, Unfurnished
  parking         boolean

Example:
User: "2 bedroom furnished apartment in Kochi under 20000 with parking"
{"city": "Kochi", "property_type": "Apartment", "bedrooms": 2, "max_rent": 20000, "furnishing": "Furnished", "parking": true}

If the request mentions no usable filter at all, respond with {}.
"""


def _extract_json(text: str) -> dict:
    """The model is told to return bare JSON, but strip fences defensively."""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    return json.loads(match.group(0))


def _sanitize_filters(raw: dict) -> dict:
    """Only pass through keys/types filter_properties() actually accepts."""
    clean = {}

    if isinstance(raw.get("city"), str) and raw["city"].strip():
        clean["city"] = raw["city"].strip()

    if raw.get("property_type") in ALLOWED_PROPERTY_TYPES:
        clean["property_type"] = raw["property_type"]

    if raw.get("furnishing") in ALLOWED_FURNISHING:
        clean["furnishing"] = raw["furnishing"]

    for key in ("min_rent", "max_rent"):
        val = raw.get(key)
        if isinstance(val, (int, float)) and val >= 0:
            clean[key] = float(val)

    bedrooms = raw.get("bedrooms")
    if isinstance(bedrooms, (int, float)) and bedrooms >= 0:
        clean["bedrooms"] = int(bedrooms)

    if isinstance(raw.get("parking"), bool):
        clean["parking"] = raw["parking"]

    return clean


def parse_query_to_filters(query: str) -> dict:
    """Raises on any failure — caller (app.py) decides the fallback."""
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    response = _client.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=FILTER_SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=300,
        ),
    )
    raw_filters = _extract_json(response.text)
    return _sanitize_filters(raw_filters)


def generate_recommendation_summary(query: str, results: list) -> str | None:
    """Grounded summary — the prompt hands the LLM only rows retrieval found."""
    if _client is None or not results:
        return None

    listing_lines = "\n".join(
        f"- {r['title']} in {r['location']}, {r['city']}: "
        f"Rs.{int(r['rent']):,}/month, {r['bedrooms']}BHK, {r['furnishing']}"
        for r in results[:5]
    )

    prompt = (
        f'A renter asked: "{query}"\n\n'
        f"These are the ONLY matching properties found in the database "
        f"(do not mention or imply any property not listed here):\n{listing_lines}\n\n"
        "Write a 2-3 sentence friendly recommendation highlighting the best fit(s) "
        "and briefly why, referencing the listed properties by name only."
    )

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=200),
    )
    return response.text.strip()


def generate_comparison_summary(properties: list) -> str | None:
    """
    Module 6 (FR-7). Grounded the same way as generate_recommendation_summary:
    the LLM only ever sees the specific properties the caller already
    fetched from the database — it compares, it doesn't invent.
    """
    if _client is None or len(properties) < 2:
        return None

    listing_lines = "\n".join(
        f"- {p['title']}: Rs.{int(p['rent']):,}/month, {p['bedrooms']}BHK/{p['bathrooms']}bath, "
        f"{p['area_sqft'] or 'unknown'} sqft, {p['furnishing']}, "
        f"{'has parking' if p['parking'] else 'no parking'}, in {p['location']}, {p['city']}"
        for p in properties
    )

    prompt = (
        "Compare ONLY these properties (do not mention any other property):\n"
        f"{listing_lines}\n\n"
        "Write a short (3-4 sentence) comparison highlighting the key trade-offs "
        "between them — e.g. price vs space, location vs furnishing — so a renter "
        "can decide which fits their priorities. Reference properties by name."
    )

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=250),
    )
    return response.text.strip()


def generate_insights_summary(stats: dict) -> str | None:
    """
    Module 6 (FR-12). Grounded in the same way — the LLM only sees the
    aggregate numbers database.py already computed from the user's real
    favorites, it doesn't see or guess at individual listings.
    """
    if _client is None or not stats or stats.get("count", 0) == 0:
        return None

    prompt = (
        f"A renter has saved {stats['count']} favorite propert"
        f"{'y' if stats['count'] == 1 else 'ies'}. "
        f"Average rent among them: Rs.{int(stats['avg_rent']):,}/month. "
        f"Most common city: {stats['top_city'] or 'no clear pattern'}. "
        f"Most common property type: {stats['top_property_type'] or 'no clear pattern'}.\n\n"
        "Write a 2-sentence friendly summary of this renter's apparent preferences, "
        "based only on the numbers above — don't invent specific property names or "
        "details not given here."
    )

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=150),
    )
    return response.text.strip()


# =================================================================
# Module 5 — AI Chatbot with RAG (SRS Section 3.1 / 7.3)
# =================================================================
#
# Two retrieval paths, matching the SRS exactly:
#   - Structured path: reuses parse_query_to_filters() + db.filter_properties()
#     from Module 4 — nothing new needed there.
#   - Semantic path: semantic_search() below, over kb_index.json, which
#     build_kb_index.py creates OFFLINE. This module never embeds the
#     knowledge base itself at request time — only the incoming
#     question gets embedded live, once per message.
#
# Scope note: SRS 3.1.1 lists four intents including "property
# comparison." This implementation routes to two real intents —
# structured search and general knowledge-base questions — plus an
# out-of-scope catch-all, and does NOT attempt chat-driven comparison
# (mapping property names mentioned in conversation back to specific
# IDs reliably is a meaningfully harder problem than the other three
# intents combined). The existing Compare page (Module 6) already
# covers that use case via explicit selection. See README for the full
# reasoning.

_KB_INDEX_PATH = os.path.join(os.path.dirname(__file__), "kb_index.json")
_kb_cache = None  # lazy-loaded once per process


def _load_kb_index():
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache

    if not os.path.exists(_KB_INDEX_PATH):
        _kb_cache = {"chunks": [], "matrix": None}
        return _kb_cache

    with open(_KB_INDEX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    matrix = np.array([c["embedding"] for c in chunks], dtype=np.float32) if chunks else None
    # Pre-normalize once at load time so similarity at query time is a
    # single dot product rather than a full cosine computation per chunk.
    if matrix is not None:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        matrix = matrix / norms

    _kb_cache = {"chunks": chunks, "matrix": matrix}
    return _kb_cache


def semantic_search(query: str, top_k: int = 3, min_similarity: float = 0.45) -> list[dict]:
    """
    SRS 7.3 semantic RAG flow, steps 2-3: embed the query, compare against
    the pre-built index, return the top-k chunks ABOVE a similarity floor.
    Returns [] if the index doesn't exist yet or nothing clears the floor
    — callers must treat an empty list as "say I don't know" (SRS 3.1.4),
    never as "the LLM can improvise here."
    """
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    index = _load_kb_index()
    if index["matrix"] is None:
        return []

    response = _client.models.embed_content(
        model=EMBED_MODEL,
        contents=query,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=index["matrix"].shape[1],
        ),
    )
    query_vec = np.array(response.embeddings[0].values, dtype=np.float32)
    query_vec = query_vec / (np.linalg.norm(query_vec) or 1)

    similarities = index["matrix"] @ query_vec  # cosine similarity (both sides pre-normalized)
    ranked = np.argsort(-similarities)[:top_k]

    results = []
    for i in ranked:
        score = float(similarities[i])
        if score < min_similarity:
            continue
        chunk = index["chunks"][i]
        results.append({**chunk, "similarity": score})
    return results


CHAT_INTENT_SYSTEM_PROMPT = """You are the intent router for RentWise's chat assistant. \
Classify the user's latest message into exactly one intent, using the conversation \
history for context (e.g. "what about something cheaper?" after a search is still "search").

Respond with ONLY a JSON object — no prose, no markdown fences:
{"intent": "search" | "general" | "out_of_scope", "filters": {...}}

- "search": the user wants properties matching some criteria. Extract filters using
  the same schema as before (city, property_type, min_rent, max_rent, bedrooms,
  furnishing, parking) — omit keys that don't apply. Use conversation history to
  resolve follow-ups (e.g. carry over city from an earlier message if not repeated).
- "general": a question about how RentWise works, policies, amenities, or
  neighbourhoods — not a request for specific listings. "filters" should be {}.
- "out_of_scope": anything unrelated to renting property through RentWise
  (e.g. general chit-chat, unrelated topics). "filters" should be {}.
"""


def classify_chat_intent(message: str, history: list[dict]) -> dict:
    """Raises on failure — caller falls back to keyword search (SRS NFR-7)."""
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    convo = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    prompt = f"{convo}\nuser: {message}" if convo else message

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CHAT_INTENT_SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=300,
        ),
    )
    raw = _extract_json(response.text)
    intent = raw.get("intent")
    if intent not in {"search", "general", "out_of_scope"}:
        intent = "out_of_scope"
    filters = _sanitize_filters(raw.get("filters", {})) if intent == "search" else {}
    return {"intent": intent, "filters": filters}


def generate_chat_search_reply(message: str, results: list) -> str:
    """Conversational version of generate_recommendation_summary — same
    grounding rule: only the properties actually returned by the query."""
    if not results:
        return "I couldn't find any properties matching that in RentWise's listings right now — want to try loosening a filter, like the budget or bedroom count?"

    if _client is None:
        titles = ", ".join(r["title"] for r in results[:5])
        return f"I found {len(results)} matching propert{'y' if len(results) == 1 else 'ies'}: {titles}."

    listing_lines = "\n".join(
        f"- {r['title']} in {r['location']}, {r['city']}: "
        f"Rs.{int(r['rent']):,}/month, {r['bedrooms']}BHK, {r['furnishing']}"
        for r in results[:5]
    )
    prompt = (
        f'The user asked: "{message}"\n\n'
        f"These are the ONLY matching properties (do not mention any other):\n{listing_lines}\n\n"
        "Reply conversationally in 2-3 sentences, as a chat assistant, highlighting the "
        "best fit(s) and why, referencing properties by name only."
    )
    response = _client.models.generate_content(
        model=MODEL, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=200)
    )
    return response.text.strip()


def generate_chat_general_reply(message: str, chunks: list[dict]) -> str:
    """
    SRS 3.1.3/3.1.4: answer ONLY from retrieved chunks; if none were
    retrieved, say so rather than guessing — this function is only
    called when semantic_search() already returned at least one chunk,
    the empty case is handled by the caller before this is reached.
    """
    context = "\n\n".join(f"[{c['heading']}]\n{c['text']}" for c in chunks)
    prompt = (
        f'The user asked: "{message}"\n\n'
        f"Answer using ONLY the information below. If it doesn't fully answer the "
        f"question, say what you can from it and note what's not covered — do not "
        f"add outside knowledge.\n\n{context}\n\n"
        "Reply conversationally in 2-4 sentences."
    )
    response = _client.models.generate_content(
        model=MODEL, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=250)
    )
    return response.text.strip()


OUT_OF_SCOPE_REPLY = (
    "I'm RentWise's assistant, so I can help with finding properties, or questions "
    "about listings, amenities, neighbourhoods, and rental policies — try asking me "
    "one of those!"
) 
"""ai_service.py — RentWise Modules 4 & 5: AI Property Finder + AI Chatbot (RAG)
Gemini edition — uses Google's free-tier-eligible Gemini API.

Module 4 (structured RAG):
  1. parse_query_to_filters() — turn free text into the same filter shape
     /properties/filter already accepts, using the LLM.
  2. generate_recommendation_summary() — write a short natural-language
     recommendation, but ONLY from the rows the database actually
     returned.

Module 5 (adds semantic RAG + the chatbot's intent routing — see the
"Chatbot" section below the Module 4 code):
  - semantic_search() retrieves from kb_index.json (built offline by
    build_kb_index.py), never at request time from the raw markdown.
  - classify_chat_intent() decides whether a chat message is a property
    search, a general question, or out of scope, and routes accordingly
    — see SRS Section 3.1.

If GEMINI_API_KEY isn't set, or any API call fails for any reason,
callers should catch the exception and fall back to plain keyword search
(SRS NFR-7). This module never fails silently — it raises so app.py can
decide the fallback behaviour.
"""

import json
import os
import re

import numpy as np
from google import genai
from google.genai import types

# gemini-3.1-flash-lite: stable (not preview), free-tier eligible, and —
# unlike gemini-2.5-flash — has no scheduled shutdown date as of this
# writing. gemini-2.5-flash is also free and works fine, but Google has
# it scheduled for shutdown on 16 October 2026; avoid it for anything
# you want running past that date. Re-check https://ai.google.dev/gemini-api/docs/models
# occasionally — Google's free-tier model lineup shifts every few months.
MODEL = os.getenv("AI_MODEL", "gemini-3.1-flash-lite")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

_api_key = os.getenv("GEMINI_API_KEY")
_client = genai.Client(api_key=_api_key) if _api_key else None

ALLOWED_PROPERTY_TYPES = {"Apartment", "Villa", "Independent House", "Studio", "PG"}
ALLOWED_FURNISHING = {"Furnished", "Semi-Furnished", "Unfurnished"}

FILTER_SYSTEM_PROMPT = """You convert a renter's natural-language housing request into a JSON \
object of search filters. Respond with ONLY a JSON object — no prose, no markdown fences.

Allowed keys (omit any that don't apply to the request):
  city            string
  property_type   one of: Apartment, Villa, Independent House, Studio, PG
  min_rent        number (monthly rent, in rupees)
  max_rent        number (monthly rent, in rupees)
  bedrooms        integer
  furnishing      one of: Furnished, Semi-Furnished, Unfurnished
  parking         boolean

Example:
User: "2 bedroom furnished apartment in Kochi under 20000 with parking"
{"city": "Kochi", "property_type": "Apartment", "bedrooms": 2, "max_rent": 20000, "furnishing": "Furnished", "parking": true}

If the request mentions no usable filter at all, respond with {}.
"""


def _extract_json(text: str) -> dict:
    """The model is told to return bare JSON, but strip fences defensively."""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    return json.loads(match.group(0))


def _sanitize_filters(raw: dict) -> dict:
    """Only pass through keys/types filter_properties() actually accepts."""
    clean = {}

    if isinstance(raw.get("city"), str) and raw["city"].strip():
        clean["city"] = raw["city"].strip()

    if raw.get("property_type") in ALLOWED_PROPERTY_TYPES:
        clean["property_type"] = raw["property_type"]

    if raw.get("furnishing") in ALLOWED_FURNISHING:
        clean["furnishing"] = raw["furnishing"]

    for key in ("min_rent", "max_rent"):
        val = raw.get(key)
        if isinstance(val, (int, float)) and val >= 0:
            clean[key] = float(val)

    bedrooms = raw.get("bedrooms")
    if isinstance(bedrooms, (int, float)) and bedrooms >= 0:
        clean["bedrooms"] = int(bedrooms)

    if isinstance(raw.get("parking"), bool):
        clean["parking"] = raw["parking"]

    return clean


def parse_query_to_filters(query: str) -> dict:
    """Raises on any failure — caller (app.py) decides the fallback."""
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    response = _client.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=FILTER_SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=300,
        ),
    )
    raw_filters = _extract_json(response.text)
    return _sanitize_filters(raw_filters)


def generate_recommendation_summary(query: str, results: list) -> str | None:
    """Grounded summary — the prompt hands the LLM only rows retrieval found."""
    if _client is None or not results:
        return None

    listing_lines = "\n".join(
        f"- {r['title']} in {r['location']}, {r['city']}: "
        f"Rs.{int(r['rent']):,}/month, {r['bedrooms']}BHK, {r['furnishing']}"
        for r in results[:5]
    )

    prompt = (
        f'A renter asked: "{query}"\n\n'
        f"These are the ONLY matching properties found in the database "
        f"(do not mention or imply any property not listed here):\n{listing_lines}\n\n"
        "Write a 2-3 sentence friendly recommendation highlighting the best fit(s) "
        "and briefly why, referencing the listed properties by name only."
    )

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=200),
    )
    return response.text.strip()


def generate_comparison_summary(properties: list) -> str | None:
    """
    Module 6 (FR-7). Grounded the same way as generate_recommendation_summary:
    the LLM only ever sees the specific properties the caller already
    fetched from the database — it compares, it doesn't invent.
    """
    if _client is None or len(properties) < 2:
        return None

    listing_lines = "\n".join(
        f"- {p['title']}: Rs.{int(p['rent']):,}/month, {p['bedrooms']}BHK/{p['bathrooms']}bath, "
        f"{p['area_sqft'] or 'unknown'} sqft, {p['furnishing']}, "
        f"{'has parking' if p['parking'] else 'no parking'}, in {p['location']}, {p['city']}"
        for p in properties
    )

    prompt = (
        "Compare ONLY these properties (do not mention any other property):\n"
        f"{listing_lines}\n\n"
        "Write a short (3-4 sentence) comparison highlighting the key trade-offs "
        "between them — e.g. price vs space, location vs furnishing — so a renter "
        "can decide which fits their priorities. Reference properties by name."
    )

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=250),
    )
    return response.text.strip()


def generate_insights_summary(stats: dict) -> str | None:
    """
    Module 6 (FR-12). Grounded in the same way — the LLM only sees the
    aggregate numbers database.py already computed from the user's real
    favorites, it doesn't see or guess at individual listings.
    """
    if _client is None or not stats or stats.get("count", 0) == 0:
        return None

    prompt = (
        f"A renter has saved {stats['count']} favorite propert"
        f"{'y' if stats['count'] == 1 else 'ies'}. "
        f"Average rent among them: Rs.{int(stats['avg_rent']):,}/month. "
        f"Most common city: {stats['top_city'] or 'no clear pattern'}. "
        f"Most common property type: {stats['top_property_type'] or 'no clear pattern'}.\n\n"
        "Write a 2-sentence friendly summary of this renter's apparent preferences, "
        "based only on the numbers above — don't invent specific property names or "
        "details not given here."
    )

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=150),
    )
    return response.text.strip()


# =================================================================
# Module 5 — AI Chatbot with RAG (SRS Section 3.1 / 7.3)
# =================================================================
#
# Two retrieval paths, matching the SRS exactly:
#   - Structured path: reuses parse_query_to_filters() + db.filter_properties()
#     from Module 4 — nothing new needed there.
#   - Semantic path: semantic_search() below, over kb_index.json, which
#     build_kb_index.py creates OFFLINE. This module never embeds the
#     knowledge base itself at request time — only the incoming
#     question gets embedded live, once per message.
#
# Scope note: SRS 3.1.1 lists four intents including "property
# comparison." This implementation routes to two real intents —
# structured search and general knowledge-base questions — plus an
# out-of-scope catch-all, and does NOT attempt chat-driven comparison
# (mapping property names mentioned in conversation back to specific
# IDs reliably is a meaningfully harder problem than the other three
# intents combined). The existing Compare page (Module 6) already
# covers that use case via explicit selection. See README for the full
# reasoning.

_KB_INDEX_PATH = os.path.join(os.path.dirname(__file__), "kb_index.json")
_kb_cache = None  # lazy-loaded once per process


def _load_kb_index():
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache

    if not os.path.exists(_KB_INDEX_PATH):
        _kb_cache = {"chunks": [], "matrix": None}
        return _kb_cache

    with open(_KB_INDEX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    matrix = np.array([c["embedding"] for c in chunks], dtype=np.float32) if chunks else None
    # Pre-normalize once at load time so similarity at query time is a
    # single dot product rather than a full cosine computation per chunk.
    if matrix is not None:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        matrix = matrix / norms

    _kb_cache = {"chunks": chunks, "matrix": matrix}
    return _kb_cache


def semantic_search(query: str, top_k: int = 3, min_similarity: float = 0.45) -> list[dict]:
    """
    SRS 7.3 semantic RAG flow, steps 2-3: embed the query, compare against
    the pre-built index, return the top-k chunks ABOVE a similarity floor.
    Returns [] if the index doesn't exist yet or nothing clears the floor
    — callers must treat an empty list as "say I don't know" (SRS 3.1.4),
    never as "the LLM can improvise here."
    """
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    index = _load_kb_index()
    if index["matrix"] is None:
        return []

    response = _client.models.embed_content(
        model=EMBED_MODEL,
        contents=query,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=index["matrix"].shape[1],
        ),
    )
    query_vec = np.array(response.embeddings[0].values, dtype=np.float32)
    query_vec = query_vec / (np.linalg.norm(query_vec) or 1)

    similarities = index["matrix"] @ query_vec  # cosine similarity (both sides pre-normalized)
    ranked = np.argsort(-similarities)[:top_k]

    results = []
    for i in ranked:
        score = float(similarities[i])
        if score < min_similarity:
            continue
        chunk = index["chunks"][i]
        results.append({**chunk, "similarity": score})
    return results


CHAT_INTENT_SYSTEM_PROMPT = """You are the intent router for RentWise's chat assistant. \
Classify the user's latest message into exactly one intent, using the conversation \
history for context (e.g. "what about something cheaper?" after a search is still "search").

Respond with ONLY a JSON object — no prose, no markdown fences:
{"intent": "search" | "general" | "out_of_scope", "filters": {...}}

- "search": the user wants properties matching some criteria. Extract filters using
  the same schema as before (city, property_type, min_rent, max_rent, bedrooms,
  furnishing, parking) — omit keys that don't apply. Use conversation history to
  resolve follow-ups (e.g. carry over city from an earlier message if not repeated).
- "general": a question about how RentWise works, policies, amenities, or
  neighbourhoods — not a request for specific listings. "filters" should be {}.
- "out_of_scope": anything unrelated to renting property through RentWise
  (e.g. general chit-chat, unrelated topics). "filters" should be {}.
"""


def classify_chat_intent(message: str, history: list[dict]) -> dict:
    """Raises on failure — caller falls back to keyword search (SRS NFR-7)."""
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    convo = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    prompt = f"{convo}\nuser: {message}" if convo else message

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CHAT_INTENT_SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=300,
        ),
    )
    raw = _extract_json(response.text)
    intent = raw.get("intent")
    if intent not in {"search", "general", "out_of_scope"}:
        intent = "out_of_scope"
    filters = _sanitize_filters(raw.get("filters", {})) if intent == "search" else {}
    return {"intent": intent, "filters": filters}


def generate_chat_search_reply(message: str, results: list) -> str:
    """Conversational version of generate_recommendation_summary — same
    grounding rule: only the properties actually returned by the query."""
    if not results:
        return "I couldn't find any properties matching that in RentWise's listings right now — want to try loosening a filter, like the budget or bedroom count?"

    if _client is None:
        # No LLM available at all — this fallback string is English-only
        # regardless of what language the user wrote in (same accepted
        # limitation as OUT_OF_SCOPE_REPLY below; translating a fixed
        # string for every supported language isn't worth the complexity
        # for a path that only fires when the AI is already down).
        titles = ", ".join(r["title"] for r in results[:5])
        return f"I found {len(results)} matching propert{'y' if len(results) == 1 else 'ies'}: {titles}."

    listing_lines = "\n".join(
        f"- {r['title']} in {r['location']}, {r['city']}: "
        f"Rs.{int(r['rent']):,}/month, {r['bedrooms']}BHK, {r['furnishing']}"
        for r in results[:5]
    )
    prompt = (
        f'The user asked: "{message}"\n\n'
        f"These are the ONLY matching properties (do not mention any other):\n{listing_lines}\n\n"
        "Reply conversationally in 2-3 sentences, as a chat assistant, highlighting the "
        "best fit(s) and why, referencing properties by name only. "
        "Reply in the SAME language the user's message above is written in — "
        "if they wrote in Malayalam, Hindi, Tamil, Kannada, etc., reply in that "
        "same language, not English, regardless of what language this instruction is in."
    )
    response = _client.models.generate_content(
        model=MODEL, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=200)
    )
    return response.text.strip()


def generate_chat_general_reply(message: str, chunks: list[dict]) -> str:
    """
    SRS 3.1.3/3.1.4: answer ONLY from retrieved chunks; if none were
    retrieved, say so rather than guessing — this function is only
    called when semantic_search() already returned at least one chunk,
    the empty case is handled by the caller before this is reached.
    """
    context = "\n\n".join(f"[{c['heading']}]\n{c['text']}" for c in chunks)
    prompt = (
        f'The user asked: "{message}"\n\n'
        f"Answer using ONLY the information below. If it doesn't fully answer the "
        f"question, say what you can from it and note what's not covered — do not "
        f"add outside knowledge.\n\n{context}\n\n"
        "Reply conversationally in 2-4 sentences. Reply in the SAME language the "
        "user's message above is written in, translating the information above as "
        "needed — but even when translating, still add nothing beyond what's given."
    )
    response = _client.models.generate_content(
        model=MODEL, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=250)
    )
    return response.text.strip()


# Static, zero-LLM-cost reply for out-of-scope messages — deliberately
# English-only. Routing this through the LLM just to translate a fixed
# sentence would add a call (and a failure mode) to the one intent that's
# supposed to be the cheapest. Accepted limitation, same category as the
# no-LLM fallback above.
# Static, zero-LLM-cost reply for out-of-scope messages — deliberately
# English-only. Routing this through the LLM just to translate a fixed
# sentence would add a call (and a failure mode) to the one intent that's
# supposed to be the cheapest. Accepted limitation, same category as the
# no-LLM fallback above.
OUT_OF_SCOPE_REPLY = (
    "I'm RentWise's assistant, so I can help with finding properties, or questions "
    "about listings, amenities, neighbourhoods, and rental policies — try asking me "
    "one of those!"
)


# =================================================================
# Voice input — audio transcription (Module 5 addition)
# =================================================================
#
# Uses Gemini's audio-understanding capability via the STABLE
# generateContent API (client.models.generate_content with an inline
# audio Part) — NOT the newer beta "Interactions" API, which Google's
# own docs currently say to avoid for production use. Audio is passed
# inline as bytes rather than uploaded via the Files API, since the
# Files API is meant for files over ~20MB; a spoken chat question will
# always be far smaller than that.
#
# Language handling: no language is specified anywhere in this function
# or its prompt. Gemini transcribes speech in whatever language and
# script it actually hears — this is what gives "automatic detection
# with no language picker" for free, rather than something built by
# guessing the language ourselves.
MAX_AUDIO_BYTES = 15 * 1024 * 1024  # ~15MB — generous for a spoken chat question,
# small enough to stay well inside Gemini's inline (non-Files-API) limit
# and to avoid wasting quota on an unreasonably large upload.


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Raises on failure — caller (app.py) returns a clear 'try typing
    instead' error rather than a raw 500."""
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Audio too large")

    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    response = _client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            "Transcribe this audio exactly as spoken, in the same language and "
            "script the speaker used — do not translate it. Output ONLY the "
            "transcript text itself: no commentary, no language name, no "
            "quotation marks, nothing else.",
        ],
    )
    return response.text.strip()

