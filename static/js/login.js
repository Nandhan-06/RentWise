const loginForm = document.getElementById("login-form");
const errorBox = document.getElementById("auth-error");

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.textContent = "";

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: loginForm.email.value,
        password: loginForm.password.value,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      errorBox.textContent = err.detail || "Something went wrong. Try again.";
      return;
    }

    // Only follow ?next= if it is a path on THIS site ("/property/3").
    // Anything else - "https://evil.example", "//evil.example", "/\\evil" -
    // would let a crafted login link send people to another website.
    const next = new URLSearchParams(window.location.search).get("next");
    window.location.href = next && /^\/(?![\/\\])/.test(next) ? next : "/";
  } catch (err) {
    errorBox.textContent = "Couldn't reach the server. Is uvicorn running?";
  }
});
