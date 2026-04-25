#!/usr/bin/env python3
"""
gpt-image-2 图片生成脚本。
通过一个 CLIProxyAPI 网关调用 OpenAI 的 gpt-image-2 模型。网关端用 ChatGPT
Pro 订阅的 Codex OAuth 代为访问 ChatGPT 后端；本脚本只需网关 URL 和 bearer
token（不做 OAuth）。

子命令：
  doctor    检查配置 + 连通性，给出排错指引
  setup     交互式首次配置（api_key + api_url）
  sizes     列出尺寸预设
  <prompt>  直接生成（默认子命令）
"""

import argparse
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_API_URL = "http://127.0.0.1:8318/v1/images/generations"
MODEL = "gpt-image-2"
CONFIG_DIR = Path.home() / ".config" / "chatgpt-image-2"

# 便捷预设。也可直接传原生 WxH 如 "1792x1024"，或不传 size 让模型自选。
SIZE_PRESETS = {
    "square":    "1024x1024",
    "landscape": "1536x1024",
    "portrait":  "1024x1536",
    "wide":      "1792x1024",
    "tall":      "1024x1792",
}


def load_config(name, env_key, default=None):
    val = os.environ.get(env_key)
    if val:
        return val.strip()
    path = CONFIG_DIR / name
    if path.exists():
        return path.read_text().strip()
    return default


def get_api_key():
    return load_config("api_key", "CHATGPT_IMAGE_API_KEY")


def get_api_url():
    return load_config("api_url", "CHATGPT_IMAGE_API_URL", DEFAULT_API_URL)


def get_workspace_dir():
    for d in [
        Path.home() / ".openclaw" / "workspace",
        Path.home() / ".claude" / "workspace",
        Path.home() / "workspace",
    ]:
        if d.is_dir():
            return str(d)
    return str(Path.home())


def make_filename(prompt, index=None):
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    words = "".join(c if c.isalnum() or c == " " else " " for c in prompt)
    words = "-".join(words.split()[:4]).lower()[:30] or "image"
    suffix = f"-{index}" if index is not None else ""
    return f"{ts}-{words}{suffix}.png"


def resolve_size(size_str):
    if not size_str:
        return None  # 不传 size，让模型默认
    lower = size_str.lower().strip()
    if lower in ("auto", "default", ""):
        return None
    return SIZE_PRESETS.get(lower, size_str)


def call_api(api_url, api_key, prompt, size_px, timeout=None):
    """timeout=None → 无限等待（生成默认 10-60s，公网链路/upstream 抖动可能更久）"""
    payload = {"model": MODEL, "prompt": prompt}
    if size_px:
        payload["size"] = size_px
    req = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_timeout(cli_value):
    """优先级：CLI --timeout > env CHATGPT_IMAGE_TIMEOUT > None（无限等）。
    任何 ≤0 的值也视为无限。"""
    if cli_value is not None:
        return None if cli_value <= 0 else cli_value
    env = os.environ.get("CHATGPT_IMAGE_TIMEOUT")
    if env:
        try:
            n = int(env)
            return None if n <= 0 else n
        except ValueError:
            pass
    return None


def extract_png(response):
    data = response.get("data") or []
    if not data:
        return None, "响应里没有 data 字段"
    item = data[0]
    if isinstance(item, dict):
        b64 = item.get("b64_json")
        if b64:
            try:
                return base64.b64decode(b64), None
            except Exception as e:
                return None, f"b64 解码失败: {e}"
        url = item.get("url")
        if url:
            try:
                with urlopen(Request(url), timeout=60) as resp:
                    return resp.read(), None
            except Exception as e:
                return None, f"下载 URL 失败: {e}"
    return None, f"响应里没找到 b64_json 或 url: {json.dumps(response, ensure_ascii=False)[:300]}"


# ─────────────── 配置引导 ───────────────


def setup_instructions():
    return (
        "\n# 配置引导\n\n"
        "本 skill 依赖一个 CLIProxyAPI 网关转发请求到 ChatGPT 后端。\n"
        "你可以：\n\n"
        "**A. 使用现有网关**（有人共享了 key）\n"
        "   问对方要 API key 和网关 URL，跑 `python3 generate.py setup` 填进去即可。\n\n"
        "**B. 自建网关**（自己有 ChatGPT Pro 订阅）\n"
        "   跑 `python3 generate.py install-guide` 看针对 LLM 的逐步装机引导（macOS / Linux 通用）。\n"
        "   或者读 https://github.com/router-for-me/CLIProxyAPI README 自己装（v6.9.35+ 含 gpt-image-2）。\n\n"
        f"配置文件会写到 `{CONFIG_DIR}/`（权限 0600），或用环境变量覆盖：\n"
        "   CHATGPT_IMAGE_API_KEY / CHATGPT_IMAGE_API_URL\n"
    )


def cmd_install_guide():
    """LLM 友好的逐步装机引导。预期由 agent 读完后帮用户执行各步。"""
    print("""# CLIProxyAPI 装机引导（写给 LLM 助手 / 高级用户）

前提：用户有 **ChatGPT Pro 订阅**（$100/月或 $200/月皆可，但需要 OAuth 能登录的真账号）。
没有 Pro 不要继续 —— 装好也不能画图。

## Step 1: 选 release 包

参考 https://github.com/router-for-me/CLIProxyAPI/releases/latest

- macOS arm64 (Apple Silicon)：`CLIProxyAPI_<ver>_darwin_arm64.tar.gz`
- macOS amd64 (Intel)：`CLIProxyAPI_<ver>_darwin_amd64.tar.gz`
- Linux amd64：`CLIProxyAPI_<ver>_linux_amd64.tar.gz`
- Linux arm64：`CLIProxyAPI_<ver>_linux_arm64.tar.gz`
- Windows amd64：`CLIProxyAPI_<ver>_windows_amd64.zip`
- Windows arm64：`CLIProxyAPI_<ver>_windows_arm64.zip`

**版本要求**：≥ v6.9.35（含 gpt-image-2 支持）。

## Step 2: 解压 + 放好 binary

```bash
mkdir -p ~/cli-proxy-api && cd ~/cli-proxy-api
curl -sLO https://github.com/router-for-me/CLIProxyAPI/releases/download/<ver>/<release-tarball>
tar -xzf <release-tarball>
chmod +x cli-proxy-api
./cli-proxy-api -v   # 验证：CLIProxyAPI Version: 6.9.36, ...
```

## Step 3: 写 config.yaml

随机生成一个 api-key（用户后面要填给 skill 的 setup）：

```yaml
host: "127.0.0.1"
port: 8318
auth-dir: "~/.cli-proxy-api-codex"
debug: false
api-keys:
  - "sk-cgw-<32-byte-hex-random>"   # 用 `openssl rand -hex 24` 生成
oauth-model-alias:
  codex:
    - { name: "gpt-5.4", alias: "cgw-gpt-5.4", fork: true }
    - { name: "gpt-5.4-mini", alias: "cgw-gpt-5.4-mini", fork: true }
```

存到 `~/cli-proxy-api/config.yaml`。

## Step 4: ChatGPT Pro OAuth 登录

```bash
./cli-proxy-api --config ~/cli-proxy-api/config.yaml -codex-device-login
```

会打印：
```
Codex device URL: https://auth.openai.com/codex/device
Codex device code: XXXX-XXXX
```

把 URL + code 显示给用户，让他**浏览器打开 URL → 输入 code → 用 ChatGPT Pro 账号登录授权**。

完成后 binary 会自动把 token 写到 `~/.cli-proxy-api-codex/codex-<email>-<plan>.json`，**进程会退出**。

## Step 5: 后台常驻

**Linux（systemd user 单元，免 root）**：

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/cliproxyapi-codex.service <<'EOF'
[Unit]
Description=CLIProxyAPI Codex Gateway
After=network.target

[Service]
Type=simple
ExecStart=%h/cli-proxy-api/cli-proxy-api --config %h/cli-proxy-api/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now cliproxyapi-codex
loginctl enable-linger $USER   # 关 ssh 后服务也活着
```

**macOS（launchd）**：

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.cliproxyapi.codex.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cliproxyapi.codex</string>
  <key>ProgramArguments</key>
  <array>
    <string>$HOME/cli-proxy-api/cli-proxy-api</string>
    <string>--config</string>
    <string>$HOME/cli-proxy-api/config.yaml</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.cliproxyapi.codex.plist
```

**Windows（Task Scheduler 或直接前台）**：

```powershell
# 推荐：Task Scheduler（管理员 PowerShell）
$action = New-ScheduledTaskAction -Execute "$HOME\cli-proxy-api\cli-proxy-api.exe" `
  -Argument "--config $HOME\cli-proxy-api\config.yaml"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "CLIProxyAPI-Codex" -Action $action -Trigger $trigger `
  -Description "CLIProxyAPI gateway for gpt-image-2"
Start-ScheduledTask -TaskName "CLIProxyAPI-Codex"

# 或者 NSSM（如果装了）：
# nssm install CLIProxyAPI-Codex %USERPROFILE%\cli-proxy-api\cli-proxy-api.exe --config ...

# 偷懒前台跑：
cd $HOME\cli-proxy-api
.\cli-proxy-api.exe --config .\config.yaml
```

**最简单路线**（任何系统，无后台需求，前台跑）：

```bash
cd ~/cli-proxy-api && ./cli-proxy-api --config config.yaml   # macOS/Linux
# Windows: cd $HOME\cli-proxy-api && .\cli-proxy-api.exe --config .\config.yaml
```

## Step 6: 验证

```bash
curl -s 127.0.0.1:8318/healthz   # 应返 {"status":"ok"}
```

## Step 7: 配置 skill 指向本地网关

```bash
python3 <SKILL_DIR>/scripts/generate.py setup
# api_key  → Step 3 生成的那串 sk-cgw-...
# api_url  → http://127.0.0.1:8318/v1/images/generations
python3 <SKILL_DIR>/scripts/generate.py doctor
# 看到 4 级全绿就 OK
```

完工。
""")





def cmd_setup():
    print(setup_instructions())

    current_key = get_api_key()
    current_url = get_api_url()
    print("## 当前状态")
    print(f"- api_key: {'已设置 (' + current_key[:12] + '...)' if current_key else '未设置'}")
    print(f"- api_url: {current_url}")
    print()

    if not sys.stdin.isatty():
        print("注意：非交互模式下自动退出。请手动在 TTY 里跑 setup，或直接写配置文件/env。")
        sys.exit(1)

    new_key = input(f"API key [{'回车保留' if current_key else '必填'}]: ").strip()
    new_url = input(f"API URL [{current_url}]: ").strip()

    if not new_key and not current_key:
        print("api_key 必填，退出。")
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if new_key:
        kp = CONFIG_DIR / "api_key"
        kp.write_text(new_key + "\n")
        os.chmod(kp, 0o600)
        print(f"写入 {kp}")
    if new_url:
        up = CONFIG_DIR / "api_url"
        up.write_text(new_url + "\n")
        os.chmod(up, 0o600)
        print(f"写入 {up}")

    print("\n配置完成。跑 `python3 generate.py doctor` 验证。")


def _api_base(api_url):
    """从 `.../v1/images/generations` 抠出 `scheme://host[:port]`"""
    from urllib.parse import urlparse
    p = urlparse(api_url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


def _check_healthz(base, timeout=10):
    """返回 (ok, detail)。detail 含 status code + body 或错误原因。"""
    try:
        with urlopen(Request(f"{base}/healthz"), timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:200]
            return resp.status == 200, f"{resp.status} {body.strip()}"
    except HTTPError as e:
        return False, f"HTTP {e.code}"
    except URLError as e:
        return False, f"{e.reason}"
    except Exception as e:
        return False, str(e)


def _check_models(base, api_key, timeout=10):
    """返回 (ok, models_list_or_error)."""
    try:
        req = Request(f"{base}/v1/models",
                      headers={"Authorization": f"Bearer {api_key}"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") for m in data.get("data", []) if m.get("id")]
            return True, models
    except HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except URLError as e:
        return False, f"{e.reason}"
    except Exception as e:
        return False, str(e)


def cmd_doctor():
    print("## 网关诊断（分级检查）\n")

    api_key = get_api_key()
    api_url = get_api_url()

    # Stage 0: 配置在不在
    print("### 0. 配置")
    print(f"- API key: {'✅ 已配置 (' + api_key[:12] + '...)' if api_key else '❌ 未找到'}")
    if api_key and len(api_key) < 20:
        print(f"   ⚠️  key 只有 {len(api_key)} 字符，怀疑被截断")
    print(f"- API URL: {api_url}")
    if not api_key:
        print("\n→ 跑 `python3 generate.py setup` 配置\n")
        print(setup_instructions())
        sys.exit(2)

    base = _api_base(api_url)
    if not base:
        print(f"\n❌ URL 格式不对，无法解析出 host：{api_url}")
        sys.exit(3)

    # Stage 1: 网关活着没
    print("\n### 1. 网关连通性（GET /healthz）")
    ok, detail = _check_healthz(base)
    if ok:
        print(f"✅ {base}/healthz → {detail}")
    else:
        print(f"❌ {base}/healthz → {detail}")
        print("   → 网关没开 / URL 写错 / 网络不通。先修这个。")
        sys.exit(3)

    # Stage 2: 鉴权 + 模型列表（含 gpt-image-2？）
    print("\n### 2. 模型列表 + 鉴权（GET /v1/models）")
    ok, result = _check_models(base, api_key)
    if not ok:
        print(f"❌ {result}")
        if "401" in result:
            print("   → api_key 不对。跑 `setup` 重新配置。")
        elif "403" in result:
            print("   → api_key 格式对但没权限。问网关管理员确认这个 key 启用了。")
        else:
            print("   → 鉴权或其他错误。检查网关 config.yaml 的 api-keys。")
        sys.exit(3)

    models = result
    has_model = MODEL in models
    print(f"✅ 拿到 {len(models)} 个模型")
    print(f"   {'✅' if has_model else '❌'} {MODEL} {'在列' if has_model else '不在列'}")
    if not has_model:
        print(f"\n   可用模型：{', '.join(models[:10])}{'...' if len(models) > 10 else ''}")
        print(f"   → 网关版本可能过旧，不支持 {MODEL}。建议 CLIProxyAPI ≥ v6.9.35。")
        print("   → 或者 config.yaml 的 oauth-model-alias 没开 gpt-image-2 路由。")
        sys.exit(3)

    # Stage 3: 端到端生成（软检查，120s 上限；失败不 exit 只 warn）
    print("\n### 3. 端到端生成（POST /v1/images/generations，120s 上限）")
    print(f"   payload: {{\"model\":\"{MODEL}\",\"prompt\":\"a single red dot on white\"}}")
    try:
        t0 = time.time()
        resp = call_api(api_url, api_key, "a single red dot on white", None, timeout=120)
        elapsed = time.time() - t0
        png, err = extract_png(resp)
        if err:
            print(f"⚠️  调用成功但无法提取图：{err}")
            return
        print(f"✅ 生成成功（{len(png)/1024:.0f}KB, {elapsed:.1f}s）—— 全链路可用")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        print(f"⚠️  HTTP {e.code}: {body}")
        if e.code == 502 and "stream disconnected" in body:
            print("   → 网关 + 模型都 OK，但 upstream 画图失败。可能原因：")
            print("     · CLIProxyAPI 版本 < v6.9.35（gpt-image-2 注入逻辑缺失）")
            print("     · OAuth token 过期 / 账号订阅问题")
        elif e.code == 400:
            print("   → 参数被 upstream 拒绝（prompt 过滤、size 越界等）")
        print("\n注：前三级都过，核心配置没问题。真实生成（默认无限等）可能仍成功。")
    except URLError as e:
        print(f"⚠️  {e.reason}")
        print("注：前三级都过，链路偶发慢不代表坏。")
    except Exception as e:
        # TLS EOF / socket timeout / ... —— 公网链路偶发抖动，不判死
        print(f"⚠️  {e}")
        print("注：前三级都过，upstream 可能慢；真实生成用默认无限等，通常仍会成功。")


# ─────────────── 主生成流程 ───────────────


def generate_image(prompt, size=None, batch=1, timeout=None):
    api_key = get_api_key()
    if not api_key:
        print("## 缺少 API key — 首次使用需要先配置 CLIProxyAPI 网关\n")
        print("**给 LLM agent**：用户没装/没配，按下面顺序帮他做：")
        print("1. `python3 <SKILL_DIR>/scripts/generate.py install-guide` —— 看完整装机引导")
        print("2. 跟着引导的 7 步带用户装 CPA + 完成 ChatGPT Pro OAuth")
        print("3. `python3 <SKILL_DIR>/scripts/generate.py setup` —— 把 key/url 填进配置")
        print("4. `python3 <SKILL_DIR>/scripts/generate.py doctor` —— 4 级验证")
        print("5. 重新跑用户的画图需求")
        print("\n**用户直接可用的命令**：")
        print("  python3 generate.py setup           # 已有 key 跳来填")
        print("  python3 generate.py install-guide   # 还没装网关")
        print("  python3 generate.py doctor          # 看当前状态")
        print(setup_instructions())
        sys.exit(2)

    api_url = get_api_url()
    size_px = resolve_size(size)
    workspace = get_workspace_dir()

    print(f"## 图片生成中...")
    print(f"- **模型**: {MODEL}")
    print(f"- **提示词**: {prompt}")
    print(f"- **尺寸**: {size_px or '模型自选'}")
    print(f"- **超时**: {'不限' if timeout is None else f'{timeout}s'}")
    if batch > 1:
        print(f"- **数量**: {batch} 张")
    print()

    def gen_one(idx=None):
        t0 = time.time()
        save_path = os.path.join(workspace, make_filename(prompt, idx))

        try:
            response = call_api(api_url, api_key, prompt, size_px, timeout=timeout)
        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return (None, f"HTTP {e.code}: {err_body[:400]}", 0)
        except URLError as e:
            return (None, f"网络错误: {e.reason}", 0)
        except Exception as e:
            return (None, f"请求失败: {e}", 0)

        png, err = extract_png(response)
        if err:
            return (None, err, 0)

        try:
            with open(save_path, "wb") as f:
                f.write(png)
        except IOError as e:
            return (None, f"写入文件失败: {e}", 0)

        elapsed = int(time.time() - t0)
        return (os.path.abspath(save_path), len(png) / 1024, elapsed)

    if batch == 1:
        path, size_or_err, elapsed = gen_one()
        if path is None:
            print(f"## 生成失败\n{size_or_err}\n")
            print("如需诊断：`python3 generate.py doctor`")
            sys.exit(1)
        print(f"## 图片已生成 ({size_or_err:.0f}KB, ~{elapsed}s)\n")
        print(f"![AI Generated Image]({path})\n")
        print(f"**文件**: `{path}`")
        return

    results = []
    with ThreadPoolExecutor(max_workers=min(batch, 4)) as pool:
        futures = {pool.submit(gen_one, i + 1): i + 1 for i in range(batch)}
        for future in as_completed(futures):
            idx = futures[future]
            path, info, elapsed = future.result()
            results.append((idx, path, info, elapsed))

    results.sort(key=lambda r: r[0])
    ok = [r for r in results if r[1] is not None]
    fail = [r for r in results if r[1] is None]

    if not ok:
        print("## 全部生成失败")
        for idx, _, err, _ in fail:
            print(f"- 第 {idx} 张: {err}")
        print("\n如需诊断：`python3 generate.py doctor`")
        sys.exit(1)

    print(f"## {len(ok)} 张图片已生成，请挑选\n")
    for idx, path, kb, elapsed in ok:
        print(f"### 第 {idx} 张 ({kb:.0f}KB, ~{elapsed}s)\n")
        print(f"![第{idx}张]({path})\n")

    if fail:
        print(f"\n**{len(fail)} 张失败**:")
        for idx, _, err, _ in fail:
            print(f"- 第 {idx} 张: {err}")

    print(f"\n---\n文件保存在: `{workspace}/`")
    print("告诉我你选哪张。")


def cmd_sizes():
    print("## 尺寸预设（便捷名，实际是任意 WxH）\n")
    print("| 简称 | 像素 | 说明 |")
    print("|------|------|------|")
    for name, px in SIZE_PRESETS.items():
        print(f"| `{name}` | {px} | — |")
    print()
    print("**也支持**：")
    print("- 原生尺寸字符串 `-s 768x1024` 等（最低 ~768+，太小会被拒）")
    print("- 不传 `-s` 参数 → 模型自选默认尺寸（通常 1024×1024）")
    print("- 非标准比例如 `-s 1792x1024` 可用")


def main():
    # 先识别子命令：setup / doctor / sizes
    if len(sys.argv) >= 2:
        sub = sys.argv[1].lower()
        if sub in ("setup", "init", "config"):
            cmd_setup()
            return
        if sub in ("doctor", "check", "diag"):
            cmd_doctor()
            return
        if sub in ("sizes", "list-sizes", "--list-sizes", "-l"):
            cmd_sizes()
            return
        if sub in ("install-guide", "install", "guide", "bootstrap"):
            cmd_install_guide()
            return

    parser = argparse.ArgumentParser(
        description="gpt-image-2 image generation via CLIProxyAPI gateway",
        epilog=(
            "Subcommands:\n"
            "  setup   interactive config\n"
            "  doctor  check gateway connectivity\n"
            "  sizes   list size presets\n"
            "\nFirst run? try: python3 generate.py doctor"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="?", help="Image generation prompt")
    parser.add_argument("--size", "-s", default=None,
                        help="preset (square/landscape/portrait/wide/tall), raw WxH (e.g. 1792x1024), or omit for model default")
    parser.add_argument("--batch", "-b", type=int, default=1,
                        help="Generate N images in parallel (1-4, default: 1)")
    parser.add_argument("--timeout", "-t", type=int, default=None,
                        help="请求超时（秒）。省略或 ≤0 → 不设限（默认，生成可能较慢）。也可用环境变量 CHATGPT_IMAGE_TIMEOUT。")

    args = parser.parse_args()

    if not args.prompt:
        parser.print_help()
        print("\nExamples:")
        print('  python3 generate.py setup                              # 首次配置')
        print('  python3 generate.py doctor                             # 诊断')
        print('  python3 generate.py "金色猫咪在阳光下"                    # 模型自选尺寸')
        print('  python3 generate.py "赛博朋克城市" -s landscape           # 横版')
        print('  python3 generate.py "水墨山水" -s 1792x1024               # 自定义超宽')
        print('  python3 generate.py "穿和服的狐狸" -b 3                   # 并行 3 张')
        sys.exit(1)

    generate_image(
        prompt=args.prompt,
        size=args.size,
        batch=max(1, min(args.batch, 4)),
        timeout=resolve_timeout(args.timeout),
    )


if __name__ == "__main__":
    main()
