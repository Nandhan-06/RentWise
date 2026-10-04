"""
voice_service.py — Voice-first chatbot using the Gemini Live API.

Separate track from the text chatbot: uses a persistent WebSocket to
Gemini's Live API. Kept in its own module because executing the "search"
tool needs both ai_service (filter extraction) and database (lookup).

Notes:
1. Live API free-tier limits are tighter than generateContent. Check
   https://aistudio.google.com/rate-limit on your account.
2. Audio-only sessions cap at ~15 minutes; no session resumption here.
3. The audio round-trip needs a real browser and API key to verify.

Message protocol sent to the browser (see static/js/voice_chat.js):
  Binary WS frames        -> raw 24kHz 16-bit PCM audio (the bot's speech)
  {"type": "ready"}                              -> Gemini session is live
  {"type": "user_transcript", "text", "final"}   -> what the user said
  {"type": "bot_transcript_chunk", "text"}       -> buffer, don't render yet
  {"type": "turn_complete"}                      -> render buffered bot text
  {"type": "interrupted"}                        -> stop playback, discard text
  {"type": "property_results", "results"}        -> render property cards
  {"type": "error", "message"}                   -> show it, session is over
"""

import asyncio
import logging
import os

from google import genai
from google.genai import types
from starlette.websockets import WebSocketDisconnect

import database as db
import ai_service

logger = logging.getLogger("voice_service")

VOICE_MODEL = os.getenv("VOICE_MODEL", "gemini-3.8-live")

_api_key = os.getenv("GEMINI_API_KEY")
_voice_client = genai.Client(api_key=_api_key) if _api_key else None

VOICE_SYSTEM_INSTRUCTION = (
    "You are the RentWise voice assistant, speaking with a renter out loud. "
    "RentWise helps people find rental properties. Keep replies short and "
    "conversational — this is spoken aloud, not read as text, so avoid long "
    "lists; mention at most two or three properties by name and let the "
    "on-screen cards show the rest. "
    "When the user asks about available properties, budgets, bedrooms, "
    "furnishing, or location, call the search tool rather than guessing — "
    "only describe properties the tool actually returned, never invent one. "
    "If the search returns nothing, say so plainly rather than making "
    "something up. For anything unrelated to finding a rental, answer "
    "briefly and steer the conversation back to helping them find a place."
)

SEARCH_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search",
            description=(
                "Search RentWise's property listings. Pass the user's housing "
                "request as a natural-language string, close to how they said it."
            ),
            parameters={
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": (
                            "The user's request in natural language, e.g. "
                            "'2 bedroom apartment in Kochi under 20000 with parking'"
                        ),
                    }
                },
                "required": ["query"],
            },
        )
    ]
)


def build_live_config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=VOICE_SYSTEM_INSTRUCTION,
        tools=[SEARCH_TOOL],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


async def execute_search(query: str) -> list:
    """
    Same structured-RAG pipeline as AI Finder / text chatbot:
    parse_query_to_filters(), falling back to keyword_fallback_search().
    Blocking calls run via asyncio.to_thread so audio keeps flowing.
    """
    filters = None
    try:
        filters = await asyncio.to_thread(ai_service.parse_query_to_filters, query)
    except Exception:
        pass

    if filters:
        results = await asyncio.to_thread(db.filter_properties, limit=5, **filters)
    else:
        results = await asyncio.to_thread(db.keyword_fallback_search, query, limit=5)

    return results


async def _handle_tool_call(tool_call, session, websocket) -> None:
    """
    Runs as a background task so the message loop (and audio relay)
    is not blocked while the search runs.
    """
    for fc in tool_call.function_calls:
        query = (fc.args or {}).get("query", "")
        try:
            results = await execute_search(query)
        except Exception:
            logger.exception("Search tool failed")
            results = []

        try:
            await websocket.send_json({"type": "property_results", "results": results})
        except Exception:
            pass  # browser socket may already be closed

        response_payload = {
            "results": [
                {"title": r["title"], "location": r["location"], "city": r["city"], "rent": float(r["rent"])}
                for r in results
            ]
        } if results else {"results": [], "note": "No matching properties found."}

        await session.send_tool_response(
            function_responses=[
                types.FunctionResponse(id=fc.id, name=fc.name, response=response_payload)
            ]
        )


async def _handle_server_message(message, session, websocket, background_tasks: set) -> None:
    if message.tool_call:
        task = asyncio.create_task(_handle_tool_call(message.tool_call, session, websocket))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return

    content = message.server_content
    if content is None:
        return

    if content.interrupted:
        await websocket.send_json({"type": "interrupted"})

    # FIX (confirmed via real live testing, not reproducible in a synthetic
    # local test): interim_input_transcription raised AttributeError against
    # an actual Live API connection. A locally-constructed LiveServerContent
    # object didn't reproduce this when checked afterward, which only shows
    # the limits of testing against the real SDK vs. a real server response —
    # the live-tested result is the one that matters here. Only final
    # transcripts are used now; there's no live "partial caption" effect
    # while the user is still speaking.
    if content.input_transcription and content.input_transcription.text:
        await websocket.send_json({
            "type": "user_transcript",
            "text": content.input_transcription.text,
            "final": True,
        })

    if content.output_transcription and content.output_transcription.text:
        await websocket.send_json({"type": "bot_transcript_chunk", "text": content.output_transcription.text})

    if content.model_turn:
        for part in content.model_turn.parts:
            if part.inline_data and part.inline_data.data:
                await websocket.send_bytes(part.inline_data.data)

    if content.turn_complete:
        await websocket.send_json({"type": "turn_complete"})


async def run_voice_session(websocket) -> None:
    """
    One browser WebSocket <-> one Gemini Live session. Two concurrent
    loops: mic audio browser -> Gemini, and everything Gemini sends
    back -> browser. The caller (app.py) has already accepted the socket.
    """
    if _voice_client is None:
        await websocket.send_json({
            "type": "error",
            "message": "Voice assistant is not configured (missing GEMINI_API_KEY).",
        })
        return

    background_tasks: set = set()

    try:
        async with _voice_client.aio.live.connect(model=VOICE_MODEL, config=build_live_config()) as session:
            await websocket.send_json({"type": "ready"})

            async def relay_browser_to_gemini():
                while True:
                    chunk = await websocket.receive_bytes()
                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                    )

            async def relay_gemini_to_browser():
                # FIX: session.receive() ends after every model turn, so
                # it must be wrapped in a loop to keep the conversation going.
                while True:
                    async for message in session.receive():
                        await _handle_server_message(message, session, websocket, background_tasks)

            await asyncio.gather(relay_browser_to_gemini(), relay_gemini_to_browser())

    except WebSocketDisconnect:
        # FIX: the user clicking the mic to stop is normal, not an error.
        logger.info("Browser closed the voice session")
    except Exception:
        logger.exception("Voice session ended with an error")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "The voice assistant hit an error and the session ended. Try starting again.",
            })
        except Exception:
            pass  # browser socket may already be gone
    finally:
        for task in list(background_tasks):
            task.cancel()
