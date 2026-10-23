const grid = document.getElementById("property-grid");
const resultCount = document.getElementById("result-count");
const sortSelect = document.getElementById("sort-select");
const filterForm = document.getElementById("filter-form");

function propertyCard(p) {
  const card = document.createElement("article");
  card.className = "property-card";
  card.innerHTML = `
    <a class="card-image" href="/property/${p.property_id}" aria-label="View ${p.title}">
      <img
        src="${p.image_url || '/static/images/placeholder.svg'}"
        alt="${p.title}"
        loading="lazy"
        onerror="this.onerror=null;this.src='/static/images/placeholder.svg'"
      >
    </a>
    <div class="card-body">
      <span class="badge">${p.furnishing}</span>
      <h3 class="card-title"><a href="/property/${p.property_id}">${p.title}</a></h3>
      <p class="card-location">${p.location}, ${p.city}</p>
      <p class="card-rent">${money(p.rent)} <span>/ month</span></p>
      <div class="card-specs">
        <span>${p.bedrooms} bed</span>
        <span>${p.bathrooms} bath</span>
        <span>${p.area_sqft ? p.area_sqft + " sqft" : "—"}</span>
        <span>${p.parking ? "Parking" : "No parking"}</span>
      </div>
      <div class="card-actions">
        <a class="card-toggle" href="/property/${p.property_id}">View details</a>
        <button class="card-toggle" data-action="save" data-id="${p.property_id}">${ICONS.heartOutline} Save</button>
        <button class="card-toggle" data-action="visit" data-id="${p.property_id}">Schedule visit</button>
      </div>
      <label class="compare-check">
        <input type="checkbox" class="compare-box" data-id="${p.property_id}" data-title="${p.title}" ${selectedForCompare.has(p.property_id) ? "checked" : ""} />
        Compare
      </label>
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
  properties.forEach((p) => grid.appendChild(propertyCard(p)));
}

grid.addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const card = btn.closest(".property-card");

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
    if (!value) continue;
    if (key === "sort" && value === "newest") continue; // the default - keep URLs clean
    params.set(key, value);
  }
  return params.toString();
}

// Each search gets a number. If a slower, older response arrives after a newer
// one (easy to cause by changing the sort quickly), it is ignored instead of
// overwriting the newer results.
let latestRequest = 0;

function clearFilters() {
  filterForm.reset(); // also resets the sort box back to "Newest first"
  fetchAndRender("");
}

async function fetchAndRender(query) {
  const thisRequest = ++latestRequest;
  resultCount.textContent = "";
  showState(grid, "loading", { title: "Loading properties…" });

  // Keep the address bar in step with what is on screen, so refreshing or
  // sharing the link shows the same filters and sort.
  history.replaceState(null, "", query ? `?${query}` : window.location.pathname);

  try {
    const url = query ? `/properties/filter?${query}` : `/properties`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    if (thisRequest !== latestRequest) return; // a newer search has started

    const results = data.results;
    resultCount.textContent = `${results.length} propert${results.length === 1 ? "y" : "ies"} found`;

    if (results.length === 0) {
      const filtered = [...new URLSearchParams(query).keys()].some((k) => k !== "sort");
      showState(grid, "empty", filtered
        ? {
            title: "No properties match those filters",
            message: "Try widening your rent range or removing a filter.",
            actionLabel: "Clear filters",
            onAction: clearFilters,
          }
        : { title: "No properties are listed right now", message: "Please check back soon." });
      return;
    }
    renderProperties(results);
  } catch (err) {
    if (thisRequest !== latestRequest) return;
    resultCount.textContent = "";
    showState(grid, "error", {
      title: "We couldn't load the properties",
      onAction: () => fetchAndRender(query),
    });
  }
}

filterForm.addEventListener("submit", (e) => {
  e.preventDefault();
  fetchAndRender(buildQuery(new FormData(filterForm)));
});

document.getElementById("clear-filters").addEventListener("click", clearFilters);

// Changing the sort re-runs the current search straight away.
sortSelect.addEventListener("change", () => {
  fetchAndRender(buildQuery(new FormData(filterForm)));
});

// Initial load. If the URL carries filters (e.g. the footer's /?city=Kochi),
// put them in the form first so the inputs match what is being shown.
const FILTER_FIELDS = ["city", "property_type", "bedrooms", "min_rent", "max_rent", "sort"];
const urlParams = new URLSearchParams(window.location.search);
FILTER_FIELDS.forEach((name) => {
  if (urlParams.has(name) && filterForm.elements[name]) {
    filterForm.elements[name].value = urlParams.get(name);
  }
});
fetchAndRender(buildQuery(new FormData(filterForm)));

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
