// Property Detail page behaviour: gallery thumbnails, Save, and the
// schedule-a-visit flow. Wrapped in an IIFE on purpose: base.html loads
// chatbot.js on every page and it declares several top-level variables, so
// anything declared at the top level here could collide with it
// ("already declared" SyntaxError). Everything below stays private.
(function () {
  const root = document.getElementById("property-detail");
  if (!root) return;

  const propertyId = Number(root.dataset.propertyId);
  const loggedIn = root.dataset.loggedIn === "true";
  const available = root.dataset.available === "true";

  // ---- Gallery: click a thumbnail to swap the main image ----
  const mainImg = document.getElementById("detail-main-img");
  document.querySelectorAll(".detail-thumb").forEach((thumb) => {
    thumb.addEventListener("click", () => {
      mainImg.src = thumb.dataset.src;
      document.querySelectorAll(".detail-thumb").forEach((t) => t.classList.remove("active"));
      thumb.classList.add("active");
    });
  });

  // ---- Save to favourites ----
  const saveBtn = document.getElementById("detail-save");
  const actionStatus = document.getElementById("detail-action-status");

  function markSaved() {
    saveBtn.innerHTML = `${ICONS.heartFilled} Saved`;
    saveBtn.disabled = true;
  }

  // If logged in, show "Saved" up front when this property is already a
  // favourite. Plain fetch (not authFetch): a failure here should be silent,
  // never redirect the visitor away from the page.
  if (loggedIn) {
    fetch("/favorites")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.results.some((f) => f.property_id === propertyId)) markSaved();
      })
      .catch(() => {});
  }

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    actionStatus.textContent = "";
    try {
      const res = await authFetch("/favorites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ property_id: propertyId }),
      });
      if (!res) return; // authFetch already redirected to /login
      if (!res.ok) throw new Error("Request failed");
      markSaved();
    } catch (err) {
      saveBtn.disabled = false;
      actionStatus.textContent = "Couldn't save - please try again.";
    }
  });

  // ---- Schedule a visit (same endpoints the property cards use) ----
  const visitToggle = document.getElementById("detail-visit-toggle");
  const visitForm = document.getElementById("detail-visit-form");
  const dateInput = document.getElementById("detail-visit-date");
  const checkBtn = document.getElementById("detail-check-slots");
  const slotList = document.getElementById("detail-slot-list");
  const visitStatus = document.getElementById("detail-visit-status");

  dateInput.min = new Date().toISOString().split("T")[0];

  visitToggle.addEventListener("click", () => {
    if (!available) return;
    visitForm.hidden = !visitForm.hidden;
  });

  checkBtn.addEventListener("click", async () => {
    if (!dateInput.value) {
      visitStatus.textContent = "Pick a date first.";
      return;
    }
    visitStatus.textContent = "";
    slotList.innerHTML = "Checking…";
    try {
      const res = await fetch(
        `/visits/availability?property_id=${propertyId}&visit_date=${dateInput.value}`
      );
      if (!res.ok) throw new Error("Request failed");
      const data = await res.json();
      if (data.available_slots.length === 0) {
        slotList.innerHTML = "";
        visitStatus.textContent = "No slots left that day - try another date.";
        return;
      }
      slotList.innerHTML = data.available_slots
        .map((s) => `<button type="button" class="slot-btn" data-time="${s}">${s}</button>`)
        .join("");
    } catch (err) {
      slotList.innerHTML = "";
      visitStatus.textContent = "Couldn't check availability - please try again.";
    }
  });

  slotList.addEventListener("click", async (e) => {
    const btn = e.target.closest(".slot-btn");
    if (!btn) return;
    visitStatus.textContent = "Booking…";
    try {
      const res = await authFetch("/visits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_id: propertyId,
          visit_date: dateInput.value,
          visit_time: btn.dataset.time + ":00",
        }),
      });
      if (!res) return; // authFetch already redirected to /login
      if (res.status === 409) {
        visitStatus.textContent = "That slot was just taken - pick another.";
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        visitStatus.textContent = err.detail || "Booking failed - please try again.";
        return;
      }
      slotList.innerHTML = "";
      visitStatus.innerHTML =
        `Visit booked for ${dateInput.value} at ${btn.dataset.time}. ` +
        `See it under <a href="/my-visits">My Visits</a>.`;
    } catch (err) {
      visitStatus.textContent = "Booking failed - please try again.";
    }
  });
})();
