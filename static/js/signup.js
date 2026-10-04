const signupForm = document.getElementById("signup-form");const errorBox = document.getElementById("auth-error");
const landlordCheck = document.getElementById("s-landlord");
const landlordNote = document.getElementById("landlord-note");

landlordCheck.addEventListener("change", () => {
  landlordNote.hidden = !landlordCheck.checked;
});

signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.textContent = "";

  // Client-side check before ever hitting the server — the backend
  // re-validates this too (never trust client-only validation for
  // something a password-manager or curl could bypass).
  if (signupForm.password.value !== signupForm.confirm_password.value) {
    errorBox.textContent = "Passwords don't match.";
    return;
  }

  try {
    const res = await fetch("/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: signupForm.name.value,
        email: signupForm.email.value,
        phone: signupForm.phone.value || null,
        password: signupForm.password.value,
        confirm_password: signupForm.confirm_password.value,
        terms_accepted: document.getElementById("s-terms").checked,
        register_as_landlord: landlordCheck.checked,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      // FastAPI/Pydantic validation errors come back as a `detail` array,
      // not a single string — handle both shapes rather than showing
      // "[object Object]" to the user.
      if (Array.isArray(err.detail)) {
        errorBox.textContent = err.detail.map((d) => d.msg).join(" ");
      } else {
        errorBox.textContent = err.detail || "Something went wrong. Try again.";
      }
      return;
    }

    window.location.href = "/";
  } catch (err) {
    errorBox.textContent = "Couldn't reach the server. Is uvicorn running?";
  }
});
