# Content Hub

情報収集 → リサーチ → 記事執筆 → X発信 → フィードバックの一気通貫サイクルを回すための統合プラットフォーム。

## 重点カテゴリ

| カテゴリ | 内容 |
|---|---|
| 農業・兼業農家 | 農業経営、スマート農業、兼業農家の実態、農業テック |
| AI駆動開発 | AIを活用したエンジニアリング手法、ツール、ベストプラクティス |
| キャリア形成 | AI駆動開発×フリーランス、農業メイン＋エンジニアサブ収入 |

## ディレクトリ構成

| ディレクトリ | 役割 |
|---|---|
| config/ | フィードソース・ダイジェストルール・投稿設定 |
| config/projects/liftly/ | X投稿のコンテキスト資料（ペルソナ・禁止語等） |
| src/collectors/ | 情報収集モジュール（RSS, Qiita, note, X） |
| src/digest/ | ダイジェスト生成（config, summarizer, renderer, generator） |
| src/x_post/ | X投稿の生成・投稿・メトリクス・実験分析 |
| src/articles/ | 記事執筆パイプライン |
| src/dashboard/ | GitHub Pages統合ダッシュボード |
| docs/ | GitHub Pages配信ディレクトリ |
| data/ | posted_tweets.json, post_metrics.json |
| output/ | 生成済み投稿ファイル |

## CLIコマンド

```
python cli.py digest:run          # ダイジェスト生成
python cli.py xpost:generate      # X投稿生成（Gemini）
python cli.py xpost:post          # X投稿（Tweepy）
python cli.py xpost:metrics       # メトリクス取得
python cli.py xpost:analyze       # 比較軸×メトリクス分析
python cli.py xpost:lint          # 投稿品質チェック
python cli.py article:generate    # 記事ドラフト生成
python cli.py article:list        # 記事一覧
python cli.py site:build          # ダッシュボード生成
python cli.py help                # ヘルプ
```

## 情報ソース（10カテゴリ）

| ソース | 取得方法 |
|---|---|
| AI Research / Product / Macro / Japan / Agriculture | RSS/Atom |
| AI Driven Dev / Career Hybrid | RSS (Google News) |
| Qiita Trending | Qiita API v2 |
| note Trending | RSS |
| X Buzz | X API v2 |

## 行動原則

- コードを読まずに書かない
- 3ステップ以上のタスクは計画を立ててから実行する
- テストを実行し、動作を確認してから完了とする
- 影響を最小限にする変更を心がける
- yaml.safe_load は常に `or {}` で正規化する
- テンプレートエンジンは Jinja2 に統一する
- 新カテゴリは CATEGORY_LABELS フォールバックで対応済み
