const form = document.getElementById("profile-form");
const status = document.getElementById("profile-status");
const insightsBox = document.getElementById("insights-box");

async function loadProfile() {
  try {
    const res = await authFetch("/users/me");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const user = await res.json();
    form.name.value = user.name || "";
    form.phone.value = user.phone || "";
    form.email.value = user.email || "";
  } catch (err) {
    status.textContent = "Couldn't load profile - is the server running?";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  status.textContent = "Saving…";
  try {
    const res = await authFetch("/users/me", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: form.name.value,
        phone: form.phone.value,
        email: form.email.value,
      }),
    });
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      status.textContent = err.detail || "Couldn't save - try again.";
      return;
    }
    status.textContent = "Saved.";
    setTimeout(() => (status.textContent = ""), 2000);
  } catch (err) {
    status.textContent = "Couldn't save - try again.";
  }
});

function formatInsightStats(stats) {
  return `${stats.count} saved · avg ${money(stats.avg_rent)}/mo · mostly ${stats.top_city}, ${stats.top_property_type}`;
}

async function loadInsights() {
  try {
    const res = await authFetch("/ai/rental-insights");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();

    if (!data.has_data) {
      insightsBox.textContent = "No favorites saved yet - save a few properties to see insights here.";
      return;
    }

    if (data.summary) {
      insightsBox.textContent = `${data.summary} (${formatInsightStats(data.stats)})`;
    } else {
      insightsBox.textContent = `${formatInsightStats(data.stats)} - AI summary unavailable right now, showing raw stats instead.`;
    }
  } catch (err) {
    insightsBox.textContent = "Couldn't load insights - is the server running?";
  }
}

loadProfile();
loadInsights();
