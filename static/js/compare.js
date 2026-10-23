const summaryBox = document.getElementById("compare-summary");
const tableWrap = document.getElementById("compare-table-wrap");

const ROWS = [
  { label: "Rent", get: (p) => `${money(p.rent)} / month` },
  { label: "Type", get: (p) => p.property_type },
  { label: "Location", get: (p) => `${p.location}, ${p.city}` },
  { label: "Bedrooms", get: (p) => p.bedrooms },
  { label: "Bathrooms", get: (p) => p.bathrooms },
  { label: "Area", get: (p) => (p.area_sqft ? `${p.area_sqft} sqft` : "—") },
  { label: "Furnishing", get: (p) => p.furnishing },
  { label: "Parking", get: (p) => (p.parking ? "Yes" : "No") },
  {
    label: "Amenities",
    get: (p) => (p.amenities.length ? p.amenities.map((a) => a.amenity_name).join(", ") : "—"),
  },
];

function renderTable(properties) {
  const table = document.createElement("table");
  table.className = "compare-table";

  const headRow = document.createElement("tr");
  headRow.innerHTML = "<th></th>" + properties.map((p) => `<th>${p.title}</th>`).join("");
  table.appendChild(headRow);

  ROWS.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td class="row-label">${row.label}</td>` +
      properties.map((p) => `<td>${row.get(p)}</td>`).join("");
    table.appendChild(tr);
  });

  tableWrap.innerHTML = "";
  tableWrap.appendChild(table);
}

async function loadComparison() {
  const params = new URLSearchParams(window.location.search);
  const idsParam = params.get("ids");
  const ids = idsParam ? idsParam.split(",").map(Number).filter(Boolean) : [];

  if (ids.length < 2) {
    showState(tableWrap, "empty", {
      title: "Pick two or three properties to compare",
      message: 'On the Properties page, tick "Compare" on each card you want, then click the Compare bar that appears.',
      actionLabel: "Browse properties",
      actionHref: "/",
    });
    return;
  }

  summaryBox.hidden = true;
  showState(tableWrap, "loading", { title: "Comparing properties…" });

  try {
    const res = await fetch("/ai/property-compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ property_ids: ids }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Request failed");
    }
    const data = await res.json();
    renderTable(data.properties);
    if (data.ai_summary) {
      summaryBox.hidden = false;
      summaryBox.textContent = data.ai_summary;
    }
  } catch (err) {
    showState(tableWrap, "error", {
      title: "We couldn't load the comparison",
      // err.message is the server's own explanation (e.g. "Property 99 not found"),
      // or a generic fallback for network problems.
      message: err.message && err.message !== "Request failed" && err.message !== "Failed to fetch" ? err.message : undefined,
      onAction: loadComparison,
    });
  }
}

loadComparison();
