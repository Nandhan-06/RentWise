const grid = document.getElementById("property-grid");
const resultCount = document.getElementById("result-count");

function showEmptyFavorites() {
  resultCount.textContent = "";
  showState(grid, "empty", {
    title: "You haven't saved any properties yet",
    message: 'Browse the properties and hit "Save" on the ones you like.',
    actionLabel: "Browse properties",
    actionHref: "/",
  });
}

function favoriteCard(p) {
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
      <p class="card-specs">${specsLine(p)}</p>
      <button class="card-toggle remove-fav" data-favorite-id="${p.favorite_id}">Remove from favorites</button>
    </div>
  `;
  return card;
}

async function loadFavorites() {
  resultCount.textContent = "";
  showState(grid, "loading", { title: "Loading your saved properties…" });
  try {
    const res = await authFetch("/favorites");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    if (data.results.length === 0) {
      showEmptyFavorites();
      return;
    }
    grid.innerHTML = "";
    resultCount.textContent = `${data.results.length} saved propert${data.results.length === 1 ? "y" : "ies"}`;
    data.results.forEach((p) => grid.appendChild(favoriteCard(p)));
  } catch (err) {
    resultCount.textContent = "";
    showState(grid, "error", {
      title: "We couldn't load your saved properties",
      onAction: loadFavorites,
    });
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
      showEmptyFavorites();
    } else {
      resultCount.textContent = `${grid.children.length} saved propert${grid.children.length === 1 ? "y" : "ies"}`;
    }
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Couldn't remove - retry";
  }
});

loadFavorites();
