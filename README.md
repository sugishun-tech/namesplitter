# namesplit_tool

辞書ベースの日本語姓名分割ツールです。

- `first_name.txt`: 名前辞書。漢字・ひらがな混在可。1行1件。
- `last_name.txt`: 名字辞書。漢字・ひらがな混在可。1行1件。
- カタカナ、半角カタカナはひらがなに正規化して照合します。
- 出力は入力の表記を保持します。
- Kanji の読み推定は行いません。`森` と `もり` は別エントリとして辞書に入れてください。

```python
from namesplitter import NameSplitter

splitter = NameSplitter("first_name.txt", "last_name.txt")
print(splitter.namesplit("森ミツコ"))  # ["森", "ミツコ"]
```

一括処理では `NameSplitter` を1回だけ作って再利用してください。
