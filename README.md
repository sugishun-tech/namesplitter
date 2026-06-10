# namesplitter

`namesplitter` は、日本人名のように名字と名前の間に空白がない文字列を、辞書とルールベースのスコアリングで `[名字, 名前]` に分割する Python モジュールです。

例として、`森満子` は `森満|子` ではなく `森|満子` として扱います。辞書さえまともなら、といういつもの但し書き付きです。現実の人名は容赦なく曖昧なので、完全な正解器ではなく、precision / recall を上げるための実用的な分割器です。

## 特徴

- `first_name.txt` と `last_name.txt` の2つの辞書を使う
- 漢字、ひらがな、カタカナに対応
- カタカナと半角カタカナはひらがなに正規化して照合
- 漢字は読み推定しない
- 入力の表記は保持して返す
- 空白入りの入力は、既に分割済みとみなして尊重
- 分割候補とスコア理由を `candidates()` で確認可能

## ファイル構成

```text
.
├── namesplitter.py
├── first_name.txt
├── last_name.txt
├── README.md
└── test_namesplitter.py
```

辞書ファイルは1行1語です。空行と `#` で始まる行は無視されます。

```text
# first_name.txt
満子
太郎
健太
みつこ
たろう
```

```text
# last_name.txt
森
佐藤
青木
もり
さとう
```

## 使い方

### もっとも簡単な使い方

`namesplitter.py` と同じディレクトリに `first_name.txt` と `last_name.txt` を置きます。

```python
from namesplitter import namesplit

print(namesplit("森満子"))
# ['森', '満子']

print(namesplit("モリミツコ"))
# ['モリ', 'ミツコ']
```

### 辞書パスを明示する

```python
from namesplitter import namesplit

result = namesplit(
    "佐藤太郎",
    first_name_path="./first_name.txt",
    last_name_path="./last_name.txt",
)

print(result)
# ['佐藤', '太郎']
```

### 大量処理する

`namesplit()` は呼び出しごとに辞書を読みます。大量処理では `NameSplitter` を1回だけ作って使い回してください。辞書を毎回読むのは、CPUに写経をさせるようなものです。

```python
from namesplitter import NameSplitter

splitter = NameSplitter(
    first_name_path="./first_name.txt",
    last_name_path="./last_name.txt",
)

for name in ["森満子", "佐藤太郎", "青木健太"]:
    print(splitter.namesplit(name))
```

### 分割候補を見る

```python
from namesplitter import NameSplitter

splitter = NameSplitter("first_name.txt", "last_name.txt")

for cand in splitter.candidates("森満子")[:5]:
    print(cand.last, cand.first, cand.score, cand.reasons)
```

`candidates()` は、すべての分割位置について以下を返します。

- `last`: 名字候補
- `first`: 名前候補
- `index`: 分割位置
- `last_in_dict`: 名字辞書にあるか
- `first_in_dict`: 名前辞書にあるか
- `score`: スコア
- `reasons`: スコア理由

## 分割ロジックの概要

分割候補ごとにスコアを付け、もっとも高い候補を選びます。

主な評価要素は以下です。

1. 名字辞書と名前辞書の両方に一致する候補を強く優先
2. 片方だけ辞書一致する候補も加点
3. 日本人名として自然な長さを弱く加点
4. 漢字・かななどの文字種境界を加点
5. 名字を長く取りすぎて、名前が未知の1文字だけ残る候補を減点

つまり、`森満子` で `森` と `森満` がどちらも名字辞書にある場合でも、`満子` が名前辞書にあれば `森|満子` が勝ちます。

## 正規化仕様

照合時には以下の正規化を行います。

- Unicode NFKC 正規化
- 空白除去
- カタカナをひらがなへ変換
- 半角カタカナも NFKC により通常のカタカナへ寄せてから、ひらがなへ変換

そのため、辞書に `もり` と `みつこ` があれば、入力 `モリミツコ` や `ﾓﾘﾐﾂｺ` にも対応できます。

ただし、漢字の読みは推定しません。辞書に `森` があっても、それだけで `もり` に一致するわけではありません。漢字と読みは別々に辞書へ入れてください。

## 例外

```python
namesplit("")
# ValueError

namesplit(123)
# TypeError
```

## テスト

pytest で実行します。

```bash
python -m pytest -q
```

実辞書を使うテストでは、リポジトリ直下に以下があることを想定します。

```text
first_name.txt
last_name.txt
```

## 注意点

このツールはルールベースです。人名の分割には本質的に曖昧性があります。

例えば `田中山太郎` のような文字列は、辞書次第で `田中|山太郎`、`田中山|太郎`、`田|中山太郎` などが候補になりえます。このため、辞書品質とスコアリングの調整が結果に大きく影響します。

用途が名寄せ、本人確認、法務・金融系の厳密処理なら、候補上位を保存して人間確認に回す設計にしてください。完全自動で断定すると、コンピュータが真顔で戸籍に喧嘩を売ります。
