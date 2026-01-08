// public/js/firebase/config.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyBX4q-sOcYbPAkzQCaKuQkrMPUuxmMPi4E",
  authDomain: "cancer-4dce7.firebaseapp.com",
  projectId: "cancer-4dce7",
  storageBucket: "cancer-4dce7.firebasestorage.app",
  messagingSenderId: "886892546006",
  appId: "1:886892546006:web:a24b1d1e09dbdf219d8677",
  measurementId: "G-2CB8SDWRLL"
};

export const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const auth = getAuth(app);
