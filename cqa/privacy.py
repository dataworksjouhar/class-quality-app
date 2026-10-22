"""Name redaction and the leak test (D15, D16). One matcher for both, so they agree on what a name is.

Redaction runs on every Observer log before it is stored or merged. The leak test is the gate after it:
it re-scans with the same matcher plus a substring scan, and any hit fails the run.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

# Words in Zoom display names that are never personal names (devices, roles, Zoom system labels).
NOT_NAMES = set("""iphone ipad android samsung galaxy phone laptop user zoom guest mobile teacher coach sir mam maam
miss mrs the and family home desktop redmi oppo vivo realme oneplus nokia moto lenovo dell asus acer mac
macbook chess eight times board class student parent mom dad amma appa
tab tablet pro max note mini plus lite
shared audio screen sound computer recording host""".split())  # Zoom system labels, e.g. "Shared Audio"
# Chess words in English, Hindi, Malayalam and Tamil. Some are also common names (Raja, Rani). They are never
# fuzzy-matched, but if someone in the class IS called that, the word is redacted everywhere: privacy wins (D17).
CHESS_WORDS = set("""king queen rook bishop knight pawn check mate castle
raja rani mantri wazir vazir ghoda ghora oont unt hathi haathi pyada pyaada sipahi
aana aane kuthira theru manthri kaalal arasan arasi yaanai kudhirai sippai""".split())
FUZZY_MIN_LEN = 5
FUZZY_RATIO = 0.88
WORD = re.compile(r"[A-Za-z]+")
# (person field) and (text fields) the redaction and leak test cover; name_heard is internal and deleted after linking.
TEXT_FIELDS = {"roster": ("voice_note", "unsure_reason"), "events": ("detail", "quote_en"), "minute_grid": ("reason",)}


def norm(w: str) -> str:
    w = re.sub(r"[^a-z]", "", w.lower())
    w = re.sub(r"(.)\1+", r"\1", w)  # Aadhi -> adhi
    return re.sub(r"(?<=[^aeiou])h", "", w)  # adhi -> adi


def tokens(names, stoplist: bool = True) -> set[str]:
    """Name tokens. stoplist=False for heard names: a name the teacher used is always a name."""
    out = set()
    for n in names:
        for w in WORD.findall(n or ""):
            if len(w) >= 3 and len(norm(w)) >= 3 and not (stoplist and w.lower() in NOT_NAMES):
                out.add(norm(w))
    return out


def _match(word: str, table: dict[str, str]) -> tuple[str | None, str]:
    """Replacement for one word, and how it matched ('exact', 'fuzzy' or '')."""
    if len(word) < 3:
        return None, ""
    n = norm(word)
    if n in table:  # someone is called this, even if it is also a chess word
        return table[n], "exact"
    if word.lower() in NOT_NAMES or word.lower() in CHESS_WORDS:
        return None, ""
    if len(n) >= FUZZY_MIN_LEN:
        for t, rep in table.items():
            if len(t) >= FUZZY_MIN_LEN - 1 and difflib.SequenceMatcher(None, n, t).ratio() >= FUZZY_RATIO:
                return rep, "fuzzy"
    return None, ""


def name_table(roster: list[dict], vtt_labels=()) -> dict[str, str]:
    """normalised name token -> replacement. A heard name maps to its roster ID; a VTT-only name to [name]."""
    table = {t: "[name]" for t in tokens(vtt_labels)}
    for r in roster:
        for t in tokens([r.get("name_heard", "")], stoplist=False):
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


def leak_test(log: dict, heard=(), vtt_labels=()) -> Counter:
    """Count remaining name hits: the redaction matcher, plus a substring scan for names of 5+ letters."""
    table = {t: "x" for t in tokens(vtt_labels) | tokens(heard, stoplist=False)}
    long_names = [t for t in table if len(t) >= FUZZY_MIN_LEN]
    hits: Counter = Counter()
    for where, item, k in _fields(log):
        text = item[k]
        for w in WORD.findall(text):
            _, how = _match(w, table)
            if how:
                hits[f"{where}:{how}"] += 1
        # names glued inside one word ("AadhiKumar"); never across words, which only finds letter accidents
        hits[f"{where}:substring"] += sum(1 for w in WORD.findall(text) for t in long_names
                                          if t in norm(w) and norm(w) != t)
    return Counter({k: v for k, v in hits.items() if v > 0})


def heard_names(log: dict) -> list[str]:
    return [r["name_heard"] for r in log.get("roster", []) if r.get("name_heard", "").strip()]


def leak_test_text(text: str, heard=(), vtt_labels=()) -> int:
    """Name hits in any text (the Judge input, the report): same matcher plus the substring scan."""
    log = {"events": [{"detail": text, "quote_en": ""}]}
    return sum(leak_test(log, heard, vtt_labels).values())
