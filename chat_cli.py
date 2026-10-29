"""Chat with the bot in your terminal - no WhatsApp, no internet needed.
   python chat_cli.py [phone]       (type a number to pick a button / list option, 'quit' to exit)"""
import os
import sys

os.environ["WHATSAPP_MOCK"] = "1"
os.environ["DISABLE_SCHEDULER"] = "1"

import bot  # noqa: E402
import db  # noqa: E402
import whatsapp as wa  # noqa: E402

db.init_db()
phone = sys.argv[1] if len(sys.argv) > 1 else "919000000078"
print("ContXpert console chat. Demo login: USN 4MC23CS078, DOB 15082005 (this CLI simulates sender 919000000078; use `python chat_cli.py <number>` to try another sender). 'quit' to exit.\n")
opts = []
while True:
    try:
        raw = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if raw.lower() in ("quit", "exit"):
        break
    rid = None
    if raw.isdigit() and opts and 1 <= int(raw) <= len(opts):
        rid, raw = opts[int(raw) - 1]
    with wa.capture() as out:
        bot.handle_incoming(phone, raw, rid)
    opts = []
    for p in out:
        print("\nBot:", wa.render(p).replace("\n", "\n     "))
        o = wa.options(p)
        if o:
            opts = o
            print("     (type a number to choose: " + ", ".join(f"{i + 1}={t}" for i, (_, t) in enumerate(o)) + ")")
    print()