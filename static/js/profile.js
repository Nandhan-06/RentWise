const form = document.getElementById("profile-form");
const status = document.getElementById("profile-status");
const insightsBox = document.getElementById("insights-box");

// What the server last gave us, so we can tell what the visitor actually changed.
let loadedProfile = { name: "", phone: "", email: "" };

async function loadProfile() {
  try {
    const res = await authFetch("/users/me");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const user = await res.json();
    loadedProfile = { name: user.name || "", phone: user.phone || "", email: user.email || "" };
    form.name.value = loadedProfile.name;
    form.phone.value = loadedProfile.phone;
    form.email.value = loadedProfile.email;
  } catch (err) {
    status.textContent = "Couldn't load your details. Please refresh the page.";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = form.name.value.trim();
  if (!name) {
    status.textContent = "Please enter your name.";
    return;
  }

  // Only send the email if it was actually changed. Re-sending an unchanged
  // address made the server re-check it, and an address it considers
  // invalid (such as the seeded demo@rentwise.test) blocked the whole save.
  const body = { name, phone: form.phone.value.trim() };
  const email = form.email.value.trim();
  if (email !== loadedProfile.email) body.email = email;

  status.textContent = "Saving…";
  try {
    const res = await authFetch("/users/me", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      status.textContent = apiErrorMessage(err.detail, "Couldn't save - try again.");
      return;
    }
    const user = await res.json();
    loadedProfile = { name: user.name || "", phone: user.phone || "", email: user.email || "" };
    status.textContent = "Saved.";
    setTimeout(() => (status.textContent = ""), 2000);
  } catch (err) {
    status.textContent = "Couldn't save - try again.";
  }
});

// ---------------------------------------------------------------
// Rental preferences (Module 11)
// ---------------------------------------------------------------
const prefForm = document.getElementById("pref-form");
const prefStatus = document.getElementById("pref-status");
const prefMatches = document.getElementById("pref-matches");

function fillPreferences(p) {
  prefForm.preferred_city.value = p.preferred_city ?? "";
  prefForm.min_budget.value = p.min_budget ?? "";
  prefForm.max_budget.value = p.max_budget ?? "";
  prefForm.bedrooms.value = p.bedrooms == null ? "" : String(Math.min(p.bedrooms, 4));
  prefForm.property_type.value = p.property_type ?? "";
  prefForm.furnishing.value = p.furnishing ?? "";
  prefForm.needs_parking.checked = Boolean(p.needs_parking);
  updateMatchLink(p);
}

// "See properties that match" opens the home page with the filters the list
// page already understands (city, type, bedrooms, rent range) pre-filled.
// Furnishing and parking are saved but the list page has no controls for
// them yet, so they are not part of this link.
function updateMatchLink(p) {
  const params = new URLSearchParams();
  if (p.preferred_city) params.set("city", p.preferred_city);
  if (p.property_type) params.set("property_type", p.property_type);
  if (p.bedrooms != null) params.set("bedrooms", String(Math.min(p.bedrooms, 4)));
  if (p.min_budget != null) params.set("min_rent", String(p.min_budget));
  if (p.max_budget != null) params.set("max_rent", String(p.max_budget));
  const query = params.toString();
  prefMatches.hidden = !query;
  prefMatches.href = query ? `/?${query}` : "/";
}

function readPreferences() {
  const num = (v) => (v === "" ? null : Number(v));
  return {
    preferred_city: prefForm.preferred_city.value.trim() || null,
    min_budget: num(prefForm.min_budget.value),
    max_budget: num(prefForm.max_budget.value),
    bedrooms: prefForm.bedrooms.value === "" ? null : Number(prefForm.bedrooms.value),
    property_type: prefForm.property_type.value || null,
    furnishing: prefForm.furnishing.value || null,
    needs_parking: prefForm.needs_parking.checked,
  };
}

async function loadPreferences() {
  try {
    const res = await authFetch("/users/me/preferences");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    fillPreferences(await res.json());
  } catch (err) {
    prefStatus.textContent = "Couldn't load your preferences. Please refresh the page.";
  }
}

async function savePreferences(prefs, doneMessage) {
  if (prefs.min_budget != null && prefs.max_budget != null && prefs.min_budget > prefs.max_budget) {
    prefStatus.textContent = "Your minimum budget can't be higher than your maximum.";
    return;
  }
  prefStatus.textContent = "Saving…";
  try {
    const res = await authFetch("/users/me/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs),
    });
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      prefStatus.textContent = apiErrorMessage(err.detail, "Couldn't save your preferences - try again.");
      return;
    }
    const saved = await res.json();
    fillPreferences(saved);
    prefStatus.textContent = doneMessage;
    setTimeout(() => (prefStatus.textContent = ""), 2500);
  } catch (err) {
    prefStatus.textContent = "Couldn't save your preferences - try again.";
  }
}

prefForm.addEventListener("submit", (e) => {
  e.preventDefault();
  savePreferences(readPreferences(), "Preferences saved.");
});

document.getElementById("pref-clear").addEventListener("click", () => {
  savePreferences(
    { preferred_city: null, min_budget: null, max_budget: null, bedrooms: null, property_type: null, furnishing: null, needs_parking: false },
    "Preferences cleared."
  );
});

function formatInsightStats(stats) {
  return `${stats.count} saved · avg ${money(stats.avg_rent)}/mo · mostly ${stats.top_city}, ${stats.top_property_type}`;
}

async function loadInsights() {
  showState(insightsBox, "loading", { title: "Loading your insights…" });
  try {
    const res = await authFetch("/ai/rental-insights");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();

    if (!data.has_data) {
      showState(insightsBox, "empty", {
        title: "No insights yet",
        message: "Save a few properties and your rental insights will show up here.",
        actionLabel: "Browse properties",
        actionHref: "/",
      });
      return;
    }

    if (data.summary) {
      insightsBox.textContent = `${data.summary} (${formatInsightStats(data.stats)})`;
    } else {
      insightsBox.textContent = `${formatInsightStats(data.stats)} - AI summary unavailable right now, showing raw stats instead.`;
    }
  } catch (err) {
    showState(insightsBox, "error", {
      title: "We couldn't load your insights",
      onAction: loadInsights,
    });
  }
}

loadProfile();
loadPreferences();
loadInsights();
