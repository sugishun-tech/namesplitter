#!/usr/bin/env python3
"""
Extract Japanese surnames and given names from JMnedict.xml / JMnedict.xml.gz.

Outputs TSV files with kanji/kana surface forms and normalized hiragana readings.
Uses only Python standard library.

Typical usage:
    python extract_jmnedict_person_names.py --download --out names_out
    python extract_jmnedict_person_names.py JMnedict.xml.gz --out names_out

Generated files:
    last_name.txt              # splitter-compatible: surname forms + hiragana readings
    first_name.txt             # splitter-compatible: given-name forms + hiragana readings
    ambiguous_name.txt         # lines appearing in both first_name.txt and last_name.txt
    surnames.tsv               # detailed form-reading pairs
    given_names.tsv            # detailed form-reading pairs
    unclassified_names.tsv
    ambiguous_pairs.tsv
    surname_forms.txt
    surname_readings.txt
    given_forms.txt
    given_readings.txt
"""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import sys
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, NamedTuple, TextIO

# The EDRDG documentation links to the FTP host. HTTPS normally works too, and is
# nicer to scripts living behind modern corporate network paranoia.
DOWNLOAD_URLS = (
    "https://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz",
    "ftp://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz",
)

SURNAME_KINDS = {"surname"}
GIVEN_KINDS = {"given", "female", "male"}
PERSON_NAME_KINDS = SURNAME_KINDS | GIVEN_KINDS | {"unclassified"}

# JMnedict XML uses DTD entities in <name_type>. ElementTree expands internal DTD
# entities into their descriptions. Some derived files keep the entity names.
# Accept both, plus old ENAMDICT one-letter codes, because compatibility is where
# software goes to develop chronic pain.
TYPE_ALIASES = {
    # XML entity names / modern tags
    "surname": "surname",
    "given": "given",
    "fem": "female",
    "female": "female",
    "masc": "male",
    "male": "male",
    "unclass": "unclassified",
    "unclassified": "unclassified",
    "person": "person",
    # ElementTree-expanded DTD descriptions seen in JMnedict
    "family or surname": "surname",
    "given name or forename, gender not specified": "given",
    "female given name or forename": "female",
    "male given name or forename": "male",
    "unclassified name": "unclassified",
    "full name of a particular person": "person",
    # ENAMDICT-style classification codes
    "s": "surname",
    "g": "given",
    "f": "female",
    "m": "male",
    "u": "unclassified",
    "h": "person",
}


class NameRow(NamedTuple):
    form: str
    reading_hira: str
    kind: str
    gender_hint: str
    ent_seq: str
    source_types: str


class Stats(dict):
    def inc(self, key: str, n: int = 1) -> None:
        self[key] = int(self.get(key, 0)) + n


def norm_text(s: str | None) -> str:
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s).strip()


def kata_to_hira(s: str) -> str:
    # Katakana U+30A1..U+30F6 maps to hiragana by subtracting 0x60.
    # Keep prolonged sound mark, middle dot, iteration marks, etc. as-is.
    chars: list[str] = []
    for c in s:
        if "ァ" <= c <= "ヶ":
            chars.append(chr(ord(c) - 0x60))
        else:
            chars.append(c)
    return "".join(chars)


def normalize_reading(s: str | None) -> str:
    return kata_to_hira(norm_text(s))


def local_name(tag: str) -> str:
    # Namespace-tolerant: '{namespace}entry' -> 'entry'
    return tag.rsplit("}", 1)[-1]


def children(elem: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in list(elem) if local_name(c.tag) == name]


def first_child_text(elem: ET.Element, name: str) -> str:
    for c in children(elem, name):
        return norm_text(c.text)
    return ""


def child_texts(elem: ET.Element, name: str) -> list[str]:
    return [norm_text(c.text) for c in children(elem, name) if norm_text(c.text)]


def canonical_name_type(raw: str) -> str | None:
    key = norm_text(raw).lower()
    key = key.strip("&;")
    return TYPE_ALIASES.get(key)


def detect_gender(kinds: set[str]) -> str:
    has_f = "female" in kinds
    has_m = "male" in kinds
    has_g = "given" in kinds
    if has_f and has_m:
        return "mixed"
    if has_f:
        return "female"
    if has_m:
        return "male"
    if has_g:
        return "unspecified"
    return ""


def is_probably_japanese_name_form(s: str) -> bool:
    # Keep kanji/kana forms. This filters accidental Latin-only material if a
    # derived file has wandered off the reservation.
    for ch in s:
        if (
            "\u3040" <= ch <= "\u309f"  # Hiragana
            or "\u30a0" <= ch <= "\u30ff"  # Katakana
            or "\u3400" <= ch <= "\u4dbf"  # CJK Extension A
            or "\u4e00" <= ch <= "\u9fff"  # CJK Unified Ideographs
            or "\uf900" <= ch <= "\ufaff"  # CJK Compatibility Ideographs
        ):
            return True
    return False


def open_xml(path: Path) -> BinaryIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return path.open("rb")


def download_jmnedict(dest_dir: Path, force: bool = False) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "JMnedict.xml.gz"
    if dest.exists() and not force:
        return dest

    last_error: Exception | None = None
    for url in DOWNLOAD_URLS:
        try:
            print(f"download: {url}", file=sys.stderr)
            with urllib.request.urlopen(url, timeout=60) as r, dest.open("wb") as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            return dest
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_error = e
            print(f"download failed: {e}", file=sys.stderr)

    raise RuntimeError(f"Could not download JMnedict.xml.gz: {last_error}")


def parse_entry(entry: ET.Element, stats: Stats) -> tuple[str, set[str], str, list[tuple[str, str]]]:
    ent_seq = first_child_text(entry, "ent_seq")

    raw_forms: list[str] = []
    for k_ele in children(entry, "k_ele"):
        keb = first_child_text(k_ele, "keb")
        if keb:
            raw_forms.append(keb)

    # Preserve order while deduplicating.
    k_forms = list(dict.fromkeys(raw_forms))

    pairs: list[tuple[str, str]] = []
    for r_ele in children(entry, "r_ele"):
        reading = normalize_reading(first_child_text(r_ele, "reb"))
        if not reading:
            continue

        restrictions = child_texts(r_ele, "re_restr")
        no_kanji = bool(children(r_ele, "re_nokanji"))

        if no_kanji or not k_forms:
            pairs.append((reading, reading))
            continue

        targets = restrictions if restrictions else k_forms
        target_set = set(k_forms)
        for form in targets:
            form = norm_text(form)
            if form in target_set:
                pairs.append((form, reading))

    # Fallback for malformed entries: keep kanji forms with empty readings.
    # Normal JMnedict entries should have r_ele, so this is mainly defensive.
    if not pairs and k_forms:
        for form in k_forms:
            pairs.append((form, ""))

    raw_types: list[str] = []
    kinds: set[str] = set()
    for trans in children(entry, "trans"):
        for nt in children(trans, "name_type"):
            raw = norm_text(nt.text)
            if not raw:
                continue
            raw_types.append(raw)
            kind = canonical_name_type(raw)
            if kind:
                kinds.add(kind)
            else:
                stats.inc(f"unknown_name_type:{raw}")

    source_types = ";".join(sorted(set(raw_types)))
    return ent_seq, kinds, source_types, list(dict.fromkeys(pairs))


def iter_rows(xml_path: Path, include_unclassified: bool, strict_japanese: bool) -> Iterator[NameRow]:
    stats = Stats()
    with open_xml(xml_path) as f:
        context = ET.iterparse(f, events=("end",))
        for _, elem in context:
            if local_name(elem.tag) != "entry":
                continue

            stats.inc("entries_seen")
            ent_seq, kinds, source_types, pairs = parse_entry(elem, stats)
            target_kinds = set(kinds)
            if not include_unclassified:
                target_kinds.discard("unclassified")
            target_kinds &= PERSON_NAME_KINDS

            if target_kinds:
                stats.inc("entries_person_name")

            gender_hint = detect_gender(kinds)
            for form, reading in pairs:
                form = norm_text(form)
                reading = normalize_reading(reading)
                if not form:
                    continue
                if strict_japanese and not is_probably_japanese_name_form(form):
                    continue

                if "surname" in target_kinds:
                    yield NameRow(form, reading, "surname", "", ent_seq, source_types)
                if target_kinds & GIVEN_KINDS:
                    yield NameRow(form, reading, "given", gender_hint, ent_seq, source_types)
                if include_unclassified and "unclassified" in target_kinds:
                    yield NameRow(form, reading, "unclassified", "", ent_seq, source_types)

            elem.clear()

    # Stash stats on the function for main() without complicating the streaming API.
    iter_rows.stats = stats  # type: ignore[attr-defined]


def write_tsv(path: Path, rows: Iterable[NameRow]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["form", "reading_hira", "kind", "gender_hint", "ent_seq", "source_types"])
        for row in sorted(set(rows), key=lambda r: (r.form, r.reading_hira, r.kind, r.gender_hint, r.ent_seq)):
            w.writerow(row)
            count += 1
    return count


def write_txt(path: Path, values: Iterable[str]) -> int:
    vals = sorted(v for v in set(values) if v)
    with path.open("w", encoding="utf-8", newline="") as f:
        for v in vals:
            f.write(v + "\n")
    return len(vals)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Extract surname/given-name form-reading pairs from JMnedict.xml(.gz)."
    )
    p.add_argument(
        "xml",
        nargs="?",
        help="Path to JMnedict.xml or JMnedict.xml.gz. Omit with --download.",
    )
    p.add_argument("--out", default="jmnedict_names", help="Output directory.")
    p.add_argument("--download", action="store_true", help="Download JMnedict.xml.gz first.")
    p.add_argument("--force-download", action="store_true", help="Re-download even if file exists.")
    p.add_argument(
        "--include-unclassified",
        action="store_true",
        help="Also export unclassified person names to unclassified_names.tsv.",
    )
    p.add_argument(
        "--no-strict-japanese",
        action="store_true",
        help="Do not filter out Latin-only/non-Japanese-looking forms.",
    )
    p.add_argument(
        "--simple-txt-mode",
        choices=("forms-and-readings", "forms-only", "readings-only"),
        default="forms-and-readings",
        help=(
            "What to put in first_name.txt / last_name.txt. "
            "Default matches the earlier splitter format: kanji/kana forms plus hiragana readings."
        ),
    )
    args = p.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.download:
        xml_path = download_jmnedict(out_dir, force=args.force_download)
    elif args.xml:
        xml_path = Path(args.xml)
    else:
        p.error("give JMnedict.xml(.gz), or use --download")

    if not xml_path.exists():
        raise FileNotFoundError(xml_path)

    strict_japanese = not args.no_strict_japanese

    surnames: set[NameRow] = set()
    given: set[NameRow] = set()
    unclassified: set[NameRow] = set()
    for row in iter_rows(
        xml_path,
        include_unclassified=args.include_unclassified,
        strict_japanese=strict_japanese,
    ):
        if row.kind == "surname":
            surnames.add(row)
        elif row.kind == "given":
            given.add(row)
        elif row.kind == "unclassified":
            unclassified.add(row)

    n_surnames = write_tsv(out_dir / "surnames.tsv", surnames)
    n_given = write_tsv(out_dir / "given_names.tsv", given)
    n_unclassified = 0
    if args.include_unclassified:
        n_unclassified = write_tsv(out_dir / "unclassified_names.tsv", unclassified)

    surname_pairs = {(r.form, r.reading_hira) for r in surnames}
    given_pairs = {(r.form, r.reading_hira) for r in given}
    ambiguous_pairs = surname_pairs & given_pairs

    ambiguous_rows = [
        NameRow(form, reading, "surname+given", "", "", "")
        for form, reading in ambiguous_pairs
    ]
    n_ambiguous_pairs = write_tsv(out_dir / "ambiguous_pairs.tsv", ambiguous_rows)

    surname_forms = {r.form for r in surnames}
    given_forms = {r.form for r in given}
    surname_readings = {r.reading_hira for r in surnames if r.reading_hira}
    given_readings = {r.reading_hira for r in given if r.reading_hira}

    n_surname_forms = write_txt(out_dir / "surname_forms.txt", surname_forms)
    n_surname_readings = write_txt(out_dir / "surname_readings.txt", surname_readings)
    n_given_forms = write_txt(out_dir / "given_forms.txt", given_forms)
    n_given_readings = write_txt(out_dir / "given_readings.txt", given_readings)
    n_ambiguous_forms = write_txt(out_dir / "ambiguous_forms.txt", surname_forms & given_forms)

    # Compatibility output for older/simpler name splitters that expect exactly
    # first_name.txt and last_name.txt as one-token-per-line dictionaries.
    # Default includes both written forms and hiragana readings, matching the
    # earlier quick extractor. This is noisier than TSV, but convenient.
    if args.simple_txt_mode == "forms-only":
        last_name_values = surname_forms
        first_name_values = given_forms
    elif args.simple_txt_mode == "readings-only":
        last_name_values = surname_readings
        first_name_values = given_readings
    else:
        last_name_values = surname_forms | surname_readings
        first_name_values = given_forms | given_readings

    n_last_name = write_txt(out_dir / "last_name.txt", last_name_values)
    n_first_name = write_txt(out_dir / "first_name.txt", first_name_values)
    n_ambiguous_name = write_txt(out_dir / "ambiguous_name.txt", last_name_values & first_name_values)

    print(f"input: {xml_path}")
    print(f"out: {out_dir}")
    print(f"first_name.txt lines: {n_first_name}")
    print(f"last_name.txt lines: {n_last_name}")
    print(f"ambiguous_name.txt lines: {n_ambiguous_name}")
    print(f"simple_txt_mode: {args.simple_txt_mode}")
    print(f"surnames.tsv rows: {n_surnames}")
    print(f"given_names.tsv rows: {n_given}")
    if args.include_unclassified:
        print(f"unclassified_names.tsv rows: {n_unclassified}")
    print(f"ambiguous_pairs.tsv rows: {n_ambiguous_pairs}")
    print(f"surname_forms.txt lines: {n_surname_forms}")
    print(f"surname_readings.txt lines: {n_surname_readings}")
    print(f"given_forms.txt lines: {n_given_forms}")
    print(f"given_readings.txt lines: {n_given_readings}")
    print(f"ambiguous_forms.txt lines: {n_ambiguous_forms}")

    stats: Stats = getattr(iter_rows, "stats", Stats())  # type: ignore[attr-defined]
    unknown = {k: v for k, v in stats.items() if k.startswith("unknown_name_type:")}
    if unknown:
        print("warning: unknown <name_type> values found:", file=sys.stderr)
        for k, v in sorted(unknown.items()):
            print(f"  {k.removeprefix('unknown_name_type:')}: {v}", file=sys.stderr)

    if n_surnames == 0 and n_given == 0:
        print(
            "warning: extracted zero surname/given rows. Check that this is JMnedict, not JMdict/EDICT2.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
