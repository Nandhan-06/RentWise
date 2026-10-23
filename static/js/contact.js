// Contact page. Wrapped in an IIFE so nothing here can collide with the
// globals declared by chatbot.js, which base.html loads on every page.
(function () {
  const form = document.getElementById("contact-form");
  if (!form) return;

  const errorBox = document.getElementById("contact-error");
  const success = document.getElementById("contact-success");
  const submitBtn = document.getElementById("contact-submit");
  const message = document.getElementById("c-message");
  const counter = document.getElementById("c-count");

  message.addEventListener("input", () => {
    counter.textContent = `${message.value.length} / 2000`;
  });

  // The server returns validation problems as a list of technical messages.
  // Turn the likely ones into plain English instead of showing them raw.
  function friendlyError(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      const fields = detail.map((d) => (d.loc && d.loc[d.loc.length - 1]) || "");
      if (fields.includes("email")) return "Please enter a valid email address.";
      if (fields.includes("message")) return "Please write a message of at least 10 characters.";
      if (fields.includes("name")) return "Please enter your name.";
    }
    return "Please check the form and try again.";
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.textContent = "";

    const body = {
      name: form.name.value,
      email: form.email.value,
      topic: form.topic.value,
      message: form.message.value,
      website: form.website.value, // honeypot - empty for real people
    };

    if (!body.name.trim()) return void (errorBox.textContent = "Please enter your name.");
    if (!body.email.trim()) return void (errorBox.textContent = "Please enter your email address.");
    if (body.message.trim().length < 10)
      return void (errorBox.textContent = "Please write a message of at least 10 characters.");

    submitBtn.disabled = true;
    submitBtn.textContent = "Sending…";
    try {
      const res = await fetch("/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        errorBox.textContent = friendlyError(err.detail);
        return;
      }
      form.hidden = true;
      success.hidden = false;
      success.focus?.();
    } catch (err) {
      errorBox.textContent = "Couldn't reach the server - please try again.";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Send message";
    }
  });
})();
