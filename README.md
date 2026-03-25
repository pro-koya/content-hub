# Content Hub

情報収集 → リサーチ → 記事執筆 → X発信 → フィードバックの一気通貫サイクルを回すための統合プラットフォーム。

## セットアップ

```bash
pip install -r requirements.txt
```

## 使い方

### ダイジェスト生成

```bash
python cli.py digest:run
```

RSS/Atom、Qiita API、note RSS、X API から日次ダイジェストを生成し、`docs/digests/` に出力。

### X投稿管理

```bash
python cli.py xpost:generate          # Gemini で投稿を生成
python cli.py xpost:post               # 未投稿のものをXに投稿
python cli.py xpost:metrics            # メトリクスを取得
python cli.py xpost:analyze            # 比較軸×メトリクス分析
python cli.py xpost:lint               # 品質チェック
```

### 記事執筆

```bash
python cli.py article:generate --topic "AI駆動開発の実践"
python cli.py article:list
```

### ダッシュボード

```bash
python cli.py site:build
```

GitHub Pages 用の統合ダッシュボードを `docs/index.html` に生成。

## GitHub Actions

| ワークフロー | スケジュール | 内容 |
|---|---|---|
| Daily Digest | 毎朝 06:30 JST | ダイジェスト生成 + Pages デプロイ |
| Daily X Post | 毎朝 06:00 JST | 投稿生成 → 投稿 |
| Fetch Metrics | 毎日 15:00 JST | メトリクス取得 |
| Deploy Pages | docs/ 変更時 | GitHub Pages デプロイ |

## GitHub Pages セットアップ

1. リポジトリを GitHub に push
2. Settings > Pages > Source を「GitHub Actions」に設定
3. Secrets を設定:

| Secret | 用途 |
|---|---|
| `GEMINI_API_KEY` | X投稿生成・記事生成 |
| `X_API_KEY` / `X_API_SECRET` | X投稿・メトリクス |
| `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | X投稿・メトリクス |
| `X_BEARER_TOKEN` | Xバズ記事取得（オプション） |
| `LLM_API_KEY` / `LLM_API_URL` / `LLM_MODEL` | LLM要約（オプション） |

## 情報ソース（10カテゴリ）

- AI Research / AI Product & SaaS / Macro & Structure / Japan Signal / Agriculture（RSS）
- AI Driven Development / Career Hybrid（RSS/Google News）
- Qiita Trending（API）
- note Trending（RSS）
- X Buzz（API）

## カスタマイズ

- フィードの追加/削除: `config/feeds.yml`
- ダイジェストルール: `config/digest.yml`
- X投稿設定: `config/x_post.json`
- 投稿ペルソナ: `config/projects/liftly/`

## ロードマップ

- [x] Phase 1: 基盤構築 + RSSダイジェスト
- [x] Phase 2: X投稿の生成・投稿・メトリクス
- [x] Phase 3: 軽量な実験分析（比較軸×メトリクス）
- [x] Phase 4: 情報収集源の拡充（Qiita/note/X）
- [x] Phase 5: 記事執筆パイプライン + 統合ダッシュボード
