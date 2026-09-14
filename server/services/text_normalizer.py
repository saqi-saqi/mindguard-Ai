"""
MindGuard - Text Normalization Engine for Evasion Resistance
=============================================================
Provides robust text cleaning, confusable-character folding, zero-width /
invisible character stripping, punctuation standardization, and token
compaction against adversarial evasion attempts.

Strict Scope Exclusions:
- Urdu script (Arabic / Perso-Arabic unicode ranges) is preserved.
- Roman Urdu words and syntax are not mangled.
"""

import re
import unicodedata
from typing import Dict, Tuple

# Comprehensive Confusable Character Mapping (Cyrillic, Greek, Fullwidth, Enclosed, etc.)
CONFUSABLE_MAP: Dict[str, str] = {
    # Cyrillic lowercase to Latin
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "c", "т": "t", "у": "y", "ф": "f", "х": "x", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
    # Ukrainian, Belarusian, and South Slavic Cyrillic
    "\u0456": "i", "\u0457": "i", "\u0406": "I", "\u0407": "I",
    "\u0455": "s", "\u0405": "S", "\u0458": "j", "\u0408": "J",
    "\u04bb": "h", "\u04ba": "H",
    # Cyrillic uppercase to Latin
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Ρ": "P",
    "С": "C", "Т": "T", "У": "Y", "Х": "X",
    # Greek lowercase to Latin
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "h", "θ": "th",
    "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p",
    "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "u", "φ": "ph", "χ": "ch", "ψ": "ps",
    "ω": "w",
    # Greek uppercase to Latin
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
}

# Add fullwidth Latin characters (U+FF01 to U+FF5E)
for code in range(0xFF01, 0xFF5F):
    ascii_code = code - 0xFEE0
    CONFUSABLE_MAP[chr(code)] = chr(ascii_code)

# Invisible / Zero-width / Variation Selector Unicode characters
ZERO_WIDTH_AND_INVISIBLE_CHARS = re.compile(
    r"["
    r"\u200B"  # Zero-width space
    r"\u200C"  # Zero-width non-joiner
    r"\u200D"  # Zero-width joiner
    r"\uFEFF"  # Zero-width no-break space / BOM
    r"\u00AD"  # Soft hyphen
    r"\u2060"  # Word joiner
    r"\u200E"  # Left-to-right mark
    r"\u200F"  # Right-to-left mark
    r"\u202A-\u202E"  # Bidi embedding/override marks
    r"\uFE00-\uFE0F"  # Variation selectors VS1-VS16
    r"\U000E0100-\U000E01EF"  # Variation selectors supplement
    r"]+"
)

# Mixed punctuation normalization
PUNCTUATION_REPLACEMENTS = [
    (re.compile(r"[\u2018\u2019\u201B\u2032]"), "'"),   # Smart single quotes
    (re.compile(r"[\u201C\u201D\u201F\u2033]"), '"'),   # Smart double quotes
    (re.compile(r"[\u2013\u2014\u2015]"), "-"),         # En-dash, Em-dash, horizontal bar
    (re.compile(r"\u2026"), "..."),                     # Horizontal ellipsis
]

# Targeted keywords for single-letter run compaction
CRISIS_COMPACTION_TARGETS = {
    "kill", "suicide", "unalive", "kms", "kys", "overdose", "cutting", "die", "death",
    "hanging", "poison", "razor", "blade", "jump", "strangle", "drown", "murder",
    "selfharm", "hurt", "bleach"
}


def is_urdu_or_arabic(text: str) -> bool:
    """Detect presence of Urdu / Arabic script to preserve text integrity."""
    for ch in text:
        code = ord(ch)
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or (0xFB50 <= code <= 0xFDFF) or (0xFE70 <= code <= 0xFEFF):
            return True
    return False


def strip_invisible_characters(text: str) -> str:
    """Removes zero-width, invisible formatting, and variation selector characters."""
    return ZERO_WIDTH_AND_INVISIBLE_CHARS.sub("", text)


def fold_confusables(text: str) -> str:
    """
    Folds Cyrillic, Greek, fullwidth, and math-alphanumeric confusable characters
    into canonical Latin ASCII equivalents, excluding native Urdu script.
    """
    out = []
    for ch in text:
        code = ord(ch)
        # Protect native Urdu / Arabic scripts
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F):
            out.append(ch)
            continue
        
        if ch in CONFUSABLE_MAP:
            out.append(CONFUSABLE_MAP[ch])
        else:
            # Handle Unicode mathematical alphanumeric symbols via NFKD where possible
            if 0x1D400 <= code <= 0x1D7FF:
                decomp = unicodedata.normalize("NFKD", ch)
                out.append(decomp)
            else:
                out.append(ch)
    return "".join(out)


def standardize_punctuation(text: str) -> str:
    """Normalizes curly quotes, various dashes, and unicode ellipses to standard ASCII."""
    for pat, repl in PUNCTUATION_REPLACEMENTS:
        text = pat.sub(repl, text)
    return text


def strip_intra_word_decorative_symbols(text: str) -> str:
    """
    Strips emojis and decorative symbols appearing *inside* words between letters.
    E.g.: 'k🔪i🔪l🔪l' -> 'kill', 's★u★i★c★i★d★e' -> 'suicide'.
    Leaves standalone emojis or emojis between separate words alone.
    """
    def _clean_match(m: re.Match) -> str:
        s = m.group(0)
        return "".join(c for c in s if c.isalnum() or c == "'")

    # Match runs of single letters interleaved with symbols/emojis/dots/asterisks
    symbol_interleaved = re.compile(r"(?:[a-zA-Z][^\w\s]){2,}[a-zA-Z]")
    return symbol_interleaved.sub(_clean_match, text)


def compact_spaced_tokens(text: str) -> str:
    """
    Compacts obfuscated spaced or dotted letter sequences that spell crisis keywords,
    while leaving legitimate spaced sentences unharmed.
    E.g.:
      'k i l l  m y s e l f' -> 'kill myself'
      's u i c i d e' -> 'suicide'
    """
    # 1. Match spaced single letter runs: sequences of 2 or more single letters separated by spaces/dots/dashes/symbols
    pattern = re.compile(r"\b([a-zA-Z](?:[\s\.\-_/\\*~|]+[a-zA-Z])+)\b")

    def _replace_run(match: re.Match) -> str:
        raw_run = match.group(1)
        letters = [c.lower() for c in raw_run if c.isalpha()]
        candidate = "".join(letters)
        
        if candidate in CRISIS_COMPACTION_TARGETS:
            return candidate
        
        if len(letters) >= 5:
            if any(sep in raw_run for sep in [".", "-", "_"]):
                return candidate
            for target in CRISIS_COMPACTION_TARGETS:
                if target in candidate or candidate in target:
                    return candidate

        return raw_run

    return pattern.sub(_replace_run, text)


def normalize_evasion_text(text: str) -> str:
    """
    Comprehensive pipeline for adversarial evasion resistance.
    Chains:
    1. Unicode NFC normalization.
    2. Invisible & zero-width character stripping.
    3. Confusable character folding (preserving Urdu).
    4. Punctuation standardization.
    5. Intra-word decorative symbol stripping.
    6. Token compaction for split/spaced forms.
    """
    if not text:
        return ""

    # Step 1: Normalize unicode
    cleaned = unicodedata.normalize("NFC", text)

    # Step 2: Strip invisible & zero-width chars
    cleaned = strip_invisible_characters(cleaned)

    # Step 3: Fold confusables (Cyrillic, Greek, fullwidth -> Latin)
    cleaned = fold_confusables(cleaned)

    # Step 4: Standardize punctuation
    cleaned = standardize_punctuation(cleaned)

    # Step 5: Strip intra-word decorative symbols / emojis
    cleaned = strip_intra_word_decorative_symbols(cleaned)

    # Step 6: Compact spaced/dotted tokens
    cleaned = compact_spaced_tokens(cleaned)

    return cleaned
