"""packages/voice_pipeline/src/jarvis_voice_pipeline/nepali_romanizer.py

Deterministic, high-quality Devanagari-to-Roman transliteration for Nepali conversational speech.
Transcribes spoken Nepali into natural Latin / Roman script (English letters),
e.g. "नमस्ते Sir, मद्दतको लागि तयार छु" -> "Namaste Sir, maddatko laagi tayaar chhu."
"""

from __future__ import annotations

import re

# Devanagari numerals translation table
DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

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
    "गर्नु": "garnu",
    "गर": "gara",
    "त": "ta",
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
    "खोल्नुहोस्": "kholnuhos",
    "खोल": "khola",
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
    # Tech & Device controls
    "ब्राइटनेस": "Brightness",
    "ब्राइट": "Bright",
    "नेस": "ness",
    "भोल्युम": "Volume",
    "भोलम": "Volume",
    "आवाज": "Aawaj",
    "साउन्ड": "sound",
    "फुल": "full",
    "कम": "kam",
    "बढी": "badhi",
    "ह्वाट्सएप": "WhatsApp",
    "ह्वाटसएप": "WhatsApp",
    "ट्सएप": "WhatsApp",
    "ट्स": "Whats",
    "एप": "App",
    "एप्स": "Apps",
    "एप्लिकेसन": "Application",
    "टेलिग्राम": "Telegram",
    "कन्फिगरेसन": "Configuration",
    "कन्फिग": "Config",
    "टोकन": "Token",
    "च्याट": "Chat",
    "मेसेज": "Message",
    "मेसेजहरू": "Messages",
    "रिप्लाई": "Reply",
    "क्युआर": "QR",
    "स्क्यानर": "Scanner",
    "सिस्टम": "System",
    "क्यामेरा": "Camera",
    "माइक्रोफोन": "Microphone",
    "माइक": "Mic",
    "सेटिङ्स": "Settings",
    "सेटिङ": "Setting",
    "सेट": "Set",
    "इन्टरनेट": "Internet",
    "वाइफाइ": "WiFi",
    "ब्लुटुथ": "Bluetooth",
    "गुगल": "Google",
    "युट्युब": "YouTube",
    "फेसबुक": "Facebook",
    "इन्स्टाग्राम": "Instagram",
    "विन्डोज": "Windows",
    "चेक": "check",
    "टेस्ट": "test",
    "अपडेट": "update",
    "फिक्स": "fix",
    "बटन": "button",
    "क्लिक": "click",
    "ओपन": "open",
    "क्लोज": "close",
    "स्टार्ट": "start",
    "स्टप": "stop",
    "सर्च": "search",
    "सेभ": "save",
    "सेन्ड": "send",
    "डिलिट": "delete",
    "एड": "add",
    "रिमूभ": "remove",
    "लगइन": "login",
    "लगआउट": "logout",
    "पासवर्ड": "password",
    "युजरनेम": "username",
    "युजर": "user",
    "एडमिन": "admin",
    "ब्याकइन्ड": "backend",
    "फ्रन्टइन्ड": "frontend",
    "टर्मिनल": "terminal",
    "कमान्ड": "command",
    "स्क्रिप्ट": "script",
    "नेटवर्क": "network",
    "ब्याट्री": "battery",
    "प्रतिशत": "%",
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


def normalize_indic_to_devanagari(text: str) -> str:
    """Normalize related South Asian Indic scripts (Bengali, Gurmukhi, Gujarati) to Devanagari.

    Multilingual speech recognition engines occasionally decode Nepali utterances
    into Bengali (0x0980-0x09FF) or Gurmukhi (0x0A00-0x0A7F) Unicode blocks due to
    shared phonetic acoustic models. Mapping these blocks to the matching Devanagari
    offsets preserves user utterances and enables uniform romanization and transcript display.
    """
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        # Bengali block (0x0980 - 0x09FF) -> Devanagari (0x0900 - 0x097F)
        if 0x0980 <= code <= 0x09FF:
            out.append(chr(code - 0x80))
        # Gurmukhi block (0x0A00 - 0x0A7F) -> Devanagari (0x0900 - 0x097F)
        elif 0x0A00 <= code <= 0x0A7F:
            out.append(chr(code - 0x100))
        # Gujarati block (0x0A80 - 0x0AFF) -> Devanagari (0x0900 - 0x097F)
        elif 0x0A80 <= code <= 0x0AFF:
            out.append(chr(code - 0x180))
        else:
            out.append(ch)
    return "".join(out)


def is_phantom_noise(text: str) -> bool:
    """Detects multi-lingual speech-to-text phantom noise or bare punctuation hallucinations.

    Multilingual STT models often hallucinate phrases in Sinhala, Bengali, Gujarati, Chinese,
    or emit `<noise>`, `<silence>`, or bare punctuation dots on low-energy background mic noise / breathing.
    """
    if not text:
        return True

    # 1. Strip STT acoustic and noise tags (e.g. <noise>, <silence>, [noise], (noise))
    cleaned = re.sub(
        r"<(?:noise|silence|whisper|music|laughter|applause|cough|throat-clearing|sigh|snicker|groan|yawn|pant|gasp|screaming|cheering)[^>]*>|"
        r"\[(?:noise|silence|whisper|music|laughter|applause|cough|sigh)\]|"
        r"\((?:noise|silence|whisper|music|laughter|applause|cough|sigh)\)",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return True

    # 2. Strip whitespace and punctuation: if nothing left, it is bare noise (e.g. '.', '..', '?')
    stripped = re.sub(r"[\s.,!?;:\"\'()\[\]{}।॥—\-_~`]+", "", cleaned)
    if not stripped:
        return True

    # 3. Check for non-Latin, non-Devanagari foreign script ranges
    # Sinhala (0D80-0DFF), Bengali (0980-09FF), Gurmukhi (0A00-0A7F), Gujarati (0A80-0AFF),
    # Oriya (0B00-0B7F), Tamil (0B80-0BFF), Telugu (0C00-0C7F), Kannada (0C80-0CFF),
    # Malayalam (0D00-0D7F), Arabic/Persian (0600-06FF, 0750-077F), CJK (3000-9FFF), Thai (0E00-0E7F)
    foreign_pattern = re.compile(
        r"[\u0600-\u08ff\u0980-\u0aff\u0b00-\u0fff\u3000-\u9fff\uac00-\ud7af]"
    )
    foreign_chars = foreign_pattern.findall(cleaned)
    if foreign_chars:
        # Count genuine Devanagari or ASCII alphanumeric characters
        valid_nepali_or_eng = len(re.findall(r"[\u0900-\u097fa-zA-Z0-9]", cleaned))
        # If foreign script dominates or there is no legitimate Nepali/English content, drop as phantom noise
        if len(foreign_chars) > valid_nepali_or_eng or valid_nepali_or_eng == 0:
            return True

    return False


def clean_phonetic_speech_artifacts(text: str) -> str:
    """Repairs common speech-to-text clipped phonemes and loanword transliterations."""
    if not text:
        return text

    repaired = text
    # e.g. "etanes phul" or "detanes phul" or "braiket phul" -> "Brightness full"
    repaired = re.sub(
        r"\b(?:etanes|detanes|braaket|braaiket|braaitanes|braaitnes)\b",
        "Brightness",
        repaired,
        flags=re.IGNORECASE,
    )
    # e.g. "ts ap" or "hwaats ap" -> "WhatsApp"
    repaired = re.sub(
        r"\b(?:ts\s+ap|hwaats\s+ap|hwaatsaep|tsap)\b",
        "WhatsApp",
        repaired,
        flags=re.IGNORECASE,
    )
    # e.g. "bholam" / "bholyum" -> "Volume"
    repaired = re.sub(
        r"\b(?:bholam|bholyum|bholiam)\b",
        "Volume",
        repaired,
        flags=re.IGNORECASE,
    )
    # e.g. "phul" -> "full"
    repaired = re.sub(r"\bphul\b", "full", repaired, flags=re.IGNORECASE)

    # Error loanword repairs: e.g. "kunaiko hiro aayo" / "ke hiro chha" / "hiro aayo" -> "error"
    repaired = re.sub(
        r"\b(?:hiro|hero)\s+(aayo|dekhayo|chha|thiyo|bhaneko)\b",
        r"error \1",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"\b(kunaiko|ke|kunai|sistamko)\s+(?:hiro|hero)\b",
        r"\1 error",
        repaired,
        flags=re.IGNORECASE,
    )

    # Action loanword repairs: e.g. "khet list" -> "delete"
    repaired = re.sub(r"\bkhet\s+list\b", "delete", repaired, flags=re.IGNORECASE)

    # Trending news repairs: e.g. "tending nyooja़" -> "trending news"
    repaired = re.sub(r"\btending\b", "trending", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bnyooja[\u093c]?", "news", repaired, flags=re.IGNORECASE)

    # App names: e.g. "stonik" / "estonik" -> "Stonic AI"
    repaired = re.sub(r"\b(?:stonik|estonik)\b", "Stonic AI", repaired, flags=re.IGNORECASE)

    # Common English action transliterations: e.g. "kriet" -> "create", "rikriet" -> "recreate"
    repaired = re.sub(r"\bkriet\b", "create", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\brikriet\b", "recreate", repaired, flags=re.IGNORECASE)

    return repaired


def romanize_nepali_text(text: str) -> str:
    """Converts a Devanagari or Indic Nepali sentence into clean Romanized Nepali (English letters).
    Leaves English words, numbers, and Latin punctuation intact.
    """
    if not text:
        return text

    # 0. Normalize any related South Asian Indic scripts (Bengali, Gurmukhi, Gujarati) to Devanagari
    text = normalize_indic_to_devanagari(text)

    # 1. Convert Devanagari numerals to ASCII digits (e.g. ६०% -> 60%)
    text = text.translate(DEV_DIGITS)

    # Quick check: does the text contain any Devanagari Unicode characters (0x0900-0x097F)?
    if not any("\u0900" <= c <= "\u097f" for c in text):
        return clean_phonetic_speech_artifacts(text)

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
    return clean_phonetic_speech_artifacts(res)


__all__ = [
    "clean_phonetic_speech_artifacts",
    "is_phantom_noise",
    "normalize_indic_to_devanagari",
    "romanize_nepali_text",
    "romanize_nepali_token",
]
