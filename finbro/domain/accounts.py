"""Numery rachunków: normalizacja i porównywanie (także zamaskowanych)."""

from __future__ import annotations

import re

_KEEP_RE = re.compile(r"[^0-9A-Z*]")


def normalize_account(text: str | None) -> str:
    """Usuwa spacje i separatory: ``PL27 1020 ...`` -> ``PL271020...``. Zachowuje gwiazdki maski."""
    if not text:
        return ""
    return _KEEP_RE.sub("", text.upper())


def _digits_core(normalized: str) -> str:
    # Prefiks kraju (PL) nie jest częścią numeru NRB.
    return normalized[2:] if normalized[:2].isalpha() else normalized


def account_matches(candidate: str | None, configured: str | None) -> bool:
    """Czy numer z wyciągu (może być zamaskowany ``*``) pasuje do skonfigurowanego numeru.

    Gdy numer jest zamaskowany, porównujemy widoczne znaki z początku i z końca.
    """
    a = _digits_core(normalize_account(candidate))
    b = _digits_core(normalize_account(configured))
    if not a or not b or "*" in b:
        return False
    if "*" not in a:
        return a == b
    head, _, rest = a.partition("*")
    tail = rest.rsplit("*", 1)[-1]
    if not head and not tail:
        return False
    return len(a) == len(b) and b.startswith(head) and b.endswith(tail)


def same_account(a: str | None, b: str | None) -> bool:
    """Czy dwa pełne (niezamaskowane) numery to ten sam rachunek, z prefiksem kraju lub bez."""
    x, y = _digits_core(normalize_account(a)), _digits_core(normalize_account(b))
    return bool(x) and "*" not in x and x == y
