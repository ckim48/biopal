# app.py
# NOTE:
# 1) You pasted a real OpenAI API key in chat. You should revoke/rotate it immediately.
# 2) The Firebase "firebaseConfig" (apiKey/authDomain/...) is for *browser client SDK*.
#    For a Python server to read ALL users/emails safely, you MUST use Firebase Admin
#    with a Service Account (recommended). Below I show hardcoded service-account fields.

import json
from datetime import datetime
from flask import Flask, render_template, request, session, jsonify

from openai import OpenAI

import firebase_admin
from firebase_admin import credentials, firestore, auth as fb_auth

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret-key"

# -----------------------------
# OpenAI (HARDCODED per your request)
# -----------------------------
# IMPORTANT: do NOT hardcode secrets in production.
OPENAI_MODEL = "gpt-4o-mini"



# -----------------------------
# Firebase (SERVER Admin SDK)
# -----------------------------
# Your web client config (kept here only because you asked):
FIREBASE_WEB_CONFIG = {
    "apiKey": "AIzaSyBX4q-sOcYbPAkzQCaKuQkrMPUuxmMPi4E",
    "authDomain": "cancer-4dce7.firebaseapp.com",
    "projectId": "cancer-4dce7",
    "storageBucket": "cancer-4dce7.firebasestorage.app",
    "messagingSenderId": "886892546006",
    "appId": "1:886892546006:web:a24b1d1e09dbdf219d8677",
    "measurementId": "G-2CB8SDWRLL",
}

# SERVER Admin credential (Service Account) — you must fill these from the JSON you downloaded:
# Firebase Console -> Project Settings -> Service Accounts -> Generate new private key
# Then copy the fields into this dict.
# FIREBASE_SERVICE_ACCOUNT = {
#     "type": "service_account",
#     "project_id": "cancer-4dce7",
#     # ---- FILL THESE FROM YOUR service account JSON ----
#     "private_key_id": "PASTE_PRIVATE_KEY_ID",
#     "private_key": "-----BEGIN PRIVATE KEY-----\nPASTE_YOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n",
#     "client_email": "PASTE_CLIENT_EMAIL@cancer-4dce7.iam.gserviceaccount.com",
#     "client_id": "PASTE_CLIENT_ID",
#     # -----------------------------------------------
#     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#     "token_uri": "https://oauth2.googleapis.com/token",
#     "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
#     "client_x509_cert_url": "PASTE_CLIENT_X509_CERT_URL",
# }

# Initialize Firebase Admin exactly once
# if not firebase_admin._apps:
#     cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
#     firebase_admin.initialize_app(cred)

# db = firestore.client()


# -----------------------------
# Pages
# -----------------------------
@app.get("/")
def home():
    return render_template("index.html")

@app.get("/profile")
def profile():
    return render_template("profile.html")

@app.get("/login")
def login():
    return render_template("login.html")

@app.get("/register")
def register():
    return render_template("register.html")

@app.get("/main")
def main():
    return render_template("main.html")


# -----------------------------
# Session login/logout
# -----------------------------
@app.post("/api/session-login")
def session_login():
    data = request.get_json(silent=True) or {}

    id_token = (data.get("idToken") or "").strip()
    email = (data.get("email") or "").strip()
    uid = (data.get("uid") or "").strip()

    if not (id_token or email or uid):
        return jsonify({"ok": False, "error": "Missing auth payload"}), 400

    session["user"] = {"email": email, "uid": uid}
    return jsonify({"ok": True})

@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# -----------------------------
# OpenAI Custom Mission API
# -----------------------------
@app.post("/api/generate_mission")
def generate_mission():
    data = request.get_json(silent=True) or {}

    index = int(data.get("index") or 1)
    profile = data.get("profile") or {}
    history = data.get("history") or []
    now_iso = (data.get("nowISO") or "").strip()

    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(history, list):
        history = []

    history_trim = history[:7]

    sched = profile.get("schedule") or {}
    med = (sched.get("medication") or {}) if isinstance(sched, dict) else {}
    dressing = (sched.get("dressing") or {}) if isinstance(sched, dict) else {}

    system = (
        "You generate ONE short wellness mission for a patient self-care dashboard. "
        "Do not provide medical advice, diagnosis, medication instructions, or clinical claims. "
        "Keep it safe, gentle, and generic (hydration, breathing, light stretch, journaling, short walk). "
        "Output must be valid JSON ONLY with keys: name, desc, icon. "
        "icon must be a Bootstrap Icons class name starting with 'bi-'. "
        "name max 30 chars, desc max 80 chars."
    )

    user = {
        "task": "Generate one custom mission.",
        "index": index,
        "nowISO": now_iso,
        "profile_hint": {
            "gender": profile.get("gender"),
            "weight": profile.get("weight"),
            "height": profile.get("height"),
            "treatmentPhase": profile.get("treatmentPhase"),
            "activityBaseline": profile.get("activityBaseline"),
            "medicalConditions": profile.get("medicalConditions"),
            "allergies": profile.get("allergies"),
            "medication_timesPerDay": med.get("timesPerDay"),
            "medication_times": med.get("times"),
            "dressing_frequency": dressing.get("frequency"),
            "dressing_time": dressing.get("time"),
            "dressing_dayOfWeek": dressing.get("dayOfWeek"),
        },
        "recent_history_hint": history_trim,
        "constraints": {
            "avoid_medical_advice": True,
            "tone": "friendly, brief, actionable",
            "examples": [
                {"name": "2-Min Breathing", "desc": "Inhale 4, exhale 6 for 2 minutes.", "icon": "bi-wind"},
                {"name": "Gentle Stretch", "desc": "Neck + shoulder rolls for 3 minutes.", "icon": "bi-universal-access"},
                {"name": "Mini Walk", "desc": "A calm 5-minute walk indoors or outside.", "icon": "bi-person-walking"},
            ],
        },
        "output_schema": {"name": "string", "desc": "string", "icon": "bi-..."},
    }

    fallback = {"name": "2-Min Breathing", "desc": "Inhale 4, exhale 6 for 2 minutes.", "icon": "bi-wind"}

    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        text = getattr(resp, "output_text", "") or ""
        if not text:
            # best-effort extraction
            try:
                parts = []
                for item in (resp.output or []):
                    for c in (getattr(item, "content", None) or []):
                        t = getattr(c, "text", None)
                        if t:
                            parts.append(t)
                text = "\n".join(parts).strip()
            except Exception:
                text = ""

        if not text:
            return jsonify(fallback)

        obj = json.loads(text)

        name = str(obj.get("name") or "").strip() or fallback["name"]
        desc = str(obj.get("desc") or "").strip() or fallback["desc"]
        icon = str(obj.get("icon") or "").strip()
        if not icon.startswith("bi-"):
            icon = fallback["icon"]

        return jsonify({"name": name[:30], "desc": desc[:80], "icon": icon})

    except Exception as e:
        print("[/api/generate_mission] error:", repr(e))
        return jsonify(fallback)


# -----------------------------
# GPT Condition Report API
# -----------------------------
@app.post("/api/condition_report")
def condition_report():
    data = request.get_json(silent=True) or {}

    profile = data.get("profile") or {}
    history = data.get("history") or []
    now_iso = (data.get("nowISO") or "").strip()

    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(history, list):
        history = []

    history_trim = history[:7]

    schema = {
        "summary": "string",
        "score": "integer (0-100)",
        "risk_level": "Low Risk | Moderate | Needs Attention",
        "highlights": ["string"],
        "concerns": ["string"],
        "recommendations": ["string"],
        "next_7_days_plan": ["string"],
    }

    system = (
        "You are BioPal's health routine assistant.\n"
        "Generate a supportive, non-medical condition report based ONLY on the provided 7-day history.\n"
        "DO NOT provide diagnosis, medication instructions, or urgent medical directives.\n"
        "If something seems concerning, suggest contacting a clinician in general terms.\n\n"
        "IMPORTANT OUTPUT RULES:\n"
        "- Output MUST be valid JSON ONLY\n"
        "- This is for young cancer patients, so do not use negative words, but cheer them."
        "- Do NOT include markdown, code fences, comments, or explanations\n"
        "- The JSON MUST match this schema exactly:\n"
        f"{json.dumps(schema, indent=2)}\n"
        "- score must be an integer between 0 and 100"
    )

    user = {
        "task": "Create a 7-day condition report.",
        "nowISO": now_iso,
        "profile_hint": {
            "gender": profile.get("gender"),
            "weight": profile.get("weight"),
            "height": profile.get("height"),
            "treatmentPhase": profile.get("treatmentPhase"),
            "activityBaseline": profile.get("activityBaseline"),
            "medicalConditions": profile.get("medicalConditions"),
            "allergies": profile.get("allergies"),
            "medication_schedule": (profile.get("schedule") or {}).get("medication"),
            "dressing_schedule": (profile.get("schedule") or {}).get("dressing"),
        },
        "history_7d": history_trim,
    }

    fallback = {
        "summary": "Not enough recent data to generate a detailed report yet.",
        "score": 50,
        "risk_level": "Moderate",
        "highlights": [],
        "concerns": ["Insufficient 7-day history."],
        "recommendations": ["Complete daily missions consistently."],
        "next_7_days_plan": ["Complete hydration missions daily."],
    }

    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.5,
        )

        # ---- Extract text safely ----
        text = ""
        if hasattr(resp, "output_text") and resp.output_text:
            text = resp.output_text.strip()
        else:
            parts = []
            for item in (resp.output or []):
                for c in (getattr(item, "content", []) or []):
                    if hasattr(c, "text") and c.text:
                        parts.append(c.text)
            text = "\n".join(parts).strip()

        if not text:
            return jsonify(fallback)

        obj = json.loads(text)

        def clean_list(v):
            return [str(x).strip() for x in v if str(x).strip()][:8] if isinstance(v, list) else []

        score = int(obj.get("score", fallback["score"]))
        score = max(0, min(100, score))

        risk = obj.get("risk_level")
        if risk not in ("Low Risk", "Moderate", "Needs Attention"):
            risk = fallback["risk_level"]

        return jsonify({
            "summary": str(obj.get("summary", fallback["summary"]))[:900],
            "score": score,
            "risk_level": risk,
            "highlights": clean_list(obj.get("highlights")) or fallback["highlights"],
            "concerns": clean_list(obj.get("concerns")) or fallback["concerns"],
            "recommendations": clean_list(obj.get("recommendations")) or fallback["recommendations"],
            "next_7_days_plan": clean_list(obj.get("next_7_days_plan")) or fallback["next_7_days_plan"],
        })

    except Exception as e:
        print("[/api/condition_report] error:", repr(e))
        return jsonify(fallback)

# -----------------------------
# EMAIL SENDER
# -----------------------------
def send_mission_start_email(
    to_email: str,
    user_name: str,
    interval_label: str = "09:00 - 12:00"
):
    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587

    SMTP_USER = "your_email@gmail.com"          # sender email
    SMTP_PASSWORD = "YOUR_GMAIL_APP_PASSWORD"   # Gmail App Password (not your normal password)
    FROM_EMAIL = "BioPal <your_email@gmail.com>"

    subject = "BioPal • Your Daily Missions Have Started"

    body = f"""
Hi {user_name},

Your BioPal missions for today have started.

Time window:
{interval_label}

Open BioPal to see your missions and begin at your own pace.
Small steps still matter.

If you’ve already completed your check-in, great job.
If not, BioPal is ready whenever you are.

Have a steady and healthy day,
BioPal
""".strip()

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


# -----------------------------
# READ ALL USERS' EMAILS (2 options)
# -----------------------------
def fetch_all_user_emails_from_firestore():
    """
    Reads from Firestore collection 'users'.
    Assumes username == email OR email field exists.
    """
    users = []
    for doc in db.collection("users").stream():
        data = doc.to_dict() or {}
        email = (data.get("username") or data.get("email") or "").strip()
        if not email:
            continue
        name = (data.get("displayName") or data.get("name") or email.split("@")[0]).strip()
        users.append({"email": email, "name": name})
    return users


def fetch_all_user_emails_from_firebase_auth():
    """
    Reads directly from Firebase Authentication user list (Admin only).
    This is the most reliable way to get EVERY registered user's email.
    """
    users = []
    page = fb_auth.list_users()
    while page:
        for u in page.users:
            if u.email:
                name = (u.display_name or u.email.split("@")[0]).strip()
                users.append({"email": u.email, "name": name})
        page = page.get_next_page()
    return users


def notify_all_users(users):
    for u in users:
        try:
            send_mission_start_email(
                to_email=u["email"],
                user_name=u.get("name", "there"),
            )
        except Exception as e:
            print(f"[Email Error] {u.get('email')}: {e}")


# Optional: an HTTP endpoint you can trigger from PythonAnywhere "Scheduled Task"
# Example scheduled task command:
#   python3 /home/youruser/app.py --send-morning
@app.get("/admin/send_morning_emails")
def admin_send_morning_emails():
    # Choose ONE source:
    # users = fetch_all_user_emails_from_firestore()
    users = fetch_all_user_emails_from_firebase_auth()

    notify_all_users(users)
    return jsonify({"ok": True, "sent": len(users)})

@app.get("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")

@app.get("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")
# app.py — FULL UPDATED /api/chat_coach (feelings-first + first question support)

import json
from flask import request, jsonify


@app.post("/api/chat_coach")
def chat_coach():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    context = data.get("context") or {}
    history = data.get("history") or []

    # 1. Identify Today's Data
    last7 = context.get("last7Days") or {}
    today_id = context.get("medicalDay")
    today_log = last7.get(today_id)

    # 2. Extract survey_v2 fields
    user_context = "No check-in completed for today yet."
    if today_log and "survey_v2" in today_log:
        survey = today_log["survey_v2"]
        cond = survey.get('A', {}).get('cond', 'unknown')
        mood = survey.get('D', {}).get('mood', 'unknown')
        pain = survey.get('A', {}).get('pain', 'none')
        fatigue = survey.get('C', {}).get('fatigue', 'unknown')
        user_context = f"Condition: {cond}, Mood: {mood}, Pain: {pain}, Fatigue: {fatigue}/10."

    # 3. Dynamic System Prompt
    # We tell the AI to prioritize the user's latest question while keeping the "BioPal" persona.
    system_prompt = (
        "You are BioPal Chat Coach, a warm health companion. "
        f"Context for today: {user_context}. "
        "Keep responses brief (approx 3 lines), empathetic, and actionable. "
        "Always respond directly to the user's last message or question. "
        "If they ask for advice, provide ONE or TWO gentle, non-medical wellness tips. "
        "No emojis. No clinical medical advice."
    )

    try:
        messages = [{"role": "system", "content": system_prompt}]

        # 4. Clean history handling
        # Ensure we are passing roles correctly
        for h in history[-8:]:  # Increased history slightly for better advice context
            messages.append({"role": h['role'], "content": h['content']})

        # Add the current user message if it's not already the last item in history
        if not history or history[-1]['content'] != message:
            messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.7
        )

        reply = response.choices[0].message.content.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        print(f"Chat Coach Error: {e}")
        return jsonify({"reply": "Hi there.\nI'm here to support you.\nHow can I help with your wellness today?"})
@app.route('/test')
def test():
    return render_template('test.html')
if __name__ == "__main__":
    app.run(debug=True, port=8080)
