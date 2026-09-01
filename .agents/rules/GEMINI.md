# Kodaira Clinic Instagram Auto-Post Automation Project

このプロジェクトは、小平内科糖尿病クリニック（https://kodaira.clinic/）の新着「お知らせ」および「糖のお話」を自動監視し、Gemini APIを用いてInstagramに自動投稿する高度な自動化システムです。

## 1. プロジェクト概要 (Project Overview)
- **目的**: クリニックHPのコンテンツ更新をトリガーに、医療広告ガイドラインに準拠したInstagram投稿（キャプション・アイキャッチ画像）を自動生成・投稿する。
- **実行基盤**: GitHub Actions (Scheduled Cron)
- **言語・主要ライブラリ**: Python 3.11+ / `google-genai` / `requests` / `beautifulsoup4` / `Pillow`

## 2. 開発・動作ルール (Core Rules & Constraints)

### A. Gemini API 仕様・モデル選定
- **推奨SDK**: `google-genai` (最新公式SDK)
- **メインモデル**: `gemini-3.7-flash` または `gemini-flash-latest`
- **キー管理**: APIキーは環境変数 `GEMINI_API_KEY` より取得し、コードへの直書きは厳禁とする。

### B. 医療広告ガイドライン遵守 (Medical Compliance & Guardrails)
- **ソフトガードレール (Prompt)**:
  1. 断定的な治療効果の保証や、誤解を招く医療表現を禁止。
  2. 文末に免責事項 `※本投稿は情報提供を目的としており、個別の診断・治療は医師にご相談ください。` を自動挿入。
- **ハードガードレール (Code)**:
  - `main.py` の投稿前処理において、キャプション内に上記免責事項が含まれているかをプログラム的にチェックし、未付与の場合は自動強制追加する。

### C. Instagram Graph API 投稿ルール & 画像ホスティング
- **画像規格**: 1080x1350px (アスペクト比 4:5)、JPEG形式 (RGB)。
- **画像ホスティング**: 生成された画像は GitHub Pages / GitHub raw URL (`https://raw.githubusercontent.com/...`) または S3 に公開し、Meta Graph APIからパブリックアクセス可能なHTTPS URLを用意する。
- **認証**: Meta Business Manager System User Token (永続トークン) を環境変数 `META_ACCESS_TOKEN` として保持。
- **投稿フロー & エラー処理**: 
  1. `/media` (コンテナ作成)
  2. `/media?fields=status_code` で5秒間隔・最大10回ポーリング (`FINISHED` で次へ進み、`ERROR` またはタイムアウト時は即時ブレイクしてアラートログを出力)
  3. `/media_publish` (公開)

### D. 状態管理 (State Persistence & GitHub Actions Permissions)
- 二重投稿を防止するため、更新済記事のハッシュ値を `seen_hashes.json` に記録する。
- GitHub Actions 実行完了時に `git commit & push` でリポジトリへ自動書き戻しを行うため、ワークフロー設定で `permissions: contents: write` を必須とする。

## 3. ディレクトリ構造 (Directory Structure)
- `kodaira-clinic-instagram-bot/`
  - `.agents/rules/GEMINI.md` : 本プロジェクトルール定義ファイル
  - `.github/workflows/monitor_and_post.yml` : 定期実行GitHub Actionsワークフロー
  - `main.py` : メイン処理スクリプト（スクレイピング、Gemini、画像生成、Instagram API）
  - `seen_hashes.json` : 既投稿コンテンツのハッシュ履歴
  - `requirements.txt` : Python依存パッケージ定義

## 4. 環境変数 (Environment Variables)
- `GEMINI_API_KEY`: Google AI Studio 発行の Gemini APIキー
- `IG_USER_ID`: Instagram ビジネスアカウントID
- `META_ACCESS_TOKEN`: Meta System User アクセストークン
