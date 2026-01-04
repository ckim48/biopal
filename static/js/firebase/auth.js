import { auth } from "./config.js";
import { signInAnonymously, signOut } from "firebase/auth";

export const login = () => signInAnonymously(auth);
export const logout = () => signOut(auth);
