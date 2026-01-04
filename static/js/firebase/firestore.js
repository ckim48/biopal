import { db } from "./config.js";
import { doc, setDoc, getDocs, collection } from "firebase/firestore";

export const saveDailyLog = (uid, date, payload) =>
  setDoc(doc(db, "users", uid, "daily_logs", date), payload, { merge: true });
