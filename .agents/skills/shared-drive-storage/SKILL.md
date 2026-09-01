---
name: shared-drive-storage
description: Google Drive APIを用いた共有ドライブ連携およびサービスアカウントの運用ルール。
---
# 共有ドライブ操作ルール

## 1. 権限設定（SupportsAllDrives）
* Drive APIを利用する際は、必ず `supportsAllDrives=true` および `includeItemsFromAllDrives=true` オプションを有効化する。
* 院長の個人のマイドライブではなく、必ず指定された「クリニック共有ドライブID」を使用する。

## 2. ファイルアクセスのスコープ
* 要求するAPIスコープは可能な限り厳格化する（例: `https://www.googleapis.com/auth/drive.file`）。
