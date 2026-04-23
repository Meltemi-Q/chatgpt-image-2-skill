---
name: chatgpt-image-2
description: |
  通过 ChatGPT OAuth 授权调用 gpt-image-2 模型生图。
  用户需有 ChatGPT Plus/Pro 订阅（Pro Lite 不含生图权限）。
  触发条件：用户说"画图"、"生成图片"、"AI 画图"且要求用 gpt-image-2。
---

# ChatGPT gpt-image-2 图片生成

通过 ChatGPT OAuth 授权，调用 ChatGPT Responses API（gpt-image-2）生图。

## 重要前提

**需要 ChatGPT Plus/Pro 订阅**（Pro Lite 不含图片生成权限）。

## 登录方式

```bash
codex login --device-auth
codex login status
```

## 使用

```bash
python3 scripts/generate.py "提示词"           # 生图（默认方形）
python3 scripts/generate.py "提示词" -s portrait  # 竖版
python3 scripts/generate.py "提示词" -s landscape # 横版
python3 scripts/generate.py "提示词" -b 3         # 批量生成 3 张
python3 scripts/generate.py status               # 查看登录状态
```

## 尺寸预设

| 简称 | 尺寸 | 用途 |
|------|------|------|
| square（默认） | 1024x1024 | 默认，通用 |
| landscape | 1536x1024 | 横版 |
| portrait | 1024x1536 | 竖版 |

## API 说明

- **使用端点**: `POST https://api.openai.com/v1/responses`（不是 /images/generations）
- **模型**: `gpt-image-2`
- **认证**: Bearer token（从 Codex auth.json 读取）
- **返回**: 图片 URL（需从 URL 下载图片）

## OAuth Token 来源

- Codex CLI OAuth token: `~/.codex/auth.json` → `tokens.access_token`
- Token 是 ChatGPT 消费者 OAuth（`auth_mode: chatgpt`）
- 登录: `codex login --device-auth`（auth0.openai.com 的 OAuth Device Flow，Codex CLI 已白名单）

## 常见问题

**401 Insufficient permissions / Missing scope: api.model.images.request**
→ 你的 ChatGPT 账号没有生图权限。需要 Plus/Pro 订阅，Pro Lite 不够。

**token 过期**
→ 重新运行 `codex login --device-auth`

**403 Forbidden / Cloudflare 拦截**
→ 直接 OAuth 请求被 Cloudflare 拦截，必须通过 Codex CLI 登录。
