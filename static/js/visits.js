const visitList = document.getElementById("visit-list");
const emptyState = document.getElementById("empty-state");

function statusClass(status) {
  return { Scheduled: "status-scheduled", Completed: "status-completed", Cancelled: "status-cancelled" }[status] || "";
}

function visitRow(v) {
  const row = document.createElement("article");
  row.className = "visit-row";
  row.innerHTML = `
    <div class="visit-info">
      <h3 class="card-title">${v.title}</h3>
      <p class="card-location">${v.location}, ${v.city}</p>
    </div>
    <div class="visit-when">
      <p>${v.visit_date}</p>
      <p>${v.visit_time}</p>
    </div>
    <span class="badge ${statusClass(v.status)}">${v.status}</span>
  `;
  return row;
}

async function loadVisits() {
  try {
    const res = await authFetch("/visits/mine");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    visitList.innerHTML = "";
    emptyState.hidden = data.results.length > 0;
    data.results.forEach((v) => visitList.appendChild(visitRow(v)));
  } catch (err) {
    emptyState.hidden = false;
    emptyState.textContent = "Couldn't reach the server. Make sure uvicorn is running.";
  }
}

loadVisits();
