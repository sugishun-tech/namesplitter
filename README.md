# Japanese Name Splitter

日本人名の `姓 / 名` をルールベースで分割する小さな Python ツールです。辞書ファイルとして `first_name.txt` と `last_name.txt` を使います。

JMnedict から辞書を抽出する `extractor.py` と、実際に分割する `namesplitter.py` を含みます。

## 特徴

- 入力は漢字、ひらがな、カタカナ、半角カタカナに対応します。
- カタカナと半角カタカナは、照合時だけひらがなへ正規化します。
- 出力は入力された表記をできるだけ保持します。
- `fullname` だけでなく、`fullname_yomi` 付きの分割にも対応します。
- `fullname` 側または `fullname_yomi` 側に半角スペースまたは全角スペースがある場合、その最初のスペース区切りを最優先します。
- 辞書にない名前でも、長さ、文字種境界、読みとの整合性を使って候補を採点します。
- どうしても分割できない場合は、`[fullname, ""]`、または `[[fullname, ""], [fullname_yomi, ""]]` を返します。

## ファイル構成

```text
extractor.py          # JMnedict.xml(.gz) から first_name.txt / last_name.txt を生成
namesplitter.py      # 名前分割本体
test_namesplitter.py # pytest
first_name.txt       # 名辞書。extractor.py で生成する想定
last_name.txt        # 姓辞書。extractor.py で生成する想定
```

`first_name.txt` と `last_name.txt` は `namesplitter.py` と同じディレクトリに置くのがデフォルトです。別パスを使う場合は、明示的に指定できます。

## 辞書形式

辞書は CSV 形式です。1行に1エントリを書きます。

```text
表記,読み1,読み2,読み3,...
```

例:

```text
武,たけし,たけ
駿,しゅん,はやお
山田,やまだ
森,もり
```

読みの数は任意です。読みが不明な場合は表記だけでも動きます。

```text
太郎
森
```

この旧形式、つまり1行1単語の辞書も読み込めます。ただし、`fullname_yomi` との整合性を使った採点を強く効かせたい場合は、読み付き形式を使ってください。辞書に読みがないのに読み照合を要求するのは、地図なしで宝探しを始める人類の伝統芸です。

## extractor.py の使い方

`extractor.py` は JMnedict から `first_name.txt` と `last_name.txt` だけを生成します。

### JMnedict を自動ダウンロードする場合

```bash
python extractor.py --download --out names_out
```

出力:

```text
names_out/first_name.txt
names_out/last_name.txt
```

### 手元の JMnedict.xml.gz を使う場合

```bash
python extractor.py JMnedict.xml.gz --out names_out
```

### 手元の JMnedict.xml を使う場合

```bash
python extractor.py JMnedict.xml --out names_out
```

### 出力仕様

`extractor.py` は以下の2ファイルだけを生成します。

```text
first_name.txt
last_name.txt
```

同じ表記が「姓」と「名」の両方に出る場合は、両方のファイルに出力します。ただし、読みは役割ごとに分離します。

たとえば、ある表記が名字としては `あずま`、名前としては `ひがし` で出る場合、概念的には次のようになります。

```text
# last_name.txt
東,あずま

# first_name.txt
東,ひがし
```

姓の読みと名の読みを混ぜません。混ぜると分割器が急に占い師になります。

## namesplitter.py の使い方

### もっとも簡単な使い方

```python
from namesplitter import namesplit

print(namesplit("山田太郎"))
# ['太郎', '山田']
```

戻り値は `[first_name, last_name]` です。

注意: 日本語の自然な順序は `姓 + 名` ですが、この関数の戻り値は指定仕様に合わせて `[名, 姓]` です。つまり `山田太郎` は `['太郎', '山田']` になります。

### 読みも渡す場合

```python
from namesplitter import namesplit

print(namesplit("山田太郎", "やまだたろう"))
# [['太郎', '山田'], ['たろう', 'やまだ']]
```

戻り値は次の形式です。

```python
[[first_name, last_name], [first_name_yomi, last_name_yomi]]
```

### fullname にスペースがある場合

```python
print(namesplit("山田 太郎"))
# ['太郎', '山田']

print(namesplit("山田　太郎"))
# ['太郎', '山田']
```

半角スペース、全角スペースのどちらにも対応します。最初のスペースが区切りとして使われます。

### fullname_yomi にスペースがある場合

```python
print(namesplit("山田太郎", "やまだ たろう"))
# [['太郎', '山田'], ['たろう', 'やまだ']]
```

`fullname` にスペースがなくても、`fullname_yomi` にスペースがあれば、その読み区切りを強いヒントとして採点します。

### カタカナ入力

```python
print(namesplit("ヤマダタロウ", "ヤマダ タロウ"))
# [['タロウ', 'ヤマダ'], ['タロウ', 'ヤマダ']]
```

カタカナは照合時にひらがなへ正規化されます。出力は入力表記を保持します。

### 辞書パスを指定する場合

```python
from namesplitter import namesplit

result = namesplit(
    "森満子",
    first_name_path="/path/to/first_name.txt",
    last_name_path="/path/to/last_name.txt",
)

print(result)
# ['満子', '森']
```

大量に処理する場合は、毎回辞書を読む `namesplit()` ではなく、`NameSplitter` を使ってください。

```python
from namesplitter import NameSplitter

splitter = NameSplitter(
    first_name_path="/path/to/first_name.txt",
    last_name_path="/path/to/last_name.txt",
)

for name in ["山田太郎", "森満子"]:
    print(splitter.namesplit(name))
```

## 候補一覧を見る

`candidates()` を使うと、内部の候補とスコアを確認できます。

```python
from namesplitter import NameSplitter

splitter = NameSplitter("first_name.txt", "last_name.txt")

for c in splitter.candidates("森満子", "もりみつこ")[:5]:
    print(c.score, c.last, c.first, c.last_yomi, c.first_yomi, c.reasons)
```

`SplitCandidate` の主なフィールド:

```text
last                 # 姓候補
first                # 名候補
last_yomi            # 姓読み候補
first_yomi           # 名読み候補
score                # 採点結果
reasons              # 採点理由
last_in_dict         # 姓候補が姓辞書にあるか
first_in_dict        # 名候補が名辞書にあるか
last_yomi_in_dict    # 姓読み候補が姓辞書の読みにあるか
first_yomi_in_dict   # 名読み候補が名辞書の読みにあるか
last_pair_in_dict    # 姓表記と姓読みのペアが辞書にあるか
first_pair_in_dict   # 名表記と名読みのペアが辞書にあるか
```

デバッグ時は `reasons` を見るのが一番早いです。スコアリングをブラックボックスにすると、だいたい未来の自分が泣きます。

## 採点ルールの概要

内部では日本語順、つまり `last + first` として候補を作ります。そのあと、公開 API の戻り値だけ `[first, last]` に並べ替えます。

採点では主に次を見ます。

- `fullname` の明示スペース区切り
- `fullname_yomi` の明示スペース区切り
- 姓表記と名表記の辞書一致
- 姓読みと名読みの辞書一致
- 表記と読みのペア一致
- 姓・名として自然な長さ
- 漢字とかなの文字種境界
- 1文字の未知名・未知姓へのペナルティ

スペース区切りは最優先です。辞書や長さ推定よりも強く扱います。

## 失敗時の戻り値

### fullname だけの場合

```python
namesplit("龘")
# ['龘', '']
```

### fullname と fullname_yomi の両方がある場合

```python
namesplit("龘", "とう")
# [['龘', ''], ['とう', '']]
```

## テスト

```bash
python -m pytest test_namesplitter.py
```

このリポジトリ単体で実行する場合は、`namesplitter.py` と `test_namesplitter.py` を同じディレクトリに置いてください。

## 注意点

このツールはルールベースです。統計モデルや機械学習モデルではありません。

辞書にない名前でもある程度は切りますが、未知語が多い場合や、表記と読みが特殊な場合は誤分割します。日本人名は「東」が姓にも名にもなり、読みも複数あり、さらに表記ゆれまであります。これを完全に処理できると思うのは、人間の楽観性がまた一つ罪を重ねた瞬間です。

精度を上げるには、次の順で効きます。

1. `first_name.txt` / `last_name.txt` に読み付き辞書を入れる
2. `fullname_yomi` を渡す
3. 可能なら `fullname` または `fullname_yomi` にスペース区切りを入れる
4. `candidates()` の `reasons` を見てスコアを調整する

## ライセンス

この README ではライセンスを定義していません。配布する場合は、プロジェクト側で `LICENSE` を追加してください。

