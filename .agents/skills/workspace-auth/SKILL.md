---
name: workspace-auth
description: @kodaira.clinic ドメイン限定認証およびGoogle Identity Services実装ルール。
---
# Google Workspace 認証仕様

## ドメイン検証の必須化
* OAuth 2.0 / OIDC 認証時、IDトークンの `hd` (hosted domain) クレームが `kodaira.clinic` であることをバックエンド（API）側で必ず検証する。
* フロントエンド側のドメインチェック（`hd`パラメータ指定）だけに頼らず、必ずサーバーサイドでの二次検証を実装すること。

```typescript
// 実装イメージ（バックエンドでのドメイン検証）
if (payload.hd !== 'kodaira.clinic') {
  throw new UnauthorizedException('kodaira.clinic ドメインのアカウントのみアクセス可能です。');
}
