# questions.json 仕様書

## 概要

`questions.json` は応用情報フラッシュカードアプリに問題データを一括登録するためのJSONファイルです。

-----

## ファイル形式

- エンコーディング：**UTF-8**（BOMなし）
- 構造：問題オブジェクトの**配列**

-----

## フィールド定義

|フィールド名         |型     |必須|説明                            |
|---------------|------|--|------------------------------|
|`category`     |文字列   |✅ |問題のカテゴリ名                      |
|`question_text`|文字列   |✅ |問題文                           |
|`answer_text`  |文字列   |✅ |正解のテキスト（`choices` の1つと完全一致が必要）|
|`explanation`  |文字列   |✅ |解説文                           |
|`choices`      |文字列の配列|✅ |4択の選択肢（正解を含む4要素）              |

-----

## カテゴリ一覧

応用情報技術者試験の試験範囲に対応した以下のカテゴリを使用してください。

|カテゴリ名         |
|--------------|
|基礎理論          |
|アルゴリズムとプログラミング|
|コンピュータ構成要素    |
|システム構成要素      |
|データベース        |
|ネットワーク        |
|セキュリティ        |
|システム開発技術      |
|プロジェクトマネジメント  |
|経営戦略・企業と法務    |

-----

## サンプル

```json
[
  {
    "category": "ネットワーク",
    "question_text": "DNSの役割は何か？",
    "answer_text": "ドメイン名をIPアドレスに変換する",
    "explanation": "DNS（Domain Name System）はwww.example.comのようなドメイン名をIPアドレスに変換するシステム。名前解決とも呼ばれる。",
    "choices": [
      "ドメイン名をIPアドレスに変換する",
      "IPアドレスをMACアドレスに変換する",
      "パケットの経路を制御する",
      "ファイアウォールのルールを管理する"
    ]
  }
]
```

-----

## 注意事項

- `answer_text` は `choices` の中のいずれか1つと**完全に一致**している必要があります
- `choices` は必ず**4要素**にしてください
- 引用符は必ず**半角ダブルクォート** `"` を使用してください（全角や特殊引用符は不可）
- ファイルの保存時はエンコーディングを **UTF-8（BOMなし）** にしてください

-----

## インポート方法

プロジェクトルートに `questions.json` を置いて、以下のコマンドを実行してください。

```bash
python -c "
import json
from app import create_app, db
from app.models import Question

app = create_app()
with app.app_context():
    with open('questions.json', encoding='utf-8') as f:
        questions = json.load(f)
    for q in questions:
        question = Question(
            category=q['category'],
            question_text=q['question_text'],
            answer_text=q['answer_text'],
            explanation=q['explanation'],
            choices=json.dumps(q['choices'], ensure_ascii=False)
        )
        db.session.add(question)
    db.session.commit()
    print(f'{len(questions)}問登録完了！')
"
```

-----

## AIで問題を生成する場合のプロンプト例

以下のプロンプトをClaude等のAIに渡すことで、仕様に沿った問題を生成できます。

```
応用情報技術者試験の「{カテゴリ名}」分野から、4択問題を{N}問作成してください。
以下のJSON形式で出力してください。引用符は半角ダブルクォートのみ使用してください。

[
  {
    "category": "{カテゴリ名}",
    "question_text": "問題文",
    "answer_text": "正解の選択肢（choicesの1つと完全一致）",
    "explanation": "解説文",
    "choices": ["正解", "不正解1", "不正解2", "不正解3"]
  }
]
```

