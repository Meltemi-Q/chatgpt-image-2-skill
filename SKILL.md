---
name: chatgpt-image-2
description: |
  通过 CLIProxyAPI 网关调用 OpenAI gpt-image-2 生图。触发条件：用户说"画图"、
  "生成图片"、"AI 画图" 且希望用 OpenAI 的 gpt-image-2 模型。
---

# gpt-image-2 图片生成

独立的 Python 脚本，任何调用方（Hermes / Claude Code / OpenClaw / 普通 shell / cron / 其他 agent 框架）都能用，只依赖 stdlib。

## 架构

```
脚本 ─HTTP→ CLIProxyAPI 网关 ─OAuth→ chatgpt.com/backend-api/codex/responses
                                      └─ 用网关管理员的 ChatGPT Pro 订阅代为出图
```

脚本是**客户端**，不处理 OAuth，只调网关的 REST。网关侧需要管理员用 ChatGPT Pro 账号完成 Codex OAuth 登录（见下方"自建网关"）。

## 首次使用

```bash
python3 scripts/generate.py doctor      # 先看配置状态 + 连通性
python3 scripts/generate.py setup       # 交互式配置
```

`doctor` 会检测 key 是否配好、URL 是否能连通、后端是否能真实出图，按错误类型给修复指引。

`setup` 会引导写入配置：
- `api_key`：网关管理员分发的 bearer token（形如 `sk-cgw-<随机串>`）
- `api_url`：网关地址，默认 `http://127.0.0.1:8318/v1/images/generations`（假设你自己在本机跑网关）；远程网关改成 `https://your-gateway.example.com/v1/images/generations`

写入 `~/.config/chatgpt-image-2/{api_key,api_url}`（权限 0600）。

也可环境变量覆盖：
```bash
export CHATGPT_IMAGE_API_KEY='sk-cgw-xxxxxxxx'
export CHATGPT_IMAGE_API_URL='https://your-gateway.example.com/v1/images/generations'
```

## 自建网关（需要 ChatGPT Pro 订阅）

1. 在一台有公网的机器上装 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
2. **当前 release 对 gpt-image-2 有 bug**，需打 [PR #2962](https://github.com/router-for-me/CLIProxyAPI/pull/2962) 补丁（自编译 Go binary）
3. OAuth 登录：
   ```bash
   cli-proxy-api --config <你的-config.yaml> -codex-device-login
   ```
   终端打印 device code，浏览器打开 `https://auth.openai.com/codex/device` 输入并登录 ChatGPT Pro 账号
4. config.yaml 里的 `api-keys` 设一个随机 bearer token（下发给客户端）
5. 启动网关，客户端用 `setup` 填配置

## 使用

```bash
python3 scripts/generate.py "金色猫咪在阳光下"              # 模型自选尺寸（默认 1024x1024）
python3 scripts/generate.py "赛博朋克城市" -s landscape      # 便捷预设
python3 scripts/generate.py "水墨山水" -s 1792x1024         # 自定义尺寸
python3 scripts/generate.py "穿和服的狐狸" -b 3              # 并行 3 张挑
```

图存到当前 workspace（优先级：`$HOME/.openclaw/workspace/` > `$HOME/.claude/workspace/` > `$HOME/workspace/` > `$HOME`）。

## 尺寸

**模型不限固定分辨率**，任意 WxH 都行，唯一限制是最小像素门槛（约 768+，太小会被拒 "below minimum pixel budget"）。

便捷预设：

| 简称 | 像素 |
|------|------|
| `square` | 1024×1024 |
| `landscape` | 1536×1024 |
| `portrait` | 1024×1536 |
| `wide` | 1792×1024 |
| `tall` | 1024×1792 |

**省略 `-s` / 传 `-s ""` / `-s auto` / `-s default`** → 让模型自选默认（通常 1024×1024）。

也可直接传原生尺寸：`-s 1280x720`、`-s 2048x2048` 等。

## 响应与耗时

- 响应体是 base64 编码的 PNG（gpt-image-2 不返 URL），脚本自动解码落盘
- 典型耗时 **12-25s**（单张）；受网络链路和 upstream 负载影响
- 默认超时 180s；upstream TLS 偶发 500，直接重试即可

## 子命令速查

| 命令 | 用途 |
|---|---|
| `setup` | 首次配置（交互） |
| `doctor` | 检查配置 + 连通性 |
| `sizes` / `-l` | 列出尺寸预设 |
| `<prompt>` | 直接生成（默认） |

## 依赖

仅 Python 3.8+ stdlib，无 pip 依赖。
