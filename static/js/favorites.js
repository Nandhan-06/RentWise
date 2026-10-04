const grid = document.getElementById("property-grid");
const resultCount = document.getElementById("result-count");
const emptyState = document.getElementById("empty-state");

function favoriteCard(p) {
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
      <button class="card-toggle remove-fav" data-favorite-id="${p.favorite_id}">Remove from favorites</button>
    </div>
  `;
  return card;
}

async function loadFavorites() {
  resultCount.textContent = "Loading…";
  try {
    const res = await authFetch("/favorites");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    grid.innerHTML = "";
    emptyState.hidden = data.results.length > 0;
    resultCount.textContent = data.results.length
      ? `${data.results.length} saved propert${data.results.length === 1 ? "y" : "ies"}`
      : "";
    data.results.forEach((p) => grid.appendChild(favoriteCard(p)));
  } catch (err) {
    resultCount.textContent = "";
    emptyState.hidden = false;
    emptyState.textContent = "Couldn't reach the server. Make sure uvicorn is running.";
  }
}

grid.addEventListener("click", async (e) => {
  if (!e.target.matches(".remove-fav")) return;
  const btn = e.target;
  btn.disabled = true;
  btn.textContent = "Removing…";
  try {
    const res = await authFetch(`/favorites/${btn.dataset.favoriteId}`, { method: "DELETE" });
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok && res.status !== 204) throw new Error("Request failed");
    btn.closest(".property-card").remove();
    if (!grid.children.length) {
      emptyState.hidden = false;
      resultCount.textContent = "";
    } else {
      resultCount.textContent = `${grid.children.length} saved propert${grid.children.length === 1 ? "y" : "ies"}`;
    }
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Couldn't remove - retry";
  }
});

loadFavorites();
