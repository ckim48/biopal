import os
import json
from flask import Flask, render_template, request, session, jsonify, redirect, url_for

# OpenAI Python SDK (v1+)
# pip install openai
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret-key"

# IMPORTANT:
# Never hardcode API keys in code. Use environment variable OPENAI_API_KEY.
# Example:
#   export OPENAI_API_KEY="sk-..."
#   export OPENAI_MODEL="gpt-4o-mini"


@app.get("/")
def home():
    # Example: require login (optional)
    # if "user" not in session:
    #     return redirect(url_for("login"))
    return render_template("index.html")


@app.get("/login")
def login():
    # Only render. JS handles authentication.
    return render_template("login.html")


@app.post("/api/session-login")
def session_login():
    """
    Called by your login.js AFTER successful JS authentication.
    Store user info in Flask session so server-rendered pages can use it.
    """
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


@app.get("/register")
def register():
    return render_template("register.html")


@app.get("/main")
def main():
    return render_template("main.html")


# -----------------------------
# OpenAI Custom Mission API
# -----------------------------
@app.post("/api/generate_mission")
def generate_mission():
    """
    Called by index.html JS:
      POST /api/generate_mission
      { index, profile, history, nowISO }

    Returns JSON:
      { "name": "...", "desc": "...", "icon": "bi-..." }
    """
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
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
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

        name = name[:30]
        desc = desc[:80]

        return jsonify({"name": name, "desc": desc, "icon": icon})

    except Exception as e:
        print("[/api/generate_mission] error:", repr(e))
        return jsonify(fallback)


# -----------------------------
# NEW: GPT Condition Report API
# -----------------------------
@app.post("/api/condition_report")
def condition_report():
    """
    Called by your dashboard JS:
      POST /api/condition_report
      { profile, history, nowISO }

    Returns JSON (used by modal UI):
      {
        "summary": "...",
        "score": 0..100,
        "risk_level": "Low Risk" | "Moderate" | "Needs Attention",
        "highlights": [...],
        "concerns": [...],
        "recommendations": [...],
        "next_7_days_plan": [...]
      }
    """
    data = request.get_json(silent=True) or {}

    profile = data.get("profile") or {}
    history = data.get("history") or []
    now_iso = (data.get("nowISO") or "").strip()

    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(history, list):
        history = []

    history_trim = history[:7]

    # Output schema your front-end can render
    schema = {
        "summary": "string",
        "score": "integer (0-100)",
        "risk_level": "string",
        "highlights": ["string"],
        "concerns": ["string"],
        "recommendations": ["string"],
        "next_7_days_plan": ["string"]
    }

    system = (
        "You are BioPal's health routine assistant. "
        "Generate a supportive, non-medical condition report based ONLY on the provided 7-day check-in history "
        "and mission completion logs. "
        "Do NOT provide diagnosis, medication instructions, or urgent medical directives. "
        "If something seems concerning, suggest contacting a clinician in general terms without alarms. "
        "Be concise and practical. Output must be valid JSON ONLY, matching the provided schema. "
        "score must be an integer 0-100."
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
        "output_schema": schema,
        "style_rules": {
            "tone": "warm, clear, encouraging",
            "no_emojis": True,
            "length": "short (about 8-12 lines total when rendered)",
            "risk_level_options": ["Low Risk", "Moderate", "Needs Attention"]
        }
    }

    fallback = {
        "summary": "Not enough recent data to generate a detailed report. Complete the daily check-in and missions for a few days.",
        "score": 50,
        "risk_level": "Moderate",
        "highlights": [],
        "concerns": ["Insufficient 7-day history."],
        "recommendations": ["Complete today's check-in to begin tracking trends."],
        "next_7_days_plan": ["Do one check-in per day.", "Complete hydration mission consistently."]
    }

    try:
        resp = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
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

        # Normalize/validate minimal fields
        summary = str(obj.get("summary") or "").strip() or fallback["summary"]

        try:
            score = int(obj.get("score"))
        except Exception:
            score = fallback["score"]
        score = max(0, min(100, score))

        risk = str(obj.get("risk_level") or "").strip()
        if risk not in ("Low Risk", "Moderate", "Needs Attention"):
            risk = fallback["risk_level"]

        def list_str(v):
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()][:8]
            return []

        out = {
            "summary": summary[:900],
            "score": score,
            "risk_level": risk,
            "highlights": list_str(obj.get("highlights")) or fallback["highlights"],
            "concerns": list_str(obj.get("concerns")) or fallback["concerns"],
            "recommendations": list_str(obj.get("recommendations")) or fallback["recommendations"],
            "next_7_days_plan": list_str(obj.get("next_7_days_plan")) or fallback["next_7_days_plan"]
        }

        return jsonify(out)

    except Exception as e:
        print("[/api/condition_report] error:", repr(e))
        return jsonify(fallback)


if __name__ == "__main__":
    app.run(debug=True, port=8080)
