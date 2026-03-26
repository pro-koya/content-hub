#!/usr/bin/env python3
"""
content-hub CLI
統合コマンドラインインターフェース。

Usage:
    python cli.py digest:run [--config CONFIG_PATH]
    python cli.py site:build
    python cli.py help
"""

from __future__ import annotations

import sys


def parse_args(argv: list[str]) -> tuple[str, dict[str, str]]:
    if not argv:
        return "help", {}

    command = argv[0]
    options: dict[str, str] = {}

    i = 1
    while i < len(argv):
        token = argv[i]
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                options[k] = v
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                options[key] = argv[i + 1]
                i += 1
            else:
                options[key] = "true"
        i += 1

    return command, options


def cmd_digest_run(options: dict[str, str]) -> None:
    from src.digest.generator import run_digest

    config_path = options.get("config", "config/digest.yml")
    result = run_digest(config_path)
    print(f"\nダイジェスト生成完了: {result['date']}")
    print(f"  記事数: {result['total_articles']}")
    print(f"  カテゴリ: {', '.join(result['categories'])}")


def cmd_xpost_generate(options: dict[str, str]) -> None:
    from src.x_post.generator import generate, save_output

    count = int(options.get("count", "1"))
    dry_run = options.get("dry-run", "false") == "true"
    posts = generate(count=count, dry_run=dry_run)
    if posts:
        save_output(posts)


def cmd_xpost_post(options: dict[str, str]) -> None:
    from src.x_post.poster import post_to_x

    dry_run = options.get("dry-run", "false") == "true"
    post_to_x(dry_run=dry_run)


def cmd_xpost_metrics(_options: dict[str, str]) -> None:
    from src.x_post.metrics import run_fetch_metrics

    run_fetch_metrics()


def cmd_xpost_analyze(_options: dict[str, str]) -> None:
    from src.x_post.experiment import generate_weekly_analysis, save_analysis_report

    report = generate_weekly_analysis()
    path = save_analysis_report(report)
    print(f"分析レポート生成完了: {path}")
    print()
    print(report)


def cmd_xpost_lint(options: dict[str, str]) -> None:
    import json
    from pathlib import Path
    from src.x_post.lint import parse_output_file, lint_batch

    output_dir = Path("output")
    files = options.get("files", "")
    if files:
        paths = [Path(f) for f in files.split(",")]
    else:
        paths = sorted(output_dir.glob("liftly_*.md"), reverse=True)[:1]

    if not paths:
        print("チェック対象のファイルが見つかりません")
        return

    max_length: int | None = None
    config_path = Path("config/x_post.json")
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            max_length = config.get("max_chars")
        except (json.JSONDecodeError, OSError):
            pass

    for path in paths:
        print(f"\n=== {path.name} ===")
        posts = parse_output_file(path)
        if not posts:
            print("  投稿が見つかりません")
            continue

        texts = [p["text"] for p in posts]
        results = lint_batch(texts, max_length=max_length)
        for r in results:
            status = "OK" if r.ok else "NG"
            print(f"  [{status}] 投稿 {r.post_index + 1}: {r.text[:40]}...")
            for err in r.errors:
                print(f"       ERROR: {err}")
            for warn in r.warnings:
                print(f"       WARN:  {warn}")


def cmd_article_generate(options: dict[str, str]) -> None:
    from src.articles.lint import lint_draft
    from src.articles.pipeline import generate_article, save_article

    topic = options.get("topic", "")
    if not topic:
        print("ERROR: --topic を指定してください", file=sys.stderr)
        sys.exit(1)
    category = options.get("category", "")
    draft = generate_article(topic, category)
    if not draft:
        print("記事生成に失敗しました")
        sys.exit(1)

    lint_result = lint_draft(draft)
    if lint_result.errors:
        print("記事生成に失敗しました。品質チェックでエラーが見つかりました。", file=sys.stderr)
        for err in lint_result.errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    for warn in lint_result.warnings:
        print(f"  WARN: {warn}")

    save_article(draft)
    print(f"\n記事ドラフト生成完了: {draft.title}")


def cmd_article_lint(options: dict[str, str]) -> None:
    from pathlib import Path
    from src.articles.lint import lint_draft
    from src.articles.pipeline import _parse_article_output

    articles_dir = Path("docs/articles")
    file_opt = options.get("file", "")
    if file_opt:
        paths = [Path(file_opt)]
    else:
        paths = sorted(articles_dir.glob("*.md"), reverse=True)[:1]

    if not paths:
        print("チェック対象の記事が見つかりません")
        return

    failed = False
    for path in paths:
        text = path.read_text(encoding="utf-8")
        draft = _parse_article_output(text)
        if not draft:
            print(f"[NG] {path.name}: frontmatter の解析に失敗しました")
            failed = True
            continue
        result = lint_draft(draft)
        status = "OK" if result.ok else "NG"
        print(f"[{status}] {path.name}")
        for err in result.errors:
            print(f"  ERROR: {err}")
        for warn in result.warnings:
            print(f"  WARN:  {warn}")
        if not result.ok:
            failed = True

    if failed:
        sys.exit(1)


def cmd_article_list(_options: dict[str, str]) -> None:
    from src.articles.pipeline import list_articles

    articles = list_articles()
    if not articles:
        print("保存済みの記事はありません。")
        return
    print(f"\n記事一覧 ({len(articles)} 件):")
    for a in articles:
        print(f"  [{a['status']}] {a['title']} ({a['category']}) — {a['file']}")


def cmd_site_build(options: dict[str, str]) -> None:
    from src.dashboard.site_builder import build_site

    result = build_site()
    print(f"サイト生成完了: {result['index_path']}")


def cmd_help(_options: dict[str, str]) -> None:
    print("""
content-hub CLI

コマンド一覧:
  digest:run [--config PATH]       ダイジェストを生成
  xpost:generate [--count N]       X投稿を生成（Gemini連携）
               [--dry-run]
  xpost:post [--dry-run]           未投稿の投稿をXに投稿
  xpost:metrics                    投稿メトリクスを取得
  xpost:analyze                     比較軸×メトリクス分析レポート
  article:generate --topic TOPIC   記事ドラフトを生成（Gemini連携）
               [--category CAT]
  article:list                     記事一覧を表示
  article:lint [--file PATH]       記事ドラフトの品質チェック
  xpost:lint [--files PATHS]       投稿の品質チェック
  site:build                       GitHub Pages 用サイトを生成
  help                             このヘルプを表示
""")


COMMANDS = {
    "digest:run": cmd_digest_run,
    "xpost:generate": cmd_xpost_generate,
    "xpost:post": cmd_xpost_post,
    "xpost:metrics": cmd_xpost_metrics,
    "article:generate": cmd_article_generate,
    "article:list": cmd_article_list,
    "article:lint": cmd_article_lint,
    "xpost:analyze": cmd_xpost_analyze,
    "xpost:lint": cmd_xpost_lint,
    "site:build": cmd_site_build,
    "help": cmd_help,
    "--help": cmd_help,
}


def main() -> None:
    command, options = parse_args(sys.argv[1:])
    handler = COMMANDS.get(command)

    if handler is None:
        print(f"不明なコマンドです: {command}")
        cmd_help({})
        sys.exit(1)

    try:
        handler(options)
    except KeyboardInterrupt:
        print("\n中断しました。")
        sys.exit(130)
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
