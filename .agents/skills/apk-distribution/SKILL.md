---
name: apk-distribution
description: 内部配布用Android APKの難読化・ビルド・セキュリティ検証ルール。
---
# APKビルド＆セキュリティガイド

## 1. 難読化と最適化
* リリースビルド時は必ず ProGuard / R8 を有効化し、難読化を行う (`minifyEnabled true`)。
* デバッグ用ログ（`Log.d`, `console.log`）はリリースビルド時に自動削除するトリマー（Tree）を設定する。

## 2. 配布セキュリティ
* 署名付きAPK（Release Signed APK）のキーストアファイル（`.jks`）およびパスワードは、リポジトリに絶対コミットしない。 `.gitignore` に追加すること。
* 野良アプリ配布時のインストーラーチェックロジックを設け、偽造APKの実行を防止する。
