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

    const params = new URLSearchParams(window.location.search);
    window.location.href = params.get("next") || "/";
  } catch (err) {
    errorBox.textContent = "Couldn't reach the server. Is uvicorn running?";
  }
});
