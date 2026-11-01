"""Optional LLM helper (Anthropic Messages API over plain HTTP). Returns None when no key / on any error,
so every feature keeps working without it."""
import json
import logging
import re

import requests

import config

log = logging.getLogger("llm")


def enabled():
    return bool(config.GEMINI_API_KEY and config.GEMINI_MODEL) or bool(config.ANTHROPIC_API_KEY)


def _gemini(system, user, max_tokens, json_mode=False):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    gen = {"maxOutputTokens": max_tokens, "temperature": 0.7}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    r = requests.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY, "content-type": "application/json"},
                      json={"system_instruction": {"parts": [{"text": system}]},
                            "contents": [{"role": "user", "parts": [{"text": user}]}],
                            "generationConfig": gen}, timeout=25)
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip() or None


def complete(system, user, max_tokens=400, json_mode=False):
    if not enabled():
        return None
    try:
        if config.GEMINI_API_KEY and config.GEMINI_MODEL:
            return _gemini(system, user, max_tokens, json_mode)
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=25)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip() or None
    except Exception as e:  # network, auth, quota ...
        log.warning("LLM call failed: %s", e)
        return None


CHAT_SYSTEM = (
    "You are ContXpert, a friendly WhatsApp assistant for engineering college students. "
    "Respond naturally to everyday messages, greetings, emotions, and general questions. "
    "Be warm, respectful, concise, and conversational (usually 1-4 short sentences). "
    "You may help with general learning and technology questions. For official college-specific "
    "facts such as fees, attendance records, exam dates, marks, or policies, never invent details; "
    "say that the student should use the relevant ContXpert menu or contact the college office. "
    "Do not claim to have performed real-world actions. Use plain text suitable for WhatsApp."
)

def chat(message, student=None):
    """Generate a general conversational reply for messages outside fixed bot intents."""
    if not enabled():
        return None
    identity = ""
    if student:
        identity = (f"\nStudent context: {student.get('name', 'Student')}, "
                    f"{student.get('department', '')}, semester {student.get('semester', '')}. "
                    "Use this only for friendly personalization; do not infer academic records.")
    return complete(CHAT_SYSTEM, f"Student message: {message}{identity}", max_tokens=300)


INTENTS = ["attendance", "cie", "fees", "timetable", "notifications", "cie_calc", "certificate",
           "cert_status", "risk", "menu", "logout", "faq"]

UNDERSTAND_SYSTEM = (
    "You are the brain of ContXpert, a friendly WhatsApp assistant for engineering college students. "
    "Read the student's message and decide what they actually mean. Reply with JSON only: "
    '{"intent": "<one of: ' + ", ".join(INTENTS) + ', chat>", "reply": "<text>"}.\n'
    "Use an academic intent ONLY when the student clearly wants that feature (e.g. 'show my marks' -> cie, "
    "'can I bunk tomorrow' -> attendance). Use faq for college rules/policy questions. "
    "Use chat for feelings, venting, greetings, small talk, jokes, motivation, study advice and general questions; "
    "then write the reply yourself: warm, human, 1-4 short sentences, plain text for WhatsApp, same language/style "
    "as the student (English, Hinglish...). Acknowledge feelings first. If they are stressed about something "
    "academic, you may gently offer the relevant option (e.g. 'want me to check your attendance? Just type attendance'). "
    "Never say they are 'at risk' unless they asked for the risk report. Never invent college facts, marks, dates or fees. "
    "If a student sounds in serious distress or mentions self-harm, respond with care, encourage talking to a trusted "
    "person or the college counsellor, and mention the Tele-MANAS helpline 14416 (India). "
    "For academic intents leave reply empty."
)


def understand(message, student=None):
    """One AI call: returns (intent, reply) or None if the AI is unavailable / answered badly."""
    who = f"Student first name: {student['name'].split()[0]}\n" if student else ""
    raw = complete(UNDERSTAND_SYSTEM, f"{who}Student message: {message}", max_tokens=700, json_mode=True)
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    intent = str(data.get("intent", "chat")).strip().lower()
    reply = str(data.get("reply", "")).strip()
    if intent not in INTENTS:
        intent = "chat"
    if intent == "chat" and not reply:
        return None
    return intent, reply