"""Name redaction and the leak test (D15, D16). One matcher for both, so they agree on what a name is.

Redaction runs on every Observer log before it is stored or merged. The leak test is the gate after it:
it re-scans with the same matcher plus a substring scan, and any hit fails the run.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

# Words in Zoom display names that are not personal names.
NOT_NAMES = set("""iphone ipad android samsung galaxy phone laptop user zoom guest mobile teacher coach sir mam maam
miss mrs the and family home desktop redmi oppo vivo realme oneplus nokia moto lenovo dell asus acer mac
macbook chess eight times king queen rook bishop knight pawn board class student parent mom dad amma appa
tab tablet pro max note mini plus lite
shared audio screen sound computer recording host""".split())  # Zoom system labels, e.g. "Shared Audio"
FUZZY_MIN_LEN = 5
FUZZY_RATIO = 0.88
WORD = re.compile(r"[A-Za-z]+")
# (person field) and (text fields) the redaction and leak test cover; name_heard is internal and deleted after linking.
TEXT_FIELDS = {"roster": ("voice_note", "unsure_reason"), "events": ("detail", "quote_en"), "minute_grid": ("reason",)}


def norm(w: str) -> str:
    w = re.sub(r"[^a-z]", "", w.lower())
    w = re.sub(r"(.)\1+", r"\1", w)  # Aadhi -> adhi
    return re.sub(r"(?<=[^aeiou])h", "", w)  # adhi -> adi


def tokens(names) -> set[str]:
    out = set()
    for n in names:
        for w in WORD.findall(n or ""):
            if len(w) >= 3 and w.lower() not in NOT_NAMES and len(norm(w)) >= 3:
                out.add(norm(w))
    return out


def _match(word: str, table: dict[str, str]) -> tuple[str | None, str]:
    """Replacement for one word, and how it matched ('exact', 'fuzzy' or '')."""
    if len(word) < 3 or word.lower() in NOT_NAMES:
        return None, ""
    n = norm(word)
    if n in table:
        return table[n], "exact"
    if len(n) >= FUZZY_MIN_LEN:
        for t, rep in table.items():
            if len(t) >= FUZZY_MIN_LEN - 1 and difflib.SequenceMatcher(None, n, t).ratio() >= FUZZY_RATIO:
                return rep, "fuzzy"
    return None, ""


def name_table(roster: list[dict], vtt_labels=()) -> dict[str, str]:
    """normalised name token -> replacement. A heard name maps to its roster ID; a VTT-only name to [name]."""
    table = {t: "[name]" for t in tokens(vtt_labels)}
    for r in roster:
        for t in tokens([r.get("name_heard", "")]):
            table[t] = f"[{r['id']}]"
    return table


def _fields(log: dict):
    for section, keys in TEXT_FIELDS.items():
        for item in log.get(section, []):
            for k in keys:
                if isinstance(item.get(k), str):
                    yield f"{section}.{k}", item, k


def redact(log: dict, vtt_labels=()) -> Counter:
    """Replace names in place in every text field except roster.name_heard. Returns counts per field and match type."""
    table = name_table(log.get("roster", []), vtt_labels)
    counts: Counter = Counter()

    for where, item, k in _fields(log):
        def sub(m: re.Match) -> str:
            rep, how = _match(m.group(0), table)
            if rep:
                counts[f"{where}:{how}"] += 1
                return rep
            return m.group(0)

        item[k] = WORD.sub(sub, item[k])
    return counts


def leak_test(log: dict, names) -> Counter:
    """Count remaining name hits: the redaction matcher, plus a substring scan for names of 5+ letters."""
    table = {t: "x" for t in tokens(names)}
    long_names = [t for t in table if len(t) >= FUZZY_MIN_LEN]
    hits: Counter = Counter()
    for where, item, k in _fields(log):
        text = item[k]
        for w in WORD.findall(text):
            _, how = _match(w, table)
            if how:
                hits[f"{where}:{how}"] += 1
        squashed = norm(text)
        hits[f"{where}:substring"] += sum(squashed.count(t) for t in long_names) - sum(
            1 for w in WORD.findall(text) if norm(w) in long_names)
    return Counter({k: v for k, v in hits.items() if v > 0})
