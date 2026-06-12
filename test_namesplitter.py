from __future__ import annotations

import csv
from pathlib import Path

import pytest

import extractor
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
    return NameSplitter.from_iterables(
        first_names=[
            "満子,みつこ",
            "美津子,みつこ",
            "太郎,たろう",
            "一郎,いちろう",
            "次郎,じろう",
            "花子,はなこ",
            "健太,けんた",
            "明子,あきこ",
            "明,あきら,あき",
            "武,たけし",
            "翼,つばさ",
            "葵,あおい",
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
            "森,もり",
            "森満,もりみつ",
            "佐藤,さとう",
            "佐,さ",
            "藤,ふじ",
            "青木,あおき",
            "青,あお",
            "木村,きむら",
            "木,き",
            "村上,むらかみ",
            "村,むら",
            "上原,うえはら",
            "上,うえ",
            "原田,はらだ",
            "原,はら",
            "田中,たなか",
            "田,た",
            "中山,なかやま",
            "中,なか",
            "山田,やまだ",
            "山,やま",
            "小野,おの",
            "小,こ",
            "大山,おおやま",
            "大,おお",
            "杉,すぎ",
            "杉下,すぎした",
            "阿部,あべ",
            "阿,あ",
            "伊藤,いとう",
            "伊,い",
            "加藤,かとう",
            "加,か",
            "高橋,たかはし",
            "高,たか",
            "長谷川,はせがわ",
            "長谷,はせ",
            "東,ひがし,あずま",
            "西,にし",
            "南,みなみ",
            "北,きた",
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
        ("森満子", ["満子", "森"]),
        ("森美津子", ["美津子", "森"]),
        ("もりみつこ", ["みつこ", "もり"]),
        ("モリミツコ", ["ミツコ", "モリ"]),
        ("ﾓﾘﾐﾂｺ", ["ﾐﾂｺ", "ﾓﾘ"]),
        ("佐藤太郎", ["太郎", "佐藤"]),
        ("青木健太", ["健太", "青木"]),
        ("木村花子", ["花子", "木村"]),
        ("村上明子", ["明子", "村上"]),
        ("上原明", ["明", "上原"]),
        ("原田翼", ["翼", "原田"]),
        ("田中葵", ["葵", "田中"]),
        ("中山太郎", ["太郎", "中山"]),
        ("山田花子", ["花子", "山田"]),
        ("小野次郎", ["次郎", "小野"]),
        ("大山一郎", ["一郎", "大山"]),
        ("長谷川ひろし", ["ひろし", "長谷川"]),
        ("森ミツコ", ["ミツコ", "森"]),
        ("もり満子", ["満子", "もり"]),
        ("阿部さくら", ["さくら", "阿部"]),
        ("伊藤まり", ["まり", "伊藤"]),
        ("加藤ゆうこ", ["ゆうこ", "加藤"]),
        ("高橋しょう", ["しょう", "高橋"]),
        ("東りん", ["りん", "東"]),
        ("西れい", ["れい", "西"]),
        ("南かな", ["かな", "南"]),
        ("北まこと", ["まこと", "北"]),
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
        first_names=["満子,みつこ"],
        last_names=["森,もり", "森満,もりみつ"],
    )

    assert splitter.namesplit("森満子") == ["満子", "森"]

    candidates = splitter.candidates("森満子")
    assert candidates[0].last == "森"
    assert candidates[0].first == "満子"
    overconsumed = next(c for c in candidates if c.last == "森満" and c.first == "子")
    assert "penalty: one-character unknown first name" in overconsumed.reasons


def test_unknown_string_uses_length_prior_when_split_is_possible() -> None:
    splitter = NameSplitter.from_iterables(first_names=[], last_names=[])
    assert splitter.namesplit("龘麤靐") == ["麤靐", "龘"]


def test_single_character_and_empty_fall_back_to_unsplit() -> None:
    splitter = NameSplitter.from_iterables(first_names=["満子"], last_names=["森"])
    assert splitter.namesplit("森") == ["森", ""]
    assert splitter.namesplit("") == ["", ""]
    assert splitter.namesplit("森", "もり") == [["森", ""], ["もり", ""]]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("森 満子", ["満子", "森"]),
        ("森　満　子", ["満子", "森"]),
        ("  佐藤   太郎  ", ["太郎", "佐藤"]),
    ],
)
def test_fullname_whitespace_uses_first_explicit_space_as_top_priority(
    hard_case_splitter: NameSplitter,
    raw: str,
    expected: list[str],
) -> None:
    assert hard_case_splitter.namesplit(raw) == expected


def test_fullname_yomi_whitespace_guides_kanji_split(hard_case_splitter: NameSplitter) -> None:
    assert hard_case_splitter.namesplit("山田太郎", "やまだ たろう") == [
        ["太郎", "山田"],
        ["たろう", "やまだ"],
    ]


def test_fullname_yomi_space_works_even_without_dictionary() -> None:
    splitter = NameSplitter.from_iterables(first_names=[], last_names=[])
    assert splitter.namesplit("山田太郎", "やまだ たろう") == [
        ["太郎", "山田"],
        ["たろう", "やまだ"],
    ]


def test_yomi_pair_hits_disambiguate_same_surface_in_first_and_last_dicts() -> None:
    splitter = NameSplitter.from_iterables(
        first_names=["東,ひがし"],
        last_names=["東,あずま"],
    )
    result = splitter.namesplit("東東", "あずま ひがし")
    assert result == [["東", "東"], ["ひがし", "あずま"]]

    best = splitter.candidates("東東", "あずま ひがし")[0]
    assert best.last_pair_in_dict is True
    assert best.first_pair_in_dict is True


def test_katakana_is_normalized_for_matching_but_preserved_in_output() -> None:
    splitter = NameSplitter.from_iterables(
        first_names=["太郎,たろう"],
        last_names=["山田,やまだ"],
    )
    assert splitter.namesplit("ヤマダタロウ", "ヤマダ タロウ") == [
        ["タロウ", "ヤマダ"],
        ["タロウ", "ヤマダ"],
    ]


@pytest.mark.parametrize("value", [None, 123, ["森満子"]])
def test_non_string_fullname_raises_type_error(hard_case_splitter: NameSplitter, value: object) -> None:
    with pytest.raises(TypeError, match="name must be str"):
        hard_case_splitter.namesplit(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [123, ["もりみつこ"]])
def test_non_string_yomi_raises_type_error(hard_case_splitter: NameSplitter, value: object) -> None:
    with pytest.raises(TypeError, match="fullname_yomi must be str or None"):
        hard_case_splitter.namesplit("森満子", value)  # type: ignore[arg-type]


def test_dictionary_files_are_actually_used_with_new_csv_format(tmp_path: Path) -> None:
    first_path, last_path = write_dicts(
        tmp_path,
        first=["乙丙,おつへい", "太郎,たろう"],
        last=["甲,こう", "甲乙,こうおつ"],
    )

    splitter = NameSplitter(first_path, last_path)
    assert splitter.namesplit("甲乙丙", "こう おつへい") == [
        ["乙丙", "甲"],
        ["おつへい", "こう"],
    ]


def test_legacy_one_token_dictionary_files_still_work(tmp_path: Path) -> None:
    first_path = tmp_path / "first_name.txt"
    last_path = tmp_path / "last_name.txt"
    first_path.write_text("\n# comment\n満子\nみつこ\n", encoding="utf-8")
    last_path.write_text("\n# comment\n森\n森満\nもり\n", encoding="utf-8")

    assert NameSplitter(first_path, last_path).namesplit("森満子") == ["満子", "森"]


def test_missing_dictionary_file_raises_file_not_found(tmp_path: Path) -> None:
    first_path = tmp_path / "missing_first_name.txt"
    last_path = tmp_path / "last_name.txt"
    last_path.write_text("森\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="dictionary file not found"):
        NameSplitter(first_path, last_path)


def test_convenience_namesplit_accepts_yomi_and_explicit_dictionary_paths(tmp_path: Path) -> None:
    first_path, last_path = write_dicts(
        tmp_path,
        first=["満子,みつこ"],
        last=["森,もり", "森満,もりみつ"],
    )

    assert namesplit("森満子", "もり みつこ", first_name_path=first_path, last_name_path=last_path) == [
        ["満子", "森"],
        ["みつこ", "もり"],
    ]


def test_default_dictionary_paths_are_module_local() -> None:
    assert namesplitter.DEFAULT_FIRST_NAME_PATH == Path(namesplitter.__file__).resolve().parent / "first_name.txt"
    assert namesplitter.DEFAULT_LAST_NAME_PATH == Path(namesplitter.__file__).resolve().parent / "last_name.txt"


def read_csv_map(path: Path) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row[0]: row[1:] for row in csv.reader(f) if row}


def test_extractor_writes_only_first_and_last_name_txt_with_role_specific_readings(tmp_path: Path) -> None:
    xml_path = tmp_path / "JMnedict.xml"
    xml_path.write_text(
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<JMnedict>
  <entry>
    <ent_seq>1</ent_seq>
    <k_ele><keb>武</keb></k_ele>
    <r_ele><reb>タケシ</reb></r_ele>
    <r_ele><reb>タケ</reb></r_ele>
    <trans><name_type>given</name_type></trans>
  </entry>
  <entry>
    <ent_seq>2</ent_seq>
    <k_ele><keb>武</keb></k_ele>
    <r_ele><reb>タケ</reb></r_ele>
    <trans><name_type>surname</name_type></trans>
  </entry>
  <entry>
    <ent_seq>3</ent_seq>
    <k_ele><keb>東</keb></k_ele>
    <r_ele><reb>ヒガシ</reb></r_ele>
    <trans><name_type>given</name_type></trans>
  </entry>
  <entry>
    <ent_seq>4</ent_seq>
    <k_ele><keb>東</keb></k_ele>
    <r_ele><reb>アズマ</reb></r_ele>
    <trans><name_type>surname</name_type></trans>
  </entry>
</JMnedict>
""",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    assert extractor.main([str(xml_path), "--out", str(out_dir)]) == 0
    assert sorted(path.name for path in out_dir.iterdir()) == ["first_name.txt", "last_name.txt"]

    first_map = read_csv_map(out_dir / "first_name.txt")
    last_map = read_csv_map(out_dir / "last_name.txt")

    assert set(first_map["武"]) == {"たけ", "たけし"}
    assert set(last_map["武"]) == {"たけ"}
    assert first_map["東"] == ["ひがし"]
    assert last_map["東"] == ["あずま"]
