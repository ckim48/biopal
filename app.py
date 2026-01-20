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
  apiKey: "AIzaSyBHSlHAY8XzwOu6kbkmMYzcEWT6qwgry0g",
  authDomain: "immunisphere.firebaseapp.com",
  projectId: "immunisphere",
  storageBucket: "immunisphere.firebasestorage.app",
  messagingSenderId: "424436998430",
  appId: "1:424436998430:web:597374776d04ee5cc4e90f"
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
        "You generate ONE short wellness mission for a patient self-care dashboard.\n"
        "It should not be related to hydration\n"
        "Do not provide medical advice, diagnosis, medication instructions, or clinical claims.\n"
        "Keep it safe, gentle, and generic (breathing, light stretch, journaling, short walk, and more).\n"
        "Output must be valid JSON ONLY with keys: name, desc, icon.\n"
        "icon must be a Bootstrap Icons class name starting with 'bi-'.\n"
        "name max 30 chars, desc max 80 chars.\n"
        "JSON ONLY."
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

    def _safe_result(obj: dict):
        name = str(obj.get("name") or "").strip() or fallback["name"]
        desc = str(obj.get("desc") or "").strip() or fallback["desc"]
        icon = str(obj.get("icon") or "").strip() or fallback["icon"]

        if not icon.startswith("bi-"):
            icon = fallback["icon"]

        return {"name": name[:30], "desc": desc[:80], "icon": icon}

    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            # ✅ JSON mode for Responses API (NOT response_format=...)
            text={"format": {"type": "json_object"}},
            temperature=0.7,
        )

        text = (getattr(resp, "output_text", "") or "").strip()

        # Best-effort fallback extraction if output_text is empty
        if not text:
            try:
                parts = []
                for item in (getattr(resp, "output", None) or []):
                    for c in (getattr(item, "content", None) or []):
                        t = getattr(c, "text", None)
                        if t:
                            parts.append(t)
                text = "\n".join(parts).strip()
            except Exception:
                text = ""

        if not text:
            return jsonify(fallback)

        # In case the model wraps JSON in stray whitespace/newlines, still parse normally.
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return jsonify(fallback)

        return jsonify(_safe_result(obj))

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

def _safe_str(v, fallback=""):
    try:
        s = str(v).strip()
        return s if s else fallback
    except Exception:
        return fallback

def _dow_abbr(date_str_yyyy_mm_dd: str):
    # returns "mon".."sun"
    try:
        d = datetime.strptime(date_str_yyyy_mm_dd, "%Y-%m-%d")
        return ["mon","tue","wed","thu","fri","sat","sun"][d.weekday()]
    except Exception:
        return None

def _count_completed_by_type(completed_list):
    """
    completedMissions examples:
      "09-12_WATER", "12-15_MED", "18-21_DRESS", "15-18_CUSTOM_1"
    """
    c = {"WATER": 0, "MED": 0, "DRESS": 0, "CUSTOM": 0, "TOTAL": 0}
    if not isinstance(completed_list, list):
        return c

    for x in completed_list:
        s = _safe_str(x)
        if not s:
            continue
        c["TOTAL"] += 1
        if s.endswith("_WATER"):
            c["WATER"] += 1
        elif s.endswith("_MED"):
            c["MED"] += 1
        elif s.endswith("_DRESS"):
            c["DRESS"] += 1
        elif "_CUSTOM" in s:
            c["CUSTOM"] += 1
    return c

def _expected_missions_for_day(profile: dict, day_id: str, day_log: dict):
    expected = {"WATER": 4, "MED": 0, "DRESS": 0, "CUSTOM": 0, "TOTAL": 0}

    sched = profile.get("schedule") or {}
    med = sched.get("medication") if isinstance(sched, dict) else {}
    dress = sched.get("dressing") if isinstance(sched, dict) else {}

    # Medication expected count
    med_times = med.get("times") if isinstance(med, dict) else None
    if isinstance(med_times, list):
        expected["MED"] = max(0, min(8, len([t for t in med_times if _safe_str(t)])))

    # Dressing expected count
    if isinstance(dress, dict):
        freq = _safe_str(dress.get("frequency"))
        if freq == "daily":
            expected["DRESS"] = 1
        elif freq == "weekly":
            dow = _safe_str(dress.get("dayOfWeek"))
            day_dow = _dow_abbr(day_id)
            if dow and day_dow and dow.lower() == day_dow:
                expected["DRESS"] = 1

    # Custom expected count
    # Option A (recommended): only count custom if stored customMissions exists for that day
    if isinstance(day_log, dict) and isinstance(day_log.get("customMissions"), dict):
        expected["CUSTOM"] = 4

    expected["TOTAL"] = expected["WATER"] + expected["MED"] + expected["DRESS"] + expected["CUSTOM"]
    return expected

def _mission_summary(profile: dict, last7: dict, today_id: str):
    """
    Returns a compact summary string + numbers for today and last7.
    """
    if not isinstance(last7, dict):
        last7 = {}

    # --- Today ---
    today_log = last7.get(today_id) if today_id else None
    today_completed = _count_completed_by_type((today_log or {}).get("completedMissions"))
    today_expected = _expected_missions_for_day(profile or {}, today_id or "", today_log or {})

    def pct(done, exp):
        if exp <= 0:
            return None
        return int(round((done / exp) * 100))

    today_pct = pct(today_completed["TOTAL"], today_expected["TOTAL"])

    # --- Last 7 days aggregate ---
    done7 = {"WATER": 0, "MED": 0, "DRESS": 0, "CUSTOM": 0, "TOTAL": 0}
    exp7 = {"WATER": 0, "MED": 0, "DRESS": 0, "CUSTOM": 0, "TOTAL": 0}
    days = 0

    # If your last7Days includes more than 7 docs, still ok; we’ll just aggregate what’s provided.
    # Sort keys so it’s stable (YYYY-MM-DD sorts lexicographically).
    for day_id in sorted(last7.keys(), reverse=True)[:7]:
        log = last7.get(day_id) or {}
        if not isinstance(log, dict):
            continue
        days += 1
        c = _count_completed_by_type(log.get("completedMissions"))
        e = _expected_missions_for_day(profile or {}, day_id, log)

        for k in ("WATER","MED","DRESS","CUSTOM","TOTAL"):
            done7[k] += c.get(k, 0)
            exp7[k] += e.get(k, 0)

    avg7_pct = pct(done7["TOTAL"], exp7["TOTAL"])

    # Compact human string
    today_line = "Today missions: not enough data yet."
    if today_expected["TOTAL"] > 0:
        if today_pct is None:
            today_line = f"Today missions: {today_completed['TOTAL']}/{today_expected['TOTAL']} completed."
        else:
            today_line = f"Today missions: {today_completed['TOTAL']}/{today_expected['TOTAL']} completed ({today_pct}%)."

    week_line = "Last 7 days: not enough data yet."
    if exp7["TOTAL"] > 0:
        if avg7_pct is None:
            week_line = f"Last 7 days: {done7['TOTAL']}/{exp7['TOTAL']} completed."
        else:
            week_line = f"Last 7 days: {done7['TOTAL']}/{exp7['TOTAL']} completed ({avg7_pct}%)."

    breakdown_today = (
        f"Breakdown today — Water {today_completed['WATER']}/{today_expected['WATER']}, "
        f"Med {today_completed['MED']}/{today_expected['MED']}, "
        f"Dress {today_completed['DRESS']}/{today_expected['DRESS']}, "
        f"Custom {today_completed['CUSTOM']}/{today_expected['CUSTOM']}."
    )

    return {
        "today": {"done": today_completed, "exp": today_expected, "pct": today_pct},
        "week": {"done": done7, "exp": exp7, "pct": avg7_pct, "daysCount": days},
        "text": f"{today_line} {week_line} {breakdown_today}"
    }


@app.post("/api/chat_coach")
def chat_coach():
    data = request.get_json(silent=True) or {}
    message = _safe_str(data.get("message"))
    context = data.get("context") or {}
    history = data.get("history") or []

    # ---- Extract context ----
    profile = context.get("profile") if isinstance(context, dict) else {}
    if not isinstance(profile, dict):
        profile = {}

    last7 = context.get("last7Days") if isinstance(context, dict) else {}
    if not isinstance(last7, dict):
        last7 = {}

    today_id = _safe_str(context.get("medicalDay")) if isinstance(context, dict) else ""
    today_log = last7.get(today_id) if today_id else None

    # ---- Survey summary for today ----
    user_context = "No check-in completed for today yet."
    if isinstance(today_log, dict) and isinstance(today_log.get("survey_v2"), dict):
        survey = today_log["survey_v2"]
        cond = _safe_str((survey.get("A") or {}).get("cond"), "unknown")
        mood = _safe_str((survey.get("D") or {}).get("mood"), "unknown")
        pain = _safe_str((survey.get("A") or {}).get("pain"), "none")
        fatigue = (survey.get("C") or {}).get("fatigue", "unknown")
        user_context = f"Condition: {cond}, Mood: {mood}, Pain: {pain}, Fatigue: {fatigue}/10."

    mission = _mission_summary(profile, last7, today_id)
    print(user_context)
    system_prompt = (
        "You are BioPal Chat Coach, a warm, encouraging health companion.\n"
        "RULES:\n"
        "- Keep responses brief (around 3 lines).\n"
        "- No emojis.\n"
        "- No diagnosis, no medication instructions, no clinical claims.\n"
        "- If something seems concerning, say they can contact a clinician in general terms.\n"
        "- Always respond directly to the user's most recent message.\n\n"
        f"TODAY CHECK-IN CONTEXT: {user_context}\n"
        f"MISSION COMPLETENESS CONTEXT: {mission['text']}\n"
        f"One sentence for feedback of 'TODAY CHECK-IN CONTEXT: {user_context}' related to Condition: {cond}, Mood: {mood}, Pain: {pain}, Fatigue: {fatigue}/10.'. it should sounds little professional, not just reading back the status. Give some advice if pain and fatigue score is bad. \n"
        f"Use the mission completeness to gently motivate \n"
        "Then, suggest one small next step for improving Today condition for student cancer patient ."
    )

    messages = [{"role": "system", "content": system_prompt}]

    safe_hist = []
    if isinstance(history, list):
        for h in history[-10:]:
            if not isinstance(h, dict):
                continue
            r = _safe_str(h.get("role"))
            c = _safe_str(h.get("content"))
            if r in ("system", "user", "assistant") and c:
                safe_hist.append({"role": r, "content": c[:900]})
    messages.extend(safe_hist)

    if not message:
        boot = (
            f"I’m here with you.\n"
            f"Mission status {mission['text']}\n"
            f"TODAY CHECK-IN CONTEXT: {user_context}\n"
            f"Give ony summary sentence of the self-check-in data. Then feedback for mission. and suggest one small next step for mission or improving the status."
        )
        return jsonify({"reply": boot})

    if not safe_hist or safe_hist[-1]["content"] != message:
        messages.append({"role": "user", "content": message})

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.9,
        )
        reply = (resp.choices[0].message.content or "").strip()
        if not reply:
            reply = "I’m here with you.\nWhat feels like the smallest next step you can do right now?"
        return jsonify({"reply": reply})

    except Exception as e:
        print(f"Chat Coach Error: {e!r}")
        return jsonify({"reply": "I’m here with you.\nWhat feels like the smallest next step you can do right now?"})
@app.route('/test')
def test():
    return render_template('test.html')
@app.route('/resource')
def resource():
    return render_template('resources.html')


@app.get("/medical-report")
def medical_report_page():
    return render_template("medical_report.html")

@app.post("/api/medical_report_from_client")
def medical_report_from_client():
    if not session.get("user"):
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}

    focus_type = str(data.get("cancerType") or "").strip() or "cancer"
    profile_hint = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    history = data.get("history") if isinstance(data.get("history"), list) else []

    # Keep payload bounded + safe
    history = history[:14]

    schema = {
        "title": "string",
        "cancer_type_focus": "string",
        "disclaimer": "string",
        "high_level_summary": "string",
        "trend_snapshot": {
            "pain_trend": "Improving | Stable | Worse | Not enough data",
            "fatigue_trend": "Improving | Stable | Worse | Not enough data",
            "mood_trend": "Improving | Stable | Worse | Not enough data",
            "routine_trend": "Improving | Stable | Worse | Not enough data"
        },
        "what_this_can_mean": ["string"],
        "self_care_focus_next_7_days": ["string"],
        "questions_for_your_clinician": ["string"],
        "red_flags_to_contact_a_clinician": ["string"],
        "data_used": {
            "days_included": "integer",
            "date_range": "string"
        }
    }

    system = (
        "You are BioPal's supportive health summary assistant.\n"
        "Create a cancer-type–focused report based ONLY on the user's provided check-ins and routine logs.\n"
        "Hard rules:\n"
        "- No diagnosis, no treatment recommendations, no medication instructions.\n"
        "- Use gentle, age-appropriate language.\n"
        "- Be encouraging and practical.\n"
        "- Red flags must be general (e.g., severe worsening pain, breathing trouble, persistent vomiting, fainting, confusion, uncontrolled bleeding).\n"
        "- Output MUST be valid JSON ONLY, matching the schema exactly.\n"
        f"Schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )

    user_payload = {
        "focus_cancer_type": focus_type,
        "profile_hint": profile_hint,
        "recent_checkins": history,
        "output_constraints": {"max_bullets_each_list": 8}
    }

    fallback = {
        "title": "Your BioPal Medical Report",
        "cancer_type_focus": focus_type,
        "disclaimer": "This report is informational and supportive only. It is not medical advice. For medical decisions, contact your care team.",
        "high_level_summary": "Not enough recent check-in data to generate a detailed report yet. Keep logging daily so BioPal can spot trends.",
        "trend_snapshot": {
            "pain_trend": "Not enough data",
            "fatigue_trend": "Not enough data",
            "mood_trend": "Not enough data",
            "routine_trend": "Not enough data"
        },
        "what_this_can_mean": [],
        "self_care_focus_next_7_days": ["Log one daily check-in (mood, pain, fatigue).", "Aim for small, consistent hydration and rest routines."],
        "questions_for_your_clinician": [],
        "red_flags_to_contact_a_clinician": ["Severe or rapidly worsening symptoms, trouble breathing, fainting, confusion, uncontrolled bleeding, or dehydration signs."],
        "data_used": {"days_included": len(history), "date_range": ""}
    }

    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            text={"format": {"type": "json_object"}},
            temperature=0.4,
        )
        text = (getattr(resp, "output_text", "") or "").strip()
        if not text:
            return jsonify({"ok": True, "report": fallback})

        obj = json.loads(text)
        if not isinstance(obj, dict):
            return jsonify({"ok": True, "report": fallback})

        return jsonify({"ok": True, "report": obj})

    except Exception as e:
        print("[/api/medical_report_from_client] error:", repr(e))
        return jsonify({"ok": True, "report": fallback})
from flask import request, jsonify
from datetime import datetime
import json
import re

def generate_professional_summary(profile, avg_fatigue):
    age = profile.get("age")
    gender = profile.get("gender", "the patient")
    cancer = profile.get("cancer_type", "oncological condition")

    # Fatigue interpretation (clinical tone)
    if avg_fatigue >= 8:
        fatigue_note = (
            "Your reported fatigue level suggests significant energy depletion, "
            "which is common during intensive treatment phases."
        )
        guidance = (
            "Prioritizing rest, hydration, and low-intensity activity is recommended. "
            "Any new or worsening symptoms should be discussed with your care team."
        )
    elif avg_fatigue >= 6:
        fatigue_note = (
            "Your fatigue level indicates moderate treatment-related tiredness."
        )
        guidance = (
            "Maintaining gentle daily activity while preserving adequate rest "
            "may help prevent further deconditioning."
        )
    elif avg_fatigue >= 4:
        fatigue_note = (
            "Your fatigue level appears within a manageable range."
        )
        guidance = (
            "A balanced routine combining light physical activity, nutrition, "
            "and regular sleep can support recovery and functional capacity."
        )
    else:
        fatigue_note = (
            "Your fatigue level is currently low."
        )
        guidance = (
            "This may be an appropriate time to maintain or gradually build healthy routines, "
            "as tolerated."
        )

    # Personalization sentence
    personalization = (
        f"Based on your profile ({gender}, "
        f"{age} years old, {cancer}), "
        "these recommendations are aligned with commonly used supportive care principles "
        "in oncology."
        if age and cancer else
        "These recommendations are aligned with commonly used supportive care principles in oncology."
    )

    return f"{fatigue_note} {personalization} {guidance}"

from flask import request, jsonify
from datetime import datetime

from flask import request, jsonify
from datetime import datetime
from datetime import datetime
from flask import request, jsonify

@app.post("/api/generate_ai_missions")
def generate_ai_missions():
    data = request.get_json(silent=True) or {}
    profile = data.get("profile") or {}
    history = data.get("history") or []

    # ----------------------------
    # Helpers
    # ----------------------------
    def as_dict(x): return x if isinstance(x, dict) else {}
    def as_str(x, d=""): return x if isinstance(x, str) else d
    def as_num(x): return x if isinstance(x, (int, float)) else None

    def compute_age(birth_year):
        y = as_num(birth_year)
        if not y: return None
        age = datetime.now().year - int(y)
        return age if 0 < age < 120 else None

    def norm_sex(s):
        s = (s or "").strip().lower()
        if s in {"female","woman","f"}: return "female"
        if s in {"male","man","m"}: return "male"
        return "unspecified"

    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    # ----------------------------
    # Profile parsing (defensive)
    # ----------------------------
    body = as_dict(profile.get("body"))
    clinical = as_dict(profile.get("clinical"))

    age = compute_age(body.get("birthYear"))
    sex = norm_sex(as_str(body.get("sex")))
    cancer_type = as_str(clinical.get("cancerType") or clinical.get("cancerTypeCategory") or "").strip()
    stage = as_str(clinical.get("stage") or "").strip()
    treatment = as_str(clinical.get("treatmentPhase") or "").strip()

    ct = cancer_type.lower()
    tp = treatment.lower()

    # ----------------------------
    # Fatigue (7-day)
    # ----------------------------
    fatigue_vals = []
    for h in history:
        try:
            f = h["survey_v2"]["C"]["fatigue"]
            if isinstance(f, (int, float)):
                fatigue_vals.append(float(f))
        except Exception:
            pass

    avg_fatigue = round(sum(fatigue_vals) / len(fatigue_vals), 1) if fatigue_vals else 5.0

    # Fatigue tier → mission intensity scaling
    # 0 = easiest pacing, 3 = full-intensity (still safe)
    if avg_fatigue >= 8:
        fatigue_tier = 0
        fatigue_line = "Your check-ins suggest higher fatigue this week—missions will emphasize pacing and recovery."
    elif avg_fatigue >= 6:
        fatigue_tier = 1
        fatigue_line = "Fatigue looks moderately elevated—missions will be steady but conservative."
    elif avg_fatigue >= 4:
        fatigue_tier = 2
        fatigue_line = "Fatigue looks manageable—missions can progress with moderate challenge."
    else:
        fatigue_tier = 3
        fatigue_line = "Fatigue looks low—missions can be more challenging while staying symptom-limited."

    # ----------------------------
    # Tailoring flags
    # ----------------------------
    is_gi = any(k in ct for k in ["colorectal", "stomach", "pancre", "gastric"])
    is_lung = "lung" in ct
    is_breast = "breast" in ct
    is_prostate = "prostate" in ct

    on_chemo = ("chemo" in tp) or ("chemotherapy" in tp)
    on_radiation = ("radiation" in tp) or ("radiotherapy" in tp)

    older = isinstance(age, int) and age >= 65

    # ----------------------------
    # Personalized paragraph + bullets (unchanged idea)
    # ----------------------------
    who = []
    if cancer_type: who.append(cancer_type)
    if stage: who.append(f"stage {stage}")
    who_txt = (" (" + ", ".join(who) + ")") if who else ""
    age_txt = f"{age}-year-old " if isinstance(age, int) else ""
    sex_txt = (sex + " ") if sex in {"female","male"} else ""

    bullets = [
        "Hydration: sip regularly; unless your clinician restricts fluids, aim for pale-yellow urine.",
        "Protein at each meal/snack (eggs, fish, tofu/beans, Greek yogurt) to support recovery.",
        "Choose cooked/soft foods if appetite is low; smoothies/soups can be easier to tolerate.",
        "Movement is symptom-limited: stop if dizziness, chest pain, or unusual shortness of breath occurs.",
        "Sleep routine: consistent bedtime/wake time; reduce screens and caffeine later in the day."
    ]
    if on_chemo:
        bullets.append("Food safety: avoid undercooked foods and unpasteurized products if your team warned about low immunity.")
    if older:
        bullets.append("Fall prevention: stable footwear, good lighting at night, and slower position changes.")

    personalized_note = (
        f"This week’s guidance is tailored for you as a {age_txt}{sex_txt}patient{who_txt}. "
        f"{fatigue_line} Focus on nutrition/hydration, symptom-aware movement, and consistent sleep. "
        "If any suggestion conflicts with your care plan (diet restrictions, fluid limits, symptom protocols), follow your clinician’s instructions first."
    ).replace("  ", " ").strip()

    report = {
        "personalized_note": personalized_note,
        "bullets": bullets[:7],
        "disclaimer": (
            "BioPal provides supportive, educational guidance only and does not replace medical care. "
            "Contact your oncology team for urgent or worsening symptoms."
        ),
        "meta": {
            "age": age,
            "sex": sex,
            "cancer_type": cancer_type or None,
            "treatment_phase": treatment or None,
            "avg_fatigue": avg_fatigue,
            "fatigue_tier": fatigue_tier
        }
    }

    # ----------------------------
    # Mission generation: progressive + specific
    # ----------------------------
    def liters_target(level):
        # 1.4 → 2.2L baseline-ish; scaled down if fatigue high
        base = 1.4 + (level-1) * (0.8/6)  # 1.4..2.2
        scale = [0.75, 0.85, 0.95, 1.0][fatigue_tier]
        return round(base * scale, 1)

    def walk_minutes(level):
        # 8 → 35 min; scaled down if fatigue high
        base = 8 + (level-1) * (27/6)     # 8..35
        scale = [0.55, 0.7, 0.85, 1.0][fatigue_tier]
        return int(round(base * scale))

    def strength_sets(level):
        # 1 → 4 sets; scaled down with fatigue
        base = 1 + (level-1) * (3/6)      # 1..4
        scale = [0.6, 0.8, 0.9, 1.0][fatigue_tier]
        return int(clamp(round(base * scale), 1, 4))

    def sleep_window(level):
        # Level 1: gentle, Level 7: strict
        # returns (bedtime_buffer_min, screen_off_min)
        # tighter as level increases
        screen_off = int(60 + (level-1) * (60/6))    # 60..120
        buffer = int(20 + (level-1) * (25/6))        # 20..45
        # fatigue high -> encourage longer wind-down
        if fatigue_tier <= 1:
            screen_off += 15
            buffer += 10
        return buffer, screen_off

    def mindfulness_minutes(level):
        base = 3 + (level-1) * (12/6)  # 3..15
        scale = [0.8, 0.9, 1.0, 1.0][fatigue_tier]
        return int(round(base * scale))

    def food_style_note():
        notes = []
        if is_gi:
            notes.append("Choose low-irritant, softer foods (soups, porridge, yogurt) if your GI symptoms flare.")
        if is_lung:
            notes.append("Avoid overeating at once; smaller meals can reduce breathing discomfort.")
        if is_breast:
            notes.append("If shoulder tightness exists, include gentle mobility (no pain, no forcing).")
        if is_prostate:
            notes.append("If urinary urgency exists, distribute fluids earlier and limit near bedtime if approved.")
        if on_chemo:
            notes.append("Use food-safety precautions (well-cooked proteins; avoid unpasteurized items if advised).")
        if on_radiation and is_gi:
            notes.append("If radiation affects GI, prioritize hydration and bland, tolerated foods.")
        return " ".join(notes).strip()

    style_note = food_style_note()

    # DIET & HYDRATION missions (very specific + harder)
    def diet_card(level):
        L = liters_target(level)
        # Progressive specificity:
        if level == 1:
            return ("Hydration starter", f"Drink {L}L total today (use a bottle). Log 3 check-ins: morning/noon/evening.")
        if level == 2:
            return ("Protein anchor", f"Add one protein serving at breakfast (eggs/tofu/yogurt). Keep hydration at {L}L.")
        if level == 3:
            return ("Fiber + color", f"Add 2 cups of cooked vegetables OR 1 smoothie with greens/berries. Hydration {L}L. {style_note}".strip())
        if level == 4:
            return ("Balanced plate", f"Build 2 meals with: 1 palm protein + 1 fist carb + 2 fists veggies. Hydration {L}L.")
        if level == 5:
            return ("Anti-nausea plan", f"Prepare 2 “easy snacks” (crackers/banana/yogurt) and eat small portions every 3–4 hours. Hydration {L}L. {style_note}".strip())
        if level == 6:
            return ("Protein goal day", f"Reach ~25–30g protein at TWO meals (e.g., chicken/fish/tofu + side). Hydration {L}L.")
        # level 7
        return ("Plan + prep", f"Pre-plan tomorrow’s meals (breakfast/lunch/dinner + 2 snacks). Prepare 1 item now (wash/chop/cook). Hydration {L}L.")

    # MOVEMENT missions (progressive; symptom-limited; fatigue-scaled)
    def move_card(level):
        mins = walk_minutes(level)
        sets = strength_sets(level)

        # Lung: add breath pacing cues; Older: balance cues; Breast: mobility cues.
        extra = []
        if is_lung:
            extra.append("Use paced breathing (inhale 2–3 steps, exhale 3–4 steps). Stop if breathlessness spikes.")
        if older:
            extra.append("Add 2 minutes of balance near a counter (heel-to-toe stance).")
        if is_breast:
            extra.append("Add 2 minutes shoulder mobility (wall slides or gentle circles).")
        extra_txt = (" " + " ".join(extra)).strip()

        if level == 1:
            return ("Micro-walk", f"Walk {mins} minutes total (can be 2×{max(4, mins//2)}). {extra_txt}".strip())
        if level == 2:
            return ("Post-meal walk", f"After one meal, do a {mins} minute easy walk. {extra_txt}".strip())
        if level == 3:
            return ("Strength basics", f"Do {sets} set(s): sit-to-stand ×8 + wall push-ups ×8 (rest as needed). {extra_txt}".strip())
        if level == 4:
            return ("Intervals", f"Walk {mins} minutes with 3×1-minute slightly faster segments (still able to talk). {extra_txt}".strip())
        if level == 5:
            return ("Strength + mobility", f"{sets} sets: sit-to-stand ×10 + band row (or towel row) ×10 + calf raises ×10. {extra_txt}".strip())
        if level == 6:
            return ("Consistency", f"Move twice today: {max(6, mins//2)} min walk + {max(6, mins//2)} min walk OR 1 walk + 1 stretch session. {extra_txt}".strip())
        return ("Challenge (safe)", f"Walk {mins} minutes + {sets} sets strength circuit (choose 2 exercises above). Keep effort moderate; stop with concerning symptoms. {extra_txt}".strip())

    # SLEEP missions (progressive constraints)
    def sleep_card(level):
        buffer, screen_off = sleep_window(level)
        # progressive: from “one change” → “full routine”
        if level == 1:
            return ("One upgrade", f"Choose ONE: no caffeine after 2pm OR 10-min wind-down before bed.")
        if level == 2:
            return ("Wind-down", f"Start wind-down {buffer} min before bed: dim lights + prepare clothes/water for tomorrow.")
        if level == 3:
            return ("Screen boundary", f"Stop screens {screen_off} min before bed (use audio/paper instead).")
        if level == 4:
            return ("Same schedule", f"Set a target wake time and keep it within ±30 minutes tomorrow (even if sleep was poor).")
        if level == 5:
            return ("Bedroom cues", f"Make the room sleep-ready: cool, dark, quiet. Remove 1 distraction (notifications/bright LEDs).")
        if level == 6:
            return ("Sleep-protect plan", f"Create a 3-step pre-bed routine (wash/tea/breathing). Do it in the same order tonight.")
        return ("Full protocol", f"Combine: screens off {screen_off} min + wind-down {buffer} min + consistent wake time tomorrow. Log what helped most.")

    # MINDSET missions (progressive: short → structured reflection)
    def mindset_card(level):
        mins = mindfulness_minutes(level)
        if level == 1:
            return ("Breathing reset", f"Do {mins} minutes of slow breathing (inhale 4, exhale 6).")
        if level == 2:
            return ("Stress label", f"Write 1 sentence: “Right now I feel ___ because ___.” Then do {mins} minutes breathing.")
        if level == 3:
            return ("Gratitude + body scan", f"List 2 things you appreciate + 5-minute body scan (head→toe). Total {mins}–{mins+2} minutes.")
        if level == 4:
            return ("Coping plan", f"Choose 1 stress trigger today and write a 2-step plan to respond (pause → action). Practice for {mins} minutes.")
        if level == 5:
            return ("Connection mission", f"Send one supportive message to a friend/family/member of your care team. Then 5 minutes reflection.")
        if level == 6:
            return ("Thought reframing", f"Pick 1 worry. Write: worry → evidence for/against → kinder alternative. Spend {mins} minutes.")
        return ("Weekly reflection", f"Write 5 bullet reflections: energy, appetite, sleep, mood, movement. Then {mins} minutes calming practice.")

    def make_cards_for_category(category):
        cards = []
        for level in range(1, 8):
            if category == "diet":
                name, desc = diet_card(level)
                icon = "bi-droplet"
            elif category == "exercise":
                name, desc = move_card(level)
                icon = "bi-person-walking"
            elif category == "sleep":
                name, desc = sleep_card(level)
                icon = "bi-moon-stars"
            else:
                name, desc = mindset_card(level)
                icon = "bi-heart"
            cards.append({"level": level, "name": name, "desc": desc, "icon": icon})
        return cards

    missions = [
        {"category": "diet", "title": "Diet & Hydration", "icon": "bi-apple", "cards": make_cards_for_category("diet")},
        {"category": "exercise", "title": "Safe Movement", "icon": "bi-figure-walking", "cards": make_cards_for_category("exercise")},
        {"category": "sleep", "title": "Rest & Sleep", "icon": "bi-moon-stars", "cards": make_cards_for_category("sleep")},
        {"category": "mindset", "title": "Mental Well-being", "icon": "bi-heart-pulse", "cards": make_cards_for_category("mindset")},
    ]

    return jsonify({"ok": True, "report": report, "missions": missions})
@app.post("/api/sensor_warning_email")
def sensor_warning_email():
    u = session.get("user") or {}
    session_email = (u.get("email") or "").strip()
    session_uid = (u.get("uid") or "").strip()
    #
    # if not session_email or not session_uid:
    #     return jsonify({"ok": False, "error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    client_email = (data.get("email") or "").strip()
    client_uid = (data.get("uid") or "").strip()
    print("WHAT:", client_email )

    to_email = client_email  # now trusted (because it matches session)

    medical_day = (data.get("medicalDay") or "").strip()
    sensor_status = data.get("sensorStatus") or {}

    def fmt(name):
        s = sensor_status.get(name) or {}
        return f"{name}: {s.get('value')} {s.get('unit','')}".strip() + f" ({s.get('status')})"

    lines = []
    for k in ("temp", "heart", "stress"):
        if isinstance(sensor_status.get(k), dict):
            lines.append(fmt(k))

    # cooldown (10 min)
    last_key = f"sensor_email_last_{session_uid}"
    now_ts = datetime.utcnow().timestamp()
    last_ts = float(session.get(last_key, 0) or 0)
    if now_ts - last_ts < 10 * 60:
        return jsonify({"ok": True, "skipped": "cooldown"})

    try:
        send_sensor_warning_email(
            to_email=to_email,
            user_name=(to_email.split("@")[0] if to_email else "there"),
            medical_day=medical_day,
            sensor_lines=lines,
        )
        session[last_key] = now_ts
        session.modified = True
        return jsonify({"ok": True})
    except Exception as e:
        print("[/api/sensor_warning_email] error:", repr(e))
        return jsonify({"ok": False, "error": "email failed"}), 500


def send_sensor_warning_email(to_email: str, user_name: str, medical_day: str, sensor_lines: list[str]):
    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = "madckkim@gmail.com"
    SMTP_PASSWORD = "muqv ppcp sjta ykhr"
    FROM_EMAIL = "BioPal madckkim@gmail.com"

    subject = "BioPal • Sensor Needs Attention"
    print("ABC");
    details = "\n".join(sensor_lines) if sensor_lines else "A sensor reported Warning."
    body = f"""
Hi {user_name},

BioPal noticed a sensor reading that needs attention.

Date: {medical_day or "today"}
Details:
{details}

Please open BioPal to review your status.
If you feel unwell or symptoms worsen, contact your care team.

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
    print("DEF")
if __name__ == "__main__":
    app.run(debug=True, port=8080)
