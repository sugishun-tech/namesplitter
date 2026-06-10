from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import namesplitter
from namesplitter import NameSplitter, kata_to_hira, namesplit, normalize_for_match


def write_dicts(tmp_path: Path, *, first: list[str], last: list[str]) -> tuple[Path, Path]:
    first_path = tmp_path / "first_name.txt"
    last_path = tmp_path / "last_name.txt"
    first_path.write_text("\n".join(first) + "\n", encoding="utf-8")
    last_path.write_text("\n".join(last) + "\n", encoding="utf-8")
    return first_path, last_path


@pytest.fixture
def hard_case_splitter() -> NameSplitter:
    """A compact deterministic dictionary for ambiguous split tests."""
    return NameSplitter.from_iterables(
        first_names=[
            "満子",
            "みつこ",
            "美津子",
            "太郎",
            "一郎",
            "次郎",
            "花子",
            "健太",
            "明子",
            "明",
            "武",
            "翼",
            "葵",
            "あおい",
            "さくら",
            "まり",
            "ゆう",
            "ゆうこ",
            "りん",
            "れい",
            "かな",
            "まこと",
            "ひろし",
            "しょう",
        ],
        last_names=[
            "森",
            "森満",
            "もり",
            "佐藤",
            "佐",
            "藤",
            "青木",
            "青",
            "木村",
            "木",
            "村上",
            "村",
            "上原",
            "上",
            "原田",
            "原",
            "田中",
            "田",
            "中山",
            "中",
            "山田",
            "山",
            "小野",
            "小",
            "大山",
            "大",
            "杉",
            "杉下",
            "阿部",
            "阿",
            "伊藤",
            "伊",
            "加藤",
            "加",
            "高橋",
            "高",
            "長谷川",
            "長谷",
            "東",
            "西",
            "南",
            "北",
        ],
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("カタカナ", "かたかな"),
        ("ﾓﾘﾐﾂｺ", "もりみつこ"),
        ("ヴァイオリン", "ゔぁいおりん"),
        ("ＡＢＣ モリ", "abc もり"),
    ],
)
def test_kata_to_hira_normalizes_katakana_and_half_width(text: str, expected: str) -> None:
    assert kata_to_hira(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (" モ リ  ", "もり"),
        ("ﾓﾘ\tﾐﾂｺ", "もりみつこ"),
        ("森 満子", "森満子"),
    ],
)
def test_normalize_for_match_removes_spaces_and_preserves_kanji(text: str, expected: str) -> None:
    assert normalize_for_match(text) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 長い名字にも見えるが、名前辞書 hit を優先するケース。
        ("森満子", ["森", "満子"]),
        ("森美津子", ["森", "美津子"]),
        # かな・カタカナ・半角カタカナは同じ辞書キーに寄せる。
        ("もりみつこ", ["もり", "みつこ"]),
        ("モリミツコ", ["モリ", "ミツコ"]),
        ("ﾓﾘﾐﾂｺ", ["ﾓﾘ", "ﾐﾂｺ"]),
        # 1文字名字と2文字名字の衝突。
        ("佐藤太郎", ["佐藤", "太郎"]),
        ("青木健太", ["青木", "健太"]),
        ("木村花子", ["木村", "花子"]),
        ("村上明子", ["村上", "明子"]),
        ("上原明", ["上原", "明"]),
        ("原田翼", ["原田", "翼"]),
        ("田中葵", ["田中", "葵"]),
        ("中山太郎", ["中山", "太郎"]),
        ("山田花子", ["山田", "花子"]),
        ("小野次郎", ["小野", "次郎"]),
        ("大山一郎", ["大山", "一郎"]),
        # 3文字名字。
        ("長谷川ひろし", ["長谷川", "ひろし"]),
        # Mixed script boundary should help without damaging output script.
        ("森ミツコ", ["森", "ミツコ"]),
        ("もり満子", ["もり", "満子"]),
        ("阿部さくら", ["阿部", "さくら"]),
        ("伊藤まり", ["伊藤", "まり"]),
        ("加藤ゆうこ", ["加藤", "ゆうこ"]),
        ("高橋しょう", ["高橋", "しょう"]),
        # 1文字名字も成立する。
        ("東りん", ["東", "りん"]),
        ("西れい", ["西", "れい"]),
        ("南かな", ["南", "かな"]),
        ("北まこと", ["北", "まこと"]),
    ],
)
def test_hard_ambiguous_names_with_compact_dictionary(
    hard_case_splitter: NameSplitter,
    raw: str,
    expected: list[str],
) -> None:
    assert hard_case_splitter.namesplit(raw) == expected


def test_does_not_overconsume_last_name_when_leftover_first_name_is_unknown() -> None:
    splitter = NameSplitter.from_iterables(
        first_names=["満子"],
        last_names=["森", "森満"],
    )

    assert splitter.namesplit("森満子") == ["森", "満子"]

    candidates = splitter.candidates("森満子")
    assert candidates[0].last == "森"
    assert candidates[0].first == "満子"
    overconsumed = next(c for c in candidates if c.last == "森満" and c.first == "子")
    assert "penalty: one-character unknown first name" in overconsumed.reasons


def test_unknown_string_falls_back_to_first_character_split(hard_case_splitter: NameSplitter) -> None:
    assert hard_case_splitter.namesplit("龘麤靐") == ["龘", "麤靐"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("森 満子", ["森", "満子"]),
        ("森　満　子", ["森", "満子"]),
        ("  佐藤   太郎  ", ["佐藤", "太郎"]),
    ],
)
def test_whitespace_separated_input_is_trusted(
    hard_case_splitter: NameSplitter,
    raw: str,
    expected: list[str],
) -> None:
    assert hard_case_splitter.namesplit(raw) == expected


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_empty_name_raises_value_error(hard_case_splitter: NameSplitter, value: str) -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        hard_case_splitter.namesplit(value)


@pytest.mark.parametrize("value", [None, 123, ["森満子"]])
def test_non_string_name_raises_type_error(hard_case_splitter: NameSplitter, value: object) -> None:
    with pytest.raises(TypeError, match="name must be str"):
        hard_case_splitter.namesplit(value)  # type: ignore[arg-type]


def test_single_character_returns_empty_first_name(hard_case_splitter: NameSplitter) -> None:
    assert hard_case_splitter.namesplit("森") == ["森", ""]


def test_dictionary_files_are_actually_used(tmp_path: Path) -> None:
    first_path, last_path = write_dicts(
        tmp_path,
        first=["乙丙", "太郎"],
        last=["甲", "甲乙"],
    )

    splitter = NameSplitter(first_path, last_path)

    # If dictionaries are ignored or hard-coded, this synthetic name cannot pass.
    assert splitter.namesplit("甲乙丙") == ["甲", "乙丙"]


def test_dictionary_loader_ignores_blank_lines_and_comments(tmp_path: Path) -> None:
    first_path = tmp_path / "first_name.txt"
    last_path = tmp_path / "last_name.txt"
    first_path.write_text("\n# comment\n満子\n", encoding="utf-8")
    last_path.write_text("\n# comment\n森\n森満\n", encoding="utf-8")

    assert NameSplitter(first_path, last_path).namesplit("森満子") == ["森", "満子"]


def test_missing_dictionary_file_raises_file_not_found(tmp_path: Path) -> None:
    first_path = tmp_path / "missing_first_name.txt"
    last_path = tmp_path / "last_name.txt"
    last_path.write_text("森\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="dictionary file not found"):
        NameSplitter(first_path, last_path)


def test_convenience_namesplit_accepts_explicit_dictionary_paths(tmp_path: Path) -> None:
    first_path, last_path = write_dicts(
        tmp_path,
        first=["満子"],
        last=["森", "森満"],
    )

    assert namesplit("森満子", first_name_path=first_path, last_name_path=last_path) == ["森", "満子"]


def test_default_dictionary_paths_are_module_local() -> None:
    assert namesplitter.DEFAULT_FIRST_NAME_PATH == Path(namesplitter.__file__).resolve().parent / "first_name.txt"
    assert namesplitter.DEFAULT_LAST_NAME_PATH == Path(namesplitter.__file__).resolve().parent / "last_name.txt"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("森満子", ["森", "満子"]),
        ("もりみつこ", ["もり", "みつこ"]),
        ("モリミツコ", ["モリ", "ミツコ"]),
        ("佐藤太郎", ["佐藤", "太郎"]),
        ("山田太郎", ["山田", "太郎"]),
        ("秋山明子", ["秋山", "明子"]),
        ("青木健太", ["青木", "健太"]),
    ],
)
def test_with_real_uploaded_dictionaries(raw: str, expected: list[str]) -> None:
    """Smoke-test realistic cases against first_name.txt and last_name.txt."""
    base = Path(namesplitter.__file__).resolve().parent
    first_path = base / "first_name.txt"
    last_path = base / "last_name.txt"

    if not first_path.exists() or not last_path.exists():
        pytest.skip("first_name.txt and last_name.txt are required for real dictionary tests")

    splitter = NameSplitter(first_path, last_path)
    assert splitter.namesplit(raw) == expected


def test_sugishita_takes_one_character_last_name_when_given_name_is_unknown_with_real_dictionary() -> None:
    """Regression spec for the hard 杉下武 case discussed during development."""
    base = Path(namesplitter.__file__).resolve().parent
    first_path = base / "first_name.txt"
    last_path = base / "last_name.txt"

    if not first_path.exists() or not last_path.exists():
        pytest.skip("first_name.txt and last_name.txt are required for real dictionary tests")

    splitter = NameSplitter(first_path, last_path)
    assert splitter.namesplit("杉下武") == ["杉下", "武"]
