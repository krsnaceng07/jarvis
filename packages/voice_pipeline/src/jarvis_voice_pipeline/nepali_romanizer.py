"""packages/voice_pipeline/src/jarvis_voice_pipeline/nepali_romanizer.py

Deterministic, high-quality Devanagari-to-Roman transliteration for Nepali conversational speech.
Transcribes spoken Nepali into natural Latin / Roman script (English letters),
e.g. "नमस्ते Sir, मद्दतको लागि तयार छु" -> "Namaste Sir, maddatko laagi tayaar chhu."
"""

from __future__ import annotations

import re

# High-frequency conversational Nepali vocabulary mappings
COMMON_NEPALI_WORDS: dict[str, str] = {
    "नमस्ते": "Namaste",
    "नमस्कार": "Namaskar",
    "हजुर": "Hajur",
    "हुन्छ": "Hunchha",
    "हुन्न": "Hunna",
    "माफ": "Maaf",
    "गर्नुहोस्": "garnuhos",
    "गर्नुस्": "garnus",
    "तपाईं": "Tapai",
    "तपाइँ": "Tapai",
    "तपाईको": "Tapaiko",
    "तपाईंको": "Tapaiko",
    "तिम्रो": "Timro",
    "तिमी": "Timi",
    "म": "Ma",
    "मलाई": "Malai",
    "मेरो": "Mero",
    "हाम्रो": "Hamro",
    "हामी": "Hami",
    "धन्यवाद": "Dhanyabaad",
    "स्वागत": "Swaagat",
    "छ": "chha",
    "छन्": "chhan",
    "छैन": "chhaina",
    "छौ": "chhau",
    "छु": "chhu",
    "भयो": "bhayo",
    "भनेर": "bhanera",
    "भन्नुहोस्": "bhannuhos",
    "भन्नुस्": "bhannus",
    "र": "ra",
    "तर": "tara",
    "वा": "wa",
    "कि": "ki",
    "पनि": "pani",
    "धेरै": "dherai",
    "अलि": "ali",
    "अलिकति": "alikati",
    "राम्रो": "ramro",
    "ठिक": "thik",
    "ठीक": "thik",
    "के": "ke",
    "कसरी": "kasari",
    "कहिले": "kahile",
    "कहाँ": "kaha",
    "किन": "kina",
    "यो": "yo",
    "त्यो": "tyo",
    "यहाँ": "yaha",
    "त्यहाँ": "tyaha",
    "सक्छु": "sakchhu",
    "सक्नुहुन्छ": "saknuhunchha",
    "गर्दैछु": "gardaichhu",
    "गरिसके": "garisake",
    "गरिदिएँ": "garidie",
    "बनाउँछु": "banauchhu",
    "बनाउँदै": "banaudai",
    "बनाएँ": "banae",
    "बनाइदिएँ": "banaidie",
    "खोलिदिएँ": "kholidie",
    "खोल्छु": "kholchhu",
    "खोल्दै": "kholdai",
    "खोज्छु": "khojchhu",
    "खोज्दै": "khojdai",
    "तयार": "tayaar",
    "मद्दत": "maddat",
    "सहयोग": "sahayog",
    "काम": "kaam",
    "कुरा": "kura",
    "दिनुहोस्": "dinuhos",
    "गर्न": "garna",
    "गरेर": "garera",
    "हुनुहुन्छ": "hunuhunchha",
    "निश्चित": "nishchit",
    "नाम": "naam",
    "नाममा": "naamma",
    "फोल्डर": "folder",
    "फाइल": "file",
    "ड्राइभ": "drive",
    "ड्राइभमा": "drivema",
    "डाउनलोड": "download",
    "डाउनलोड्स": "downloads",
    "डाउनलोडमा": "downloadma",
    "ब्राउजर": "browser",
    "कम्प्युटर": "computer",
    "स्क्रिन": "screen",
    "स्क्रिनसट": "screenshot",
}

VOWELS: dict[str, str] = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "अं": "am",
    "अः": "ah",
}

MATRAS: dict[str, str] = {
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ं": "n",
    "ँ": "n",
    "ः": "h",
}

CONSONANTS: dict[str, str] = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "ng",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "ny",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "w",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "क्ष": "ksh",
    "त्र": "tr",
    "ज्ञ": "gya",
}

HALANTA = "्"


def romanize_nepali_token(token: str) -> str:
    """Transliterates a single Devanagari word into Romanized Nepali."""
    if not token:
        return token

    # Check exact vocabulary match
    lower_token = token.strip()
    if lower_token in COMMON_NEPALI_WORDS:
        return COMMON_NEPALI_WORDS[lower_token]

    # Transliterate character by character
    chars = list(token)
    out: list[str] = []
    i = 0
    n = len(chars)

    while i < n:
        ch = chars[i]
        if ch in CONSONANTS:
            cons = CONSONANTS[ch]
            # Next is halanta (suppress inherent vowel)
            if i + 1 < n and chars[i + 1] == HALANTA:
                out.append(cons)
                i += 2
                continue
            # Next is vowel matra
            elif i + 1 < n and chars[i + 1] in MATRAS:
                matra_vowel = MATRAS[chars[i + 1]]
                out.append(cons + matra_vowel)
                i += 2
                continue
            else:
                # Inherent vowel logic:
                # In Nepali phonology, word-final consonant drops inherent 'a' (e.g. 'नाम' -> 'naam', not 'naama')
                if i + 1 == n:
                    out.append(cons)
                else:
                    out.append(cons + "a")
                i += 1
                continue
        elif ch in VOWELS:
            out.append(VOWELS[ch])
        elif ch in MATRAS:
            out.append(MATRAS[ch])
        elif ch == "।":
            out.append(".")
        else:
            out.append(ch)
        i += 1

    return "".join(out)


def romanize_nepali_text(text: str) -> str:
    """Converts a Devanagari Nepali sentence into clean Romanized Nepali (English letters).
    Leaves English words, numbers, and Latin punctuation intact.
    """
    if not text:
        return text

    # Quick check: does the text contain any Devanagari Unicode characters (0x0900-0x097F)?
    if not any("\u0900" <= c <= "\u097f" for c in text):
        return text

    # Tokenize words while preserving spaces, punctuation and English words
    tokens = re.split(r"([ \t\n\r]+|[.,!?;:\"\'()\[\]{}।]+)", text)
    result: list[str] = []

    for tok in tokens:
        if not tok:
            continue
        if any("\u0900" <= c <= "\u097f" for c in tok):
            # Devanagari word
            # Clean any internal punctuation if split missed it
            if tok == "।":
                result.append(".")
            else:
                result.append(romanize_nepali_token(tok))
        else:
            result.append(tok)

    res = "".join(result)
    # Tidy up repeated vowels and common artifacts
    res = re.sub(r"aa+", "aa", res)
    res = re.sub(r"\s+", " ", res).strip()
    return res
