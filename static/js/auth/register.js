import { auth } from "../firebase/config.js";
import {
  createUserWithEmailAndPassword
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const $ = (id) => document.getElementById(id);
const msg = $("msg");

function show(text, ok = true) {
  msg.textContent = text;
  msg.classList.add("show");
  msg.style.borderColor = ok ? "rgba(30,136,255,.22)" : "rgba(220,38,38,.22)";
  msg.style.background = ok ? "rgba(99,185,255,.10)" : "rgba(220,38,38,.08)";
}

$("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.classList.remove("show");

  const email = $("email").value.trim();
  const p1 = $("password").value;
  const p2 = $("password2").value;

  if (p1 !== p2) {
    show("Passwords do not match.", false);
    return;
  }

  try {
    await createUserWithEmailAndPassword(auth, email, p1);
    // after registration, go to daily form page
    window.location.href = "./index.html";
  } catch (err) {
    show(err.message, false);
  }
});
