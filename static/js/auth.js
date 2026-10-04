// Module 7 — loaded globally (like common.js/chatbot.js) from base.html.
//
// authFetch() is a drop-in replacement for fetch() for any request that
// needs a logged-in user. The session cookie itself is sent automatically
// by the browser on every same-origin request - nothing to attach here —
// this wrapper's only job is: if the server says 401 (not logged in),
// redirect to /login instead of letting the calling page's JS try to
// render undefined data.
async function authFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
    return null; // caller's await will hang briefly during redirect; fine.
  }
  return res;
}

// Wire up the logout button in the nav (present on every page via base.html).
document.addEventListener("DOMContentLoaded", () => {
  const logoutBtn = document.getElementById("nav-logout");
  if (!logoutBtn) return;
  logoutBtn.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST" });
    window.location.href = "/";
  });
});
