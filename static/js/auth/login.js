// public/js/auth/login.js
import { auth } from "../firebase/config.js";
import {
  signInWithEmailAndPassword,
  sendPasswordResetEmail
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const $ = (id) => document.getElementById(id);
const msg = $("msg");
const submitBtn = $("submitBtn");

function show(text, ok = true) {
  msg.textContent = text;
  msg.classList.add("show");
  msg.style.borderColor = ok ? "rgba(30,136,255,.22)" : "rgba(220,38,38,.22)";
  msg.style.background = ok ? "rgba(99,185,255,.10)" : "rgba(220,38,38,.08)";
}

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.classList.remove("show");

  const email = $("email").value.trim();
  const password = $("password").value;

  try {
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in…";

    await signInWithEmailAndPassword(auth, email, password);
    console.log("ABC");
    window.location.replace("/main");
  } catch (err) {
    show(err.message, false);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Continue";
  }
});

$("forgotLink").addEventListener("click", async (e) => {
  e.preventDefault();
  msg.classList.remove("show");

  const email = $("email").value.trim();
  if (!email) {
    show("Please enter your email first, then click “Forgot password?”.", false);
    return;
  }

  try {
    await sendPasswordResetEmail(auth, email);
    show("Password reset email sent. Please check your inbox.");
  } catch (err) {
    show(err.message, false);
  }
});
