---
name: structured-logging
description: エラーログの構造化（JSON形式）と障害ログトラッキングの設計ルール。
---
# 構造化ログ設計ルール

## 1. ログフォーマット（JSON標準）
すべてのログはテキストプレーンではなく、以下のキーを含む構造化JSONで出力する。

```json
{
  "timestamp": "ISO8601形式",
  "severity": "INFO | WARN | ERROR | FATAL",
  "userId": "ユーザーのハッシュ値（@kodaira.clinic）",
  "action": "操作内容（例: EXAM_RECORD_READ）",
  "traceId": "分散トレーシング用ID",
  "error": {
    "code": "ERR_DRIVE_API_001",
    "message": "エラー概要",
    "stack": "スタックトレース"
  }
}

## 2. エラー処理原則
キャッチされた例外を飲み込まない（catch (e) {} の禁止）。
ユーザー画面には親切なメッセージ（例: 「一時的なエラーが発生しました」）を表示し、管理者向けログには詳細な traceId とスタックトレースを保存する。
