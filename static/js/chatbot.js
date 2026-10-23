// Consolidated AI Chatbot widget — present on every page via base.html.
//
// This merges what used to be three separate experiences:
//   1. The Module 5 text chatbot (intent routing, structured + semantic RAG)
//   2. The AI Finder page's richer result rendering (filter chips, AI
//      summary, full property cards with a Save button, fallback notice)
//   3. The Gemini Live API voice assistant (real-time two-way voice,
//      replacing the old MediaRecorder-based "record a question, review
//      the transcript, then send it" dictation flow — that's gone)
//
// IMPORTANT SCOPE LIMIT: text mode and voice mode are two separate
// backend pipelines (text: stateless POST /ai/chatbot with client-replayed
// history; voice: a stateful Gemini Live WebSocket session). They both
// render into this same bubble list, so the conversation LOOKS
// continuous, but the model does not actually share memory across a
// mode switch — starting a voice session doesn't know what you typed
// moments earlier, and vice versa. Properly unifying that would mean
// feeding one pipeline's history into the other's context, which is a
// meaningfully bigger change than merging the UI — not attempted here.
//
// Bug fixes folded in from real browser/live-API testing (see
// voice_service.py for the backend side of these): final-only transcripts
// (no interim/partial captions — a live Gemini connection raised
// AttributeError on that field), and the two-way audio relay now expects
// the backend's receive loop to keep running across multiple turns.

let chatHistory = [];

const toggleBtn = document.getElementById("chat-toggle");
const closeBtn = document.getElementById("chat-close");
const panel = document.getElementById("chat-panel");
const messagesBox = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const voiceToggleBtn = document.getElementById("chat-voice-toggle");
const voiceStatusBox = document.getElementById("chat-voice-status");
const voiceStatusText = document.getElementById("chat-voice-status-text");

// ---------------------------------------------------------------
// Shared bubble/panel helpers (used by both text and voice modes)
// ---------------------------------------------------------------

function addBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble chat-${role}`;
  bubble.textContent = text;
  messagesBox.appendChild(bubble);
  messagesBox.scrollTop = messagesBox.scrollHeight;
  return bubble;
}

function setPanelOpen(isOpen) {
  panel.hidden = !isOpen;
  panel.style.display = isOpen ? "flex" : "none"; // explicit, wins over any CSS display rule
  if (isOpen) {
    if (!messagesBox.children.length) {
      addBubble(
        "assistant",
        "Hi! I can help you find properties, or answer questions about listings, amenities, policies, and neighbourhoods. Type below, or tap the mic for a live voice conversation."
      );
    }
    input.focus();
  }
}

// Ensure it starts closed regardless of markup/CSS state.
setPanelOpen(false);

toggleBtn.addEventListener("click", () => setPanelOpen(panel.hidden));
closeBtn.addEventListener("click", () => {
  setPanelOpen(false);
  if (voiceSessionActive) endVoiceSession(); // closing the panel ends an in-progress voice call too
});

// ---------------------------------------------------------------
// Rich result rendering (ported from the old AI Finder page) —
// filter chips, full property cards with Save, fallback notice.
// Used by both text search results and voice-triggered property_results.
// ---------------------------------------------------------------

const FILTER_LABELS = {
  city: "City",
  property_type: "Type",
  min_rent: "Min rent",
  max_rent: "Max rent",
  bedrooms: "Bedrooms",
  furnishing: "Furnishing",
  parking: "Parking",
};

function formatFilterValue(key, value) {
  if (key === "min_rent" || key === "max_rent") return money(value);
  if (key === "parking") return value ? "Required" : "Not required";
  return value;
}

function addFilterChips(filters) {
  const entries = Object.entries(filters || {});
  if (!entries.length) return;
  const box = document.createElement("div");
  box.className = "ai-filters chat-filters";
  box.innerHTML = entries
    .map(([k, v]) => `<span class="filter-chip">${FILTER_LABELS[k] || k}: ${formatFilterValue(k, v)}</span>`)
    .join("");
  messagesBox.appendChild(box);
  messagesBox.scrollTop = messagesBox.scrollHeight;
}

function addFallbackNotice() {
  const notice = document.createElement("div");
  notice.className = "ai-summary chat-fallback-notice";
  notice.textContent = "The AI assistant is unavailable right now, so this is a plain keyword search instead.";
  messagesBox.appendChild(notice);
  messagesBox.scrollTop = messagesBox.scrollHeight;
}

function chatPropertyCard(p) {
  const card = document.createElement("article");
  card.className = "property-card chat-property-card";
  card.innerHTML = `
    <div class="card-body">
      <span class="badge">${p.furnishing}</span>
      <h3 class="card-title"><a href="/property/${p.property_id}" target="_blank" rel="noopener">${p.title}</a></h3>
      <p class="card-location">${p.location}, ${p.city}</p>
      <p class="card-rent">${money(p.rent)} <span>/ month</span></p>
      <p class="card-specs">${specsLine(p)}</p>
      <div class="card-actions">
        <a class="card-toggle" href="/property/${p.property_id}" target="_blank" rel="noopener">View details</a>
        <button class="card-toggle" data-action="save" data-id="${p.property_id}">${ICONS.heartOutline} Save</button>
      </div>
    </div>
  `;
  return card;
}

function addPropertyCards(results) {
  if (!results || !results.length) return;
  const grid = document.createElement("div");
  grid.className = "chat-property-grid";
  results.forEach((p) => grid.appendChild(chatPropertyCard(p)));
  messagesBox.appendChild(grid);
  messagesBox.scrollTop = messagesBox.scrollHeight;
}

// Save-to-favorites, with login redirect — delegated on messagesBox so it
// works for cards added by either text search or voice search results.
messagesBox.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action='save']");
  if (!btn) return;
  btn.disabled = true;
  try {
    const res = await authFetch("/favorites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ property_id: Number(btn.dataset.id) }),
    });
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    btn.innerHTML = `${ICONS.heartFilled} Saved`;
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Couldn't save — retry";
  }
});

// ---------------------------------------------------------------
// Text chat (Module 5) — same /ai/chatbot endpoint as before, now
// rendering the richer result set the backend provides (filters +
// up to 10 results, instead of a plain 5-line list).
// ---------------------------------------------------------------

async function sendMessage(message) {
  addBubble("user", message);
  input.value = "";
  input.disabled = true;
  const thinking = addBubble("assistant", "…");

  try {
    const res = await fetch("/ai/chatbot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: chatHistory.slice(-10) }),
    });
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();

    thinking.textContent = data.reply;

    if (data.intent === "search") {
      if (data.used_fallback) {
        addFallbackNotice();
      } else if (data.filters && Object.keys(data.filters).length) {
        addFilterChips(data.filters);
      }
      addPropertyCards(data.results);
    }

    chatHistory.push({ role: "user", content: message });
    chatHistory.push({ role: "assistant", content: data.reply });
  } catch (err) {
    thinking.textContent = "Sorry, I couldn't reach the server. Is uvicorn running?";
  } finally {
    input.disabled = false;
    input.focus();
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  sendMessage(message);
});

// ---------------------------------------------------------------
// Live voice conversation (Gemini Live API) — ported from the old
// standalone /voice-assistant page into this widget. Toggled by the mic
// button next to Send; while active, the text input is disabled (this
// is a continuous hands-free conversation, not type-then-send) and
// chat-voice-status shows Listening/Speaking. See voice_service.py for
// the backend half and the full WebSocket message protocol.
//
// Uses ScriptProcessorNode for mic capture, not the modern (and more
// complex to wire up) AudioWorkletNode — see the original /voice-assistant
// build notes; this is a deliberate minimal-but-working choice, not an
// oversight.
// ---------------------------------------------------------------

const MIC_SAMPLE_RATE = 16000;
const PLAYBACK_SAMPLE_RATE = 24000;

let voiceWs = null;
let voiceSessionActive = false;
let micStream = null;
let micAudioCtx = null;
let micSourceNode = null;
let micProcessorNode = null;

let playbackAudioCtx = null;
let nextPlaybackTime = 0;
let scheduledSources = [];
let pendingChunksForTurn = 0;
let turnCompleteReceived = false;
let pendingBotText = "";

const canDoLiveVoice = !!(
  navigator.mediaDevices &&
  navigator.mediaDevices.getUserMedia &&
  (window.AudioContext || window.webkitAudioContext) &&
  window.WebSocket
);

if (!canDoLiveVoice) {
  voiceToggleBtn.hidden = true; // browser can't support this at all — hide rather than show something broken
}

function setVoiceUiState(label) {
  // label: "listening" | "speaking"
  voiceToggleBtn.classList.remove("listening", "speaking");
  voiceToggleBtn.classList.add(label);
  voiceStatusText.textContent = label === "speaking" ? "Speaking…" : "Listening…";
}

function floatTo16BitPCM(float32Array) {
  const output = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output;
}

async function startMicCapture() {
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

  // Creating the AudioContext AT 16000Hz (rather than relying on a
  // getUserMedia constraint, which browsers often ignore) is what
  // actually gets 16kHz audio reliably — the browser resamples the raw
  // mic input to match the context's own rate internally.
  micAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: MIC_SAMPLE_RATE });
  micSourceNode = micAudioCtx.createMediaStreamSource(micStream);

  micProcessorNode = micAudioCtx.createScriptProcessor(4096, 1, 1);
  micProcessorNode.onaudioprocess = (event) => {
    if (!voiceWs || voiceWs.readyState !== WebSocket.OPEN) return;
    const pcm16 = floatTo16BitPCM(event.inputBuffer.getChannelData(0));
    voiceWs.send(pcm16.buffer);
  };

  micSourceNode.connect(micProcessorNode);
  micProcessorNode.connect(micAudioCtx.destination); // required by some browsers to keep the graph running
}

function stopMicCapture() {
  if (micProcessorNode) micProcessorNode.disconnect();
  if (micSourceNode) micSourceNode.disconnect();
  if (micAudioCtx) micAudioCtx.close();
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  micProcessorNode = micSourceNode = micAudioCtx = micStream = null;
}

function ensurePlaybackContext() {
  if (!playbackAudioCtx) {
    playbackAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: PLAYBACK_SAMPLE_RATE });
    nextPlaybackTime = playbackAudioCtx.currentTime;
  }
}

function playPcmChunk(arrayBuffer) {
  ensurePlaybackContext();
  const int16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
  }

  const buffer = playbackAudioCtx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
  buffer.copyToChannel(float32, 0);

  const source = playbackAudioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackAudioCtx.destination);

  const startAt = Math.max(playbackAudioCtx.currentTime, nextPlaybackTime);
  source.start(startAt);
  nextPlaybackTime = startAt + buffer.duration;

  pendingChunksForTurn++;
  scheduledSources.push(source);
  source.onended = () => {
    scheduledSources = scheduledSources.filter((s) => s !== source);
    pendingChunksForTurn = Math.max(0, pendingChunksForTurn - 1);
    maybeFlushBotBubble();
    if (scheduledSources.length === 0 && voiceSessionActive) setVoiceUiState("listening");
  };

  setVoiceUiState("speaking");
}

function stopPlaybackImmediately() {
  scheduledSources.forEach((s) => {
    try {
      s.onended = null;
      s.stop();
    } catch (err) {
      // already stopped/ended — fine to ignore
    }
  });
  scheduledSources = [];
  pendingChunksForTurn = 0;
  if (playbackAudioCtx) nextPlaybackTime = playbackAudioCtx.currentTime;
}

function maybeFlushBotBubble() {
  if (turnCompleteReceived && pendingChunksForTurn === 0 && pendingBotText) {
    addBubble("assistant", pendingBotText);
    pendingBotText = "";
    turnCompleteReceived = false;
  }
}

function handleVoiceServerMessage(event) {
  if (event.data instanceof ArrayBuffer) {
    playPcmChunk(event.data);
    return;
  }
  if (event.data instanceof Blob) {
    event.data.arrayBuffer().then(playPcmChunk);
    return;
  }

  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case "ready":
      voiceStatusText.textContent = "Connected — go ahead and speak.";
      setVoiceUiState("listening");
      break;

    case "user_transcript":
      // Backend now only ever sends final transcripts (see voice_service.py
      // — a live Gemini connection raised AttributeError on the interim
      // field, so there's no partial "live caption" effect here).
      addBubble("user", msg.text);
      break;

    case "bot_transcript_chunk":
      pendingBotText += msg.text;
      break;

    case "turn_complete":
      turnCompleteReceived = true;
      maybeFlushBotBubble();
      break;

    case "interrupted":
      stopPlaybackImmediately();
      pendingBotText = ""; // discard the cut-off reply's buffered text
      turnCompleteReceived = false;
      setVoiceUiState("listening");
      break;

    case "property_results":
      addPropertyCards(msg.results);
      break;

    case "error":
      addBubble("assistant", msg.message);
      endVoiceSession();
      break;
  }
}

async function startVoiceSession() {
  if (panel.hidden) setPanelOpen(true);

  try {
    await startMicCapture();
  } catch (err) {
    addBubble("assistant", "I don't have permission to use your microphone — check your browser's site settings for this page.");
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  voiceWs = new WebSocket(`${protocol}//${window.location.host}/ws/voice-chat`);
  voiceWs.binaryType = "arraybuffer";

  voiceWs.addEventListener("message", handleVoiceServerMessage);
  voiceWs.addEventListener("close", () => {
    if (voiceSessionActive) endVoiceSession(); // server closed unexpectedly mid-session
  });
  voiceWs.addEventListener("error", () => {
    addBubble("assistant", "Voice connection error — try starting again.");
  });

  voiceSessionActive = true;
  input.disabled = true;
  voiceStatusBox.hidden = false;
  voiceToggleBtn.classList.add("active");
  voiceStatusText.textContent = "Connecting…";
  setVoiceUiState("listening");
}

function endVoiceSession() {
  voiceSessionActive = false;
  stopMicCapture();
  stopPlaybackImmediately();
  if (voiceWs) {
    voiceWs.close();
    voiceWs = null;
  }
  pendingBotText = "";
  turnCompleteReceived = false;
  input.disabled = false;
  voiceStatusBox.hidden = true;
  voiceToggleBtn.classList.remove("active", "listening", "speaking");
  input.focus();
}

voiceToggleBtn.addEventListener("click", () => {
  voiceSessionActive ? endVoiceSession() : startVoiceSession();
});
