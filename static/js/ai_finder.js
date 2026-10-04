const form = document.getElementById("ai-form");
const queryInput = document.getElementById("ai-query");
const statusBox = document.getElementById("ai-status");
const summaryBox = document.getElementById("ai-summary");
const filtersBox = document.getElementById("ai-filters");
const grid = document.getElementById("property-grid");
const emptyState = document.getElementById("empty-state");

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

function renderFilters(filters) {
  const entries = Object.entries(filters || {});
  if (!entries.length) {
    filtersBox.hidden = true;
    return;
  }
  filtersBox.hidden = false;
  filtersBox.innerHTML = entries
    .map(([k, v]) => `<span class="filter-chip">${FILTER_LABELS[k] || k}: ${formatFilterValue(k, v)}</span>`)
    .join("");
}

function aiPropertyCard(p) {
  const card = document.createElement("article");
  card.className = "property-card";
  card.innerHTML = `
    <div class="card-image">No image</div>
    <div class="card-body">
      <span class="badge">${p.furnishing}</span>
      <h3 class="card-title">${p.title}</h3>
      <p class="card-location">${p.location}, ${p.city}</p>
      <p class="card-rent">${money(p.rent)} <span>/ month</span></p>
      <p class="card-specs">${specsLine(p)}</p>
      <button class="card-toggle" data-action="save" data-id="${p.property_id}">${ICONS.heartOutline} Save</button>
    </div>
  `;
  return card;
}

grid.addEventListener("click", async (e) => {
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
    btn.textContent = "Couldn't save - retry";
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  statusBox.hidden = false;
  statusBox.textContent = "Thinking…";
  summaryBox.hidden = true;
  filtersBox.hidden = true;
  grid.innerHTML = "";
  emptyState.hidden = true;

  try {
    const res = await fetch("/ai/property-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();

    statusBox.hidden = true;

    if (data.used_fallback) {
      summaryBox.hidden = false;
      summaryBox.textContent =
        "The AI assistant is unavailable right now, so this is a plain keyword search instead.";
    } else {
      renderFilters(data.filters);
      if (data.summary) {
        summaryBox.hidden = false;
        summaryBox.textContent = data.summary;
      }
    }

    if (data.results.length === 0) {
      emptyState.hidden = false;
      emptyState.textContent = "No properties matched that request. Try loosening a constraint.";
    } else {
      data.results.forEach((p) => grid.appendChild(aiPropertyCard(p)));
    }
  } catch (err) {
    statusBox.hidden = false;
    statusBox.textContent = "Couldn't reach the server. Make sure uvicorn is running.";
  }
});
