// public/js/firebase/config.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyAt906fBZy_HEphH847kG8WmszeOvX56fI",
  authDomain: "cancertest-1e83a.firebaseapp.com",
  projectId: "cancertest-1e83a",
  storageBucket: "cancertest-1e83a.firebasestorage.app",
  messagingSenderId: "408747690644",
  appId: "1:408747690644:web:0dae3cdb595cc5ff054281",
  measurementId: "G-5NXEDFTWS2"
};

export const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const auth = getAuth(app);
