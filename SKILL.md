---
name: chatgpt-image-2
description: "Use OpenAI gpt-image-2 via CLIProxyAPI gateway to generate images. 触发: 画图 / 生成图片 / AI 画图 / generate image / gpt-image-2。网关默认 127.0.0.1:8318，key 存 ~/.config/chatgpt-image-2/api_key。脚本: scripts/generate.py（纯 stdlib）。"
---

# gpt-image-2 图片生成

通过 CLIProxyAPI 网关调用 OpenAI `gpt-image-2` 模型。纯 Python stdlib，任意 agent 框架/CLI 都能用。

## Quick Reference

**Script:** `python3 <SKILL_DIR>/scripts/generate.py <PROMPT>`
（`<SKILL_DIR>` = 本 SKILL.md 所在目录；常见路径：`/root/.hermes/skills/chatgpt-image-2` 或 `/root/.openclaw/skills/chatgpt-image-2`）

**常用调用**：
```bash
python3 <SKILL_DIR>/scripts/generate.py "一只金毛"                      # 默认尺寸
python3 <SKILL_DIR>/scripts/generate.py "赛博城市" -s landscape          # 预设
python3 <SKILL_DIR>/scripts/generate.py "超宽海报" -s 1792x1024          # 自定义
python3 <SKILL_DIR>/scripts/generate.py "候选方案" -b 3                   # 并行 3 张挑选
python3 <SKILL_DIR>/scripts/generate.py doctor                          # 故障排查
python3 <SKILL_DIR>/scripts/generate.py setup                           # 交互配置
```

**配置**：`~/.config/chatgpt-image-2/api_key` 和 `api_url`（0600）。
**默认 API URL**：`http://127.0.0.1:8318/v1/images/generations`（本机网关）。
**认证**：Bearer token（形如 `sk-cgw-<随机串>`），由网关管理员分发。

**返回**：PNG 文件路径，图片存到 workspace（优先级 `$HOME/.openclaw/workspace` > `$HOME/.claude/workspace` > `$HOME/workspace` > `$HOME`），并渲染 `![Alt](/绝对路径.png)` markdown。

## 架构

```
脚本 ─HTTP→ CLIProxyAPI 网关 ─OAuth→ chatgpt.com/backend-api/codex/responses
                                      └─ 用挂载的 ChatGPT Pro 订阅出图
```

脚本是客户端，不处理 OAuth；网关侧管理员完成 ChatGPT Pro Codex OAuth 登录即可。

## 首次使用

```bash
python3 <SKILL_DIR>/scripts/generate.py doctor     # 检查配置 + 连通性
python3 <SKILL_DIR>/scripts/generate.py setup      # 交互式配置
```

`doctor` 检测：API key 是否配置 / URL 是否连通 / 后端是否能真实出图。按错误类型给修复指引（401/404/502/超时 等）。

`setup` 引导填：
- `api_key`（从网关管理员处获取）
- `api_url`（默认本机，远程改成 `https://your-gateway.example.com/v1/images/generations`）

写入 `~/.config/chatgpt-image-2/`（0600）。

也可用环境变量：
```bash
export CHATGPT_IMAGE_API_KEY='sk-cgw-xxxxxxxx'
export CHATGPT_IMAGE_API_URL='https://your-gateway.example.com/v1/images/generations'
```

## 自建网关（有 ChatGPT Pro 订阅）

1. 装 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) **v6.9.35 或更新**（含 gpt-image-2 支持，PR #2962 已合并）
2. OAuth 登录：`cli-proxy-api --config <yaml> -codex-device-login`，浏览器输 device code 用 ChatGPT Pro 账号登
3. `api-keys` 设一个随机 bearer token 分发给客户端

## 尺寸

**模型不限固定分辨率**。任意 WxH 都行，最小约 768+（太小会被 upstream 拒）。

| 预设 | 像素 |
|------|------|
| `square` | 1024×1024 |
| `landscape` | 1536×1024 |
| `portrait` | 1024×1536 |
| `wide` | 1792×1024 |
| `tall` | 1024×1792 |

**不传 `-s` / `-s ""` / `-s auto` / `-s default`** → 模型自选（会根据 prompt 推断比例）。

原生尺寸直接传：`-s 1280x720`、`-s 2048x2048`。

## 耗时 / 超时

- 单张 12-25s，1024×1024 约 1.4MB PNG
- **默认不设超时**（None）—— 生成偶尔会超过 60s，设限反而打断有效请求
- 想加安全阀：`-t 300` 或环境变量 `CHATGPT_IMAGE_TIMEOUT=300`（秒，≤0 视作无限）
- 本机 loopback 最快，远程走公网会多几秒
- `doctor` 子命令固定 60s 超时（连通性测试，不通就是不通）

## 子命令

| 命令 | 用途 |
|---|---|
| `setup` | 交互配置 |
| `doctor` | 诊断 |
| `sizes` / `-l` | 列出预设 |
| `<prompt>` | 生成（默认） |

## 依赖

仅 Python 3.8+ stdlib。
