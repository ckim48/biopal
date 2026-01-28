import { auth } from "../firebase/config.js";
import { sendPasswordResetEmail } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const $ = (id) => document.getElementById(id);
const msg = $("msg");
const submitBtn = $("submitBtn");

function show(text, ok = true) {
  msg.textContent = text;
  msg.classList.add("show");
  msg.style.borderColor = ok ? "rgba(30,136,255,.22)" : "rgba(220,38,38,.22)";
  msg.style.background = ok ? "rgba(99,185,255,.10)" : "rgba(220,38,38,.08)";
}

function getPrefillEmail() {
  const params = new URLSearchParams(window.location.search);
  return (params.get("email") || "").trim();
}

window.addEventListener("DOMContentLoaded", () => {
  const prefill = getPrefillEmail();
  if (prefill) $("email").value = prefill;
});

$("resetForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.classList.remove("show");

  const email = $("email").value.trim();
  if (!email) return show("Please enter your email.", false);

  try {
    submitBtn.disabled = true;
    submitBtn.textContent = "Sending…";

    await sendPasswordResetEmail(auth, email);

    show("Reset email sent. Please check your inbox (and spam folder).");
  } catch (err) {
    show(err.message, false);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Send reset email";
  }
});
