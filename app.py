import os
import json
from flask import Flask, render_template, request, session, jsonify, redirect, url_for

# OpenAI Python SDK (v1+)
# pip install openai
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret-key"

# Uses OPENAI_API_KEY from environment


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
# NEW: OpenAI Custom Mission API
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

    # Light safety/size guards
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(history, list):
        history = []

    # Keep history short to reduce tokens/cost
    history_trim = history[:7]

    # Pull a few helpful fields (optional)
    sched = profile.get("schedule") or {}
    med = (sched.get("medication") or {}) if isinstance(sched, dict) else {}
    dressing = (sched.get("dressing") or {}) if isinstance(sched, dict) else {}

    # We want short, actionable, non-medical “missions”
    # Do NOT give medical instructions. Keep it lifestyle-level only.
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
        # Use Responses API style (OpenAI SDK v1+).
        # If your installed SDK only supports chat.completions, see note below.
        resp = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            # Try to force JSON output:
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        # Extract text
        text = ""
        # Responses API commonly provides output_text convenience
        if hasattr(resp, "output_text") and resp.output_text:
            text = resp.output_text
        else:
            # Fallback extraction (best effort)
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

        name = str(obj.get("name") or "").strip()
        desc = str(obj.get("desc") or "").strip()
        icon = str(obj.get("icon") or "").strip()

        if not name:
            name = fallback["name"]
        if not desc:
            desc = fallback["desc"]
        if not (icon.startswith("bi-")):
            icon = fallback["icon"]

        # Hard length clamps
        name = name[:30]
        desc = desc[:80]

        return jsonify({"name": name, "desc": desc, "icon": icon})

    except Exception as e:
        # Server-side debug
        print("[/api/generate_mission] error:", repr(e))
        return jsonify(fallback)



if __name__ == "__main__":
    app.run(debug=True, port=8080)
