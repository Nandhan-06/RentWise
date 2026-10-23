"""
app.py — RentWise API

Endpoints:
  GET    /properties
  GET    /properties/{id}
  GET    /properties/search
  GET    /properties/filter
  POST   /favorites            [login required]
  GET    /favorites            [login required]
  DELETE /favorites/{id}       [login required]
  GET    /visits/availability
  POST   /visits               [login required]
  GET    /visits/{id}
  GET    /visits/mine          [login required]
  GET    /users/me             [login required]
  PUT    /users/me             [login required]
  POST   /ai/property-search
  POST   /ai/property-compare
  GET    /ai/rental-insights   [login required]
  POST   /ai/chatbot
  POST   /auth/signup
  POST   /auth/login
  POST   /auth/logout          [login required]
  GET    /auth/me              [login required]

Pages:
  GET /             Property list + filter (Module 2)
  GET /my-favorites Saved properties (Module 3)
  GET /my-visits    Scheduled visits (Module 3)
  GET /compare      Side-by-side comparison (Module 6)
  GET /profile      User details + AI rental insights (Module 6)
  GET /login        Login page (Module 7)
  GET /signup       Signup page (Module 7)
  GET /property/{id} Property detail page
  GET /contact      Contact page (Module 9); POST /contact stores a message

Module 7 (auth) changed several endpoint shapes from earlier modules —
see README "Module 7" for the full list of what moved and why. The
short version: every endpoint that used to trust a client-supplied
user_id now derives identity from the session cookie instead. That
wasn't just a style choice — the old shape let any client view or edit
any other user's data by changing a query parameter.
"""

import logging
import os
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mysql.connector import Error as MySQLError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import auth
import database as db
import ai_service
import voice_service
from schemas import (
    AISearchRequest,
    ChatRequest,
    CompareRequest,
    ContactCreate,
    FavoriteCreate,
    LoginRequest,
    PreferencesUpdate,
    SignupRequest,
    UserUpdate,
    VisitCreate,
)

logger = logging.getLogger("rentwise")

# Module 10: the session cookie is only as safe as SESSION_SECRET_KEY. If it is
# missing or still a placeholder, the key is public (it's in this file / the
# example env file) and anyone could forge a login cookie. Warn loudly, don't
# refuse to start - that would break first-time local setup.
_INSECURE_SESSION_KEYS = {"", "dev-only-change-this-before-any-real-deploy", "change_this_to_a_random_string"}
if os.getenv("SESSION_SECRET_KEY", "") in _INSECURE_SESSION_KEYS:
    logger.warning(
        "SESSION_SECRET_KEY is missing or still a placeholder - set a random value in .env. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )

app = FastAPI(title="RentWise API", version="0.1.0")

# Allow the Jinja/JS frontend (served separately or same-origin) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module 7: session cookie auth. SESSION_SECRET_KEY signs the cookie so it
# can't be forged/tampered with client-side; same_site="lax" is the
# proportionate CSRF mitigation for this app's shape (see README) rather
# than a full CSRF-token system. https_only is left False for local dev —
# flip it to True once this is deployed behind HTTPS, or the cookie won't
# be sent at all over http.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "dev-only-change-this-before-any-real-deploy"),
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def inr(value) -> str:
    """Format a number as rupees with Indian digit grouping (1,50,000),
    matching money() in static/js/common.js so server-rendered and
    JS-rendered prices look identical."""
    n = int(round(float(value)))
    digits = str(abs(n))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return ("-" if n < 0 else "") + "\u20b9" + digits


templates.env.filters["inr"] = inr


def render(request: Request, template_name: str, status_code: int = 200, **extra):
    """Every page route uses this instead of templates.TemplateResponse
    directly, so `user` (or None for guests) is always available to
    base.html's nav without repeating this line on every route."""
    user = auth.get_current_user_optional(request)
    return templates.TemplateResponse(
        request, template_name, {"user": user, **extra}, status_code=status_code
    )


# ---------------------------------------------------------------
# Pages
# ---------------------------------------------------------------

@app.get("/")
def home(request: Request):
    return render(request, "properties.html")


# NOTE: these pages are named /my-favorites and /my-visits, not /favorites
# and /visits, because those exact paths are already the JSON API routes
# below. See Module 3 for the full reasoning.
@app.get("/my-favorites")
def favorites_page(request: Request):
    return render(request, "favorites.html")


@app.get("/my-visits")
def visits_page(request: Request):
    return render(request, "visits.html")


@app.get("/compare")
def compare_page(request: Request):
    return render(request, "compare.html")


# NOTE: singular /property/{id}, not /properties/{id} — that exact path is
# already the JSON API route further down (same reasoning as /my-favorites).
@app.get("/property/{property_id}")
def property_detail_page(request: Request, property_id: int):
    prop = db.get_property(property_id)
    if not prop:
        return render(request, "property_detail.html", status_code=404, property=None)
    return render(request, "property_detail.html", property=prop)


@app.get("/contact")
def contact_page(request: Request):
    return render(request, "contact.html", active="contact")


@app.get("/profile")
def profile_page(request: Request):
    return render(request, "profile.html")


@app.get("/login")
def login_page(request: Request):
    return render(request, "login.html")


@app.get("/signup")
def signup_page(request: Request):
    return render(request, "signup.html")


@app.get("/terms")
def terms_page(request: Request):
    return render(request, "terms.html")


@app.get("/privacy")
def privacy_page(request: Request):
    return render(request, "privacy.html")


@app.get("/voice-assistant")
def voice_assistant_page():
    """
    Retired as a standalone page: live voice conversation now lives in the
    chat widget on every page (see static/js/chatbot.js), using the same
    /ws/voice-chat endpoint below. This redirect isn't just tidiness —
    templates/voice_assistant.html still loads static/js/voice_chat.js in
    its own <script> tag, and that file declares several top-level
    variables (messagesBox, micStream, micAudioCtx, playbackAudioCtx)
    that are now ALSO declared by chatbot.js, which loads globally on
    every page via base.html. Rendering this page would load both files
    together and throw the exact "already declared" SyntaxError this
    project has hit before — redirecting away avoids ever reaching that
    state, rather than leaving a page that silently breaks if visited.
    """
    return RedirectResponse(url="/")


@app.websocket("/ws/voice-chat")
async def voice_chat_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        await voice_service.run_voice_session(websocket)
    except WebSocketDisconnect:
        pass  # browser closed the tab/connection — nothing more to do


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------
# Friendly errors (Module 10)
# Visitors loading a PAGE get a styled error page; fetch() calls from the
# site's JavaScript still get JSON. Real error details go to the server log,
# never to the browser (the old handler sent the raw MySQL message - host,
# port and all - to whoever triggered it).
# ---------------------------------------------------------------

def _wants_html(request: Request) -> bool:
    # Browsers navigating to a page send "text/html" in Accept; fetch() calls
    # from our JS send "*/*", so API clients keep getting JSON.
    return "text/html" in request.headers.get("accept", "")


def _error_page(request: Request, status_code: int, title: str, message: str):
    try:
        user = auth.get_current_user_optional(request)
    except Exception:
        user = None  # e.g. the database itself is what broke - don't fail twice
    return templates.TemplateResponse(
        request,
        "error.html",
        {"user": user, "status_code": status_code, "title": title, "message": message},
        status_code=status_code,
    )


NOT_FOUND_TEXT = ("Page not found", "The page you're looking for doesn't exist or may have moved.")
SERVER_ERROR_TEXT = ("Something went wrong", "We hit a problem on our side. Please try again in a moment.")


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and _wants_html(request):
        return _error_page(request, 404, *NOT_FOUND_TEXT)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # A page address like /property/abc is simply "not found" to a visitor.
    if _wants_html(request):
        return _error_page(request, 404, *NOT_FOUND_TEXT)
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(MySQLError)
async def mysql_error_handler(request: Request, exc: MySQLError):
    logger.error("Database error on %s %s: %s", request.method, request.url.path, exc)
    if _wants_html(request):
        return _error_page(request, 500, *SERVER_ERROR_TEXT)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again in a moment."})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    # Last resort for bugs nobody anticipated. The server still logs the full
    # traceback; the visitor just sees a calm message instead of a stack trace.
    if _wants_html(request):
        return _error_page(request, 500, *SERVER_ERROR_TEXT)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again in a moment."})


# ---------------------------------------------------------------
# Auth (Module 7)
# ---------------------------------------------------------------

@app.post("/auth/signup", status_code=201)
def signup(payload: SignupRequest, request: Request):
    if db.get_user_by_email_with_hash(payload.email):
        # Deliberately vague — "email already registered" doesn't leak
        # anything sensitive, unlike login's error, which stays even
        # vaguer on purpose (see /auth/login below).
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    password_hash = auth.hash_password(payload.password)
    role = "landlord" if payload.register_as_landlord else "renter"
    user = db.create_user(
        name=payload.name,
        email=payload.email,
        password_hash=password_hash,
        phone=payload.phone,
        role=role,
    )
    request.session["user_id"] = user["user_id"]
    return user


@app.post("/auth/login")
def login(payload: LoginRequest, request: Request):
    user = db.get_user_by_email_with_hash(payload.email)
    # Same generic error whether the email doesn't exist or the password
    # is wrong — confirming which one it was makes account enumeration
    # trivial for an attacker.
    if not user or not auth.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    request.session["user_id"] = user["user_id"]
    user.pop("password_hash")
    return user


@app.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "logged_out"}


@app.get("/auth/me")
def me(current_user: dict = Depends(auth.get_current_user)):
    return current_user


# ---------------------------------------------------------------
# AI Property Finder (Module 4 — structured RAG)
# ---------------------------------------------------------------

@app.post("/ai/property-search")
def ai_property_search(payload: AISearchRequest):
    query = payload.query.strip()
    used_fallback = False
    filters: dict = {}

    try:
        filters = ai_service.parse_query_to_filters(query)
    except Exception:
        used_fallback = True

    if used_fallback:
        results = db.keyword_fallback_search(query, limit=10)
        summary = None
    else:
        results = db.filter_properties(limit=10, **filters)
        try:
            summary = ai_service.generate_recommendation_summary(query, results)
        except Exception:
            summary = None

    return {
        "query": query,
        "filters": filters,
        "used_fallback": used_fallback,
        "count": len(results),
        "results": results,
        "summary": summary,
    }


# ---------------------------------------------------------------
# Compare Properties (Module 6 — FR-6/FR-7). Left public: comparing
# listings needs no personal data, same reasoning as browsing itself.
# ---------------------------------------------------------------

@app.post("/ai/property-compare")
def compare_properties(payload: CompareRequest):
    ids = list(dict.fromkeys(payload.property_ids))
    properties = []
    for pid in ids:
        prop = db.get_property(pid)
        if not prop:
            raise HTTPException(status_code=404, detail=f"Property {pid} not found")
        properties.append(prop)

    try:
        summary = ai_service.generate_comparison_summary(properties)
    except Exception:
        summary = None

    return {"properties": properties, "ai_summary": summary}


# ---------------------------------------------------------------
# Users / Profile (Module 6 — FR-10)
#
# Module 7 change: these used to be /users/{user_id}, trusting whatever
# id the client sent — meaning any logged-in-or-not client could read or
# edit ANY user's profile by changing a number in the URL. They're now
# /users/me, with the id coming from the session instead. There is no
# route left that takes a user_id from the client for this.
# ---------------------------------------------------------------

@app.get("/users/me")
def get_my_profile(current_user: dict = Depends(auth.get_current_user)):
    return current_user


@app.put("/users/me")
def update_my_profile(payload: UserUpdate, current_user: dict = Depends(auth.get_current_user)):
    fields = payload.model_dump(exclude_unset=True)

    # Without this, taking another account's email hit the database's UNIQUE
    # rule and the visitor just saw a generic "something went wrong".
    new_email = fields.get("email")
    if new_email:
        owner = db.get_user_by_email_with_hash(new_email)
        if owner and owner["user_id"] != current_user["user_id"]:
            raise HTTPException(status_code=400, detail="That email is already used by another account")

    return db.update_user(current_user["user_id"], **fields)


# ---------------------------------------------------------------
# Rental preferences (Module 11) - private to the logged-in user
# ---------------------------------------------------------------

@app.get("/users/me/preferences")
def get_my_preferences(current_user: dict = Depends(auth.get_current_user)):
    return db.get_preferences(current_user["user_id"])


@app.put("/users/me/preferences")
def update_my_preferences(payload: PreferencesUpdate, current_user: dict = Depends(auth.get_current_user)):
    return db.save_preferences(current_user["user_id"], payload.model_dump())


# ---------------------------------------------------------------
# AI Rental Insights (Module 6 — FR-12) — same user_id -> session change as above
# ---------------------------------------------------------------

@app.get("/ai/rental-insights")
def rental_insights(current_user: dict = Depends(auth.get_current_user)):
    stats = db.get_favorite_stats(current_user["user_id"])

    if stats["count"] == 0:
        return {"stats": stats, "summary": None, "has_data": False}

    try:
        summary = ai_service.generate_insights_summary(stats)
    except Exception:
        summary = None

    return {"stats": stats, "summary": summary, "has_data": True}


# ---------------------------------------------------------------
# AI Chatbot with RAG (Module 5). Left public on purpose — a guest
# asking "what neighbourhoods do you cover?" shouldn't need an account
# any more than reading the FAQ page would.
# ---------------------------------------------------------------

@app.post("/ai/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Voice input for the chatbot. Records via the browser's MediaRecorder
    (any modern browser — Chrome, Firefox, Safari all support it, unlike
    the Web Speech API this replaced), uploads the raw audio here, and
    Gemini transcribes it. No language is specified anywhere in this
    path — Gemini transcribes in whatever language/script it hears,
    which is what gives automatic language detection with no picker.
    """
    audio_bytes = await audio.read()
    mime_type = audio.content_type or "audio/webm"

    try:
        transcript = ai_service.transcribe_audio(audio_bytes, mime_type)
    except ValueError:
        raise HTTPException(status_code=413, detail="That recording is too long — try a shorter question.")
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Voice transcription is unavailable right now — try typing your question instead.",
        )

    return {"transcript": transcript}


@app.post("/ai/chatbot")
def chatbot(payload: ChatRequest):
    message = payload.message.strip()
    history = [h.model_dump() for h in payload.history]

    try:
        routed = ai_service.classify_chat_intent(message, history)
    except Exception:
        results = db.keyword_fallback_search(message, limit=10)
        titles = ", ".join(r["title"] for r in results[:5])
        reply = (
            f"The AI assistant is unavailable right now, so here's a plain keyword "
            f"search instead: {titles}" if results else
            "The AI assistant is unavailable right now, and a plain keyword search "
            "didn't find anything either — try rephrasing, or browse Properties directly."
        )
        return {"reply": reply, "intent": "search", "used_fallback": True, "results": results, "filters": {}, "sources": []}

    intent = routed["intent"]

    if intent == "search":
        # limit=10 (not 5) and filters included in the response: the
        # consolidated chat widget now renders full property cards and
        # filter chips, same as the old standalone AI Finder page did —
        # the frontend needs the actual filter values to show as chips,
        # which a plain results list never required.
        results = db.filter_properties(limit=10, **routed["filters"])
        try:
            reply = ai_service.generate_chat_search_reply(message, results)
        except Exception:
            titles = ", ".join(r["title"] for r in results[:5])
            reply = f"Found {len(results)}: {titles}" if results else "No matching properties found."
        return {
            "reply": reply,
            "intent": "search",
            "used_fallback": False,
            "results": results,
            "filters": routed["filters"],
            "sources": [],
        }

    if intent == "general":
        try:
            chunks = ai_service.semantic_search(message)
        except Exception:
            reply = "The AI assistant is unavailable right now — try again in a moment."
            return {"reply": reply, "intent": "general", "used_fallback": True, "results": [], "filters": {}, "sources": []}

        if not chunks:
            reply = "I couldn't find anything about that in RentWise's FAQ, policies, or neighbourhood info. Try asking about listings instead, or rephrase the question."
            return {"reply": reply, "intent": "general", "used_fallback": False, "results": [], "filters": {}, "sources": []}

        try:
            reply = ai_service.generate_chat_general_reply(message, chunks)
        except Exception:
            reply = chunks[0]["text"]

        sources = [{"source": c["source"], "heading": c["heading"]} for c in chunks]
        return {"reply": reply, "intent": "general", "used_fallback": False, "results": [], "filters": {}, "sources": sources}

    return {
        "reply": ai_service.OUT_OF_SCOPE_REPLY,
        "intent": "out_of_scope",
        "filters": {},
        "used_fallback": False,
        "results": [],
        "sources": [],
    }


# ---------------------------------------------------------------
# Properties (public — browsing never requires login)
# ---------------------------------------------------------------

SortOption = Literal["newest", "rent_low", "rent_high"]


@app.get("/properties")
def get_properties(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: SortOption = "newest",
):
    offset = (page - 1) * page_size
    items = db.list_properties(limit=page_size, offset=offset, sort=sort)
    total = db.count_properties()
    return {"page": page, "page_size": page_size, "total": total, "results": items}


@app.get("/properties/search")
def search_properties(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    results = db.search_properties(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@app.get("/properties/filter")
def filter_properties(
    city: str | None = None,
    property_type: str | None = None,
    min_rent: float | None = Query(None, ge=0),
    max_rent: float | None = Query(None, ge=0),
    bedrooms: int | None = Query(None, ge=0),
    furnishing: str | None = None,
    parking: bool | None = None,
    limit: int = Query(20, ge=1, le=100),
    sort: SortOption = "newest",
):
    if min_rent is not None and max_rent is not None and min_rent > max_rent:
        raise HTTPException(status_code=400, detail="min_rent cannot exceed max_rent")

    results = db.filter_properties(
        city=city, property_type=property_type, min_rent=min_rent, max_rent=max_rent,
        bedrooms=bedrooms, furnishing=furnishing, parking=parking, limit=limit, sort=sort,
    )
    return {"count": len(results), "results": results}


# NOTE: this static route must be declared before /properties/{property_id}
# so FastAPI doesn't try to parse "search" or "filter" as an integer id.
@app.get("/properties/{property_id}")
def get_property(property_id: int):
    prop = db.get_property(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


# ---------------------------------------------------------------
# Favorites [login required — see Module 7 note in the docstring above]
# ---------------------------------------------------------------

@app.post("/favorites", status_code=201)
def create_favorite(payload: FavoriteCreate, current_user: dict = Depends(auth.get_current_user)):
    if not db.get_property(payload.property_id):
        raise HTTPException(status_code=404, detail="Property not found")
    return db.add_favorite(current_user["user_id"], payload.property_id)


@app.get("/favorites")
def get_favorites(current_user: dict = Depends(auth.get_current_user)):
    return {"results": db.list_favorites(current_user["user_id"])}


@app.delete("/favorites/{favorite_id}", status_code=204)
def delete_favorite(favorite_id: int, current_user: dict = Depends(auth.get_current_user)):
    removed = db.remove_favorite(favorite_id, current_user["user_id"])
    if not removed:
        raise HTTPException(status_code=404, detail="Favorite not found")


# ---------------------------------------------------------------
# Contact (Module 9) — open to guests and logged-in users alike
# ---------------------------------------------------------------

# Anti-spam limits. Deliberately simple: no extra libraries, just a count of
# recent rows. They stop a bot flooding the table; they are not a full
# defence (a determined attacker can vary emails).
CONTACT_MAX_PER_EMAIL_PER_HOUR = 3
CONTACT_MAX_TOTAL_PER_HOUR = 50


@app.post("/contact", status_code=201)
def submit_contact(payload: ContactCreate, request: Request):
    # Honeypot: real visitors never see this field. If it has text, it was a
    # bot — answer "success" so it learns nothing, and store nothing.
    if payload.website:
        return {"status": "received"}

    email = payload.email.lower()
    if (
        db.count_recent_contact_messages(email) >= CONTACT_MAX_PER_EMAIL_PER_HOUR
        or db.count_recent_contact_messages() >= CONTACT_MAX_TOTAL_PER_HOUR
    ):
        raise HTTPException(
            status_code=429,
            detail="We've received a lot of messages from you recently. Please try again in a little while.",
        )

    user = auth.get_current_user_optional(request)
    db.create_contact_message(
        user["user_id"] if user else None, payload.name, email, payload.topic, payload.message
    )
    return {"status": "received"}


# ---------------------------------------------------------------
# Visits
# ---------------------------------------------------------------

@app.get("/visits/availability")
def visit_availability(property_id: int, visit_date: str):
    if not db.get_property(property_id):
        raise HTTPException(status_code=404, detail="Property not found")
    slots = db.get_visit_availability(property_id, visit_date)
    return {"property_id": property_id, "visit_date": visit_date, "available_slots": slots}


@app.post("/visits", status_code=201)
def schedule_visit(payload: VisitCreate, current_user: dict = Depends(auth.get_current_user)):
    prop = db.get_property(payload.property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    if not prop["availability"]:
        raise HTTPException(status_code=400, detail="This property is not available for visits right now")

    slot = payload.visit_time.strftime("%H:%M")
    open_slots = db.get_visit_availability(payload.property_id, str(payload.visit_date))
    if slot not in open_slots:
        raise HTTPException(status_code=409, detail="That time slot is no longer available")

    return db.create_visit(
        current_user["user_id"], payload.property_id, str(payload.visit_date), str(payload.visit_time)
    )


@app.get("/visits/mine")
def get_my_visits(current_user: dict = Depends(auth.get_current_user)):
    return {"results": db.list_visits_for_user(current_user["user_id"])}


# NOTE: /visits/mine must be declared BEFORE this route, for the same
# reason /properties/{property_id} is declared after /properties/search
# and /properties/filter — otherwise FastAPI tries to parse "mine" as an
# integer visit_id and returns 422 instead of ever reaching /visits/mine.
@app.get("/visits/{visit_id}")
def get_visit(visit_id: int, current_user: dict = Depends(auth.get_current_user)):
    visit = db.get_visit(visit_id)
    # Someone else's visit gets the same 404 as a visit that doesn't exist,
    # so visit ids can't be probed to see which ones are taken.
    if not visit or visit["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=404, detail="Visit not found")
    return visit
