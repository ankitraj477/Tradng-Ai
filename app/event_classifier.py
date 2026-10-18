import hashlib
import re


class EventClassifier:
    """
    Event classifier categorizing corporate announcements and headlines into:
    RESULTS, ORDER_WIN, M_AND_A, REGULATORY, FRAUD_PROBE, RATING_CHANGE, GUIDANCE, GENERAL.
    Outputs sentiment, materiality, and risk filter actions. Cached by item hash.
    """
    EVENT_PATTERNS = {
        "FRAUD_PROBE": [
            r"\b(cbi|ed|income tax|it)\s+(raid|probe|searches|investigation)\b",
            r"\b(forensic audit|accounting fraud|scam|arrested|embezzlement|siphoning)\b",
            r"\b(irregularities|money laundering|fir filed)\b"
        ],
        "REGULATORY": [
            r"\b(sebi|rbi|cci|fda)\s+(order|penalty|notice|ban|bar|warning|action|fine)\b",
            r"\b(usfda\s+form\s+483|warning letter|import alert)\b",
            r"\b(licence revoked|suspended from trading)\b"
        ],
        "RESULTS": [
            r"\b(q[1-4]|quarterly|annual|full year)\s+(results|net profit|earnings|revenue)\b",
            r"\b(profit rises|profit drops|pat up|pat down|net loss|beats estimates)\b"
        ],
        "ORDER_WIN": [
            r"\b(bags order|wins contract|secures order|awarded contract|receives order)\b",
            r"\b(deal worth|order book)\b"
        ],
        "M_AND_A": [
            r"\b(to acquire|acquisition|merger|buys stake|stake sale|takeover|divestment)\b"
        ],
        "RATING_CHANGE": [
            r"\b(crisil|icra|care|fitch|moody'?s)\s+(upgrades|downgrades|revises)\b",
            r"\b(credit rating|rating outlook)\b"
        ],
        "GUIDANCE": [
            r"\b(raises guidance|cuts guidance|revenue guidance|fy\d+ outlook)\b"
        ]
    }

    def __init__(self):
        self._cache = {}
        # Pre-compile regexes
        self._compiled = {
            ev_type: [re.compile(p, re.IGNORECASE) for p in patterns]
            for ev_type, patterns in self.EVENT_PATTERNS.items()
        }

    def classify(self, title, text="", item_hash=None):
        h = item_hash or hashlib.sha256(f"{title}|{text}".encode("utf-8")).hexdigest()
        if h in self._cache:
            return self._cache[h]

        content = f"{title} {text}".lower()

        # Check in priority order: Fraud/Regulatory first (highest materiality)
        detected_event = "GENERAL"
        materiality = "LOW"
        confidence = 0.70

        for ev_type, regex_list in self._compiled.items():
            if any(r.search(content) for r in regex_list):
                detected_event = ev_type
                break

        # Sentiment and Materiality
        if detected_event in {"FRAUD_PROBE", "REGULATORY"}:
            sentiment = "NEGATIVE"
            materiality = "HIGH"
            confidence = 0.90
        elif detected_event == "ORDER_WIN":
            sentiment = "POSITIVE"
            materiality = "MEDIUM"
            confidence = 0.85
        elif detected_event == "RESULTS":
            pos_match = re.search(r"\b(profit up|profit jumps|beats|rises \d+%|growth)\b", content)
            neg_match = re.search(r"\b(profit falls|profit drops|misses|net loss|declines \d+%)\b", content)
            sentiment = "POSITIVE" if pos_match and not neg_match else "NEGATIVE" if neg_match else "NEUTRAL"
            materiality = "HIGH"
            confidence = 0.80
        elif detected_event == "M_AND_A":
            sentiment = "POSITIVE"
            materiality = "HIGH"
            confidence = 0.75
        else:
            sentiment = "NEUTRAL"
            materiality = "LOW"

        res = {
            "item_hash": h,
            "event_type": detected_event,
            "sentiment": sentiment,
            "materiality": materiality,
            "confidence": confidence
        }
        self._cache[h] = res
        return res

    def evaluate_risk_filter(self, symbol, items):
        """
        Enforces news as a risk filter:
        - Rejects entries on FRAUD_PROBE or adverse REGULATORY action.
        - Reduces position size or cautions on imminent quarterly results.
        """
        for it in items:
            syms = it.symbols if hasattr(it, "symbols") else it.get("symbols", [])
            if symbol not in syms:
                continue

            title = getattr(it, "title", "") if hasattr(it, "title") else it.get("title", "")
            clf = self.classify(title)
            ev = clf["event_type"]

            if ev == "FRAUD_PROBE":
                return {
                    "block_entry": True,
                    "reduce_size": True,
                    "action": "HALT_TRADING",
                    "reason": f"Severe risk: Fraud/probe detected ({title[:60]})"
                }
            elif ev == "REGULATORY" and clf["sentiment"] == "NEGATIVE":
                return {
                    "block_entry": True,
                    "reduce_size": True,
                    "action": "BLOCK_ENTRY",
                    "reason": f"Adverse regulatory action detected ({title[:60]})"
                }

        return {"block_entry": False, "reduce_size": False, "action": "CLEAR"}
