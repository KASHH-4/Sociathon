"""
Spoken-number and script normalization.
Converts multilingual PA transcripts into a canonical form suitable for
regex extraction and fuzzy matching.
"""
from __future__ import annotations

import re
import unicodedata
import difflib
from typing import Any

# ---------------------------------------------------------------------------
# Devanagari digit map
# ---------------------------------------------------------------------------
_DEVA_DIGIT = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

# ---------------------------------------------------------------------------
# Spoken-digit maps (English and Hindi/Marathi romanised)
# ---------------------------------------------------------------------------
_EN_WORD = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "won": "1",
    "two": "2", "too": "2", "to": "2",
    "three": "3",
    "four": "4", "for": "4", "fore": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
}

_HI_WORD = {
    "ek": "1", "ik": "1",
    "do": "2", "doh": "2",
    "teen": "3", "tin": "3",
    "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5", "pach": "5",
    "chhe": "6", "chhah": "6", "chha": "6", "chhey": "6",
    "saat": "7", "sat": "7",
    "aath": "8", "ath": "8",
    "nau": "9", "nav": "9",
}

# Devanagari digit-word map (Unicode)
_DEVA_WORD = {
    "एक": "1", "दो": "2", "दो": "2",
    "तीन": "3", "तिन": "3",
    "चार": "4",
    "पाँच": "5", "पांच": "5",
    "छह": "6", "छे": "6",
    "सात": "7",
    "आठ": "8",
    "नौ": "9", "नव": "9",
    "शून्य": "0",
}

_ALL_DIGIT_WORDS: dict[str, str] = {**_EN_WORD, **_HI_WORD, **_DEVA_WORD}

# Words that look like digit-words but must NOT be collapsed in normal sentences
# (we only collapse runs of >=3 digit-words; this is enforced in the collapsing logic)
_AMBIGUOUS_WORDS = {"to", "for", "oh", "o"}


def _replace_deva_digits(text: str) -> str:
    """Replace Devanagari digit characters (०-९) with ASCII digits."""
    return "".join(_DEVA_DIGIT.get(ch, ch) for ch in text)


def _replace_deva_words(text: str) -> str:
    """Replace Devanagari digit-words with their ASCII equivalents."""
    for word, digit in _DEVA_WORD.items():
        text = re.sub(r"(?<!\w)" + re.escape(word) + r"(?!\w)", digit, text)
    return text


def _collapse_spoken_digits(tokens: list[str]) -> list[str]:
    """
    Collapse runs of 3+ consecutive digit-word tokens into a single digit string.
    Also collapses runs of 3+ consecutive single-digit ASCII tokens (from Devanagari replacement).
    Runs of exactly 1 or 2 are left intact so "to" and "for" survive in sentences.
    """
    result: list[str] = []
    run: list[str] = []
    run_is_digits: bool = False  # True if run consists of already-digit chars

    def flush_run() -> None:
        if len(run) >= 3:
            result.append("".join(run))
        else:
            result.extend(run)  # put back unchanged tokens
        run.clear()

    for tok in tokens:
        # Check if token is already a single digit (from Devanagari word replacement)
        if len(tok) == 1 and tok.isdigit():
            if run and not run_is_digits:
                flush_run()
            run.append(tok)
            run_is_digits = True
        else:
            if run_is_digits:
                flush_run()
                run_is_digits = False
            mapped = _ALL_DIGIT_WORDS.get(tok)
            if mapped is not None:
                run.append(mapped)
            else:
                flush_run()
                run_is_digits = False
                result.append(tok)
    flush_run()
    return result


def _handle_double_triple(text: str) -> str:
    """
    Convert "double X" → XX and "triple X" → XXX where X is a digit or digit-word.
    e.g. "double one" → "11", "triple two eight" is handled after standard collapse.
    """
    # Handle "double <digit>" and "triple <digit>" (already normalised to digits)
    text = re.sub(r"\bdouble\s+(\d)\b", lambda m: m.group(1) * 2, text)
    text = re.sub(r"\btriple\s+(\d)\b", lambda m: m.group(1) * 3, text)
    # Handle "double <word>" before digit-word expansion
    for word, digit in _ALL_DIGIT_WORDS.items():
        text = re.sub(
            r"\bdouble\s+" + re.escape(word) + r"\b",
            digit * 2,
            text,
        )
        text = re.sub(
            r"\btriple\s+" + re.escape(word) + r"\b",
            digit * 3,
            text,
        )
    return text


def normalize(text: str) -> str:
    """
    Full normalization pipeline:
    1. Lowercase + strip punctuation
    2. Devanagari digits → ASCII
    3. Devanagari digit-words → ASCII
    4. Handle "double/triple X"
    5. Collapse runs of ≥3 spoken-digit tokens
    """
    # Step 1a: Devanagari word replacement BEFORE stripping combining marks
    text = _replace_deva_words(text)

    # Step 1b: lowercase
    text = text.lower().strip()
    # Remove punctuation except hyphens (train numbers sometimes use them) and spaces
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Step 2: Devanagari script digits
    text = _replace_deva_digits(text)

    # Step 4: double/triple patterns
    text = _handle_double_triple(text)

    # Step 5: tokenize and collapse runs of ≥3 digit-word tokens
    tokens = text.split()
    tokens = _collapse_spoken_digits(tokens)

    return " ".join(tokens)


def find_train_numbers(text: str) -> list[dict[str, Any]]:
    """
    Return all digit sequences in the normalized text categorized by length.
    5-digit sequences are the primary candidates; 4- and 6-digit are flagged malformed.
    """
    results = []
    for m in re.finditer(r"\b(\d+)\b", text):
        seq = m.group(1)
        length = len(seq)
        if length == 5:
            results.append({"number": seq, "malformed": False})
        elif length in (4, 6):
            results.append({"number": seq, "malformed": True})
    return results


def match_alias(text: str, entries: list[dict[str, Any]], key: str = "name") -> dict[str, Any] | None:
    """
    Fuzzy-match *text* against the ``key`` field and the ``aliases`` list of each
    entry. Returns the best entry with ratio ≥ 0.85, or None.
    """
    best_ratio = 0.0
    best_entry = None
    text_lc = text.lower()

    for entry in entries:
        candidates = [str(entry.get(key, "")).lower()]
        for alias in entry.get("aliases", []):
            candidates.append(str(alias).lower())
        for candidate in candidates:
            ratio = difflib.SequenceMatcher(None, text_lc, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = entry

    return best_entry if best_ratio >= 0.85 else None
