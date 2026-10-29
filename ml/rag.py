"""FAQ retrieval (TF-IDF cosine similarity) + optional LLM answer generation grounded on the retrieved text."""
import json
import os
import threading

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

import config
import llm

_state = {}
_lock = threading.Lock()

SYSTEM = ("You are ContXpert, a WhatsApp assistant for engineering college students. Answer ONLY using the "
          "context provided. Be concise (max 4 short sentences), friendly, plain text with *bold* only for key "
          "facts. If the context does not contain the answer, say you don't have that information and suggest "
          "contacting the college office.")


def _load():
    with _lock:
        if not _state:
            with open(os.path.join(config.DATA_DIR, "faq.json"), encoding="utf-8") as f:
                items = json.load(f)
            vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
            mat = vec.fit_transform([i["q"] + " " + i["a"] for i in items])
            _state.update(items=items, vec=vec, mat=mat)
    return _state


def retrieve(question, k=3):
    s = _load()
    sims = (s["mat"] @ s["vec"].transform([question]).T).toarray().ravel()
    idx = np.argsort(-sims)[:k]
    return [(float(sims[i]), s["items"][i]) for i in idx if sims[i] > 0]


def answer(question):
    hits = retrieve(question)
    if llm.enabled():
        ctx = "\n\n".join(f"Q: {h['q']}\nA: {h['a']}" for _, h in hits) or "(no matching context)"
        text = llm.complete(SYSTEM, f"Context:\n{ctx}\n\nStudent question: {question}")
        if text:
            return text
    if hits and hits[0][0] >= 0.20:
        return hits[0][1]["a"]
    return None
