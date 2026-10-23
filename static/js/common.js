// Shared across every page's JS.
//
// Module 7 removed DEMO_USER_ID entirely — identity now comes from the
// session cookie the browser sends automatically, not from a hardcoded
// constant. Any request that needs to know "which user" just fetches
// from an endpoint that reads request.session server-side (see auth.js
// for the shared fetch wrapper that handles the "not logged in" case).

function money(n) {
  return "₹" + Math.round(Number(n)).toLocaleString("en-IN");
}

function specsLine(p) {
  return `${p.bedrooms} bed · ${p.bathrooms} bath · ${p.area_sqft ? p.area_sqft + " sqft" : "—"} · ${p.parking ? "Parking" : "No parking"}`;
}

// Small inline SVG icons, replacing the emoji characters (♡ ♥ 💬 ✕) the
// UI used to rely on for icon duty — emoji rendering varies by OS/font
// and reads as an unstyled default rather than a deliberate choice.
// currentColor means each icon inherits whatever color its button uses.
const ICONS = {
  heartOutline: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
  heartFilled: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:-2px"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
};

// ---------------------------------------------------------------
// Module 10 - one look for "loading", "nothing here" and "something broke".
//
//   showState(container, "loading")
//   showState(container, "empty",  { title, message, actionLabel, actionHref })
//   showState(container, "error",  { message, onAction })   // onAction = retry
//
// It REPLACES whatever is inside `container` (cards, a table, old text) with
// one consistent panel. Text goes in with textContent, never innerHTML, so a
// message can never inject markup.
// ---------------------------------------------------------------
const STATE_DEFAULTS = {
  loading: { title: "Loading…" },
  empty: { title: "Nothing here yet" },
  error: {
    title: "Something went wrong",
    message: "We couldn't load this right now. Please check your connection and try again.",
    actionLabel: "Try again",
  },
};

function showState(container, kind, options = {}) {
  const o = { ...STATE_DEFAULTS[kind], ...options };
  const box = document.createElement("div");
  box.className = `state state-${kind}`;
  box.setAttribute("role", kind === "error" ? "alert" : "status");

  if (kind === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "state-spinner";
    spinner.setAttribute("aria-hidden", "true");
    box.appendChild(spinner);
  }

  const title = document.createElement("p");
  title.className = "state-title";
  title.textContent = o.title;
  box.appendChild(title);

  if (o.message) {
    const msg = document.createElement("p");
    msg.className = "state-message";
    msg.textContent = o.message;
    box.appendChild(msg);
  }

  if (o.actionLabel && o.actionHref) {
    const a = document.createElement("a");
    a.className = "state-action";
    a.href = o.actionHref;
    a.textContent = o.actionLabel;
    box.appendChild(a);
  } else if (o.actionLabel && o.onAction) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "state-action";
    b.textContent = o.actionLabel;
    b.addEventListener("click", o.onAction);
    box.appendChild(b);
  }

  container.replaceChildren(box);
  return box;
}

// Turns whatever the server put in `detail` into one readable sentence.
// FastAPI sends a plain string for errors we raise ourselves ("That email is
// already used...") but a LIST of technical objects for form-validation
// errors - showing that list directly prints "[object Object]".
function apiErrorMessage(detail, fallback) {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail[0] && detail[0].msg) {
    return String(detail[0].msg).replace(/^Value error,\s*/, "");
  }
  return fallback;
}
