const visitList = document.getElementById("visit-list");

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
  showState(visitList, "loading", { title: "Loading your visits…" });
  try {
    const res = await authFetch("/visits/mine");
    if (!res) return; // authFetch already redirected to /login
    if (!res.ok) throw new Error("Request failed");
    const data = await res.json();
    if (data.results.length === 0) {
      showState(visitList, "empty", {
        title: "No visits scheduled yet",
        message: 'Open a property and choose "Schedule a visit" to book one.',
        actionLabel: "Browse properties",
        actionHref: "/",
      });
      return;
    }
    visitList.innerHTML = "";
    data.results.forEach((v) => visitList.appendChild(visitRow(v)));
  } catch (err) {
    showState(visitList, "error", {
      title: "We couldn't load your visits",
      onAction: loadVisits,
    });
  }
}

loadVisits();
