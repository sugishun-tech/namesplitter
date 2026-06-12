from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata
from typing import Iterable

_SPACE_RE = re.compile(r"\s+")
_EXPLICIT_SPACE_RE = re.compile(r"[ \u3000]")
MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_FIRST_NAME_PATH = MODULE_DIR / "first_name.txt"
DEFAULT_LAST_NAME_PATH = MODULE_DIR / "last_name.txt"


NameSplitResult = list[str] | list[list[str]]


def kata_to_hira(text: str) -> str:
    """Convert Katakana in *text* to Hiragana after NFKC normalization.

    Kanji are preserved. This is matching-only normalization; returned name
    pieces keep the spelling/script supplied by the caller.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
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


def _normalize_yomi_output(text: str) -> str:
    """Normalize yomi for stable indexing, without forcing Katakana to Hiragana."""
    return unicodedata.normalize("NFKC", text.strip())


def _compact_output_piece(text: str) -> str:
    return _SPACE_RE.sub("", text.strip())


def _first_explicit_space_split(text: str) -> tuple[str, str] | None:
    """Split at the first ASCII or full-width space, if both sides exist."""
    raw = text.strip()
    match = _EXPLICIT_SPACE_RE.search(raw)
    if not match:
        return None

    left = _compact_output_piece(raw[: match.start()])
    right = _compact_output_piece(raw[match.end() :])
    if not left or not right:
        return None
    return left, right


def _is_kanji(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
    )


def _is_kana(ch: str) -> bool:
    code = ord(unicodedata.normalize("NFKC", ch)[0]) if ch else 0
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


def _looks_like_kana_reading(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text.strip())
    has_kana = False
    for ch in normalized:
        if ch.isspace():
            continue
        if _is_kana(ch):
            has_kana = True
            continue
        if ch in {"ー", "ゝ", "ゞ", "ヽ", "ヾ", "・", "･"}:
            continue
        return False
    return has_kana


def _norm_len(text: str) -> int:
    return len(normalize_for_match(text))


def _length_prior(text: str, role: str) -> int:
    """Weak prior for Japanese surname/given-name lengths."""
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


def _yomi_length_prior(text: str, role: str) -> int:
    n = _norm_len(text)
    if role == "last":
        table = {1: -4, 2: 7, 3: 10, 4: 9, 5: 6, 6: 3}
    else:
        table = {1: -8, 2: 8, 3: 12, 4: 10, 5: 7, 6: 4, 7: 1}
    return table.get(n, -6)


@dataclass
class RoleDictionary:
    forms: set[str] = field(default_factory=set)
    readings: set[str] = field(default_factory=set)
    form_to_readings: dict[str, set[str]] = field(default_factory=dict)

    @property
    def match_keys(self) -> set[str]:
        return self.forms | self.readings

    def add(self, form: str, readings: Iterable[str] = ()) -> None:
        form_key = normalize_for_match(form)
        if not form_key:
            return

        self.forms.add(form_key)
        reading_keys: set[str] = set()

        if _looks_like_kana_reading(form):
            reading_keys.add(form_key)

        for reading in readings:
            reading_key = normalize_for_match(reading)
            if reading_key:
                reading_keys.add(reading_key)

        if reading_keys:
            self.readings.update(reading_keys)
            self.form_to_readings.setdefault(form_key, set()).update(reading_keys)
        else:
            self.form_to_readings.setdefault(form_key, set())

    def contains_segment(self, segment: str) -> bool:
        key = normalize_for_match(segment)
        return bool(key and (key in self.forms or key in self.readings))

    def contains_yomi(self, yomi: str) -> bool:
        key = normalize_for_match(yomi)
        return bool(key and key in self.readings)

    def pair_matches(self, form: str, yomi: str) -> bool:
        form_key = normalize_for_match(form)
        yomi_key = normalize_for_match(yomi)
        if not form_key or not yomi_key:
            return False
        if yomi_key in self.form_to_readings.get(form_key, set()):
            return True
        # Kana full names often use the reading itself as the visible segment.
        return form_key == yomi_key and yomi_key in self.readings

    def has_known_readings_for_form(self, form: str) -> bool:
        form_key = normalize_for_match(form)
        return bool(self.form_to_readings.get(form_key))

    @classmethod
    def from_lines(cls, lines: Iterable[str]) -> "RoleDictionary":
        role = cls()
        for raw_line in lines:
            line = raw_line.strip().lstrip("\ufeff")
            if not line or line.startswith("#"):
                continue
            try:
                fields = next(csv.reader([line]))
            except csv.Error:
                # Treat a malformed CSV line as a plain legacy dictionary token.
                fields = [line]
            fields = [field.strip() for field in fields if field.strip()]
            if not fields:
                continue
            role.add(fields[0], fields[1:])
        return role


@dataclass(frozen=True)
class _NamePieces:
    last: str
    first: str
    index: int
    from_space: bool


@dataclass(frozen=True)
class _YomiPieces:
    last_yomi: str
    first_yomi: str
    index: int | None
    from_space: bool
    has_yomi: bool
    is_split: bool


@dataclass(frozen=True)
class SplitCandidate:
    """One internal Japanese-order candidate: last/family name + first/given name."""

    last: str
    first: str
    index: int
    last_yomi: str
    first_yomi: str
    yomi_index: int | None
    last_in_dict: bool
    first_in_dict: bool
    last_yomi_in_dict: bool
    first_yomi_in_dict: bool
    last_pair_in_dict: bool
    first_pair_in_dict: bool
    score: int
    reasons: tuple[str, ...]


class NameSplitter:
    """Rule-based splitter for Japanese full names.

    Input is assumed to be Japanese order internally: family name followed by
    given name. Public return values follow the requested field order:

    - namesplit(fullname) -> [first_name, last_name]
    - namesplit(fullname, fullname_yomi) -> [[first_name, last_name], [first_name_yomi, last_name_yomi]]

    Katakana/half-width Katakana are normalized to Hiragana only for matching.
    Name output preserves the caller's spelling except that explicit spaces used
    as separators are removed from returned pieces.
    """

    def __init__(
        self,
        first_name_path: str | Path = DEFAULT_FIRST_NAME_PATH,
        last_name_path: str | Path = DEFAULT_LAST_NAME_PATH,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self.first = self._load_name_dict(first_name_path, encoding=encoding)
        self.last = self._load_name_dict(last_name_path, encoding=encoding)
        # Backward-compatible attributes for callers/tests that only need the
        # normalized one-token match sets. Naturally, compatibility: the tiny
        # altar on which all clean designs are sacrificed.
        self.first_names = self.first.match_keys
        self.last_names = self.last.match_keys

    @staticmethod
    def _load_name_dict(path: str | Path, *, encoding: str) -> RoleDictionary:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"dictionary file not found: {path}")

        with path.open("r", encoding=encoding) as f:
            return RoleDictionary.from_lines(f)

    @classmethod
    def from_iterables(
        cls,
        *,
        first_names: Iterable[str],
        last_names: Iterable[str],
    ) -> "NameSplitter":
        """Build a splitter directly from iterable dictionary lines.

        Items may be legacy one-token entries ("太郎") or the new extractor
        format ("太郎,たろう").
        """
        obj = cls.__new__(cls)
        obj.first = RoleDictionary.from_lines(first_names)
        obj.last = RoleDictionary.from_lines(last_names)
        obj.first_names = obj.first.match_keys
        obj.last_names = obj.last.match_keys
        return obj

    def namesplit(self, fullname: str, fullname_yomi: str | None = None) -> NameSplitResult:
        if not isinstance(fullname, str):
            raise TypeError("name must be str")
        if fullname_yomi is not None and not isinstance(fullname_yomi, str):
            raise TypeError("fullname_yomi must be str or None")

        raw = fullname.strip()
        yomi_raw = _normalize_yomi_output(fullname_yomi) if fullname_yomi is not None else None
        if not raw:
            return self._fallback(raw, yomi_raw)

        candidates = self.candidates(raw, yomi_raw)
        if not candidates:
            return self._fallback(raw, yomi_raw)

        best = candidates[0]
        if fullname_yomi is None:
            return [best.first, best.last]
        return [[best.first, best.last], [best.first_yomi, best.last_yomi]]

    def candidates(self, fullname: str, fullname_yomi: str | None = None) -> list[SplitCandidate]:
        """Return possible splits with combined fullname/yomi scores, best first."""
        if not isinstance(fullname, str):
            raise TypeError("name must be str")
        if fullname_yomi is not None and not isinstance(fullname_yomi, str):
            raise TypeError("fullname_yomi must be str or None")

        raw = fullname.strip()
        if not raw:
            return []

        yomi_raw = _normalize_yomi_output(fullname_yomi) if fullname_yomi is not None else None
        name_options = self._name_options(raw)
        yomi_options = self._yomi_options(yomi_raw)
        result: list[SplitCandidate] = []

        for name_pieces in name_options:
            for yomi_pieces in yomi_options:
                result.append(self._candidate(name_pieces, yomi_pieces))

        result.sort(key=self._sort_key, reverse=True)
        return result

    def _name_options(self, raw: str) -> list[_NamePieces]:
        space_split = _first_explicit_space_split(raw)
        if space_split:
            last, first = space_split
            return [_NamePieces(last=last, first=first, index=len(last), from_space=True)]

        compact = _compact_output_piece(raw)
        if len(compact) < 2:
            return []

        return [
            _NamePieces(last=compact[:i], first=compact[i:], index=i, from_space=False)
            for i in range(1, len(compact))
        ]

    def _yomi_options(self, yomi_raw: str | None) -> list[_YomiPieces]:
        if yomi_raw is None:
            return [_YomiPieces("", "", None, False, False, False)]

        yomi = _normalize_yomi_output(yomi_raw)
        if not yomi:
            return [_YomiPieces("", "", None, False, False, False)]

        space_split = _first_explicit_space_split(yomi)
        if space_split:
            last_yomi, first_yomi = space_split
            return [
                _YomiPieces(
                    last_yomi=last_yomi,
                    first_yomi=first_yomi,
                    index=len(last_yomi),
                    from_space=True,
                    has_yomi=True,
                    is_split=True,
                )
            ]

        compact = _compact_output_piece(yomi)
        if len(compact) < 2:
            return [_YomiPieces("", compact, None, False, True, False)]

        return [
            _YomiPieces(
                last_yomi=compact[:i],
                first_yomi=compact[i:],
                index=i,
                from_space=False,
                has_yomi=True,
                is_split=True,
            )
            for i in range(1, len(compact))
        ]

    def _candidate(self, name: _NamePieces, yomi: _YomiPieces) -> SplitCandidate:
        last_hit = self.last.contains_segment(name.last)
        first_hit = self.first.contains_segment(name.first)
        last_yomi_hit = yomi.is_split and self.last.contains_yomi(yomi.last_yomi)
        first_yomi_hit = yomi.is_split and self.first.contains_yomi(yomi.first_yomi)
        last_pair_hit = yomi.is_split and self.last.pair_matches(name.last, yomi.last_yomi)
        first_pair_hit = yomi.is_split and self.first.pair_matches(name.first, yomi.first_yomi)

        score, reasons = self._score(
            name=name,
            yomi=yomi,
            last_hit=last_hit,
            first_hit=first_hit,
            last_yomi_hit=last_yomi_hit,
            first_yomi_hit=first_yomi_hit,
            last_pair_hit=last_pair_hit,
            first_pair_hit=first_pair_hit,
        )

        return SplitCandidate(
            last=name.last,
            first=name.first,
            index=name.index,
            last_yomi=yomi.last_yomi,
            first_yomi=yomi.first_yomi,
            yomi_index=yomi.index,
            last_in_dict=last_hit,
            first_in_dict=first_hit,
            last_yomi_in_dict=last_yomi_hit,
            first_yomi_in_dict=first_yomi_hit,
            last_pair_in_dict=last_pair_hit,
            first_pair_in_dict=first_pair_hit,
            score=score,
            reasons=tuple(reasons),
        )

    def _score(
        self,
        *,
        name: _NamePieces,
        yomi: _YomiPieces,
        last_hit: bool,
        first_hit: bool,
        last_yomi_hit: bool,
        first_yomi_hit: bool,
        last_pair_hit: bool,
        first_pair_hit: bool,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        if name.from_space:
            score += 100_000
            reasons.append("fullname first explicit space split")
        if yomi.from_space:
            score += 80_000
            reasons.append("fullname_yomi first explicit space split")

        if last_pair_hit and first_pair_hit:
            score += 30_000
            reasons.append("last+first form/yomi pair hit")
        elif last_pair_hit:
            score += 7_000
            reasons.append("last form/yomi pair hit")
        elif first_pair_hit:
            score += 6_800
            reasons.append("first form/yomi pair hit")

        if last_hit and first_hit:
            score += 5_000
            reasons.append("last+first dictionary hit")
        elif last_hit:
            score += 1_000
            reasons.append("last dictionary hit")
        elif first_hit:
            score += 950
            reasons.append("first dictionary hit")

        if last_yomi_hit and first_yomi_hit:
            score += 3_500
            reasons.append("last+first yomi dictionary hit")
        elif last_yomi_hit:
            score += 800
            reasons.append("last yomi dictionary hit")
        elif first_yomi_hit:
            score += 780
            reasons.append("first yomi dictionary hit")

        lp = _length_prior(name.last, "last")
        fp = _length_prior(name.first, "first")
        score += lp + fp
        reasons.append(f"length prior last={lp} first={fp}")

        if yomi.is_split:
            ylp = _yomi_length_prior(yomi.last_yomi, "last")
            yfp = _yomi_length_prior(yomi.first_yomi, "first")
            score += ylp + yfp
            reasons.append(f"yomi length prior last={ylp} first={yfp}")

        left_kind = _char_kind(name.last[-1])
        right_kind = _char_kind(name.first[0])
        if left_kind != right_kind and left_kind != "other" and right_kind != "other":
            score += 60
            reasons.append("script boundary")

        if yomi.is_split:
            if normalize_for_match(name.last) == normalize_for_match(yomi.last_yomi):
                score += 250
                reasons.append("last visible segment equals yomi")
            if normalize_for_match(name.first) == normalize_for_match(yomi.first_yomi):
                score += 250
                reasons.append("first visible segment equals yomi")

            if self.last.has_known_readings_for_form(name.last) and not last_pair_hit:
                score -= 120
                reasons.append("soft penalty: last form/yomi pair mismatch")
            if self.first.has_known_readings_for_form(name.first) and not first_pair_hit:
                score -= 120
                reasons.append("soft penalty: first form/yomi pair mismatch")

        if last_hit and not first_hit and _norm_len(name.first) == 1:
            score -= 500
            reasons.append("penalty: one-character unknown first name")

        if first_hit and not last_hit and _norm_len(name.last) == 1:
            score -= 80
            reasons.append("penalty: one-character unknown last name")

        return score, reasons

    @staticmethod
    def _sort_key(candidate: SplitCandidate) -> tuple[int, int, int, int, int]:
        pair_hits = int(candidate.last_pair_in_dict) + int(candidate.first_pair_in_dict)
        dict_hits = int(candidate.last_in_dict) + int(candidate.first_in_dict)
        balance = -abs(_norm_len(candidate.last) - _norm_len(candidate.first))
        early_split = -candidate.index
        yomi_balance = 0
        if candidate.yomi_index is not None:
            yomi_balance = -abs(_norm_len(candidate.last_yomi) - _norm_len(candidate.first_yomi))
        return (candidate.score, pair_hits, dict_hits, balance + yomi_balance, early_split)

    @staticmethod
    def _fallback(fullname: str, fullname_yomi: str | None = None) -> NameSplitResult:
        if fullname_yomi is None:
            return [fullname, ""]
        yomi = _normalize_yomi_output(fullname_yomi)
        return [[fullname, ""], [yomi, ""]]


# Convenience function for small scripts. For bulk processing, instantiate
# NameSplitter once and reuse it instead of re-reading dictionary files.
def namesplit(
    fullname: str,
    fullname_yomi: str | None = None,
    *,
    first_name_path: str | Path = DEFAULT_FIRST_NAME_PATH,
    last_name_path: str | Path = DEFAULT_LAST_NAME_PATH,
    encoding: str = "utf-8",
) -> NameSplitResult:
    return NameSplitter(first_name_path, last_name_path, encoding=encoding).namesplit(fullname, fullname_yomi)
