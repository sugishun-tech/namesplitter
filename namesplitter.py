from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Iterable

_SPACE_RE = re.compile(r"\s+")
MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_FIRST_NAME_PATH = MODULE_DIR / "first_name.txt"
DEFAULT_LAST_NAME_PATH = MODULE_DIR / "last_name.txt"


def kata_to_hira(text: str) -> str:
    """Convert Katakana in *text* to Hiragana after NFKC normalization.

    This intentionally does not transliterate Kanji readings. For example,
    "森" stays "森". It only makes "モリ", "ﾓﾘ" and "もり" match the same
    dictionary key.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        # Katakana small A through small Ke, including ヴ.
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        # Katakana iteration marks ヽヾ -> Hiragana ゝゞ.
        elif 0x30FD <= code <= 0x30FE:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def normalize_for_match(text: str) -> str:
    """Normalize a dictionary entry or query segment for matching."""
    text = unicodedata.normalize("NFKC", text.strip())
    text = _SPACE_RE.sub("", text)
    return kata_to_hira(text)


def _is_kanji(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF   # CJK Extension A
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0xF900 <= code <= 0xFAFF  # CJK Compatibility Ideographs
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
    )


def _is_kana(ch: str) -> bool:
    code = ord(ch)
    return 0x3041 <= code <= 0x309F or 0x30A1 <= code <= 0x30FF


def _char_kind(ch: str) -> str:
    ch = unicodedata.normalize("NFKC", ch)
    if not ch:
        return "other"
    ch = ch[0]
    if _is_kanji(ch):
        return "kanji"
    if _is_kana(ch):
        return "kana"
    if ch.isascii() and ch.isalpha():
        return "latin"
    return "other"


def _script_kind(text: str) -> str:
    kinds = {_char_kind(ch) for ch in unicodedata.normalize("NFKC", text) if not ch.isspace()}
    kinds.discard("other")
    if not kinds:
        return "other"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _norm_len(text: str) -> int:
    return len(normalize_for_match(text))


def _length_prior(text: str, role: str) -> int:
    """A small prior for Japanese name lengths.

    It is deliberately weak. Dictionary hits dominate; this only breaks ties
    and avoids pathological splits such as 森満|子 when 森|満子 is plausible.
    """
    n = _norm_len(text)
    kind = _script_kind(text)

    if role == "last":
        if kind == "kanji":
            table = {1: 9, 2: 12, 3: 9, 4: 4}
        elif kind == "kana":
            table = {1: -2, 2: 8, 3: 10, 4: 9, 5: 6, 6: 3}
        else:
            table = {1: 3, 2: 8, 3: 9, 4: 7, 5: 4}
    else:
        if kind == "kanji":
            table = {1: 5, 2: 12, 3: 8, 4: 3}
        elif kind == "kana":
            table = {1: -8, 2: 8, 3: 12, 4: 9, 5: 5, 6: 1}
        else:
            table = {1: 0, 2: 8, 3: 9, 4: 7, 5: 4}
    return table.get(n, -10)


@dataclass(frozen=True)
class SplitCandidate:
    last: str
    first: str
    index: int
    last_in_dict: bool
    first_in_dict: bool
    score: int
    reasons: tuple[str, ...]


class NameSplitter:
    """Rule-based splitter for Japanese family-name / given-name strings.

    Matching is performed against normalized dictionary entries:
    - Katakana and half-width Katakana are normalized to Hiragana.
    - Kanji are kept as-is. This class does not infer readings for Kanji.
    - Output preserves the original spelling and script.
    """

    def __init__(
        self,
        first_name_path: str | Path = DEFAULT_FIRST_NAME_PATH,
        last_name_path: str | Path = DEFAULT_LAST_NAME_PATH,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self.first_names = self._load_name_set(first_name_path, encoding=encoding)
        self.last_names = self._load_name_set(last_name_path, encoding=encoding)

    @staticmethod
    def _load_name_set(path: str | Path, *, encoding: str) -> set[str]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"dictionary file not found: {path}")

        names: set[str] = set()
        with path.open("r", encoding=encoding) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                key = normalize_for_match(line)
                if key:
                    names.add(key)
        return names

    @classmethod
    def from_iterables(
        cls,
        *,
        first_names: Iterable[str],
        last_names: Iterable[str],
    ) -> "NameSplitter":
        """Build a splitter directly from iterables. Useful for tests."""
        obj = cls.__new__(cls)
        obj.first_names = {normalize_for_match(x) for x in first_names if normalize_for_match(x)}
        obj.last_names = {normalize_for_match(x) for x in last_names if normalize_for_match(x)}
        return obj

    def namesplit(self, name: str) -> list[str]:
        """Return [family_name, given_name]."""
        if not isinstance(name, str):
            raise TypeError("name must be str")

        raw = name.strip()
        if not raw:
            raise ValueError("name must not be empty")

        # If the input already contains whitespace, trust it.  This is not the
        # main use case, but it prevents needless damage to already-split data.
        parts = [p for p in _SPACE_RE.split(raw) if p]
        if len(parts) >= 2:
            return [parts[0], "".join(parts[1:])]

        if len(raw) == 1:
            return [raw, ""]

        candidates = self.candidates(raw)
        if not candidates:
            return [raw[0], raw[1:]]

        dict_hit_candidates = [c for c in candidates if c.last_in_dict or c.first_in_dict]
        if not dict_hit_candidates:
            return [raw[0], raw[1:]]

        best = max(dict_hit_candidates, key=lambda c: (c.score, -abs(_norm_len(c.last) - _norm_len(c.first)), -c.index))
        return [best.last, best.first]

    def candidates(self, name: str) -> list[SplitCandidate]:
        """Return every possible split with scores, sorted best first."""
        raw = name.strip()
        result: list[SplitCandidate] = []
        for i in range(1, len(raw)):
            last = raw[:i]
            first = raw[i:]
            last_key = normalize_for_match(last)
            first_key = normalize_for_match(first)
            last_hit = last_key in self.last_names
            first_hit = first_key in self.first_names
            score, reasons = self._score(last, first, last_hit, first_hit)
            result.append(
                SplitCandidate(
                    last=last,
                    first=first,
                    index=i,
                    last_in_dict=last_hit,
                    first_in_dict=first_hit,
                    score=score,
                    reasons=tuple(reasons),
                )
            )
        result.sort(key=lambda c: (c.score, -abs(_norm_len(c.last) - _norm_len(c.first)), -c.index), reverse=True)
        return result

    def _score(self, last: str, first: str, last_hit: bool, first_hit: bool) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        if last_hit and first_hit:
            score += 5000
            reasons.append("last+first dictionary hit")
        elif last_hit:
            score += 1000
            reasons.append("last dictionary hit")
        elif first_hit:
            score += 950
            reasons.append("first dictionary hit")

        lp = _length_prior(last, "last")
        fp = _length_prior(first, "first")
        score += lp + fp
        reasons.append(f"length prior last={lp} first={fp}")

        # Mixed-script boundaries are strong hints in strings like 森ミツコ or もり満子.
        left_kind = _char_kind(last[-1])
        right_kind = _char_kind(first[0])
        if left_kind != right_kind and left_kind != "other" and right_kind != "other":
            score += 60
            reasons.append("script boundary")

        # Avoid over-consuming a surname when the leftover given name is a single
        # character that is not in the first-name dictionary: 森満|子 should lose
        # to 森|満子 when both 森 and 森満 are surnames.
        if last_hit and not first_hit and _norm_len(first) == 1:
            score -= 500
            reasons.append("penalty: one-character unknown first name")

        # A one-character unknown surname is possible, but it is weaker than a
        # known surname when another reasonable split exists.
        if first_hit and not last_hit and _norm_len(last) == 1:
            score -= 80
            reasons.append("penalty: one-character unknown last name")

        return score, reasons


# Convenience function for small scripts.  For bulk processing, instantiate
# NameSplitter once and reuse it instead of re-reading dictionary files.
def namesplit(
    name: str,
    *,
    first_name_path: str | Path = DEFAULT_FIRST_NAME_PATH,
    last_name_path: str | Path = DEFAULT_LAST_NAME_PATH,
    encoding: str = "utf-8",
) -> list[str]:
    return NameSplitter(first_name_path, last_name_path, encoding=encoding).namesplit(name)
