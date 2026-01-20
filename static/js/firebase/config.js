// public/js/firebase/config.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyBHSlHAY8XzwOu6kbkmMYzcEWT6qwgry0g",
  authDomain: "immunisphere.firebaseapp.com",
  projectId: "immunisphere",
  storageBucket: "immunisphere.firebasestorage.app",
  messagingSenderId: "424436998430",
  appId: "1:424436998430:web:597374776d04ee5cc4e90f"
};
//const firebaseConfig = {
//  apiKey: "AIzaSyBHSlHAY8XzwOu6kbkmMYzcEWT6qwgry0g",
//  authDomain: "immunisphere.firebaseapp.com",
//  projectId: "immunisphere",
//  storageBucket: "immunisphere.firebasestorage.app",
//  messagingSenderId: "424436998430",
//  appId: "1:424436998430:web:597374776d04ee5cc4e90f"
//};
export const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const auth = getAuth(app);
