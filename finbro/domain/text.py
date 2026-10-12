"""Normalizacja tekstu do porównań: bez wielkości liter, polskich znaków i wielokrotnych spacji."""

from __future__ import annotations

import unicodedata

_POLISH = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold(text: str | None) -> str:
    if not text:
        return ""
    text = text.translate(_POLISH)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())
