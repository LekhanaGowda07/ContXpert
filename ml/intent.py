"""ML intent classifier: TF-IDF (word + char n-grams, so typos / Hinglish still work) + Logistic Regression.
Trained at start-up from the phrases below (takes ~1s). Add more phrases to improve it - or log real
student messages and retrain."""
import threading

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

TRAIN = {
    "greeting": ["hi", "hello", "hey", "hii", "hello bot", "good morning", "good evening", "good afternoon",
                 "namaste", "hey there", "hi there", "helo", "yo", "hola"],
    "menu": ["menu", "show menu", "main menu", "options", "what can you do", "show options", "help", "i need help",
             "how to use this bot", "how does this work", "what are the commands", "features", "start", "services",
             "guide me", "what is this bot"],
    "attendance": ["attendance", "my attendance", "show my attendance", "attendance percentage", "attendence",
                   "how many classes have i attended", "am i short of attendance", "attendance shortage",
                   "can i bunk", "how many classes can i miss", "attendance status", "subject wise attendance",
                   "am i eligible for exams attendance", "detention list", "mera attendance kitna hai",
                   "attendence kitna hai", "attendance check", "att percentage", "classes attended"],
    "cie": ["cie marks", "internal marks", "my cie", "ia marks", "internals", "show my marks", "test marks",
            "ia1 marks", "ia 2 marks", "assignment marks", "how much did i score in internals", "cie result",
            "marks kitne aaye hai", "internal marks batao", "my internal assessment", "cie score",
            "show cie", "my ia scores"],
    "fees": ["fees", "fee status", "fee due", "pending fees", "how much fee is due", "tuition fee",
             "fee balance", "have i paid my fees", "fee payment status", "due date for fees",
             "fees kitna baaki hai", "fee details", "fee pending", "college fees", "balance fee amount"],
    "timetable": ["timetable", "time table", "today's classes", "class schedule", "what classes do i have today",
                  "tomorrow's timetable", "schedule for tomorrow", "next class", "my schedule", "which class is next",
                  "periods today", "class kab hai", "aaj ka timetable", "tt", "show timetable", "weekly timetable",
                  "classes tomorrow", "today timetable"],
    "notifications": ["notifications", "notices", "announcements", "circular", "latest news", "any updates",
                      "college notices", "exam notification", "what's new", "latest circulars",
                      "any announcement today", "notice board", "new notifications", "any new circular"],
    "cie_calc": ["cie calculator", "how many marks do i need", "marks needed to pass", "required marks in see",
                 "how much should i score in sem exam", "calculate cie", "what do i need to score",
                 "marks required for pass", "target grade", "need marks in final exam", "how much to score to get 90",
                 "predict required marks", "how much do i need in semester exam", "see marks needed",
                 "marks needed in end sem", "cie aggregation"],
    "certificate": ["certificate", "request certificate", "bonafide", "i need a bonafide certificate",
                    "apply for study certificate", "transcript request", "noc letter", "conduct certificate",
                    "get certificate", "need a certificate for bank", "apply for certificate", "order transcript",
                    "bonafide certificate please", "i want a certificate", "internship noc"],
    "cert_status": ["certificate status", "status of my certificate", "is my certificate ready",
                    "track certificate request", "my certificate requests", "bonafide status",
                    "where is my certificate", "certificate ready or not", "check certificate status",
                    "my certificate is ready?", "track my request"],
    "risk": ["risk report", "am i at risk", "ai analysis", "performance prediction", "will i be detained",
             "how am i doing overall", "academic risk", "analyse my performance", "my academic health",
             "predict my performance", "student risk score", "ai insights", "progress report", "risk analysis",
             "am i going to fail", "overall performance", "ai report"],
    "thanks": ["thanks", "thank you", "thx", "ok thanks", "great", "awesome", "cool", "ty", "got it", "nice",
               "perfect", "thank u so much", "ok", "okay", "good bot"],
    "logout": ["logout", "unregister", "unlink my number", "change my number", "reset registration",
               "deregister", "remove my account", "disconnect", "switch usn", "register again", "log out"],
    "faq": ["what is the minimum attendance required for exams", "library timings", "hostel rules",
            "how is cie calculated", "what is see", "what is detention", "revaluation process",
            "how to apply for scholarship", "bus timings", "who is the hod", "placement cell contact",
            "exam rules", "grading system", "when do exams start", "what is the passing marks",
            "how to contact the office", "college timings", "can i get re-exam", "what is a backlog",
            "tell me about the college", "dress code", "id card lost", "what documents are needed for bonafide"],
}

_model = None
_lock = threading.Lock()


def _build():
    X, y = [], []
    for label, phrases in TRAIN.items():
        for p in phrases:
            X.append(p.lower())
            y.append(label)
    feats = FeatureUnion([
        ("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)),
    ])
    pipe = Pipeline([("f", feats), ("clf", LogisticRegression(C=30, max_iter=3000))])
    pipe.fit(X, y)
    return pipe


def get_model():
    global _model
    with _lock:
        if _model is None:
            _model = _build()
    return _model


def predict(text):
    """Returns (intent, confidence). Low confidence -> ('unknown', conf)."""
    text = (text or "").strip().lower()
    if not text:
        return "unknown", 0.0
    m = get_model()
    probs = m.predict_proba([text])[0]
    i = probs.argmax()
    label, conf = str(m.classes_[i]), float(probs[i])
    return (label if conf >= 0.30 else "unknown"), conf
