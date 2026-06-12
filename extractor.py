#!/usr/bin/env python3
"""
Extract Japanese surname and given-name dictionaries from JMnedict.xml / JMnedict.xml.gz.

Generated files, and only these files:
    last_name.txt
    first_name.txt

Each output line is:
    surface,reading1,reading2,...

Examples:
    武,たけし,たけ
    駿,しゅん,はやお

Readings are normalized to Hiragana. A surface form that is both a surname and
a given name is written to both files, but each file keeps only the readings
observed for that role.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sys
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import BinaryIO, Iterator, NamedTuple

DOWNLOAD_URLS = (
    "https://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz",
    "ftp://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz",
)

SURNAME_KINDS = {"surname"}
GIVEN_KINDS = {"given", "female", "male"}
PERSON_NAME_KINDS = SURNAME_KINDS | GIVEN_KINDS

# JMnedict XML may contain entity names, expanded descriptions, or older
# ENAMDICT-style one-letter codes. The format gods clearly wanted a scavenger
# hunt, so accept all of them.
TYPE_ALIASES = {
    "surname": "surname",
    "given": "given",
    "fem": "female",
    "female": "female",
    "masc": "male",
    "male": "male",
    "unclass": "unclassified",
    "unclassified": "unclassified",
    "person": "person",
    "family or surname": "surname",
    "given name or forename, gender not specified": "given",
    "female given name or forename": "female",
    "male given name or forename": "male",
    "unclassified name": "unclassified",
    "full name of a particular person": "person",
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


class Stats(dict):
    def inc(self, key: str, n: int = 1) -> None:
        self[key] = int(self.get(key, 0)) + n


def norm_text(s: str | None) -> str:
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s).strip()


def kata_to_hira(s: str) -> str:
    chars: list[str] = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        elif 0x30FD <= code <= 0x30FE:
            chars.append(chr(code - 0x60))
        else:
            chars.append(ch)
    return "".join(chars)


def normalize_reading(s: str | None) -> str:
    return kata_to_hira(norm_text(s))


def local_name(tag: str) -> str:
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
    key = norm_text(raw).lower().strip("&;")
    return TYPE_ALIASES.get(key)


def is_probably_japanese_name_form(s: str) -> bool:
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


def parse_entry(entry: ET.Element, stats: Stats) -> tuple[set[str], list[tuple[str, str]]]:
    raw_forms: list[str] = []
    for k_ele in children(entry, "k_ele"):
        keb = first_child_text(k_ele, "keb")
        if keb:
            raw_forms.append(keb)

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

    if not pairs and k_forms:
        for form in k_forms:
            pairs.append((form, ""))

    kinds: set[str] = set()
    for trans in children(entry, "trans"):
        for nt in children(trans, "name_type"):
            raw = norm_text(nt.text)
            if not raw:
                continue
            kind = canonical_name_type(raw)
            if kind:
                kinds.add(kind)
            else:
                stats.inc(f"unknown_name_type:{raw}")

    return kinds, list(dict.fromkeys(pairs))


def iter_rows(xml_path: Path, strict_japanese: bool) -> Iterator[NameRow]:
    stats = Stats()
    with open_xml(xml_path) as f:
        context = ET.iterparse(f, events=("end",))
        for _, elem in context:
            if local_name(elem.tag) != "entry":
                continue

            stats.inc("entries_seen")
            kinds, pairs = parse_entry(elem, stats)
            target_kinds = kinds & PERSON_NAME_KINDS
            if target_kinds:
                stats.inc("entries_person_name")

            for form, reading in pairs:
                form = norm_text(form)
                reading = normalize_reading(reading)
                if not form:
                    continue
                if strict_japanese and not is_probably_japanese_name_form(form):
                    continue

                if "surname" in target_kinds:
                    yield NameRow(form, reading, "surname")
                if target_kinds & GIVEN_KINDS:
                    yield NameRow(form, reading, "given")

            elem.clear()

    iter_rows.stats = stats  # type: ignore[attr-defined]


def add_role_reading(form_to_readings: dict[str, list[str]], form: str, reading: str) -> None:
    readings = form_to_readings.setdefault(form, [])
    if reading and reading not in readings:
        readings.append(reading)


def write_name_csv(path: Path, form_to_readings: dict[str, list[str]]) -> int:
    items = sorted(form_to_readings.items(), key=lambda item: (normalize_reading(item[0]), item[0]))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        for form, readings in items:
            writer.writerow([form, *[r for r in readings if r]])
    return len(items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract first_name.txt and last_name.txt from JMnedict.xml(.gz)."
    )
    parser.add_argument(
        "xml",
        nargs="?",
        help="Path to JMnedict.xml or JMnedict.xml.gz. Omit with --download.",
    )
    parser.add_argument("--out", default="jmnedict_names", help="Output directory.")
    parser.add_argument("--download", action="store_true", help="Download JMnedict.xml.gz first.")
    parser.add_argument("--force-download", action="store_true", help="Re-download even if file exists.")
    parser.add_argument(
        "--no-strict-japanese",
        action="store_true",
        help="Do not filter out Latin-only/non-Japanese-looking forms.",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.download:
        xml_path = download_jmnedict(out_dir, force=args.force_download)
    elif args.xml:
        xml_path = Path(args.xml)
    else:
        parser.error("give JMnedict.xml(.gz), or use --download")

    if not xml_path.exists():
        raise FileNotFoundError(xml_path)

    strict_japanese = not args.no_strict_japanese
    last_name_map: dict[str, list[str]] = {}
    first_name_map: dict[str, list[str]] = {}

    for row in iter_rows(xml_path, strict_japanese=strict_japanese):
        if row.kind == "surname":
            add_role_reading(last_name_map, row.form, row.reading_hira)
        elif row.kind == "given":
            add_role_reading(first_name_map, row.form, row.reading_hira)

    n_last = write_name_csv(out_dir / "last_name.txt", last_name_map)
    n_first = write_name_csv(out_dir / "first_name.txt", first_name_map)

    print(f"input: {xml_path}")
    print(f"out: {out_dir}")
    print(f"first_name.txt lines: {n_first}")
    print(f"last_name.txt lines: {n_last}")
    print("generated files: first_name.txt, last_name.txt")

    stats: Stats = getattr(iter_rows, "stats", Stats())  # type: ignore[attr-defined]
    unknown = {k: v for k, v in stats.items() if k.startswith("unknown_name_type:")}
    if unknown:
        print("warning: unknown <name_type> values found:", file=sys.stderr)
        for k, v in sorted(unknown.items()):
            print(f"  {k.removeprefix('unknown_name_type:')}: {v}", file=sys.stderr)

    if n_last == 0 and n_first == 0:
        print(
            "warning: extracted zero surname/given rows. Check that this is JMnedict, not JMdict/EDICT2.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
