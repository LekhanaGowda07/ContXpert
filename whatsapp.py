"""WhatsApp Cloud API client (text, buttons, list, template). In mock mode nothing is sent to Meta:
messages are printed (or captured, which the CLI simulator and tests use)."""
import json
import logging
import threading

import requests

import config

log = logging.getLogger("whatsapp")
_local = threading.local()


class capture:
    """with capture() as out:  -> every message sent in this thread is appended to `out` (as payload dicts)."""

    def __enter__(self):
        self.out = []
        _local.buf = self.out
        return self.out

    def __exit__(self, *exc):
        _local.buf = None


def render(payload):
    """Human-readable form of an outgoing payload (for console / CLI)."""
    t = payload.get("type")
    if t == "text":
        return payload["text"]["body"]
    if t == "interactive":
        i = payload["interactive"]
        lines = [i["body"]["text"]]
        if i["type"] == "button":
            lines += [f"   [{b['reply']['title']}]" for b in i["action"]["buttons"]]
        else:
            for s in i["action"]["sections"]:
                for r in s["rows"]:
                    d = f" - {r['description']}" if r.get("description") else ""
                    lines.append(f"   * {r['title']}{d}")
        return "\n".join(lines)
    if t == "template":
        return f"[template {payload['template']['name']}]"
    return json.dumps(payload)


def options(payload):
    """[(reply_id, title)] of an interactive payload (used by the CLI to let you pick by number)."""
    if payload.get("type") != "interactive":
        return []
    i = payload["interactive"]
    if i["type"] == "button":
        return [(b["reply"]["id"], b["reply"]["title"]) for b in i["action"]["buttons"]]
    return [(r["id"], r["title"]) for s in i["action"]["sections"] for r in s["rows"]]


def _send(to, payload):
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **payload}
    buf = getattr(_local, "buf", None)
    if buf is not None:
        buf.append(payload)
        return True
    if config.WHATSAPP_MOCK:
        print(f"\n[BOT -> {to}]\n{render(payload)}\n")
        return True
    url = f"https://graph.facebook.com/{config.GRAPH_VERSION}/{config.WA_PHONE_ID}/messages"
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {config.WA_TOKEN}"}, json=payload, timeout=15)
    except requests.RequestException as e:
        log.error("WhatsApp request failed: %s", e)
        return False
    if r.status_code >= 400:
        log.error("WhatsApp API error %s: %s", r.status_code, r.text)
        return False
    return True


def send_text(to, body):
    return _send(to, {"type": "text", "text": {"body": body[:4096], "preview_url": True}})


def send_buttons(to, body, buttons):
    """buttons: up to 3 (id, title); title max 20 chars."""
    return _send(to, {"type": "interactive", "interactive": {
        "type": "button", "body": {"text": body[:1024]},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i[:256], "title": t[:20]}} for i, t in buttons[:3]]}}})


def send_list(to, body, button_label, rows, section_title="Options"):
    """rows: up to 10 (id, title, description); title max 24 chars, description max 72."""
    return _send(to, {"type": "interactive", "interactive": {
        "type": "list", "body": {"text": body[:1024]},
        "action": {"button": button_label[:20], "sections": [{"title": section_title[:24], "rows": [
            {"id": r[0][:200], "title": r[1][:24], **({"description": r[2][:72]} if len(r) > 2 and r[2] else {})}
            for r in rows[:10]]}]}}})


def send_template(to, name, params, lang=None):
    comps = [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:500]} for p in params]}] if params else []
    return _send(to, {"type": "template", "template": {
        "name": name, "language": {"code": lang or config.WA_TEMPLATE_LANG}, "components": comps}})
