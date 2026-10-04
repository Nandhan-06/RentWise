const grid = document.getElementById("property-grid");
const resultCount = document.getElementById("result-count");
const emptyState = document.getElementById("empty-state");
const filterForm = document.getElementById("filter-form");

function propertyCard(p) {
  const card = document.createElement("article");
  card.className = "property-card";
  card.innerHTML = `
    <div class="card-image">
      <img
        src="${p.image_url || '/static/images/prop8.jpg'}"
        alt="${p.title}"
        loading="lazy"
        onerror="this.style.display='none'"
      >
    </div>
    <div class="card-body">
      <span class="badge">${p.furnishing}</span>
      <h3 class="card-title">${p.title}</h3>
      <p class="card-location">${p.location}, ${p.city}</p>
      <p class="card-rent">${money(p.rent)} <span>/ month</span></p>
      <div class="card-specs">
        <span>${p.bedrooms} bed</span>
        <span>${p.bathrooms} bath</span>
        <span>${p.area_sqft ? p.area_sqft + " sqft" : "—"}</span>
        <span>${p.parking ? "Parking" : "No parking"}</span>
      </div>
      <div class="card-actions">
        <button class="card-toggle" data-action="details" data-id="${p.property_id}">View details</button>
        <button class="card-toggle" data-action="save" data-id="${p.property_id}">${ICONS.heartOutline} Save</button>
        <button class="card-toggle" data-action="visit" data-id="${p.property_id}">Schedule visit</button>
      </div>
      <label class="compare-check">
        <input type="checkbox" class="compare-box" data-id="${p.property_id}" data-title="${p.title}" />
        Compare
      </label>
      <div class="card-details" hidden></div>
      <div class="card-visit-form" hidden>
        <label>Pick a date
          <input type="date" class="visit-date" min="${new Date().toISOString().split("T")[0]}" />
        </label>
        <button class="check-slots" data-id="${p.property_id}">Check availability</button>
        <div class="slot-list"></div>
        <p class="visit-status"></p>
      </div>
    </div>
  `;
  return card;
}

function renderProperties(properties) {
  grid.innerHTML = "";
  emptyState.hidden = properties.length > 0;
  properties.forEach((p) => grid.appendChild(propertyCard(p)));
}

// Fetch full details (with amenities) only when a card is expanded,
// since /properties (list) doesn't include the amenities join.
async function loadDetails(propertyId, container) {
  container.innerHTML = "Loading…";
  try {
    const res = await fetch(`/properties/${propertyId}`);
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    const amenities = data.amenities.length
      ? `<div class="amenity-list">${data.amenities
        .map((a) => `<span>${a.amenity_name}</span>`)
        .join("")}</div>`
      : "<p>No amenities listed.</p>";
    container.innerHTML = `<p>${data.description || ""}</p>${amenities}`;
  } catch (err) {
    container.innerHTML = "Couldn't load details. Is the server running?";
  }
}

grid.addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const card = btn.closest(".property-card");

  if (btn.dataset.action === "details") {
    const details = card.querySelector(".card-details");
    const isHidden = details.hidden;
    details.hidden = !isHidden;
    btn.textContent = isHidden ? "Hide details" : "View details";
    if (isHidden && !details.dataset.loaded) {
      details.dataset.loaded = "1";
      loadDetails(btn.dataset.id, details);
    }
    return;
  }

  if (btn.dataset.action === "save") {
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
    return;
  }

  if (btn.dataset.action === "visit") {
    const visitForm = card.querySelector(".card-visit-form");
    visitForm.hidden = !visitForm.hidden;
    return;
  }

  if (btn.classList.contains("check-slots")) {
    const visitForm = btn.closest(".card-visit-form");
    const dateInput = visitForm.querySelector(".visit-date");
    const slotList = visitForm.querySelector(".slot-list");
    const status = visitForm.querySelector(".visit-status");
    if (!dateInput.value) {
      status.textContent = "Pick a date first.";
      return;
    }
    status.textContent = "";
    slotList.innerHTML = "Checking…";
    try {
      const res = await fetch(
        `/visits/availability?property_id=${btn.dataset.id}&visit_date=${dateInput.value}`
      );
      if (!res.ok) throw new Error("Request failed");
      const data = await res.json();
      if (data.available_slots.length === 0) {
        slotList.innerHTML = "";
        status.textContent = "No slots left that day - try another date.";
        return;
      }
      slotList.innerHTML = data.available_slots
        .map((s) => `<button class="slot-btn" data-time="${s}" data-id="${btn.dataset.id}" data-date="${dateInput.value}">${s}</button>`)
        .join("");
    } catch (err) {
      slotList.innerHTML = "";
      status.textContent = "Couldn't check availability - is the server running?";
    }
    return;
  }

  if (btn.classList.contains("slot-btn")) {
    const status = card.querySelector(".visit-status");
    const slotList = card.querySelector(".slot-list");
    status.textContent = "Booking…";
    try {
      const res = await authFetch("/visits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_id: Number(btn.dataset.id),
          visit_date: btn.dataset.date,
          visit_time: btn.dataset.time + ":00",
        }),
      });
      if (!res) return; // authFetch already redirected to /login
      if (res.status === 409) {
        status.textContent = "That slot was just taken - pick another.";
        return;
      }
      if (!res.ok) throw new Error("Request failed");
      slotList.innerHTML = "";
      status.textContent = `Visit booked for ${btn.dataset.date} at ${btn.dataset.time}. See it under "My Visits".`;
    } catch (err) {
      status.textContent = "Booking failed - try again.";
    }
  }
});

function buildQuery(formData) {
  const params = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (value) params.set(key, value);
  }
  return params.toString();
}

async function fetchAndRender(query) {
  resultCount.textContent = "Loading…";
  try {
    const hasFilters = query.length > 0;
    const url = hasFilters ? `/properties/filter?${query}` : `/properties`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    const results = data.results;
    resultCount.textContent = `${results.length} propert${results.length === 1 ? "y" : "ies"} found`;
    renderProperties(results);
  } catch (err) {
    resultCount.textContent = "";
    grid.innerHTML = "";
    emptyState.hidden = false;
    emptyState.textContent =
      "Couldn't reach the server. Make sure uvicorn is running and MySQL is connected.";
  }
}

filterForm.addEventListener("submit", (e) => {
  e.preventDefault();
  fetchAndRender(buildQuery(new FormData(filterForm)));
});

document.getElementById("clear-filters").addEventListener("click", () => {
  filterForm.reset();
  fetchAndRender("");
});

// Initial load
fetchAndRender("");

// --- Compare selection (Module 6) ---
const MAX_COMPARE = 3;
const selectedForCompare = new Map(); // property_id -> title

const compareBar = document.createElement("div");
compareBar.className = "compare-bar";
compareBar.hidden = true;
compareBar.innerHTML = `<span class="compare-bar-text"></span> <button id="compare-go">Compare</button>`;
document.body.appendChild(compareBar);

function updateCompareBar() {
  const n = selectedForCompare.size;
  if (n < 2) {
    compareBar.hidden = true;
    return;
  }
  compareBar.hidden = false;
  compareBar.querySelector(".compare-bar-text").textContent =
    `${n} selected: ${[...selectedForCompare.values()].join(", ")}`;
}

compareBar.querySelector("#compare-go").addEventListener("click", () => {
  const ids = [...selectedForCompare.keys()].join(",");
  window.location.href = `/compare?ids=${ids}`;
});

grid.addEventListener("change", (e) => {
  if (!e.target.matches(".compare-box")) return;
  const box = e.target;
  const id = Number(box.dataset.id);

  if (box.checked) {
    if (selectedForCompare.size >= MAX_COMPARE) {
      box.checked = false;
      alert(`You can compare up to ${MAX_COMPARE} properties. Uncheck one first.`);
      return;
    }
    selectedForCompare.set(id, box.dataset.title);
  } else {
    selectedForCompare.delete(id);
  }
  updateCompareBar();
});
