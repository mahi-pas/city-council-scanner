"""AI vocabulary for finding and then verifying NYC Council legislation.

Legistar's full-text search treats an unquoted multi-word query as an AND of
its words, so "large language model" happily returns a campaign-finance law
that contains "large", "language" and "model" in unrelated sentences. Quoting
the query gives phrase behaviour, but the index also stems and is not fully
documented, so every hit is re-verified against the bill's own text with the
patterns below.

SEARCH_TERMS therefore optimises for recall; VERIFY decides what is kept.
"""

from __future__ import annotations

import re

# --- what we ask Legistar for -------------------------------------------
SEARCH_TERMS = [
    "artificial intelligence",
    "generative artificial intelligence",
    "generative AI",
    "A.I.",
    "machine learning",
    "deep learning",
    "large language model",
    "neural network",
    "natural language processing",
    "computer vision",
    "chatbot",
    "chatbots",
    "deepfake",
    "deep fake",
    "synthetic media",
    "digital replica",
    "voice cloning",
    "emotion recognition",
    "algorithm",
    "algorithms",
    "algorithmic",
    "automated decision",
    "automated decision system",
    "automated decision-making",
    "automated employment decision",
    "automated employment decision tool",
    "automated hiring",
    "automated tool",
    "decision-making tool",
    "intelligence tool",
    "bias audit",
    "facial recognition",
    "biometric identifier",
    "biometric recognition",
    "predictive analytics",
    "predictive policing",
    "robot",
    "robotic",
    "autonomous vehicle",
    "surveillance technology",
    "automated system",
]

TITLE_SEARCH_TERMS = [
    "artificial intelligence",
    "generative AI",
    "A.I.",
    "machine learning",
    "algorithmic",
    "automated decision",
    "facial recognition",
    "chatbot",
    "deepfake",
]

# --- what counts as a genuine hit ---------------------------------------
# (label, compiled pattern). Patterns are case-insensitive unless they need
# case to avoid false hits (the bare "AI" token).
CORE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("artificial intelligence", re.compile(r"artificial\s+intelligence", re.I)),
    ("generative AI", re.compile(r"generative\s+(?:a\.?i\.?|artificial\s+intelligence)", re.I)),
    # A bare "AI" is too noisy on its own: Legistar text contains the architect
    # credential "A.I.A." and a landmark called the "A.I. Namm & Son Department
    # Store". Require AI-ish context around the token.
    ("AI (as a term)", re.compile(
        r"\bAI[-\s](?:system|tool|model|technolog|chatbot|program|applicat|literac"
        r"|generat|power|driven|assist|scam|governance|readiness|polic)"
        r"|\b(?:generative|deceptive|using|use of|adopt|deploy|regulat)\s+AI\b",
        re.I)),
    ("machine learning", re.compile(r"machine\s+learning", re.I)),
    ("deep learning", re.compile(r"deep\s+learning", re.I)),
    ("large language model", re.compile(r"large\s+language\s+models?", re.I)),
    ("neural network", re.compile(r"neural\s+networks?", re.I)),
    ("natural language processing", re.compile(r"natural\s+language\s+processing", re.I)),
    ("computer vision", re.compile(r"computer\s+vision", re.I)),
    ("chatbot", re.compile(r"chat\s?bots?", re.I)),
    ("deepfake", re.compile(r"deep\s?fakes?", re.I)),
    ("synthetic media", re.compile(r"synthetic\s+media", re.I)),
    ("digital replica", re.compile(r"digital\s+replicas?", re.I)),
    ("voice cloning", re.compile(r"voice\s+clon(?:e|es|ing)", re.I)),
    ("emotion recognition", re.compile(r"emotion(?:al)?\s+recognition", re.I)),
]

ADJACENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("algorithmic / algorithm", re.compile(r"algorithmic|algorithms?\b", re.I)),
    ("automated decision system", re.compile(r"automated\s+decision[\s-]*(?:system|making|tool)", re.I)),
    ("automated employment decision tool", re.compile(r"automated\s+employment\s+decision", re.I)),
    ("automated hiring", re.compile(r"automated\s+(?:hiring|employment|screening)", re.I)),
    ("facial recognition", re.compile(r"facial\s+recognition|face\s+recognition", re.I)),
    ("biometric identifier", re.compile(r"biometric", re.I)),
    ("predictive analytics / policing", re.compile(r"predictive\s+(?:analytics|policing|model)", re.I)),
    ("bias audit", re.compile(r"bias\s+audits?", re.I)),
    ("robot / robotic", re.compile(r"\brobots?\b|robotic", re.I)),
    ("autonomous vehicle", re.compile(r"autonomous\s+vehicles?|self[\s-]driving", re.I)),
]

ALL_PATTERNS = [(l, p, "core") for l, p in CORE_PATTERNS] + [
    (l, p, "adjacent") for l, p in ADJACENT_PATTERNS
]

# Core vocabulary that means AI even on a single mention. The three core terms
# left out of this set are ambiguous in ordinary English: a bare "AI" token, and
# "computer vision" / "emotion recognition", which also describe human faculties
# (several mask-mandate resolutions discuss children's emotion recognition).
UNAMBIGUOUS = {
    "artificial intelligence",
    "generative AI",
    "machine learning",
    "deep learning",
    "large language model",
    "neural network",
    "natural language processing",
    "chatbot",
    "deepfake",
    "synthetic media",
    "digital replica",
    "voice cloning",
}


def verify(text: str, with_context: bool = False) -> list[dict]:
    """Return the AI vocabulary actually present in a piece of text."""
    text = text or ""
    found = []
    for label, pattern, tier in ALL_PATTERNS:
        hits = list(pattern.finditer(text))
        if not hits:
            continue
        entry = {"term": label, "tier": tier, "count": len(hits)}
        if with_context:
            start, end = hits[0].span()
            entry["context"] = ("…" if start > 90 else "") + text[max(0, start - 90):end + 110].strip() + "…"
        found.append(entry)
    return found
