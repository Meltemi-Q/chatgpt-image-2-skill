#!/usr/bin/env python3
"""
ChatGPT gpt-image-2 图片生成脚本。
从 Codex CLI auth.json 读取 access_token，调用 ChatGPT Responses API (gpt-image-2)。
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

CODEX_AUTH_FILE = Path.home() / ".codex" / "auth.json"
API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-image-2"

SIZE_PRESETS = {
    "square":    "1024x1024",
    "landscape": "1536x1024",
    "portrait":  "1024x1536",
}


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


def load_codex_token():
    if not CODEX_AUTH_FILE.exists():
        return None
    try:
        with open(CODEX_AUTH_FILE) as f:
            data = json.load(f)
        tokens = data.get("tokens", {})
        return tokens.get("access_token")
    except (json.JSONDecodeError, IOError) as e:
        print(f"读取 Codex auth 失败: {e}")
        return None


def resolve_size(size_str):
    lower = size_str.lower().strip()
    return SIZE_PRESETS.get(lower, size_str)


def generate_image(prompt, size="square", batch=1):
    access_token = load_codex_token()
    if not access_token:
        print("未登录！请先运行: codex login --device-auth")
        sys.exit(1)

    size_px = resolve_size(size)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    # Responses API payload for image generation
    payload = {
        "model": MODEL,
        "input": prompt,
        "stream": False,
        "features": {
            "image_inputs": "generate"
        },
        "size": size_px,
    }

    print(f"## 图片生成中...")
    print(f"- **模型**: {MODEL}")
    print(f"- **提示词**: {prompt}")
    print(f"- **尺寸**: {size_px}")
    if batch > 1:
        print(f"- **数量**: {batch} 张")
    print()

    workspace = get_workspace_dir()

    def gen_one(idx=None):
        t0 = time.time()
        save_path = os.path.join(workspace, make_filename(prompt, idx))

        try:
            req = Request(
                API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # 从 Responses API 提取图片 URL
            # 响应格式: {"data": [{"url": "..."}]} 或类似结构
            image_url = None
            if "data" in data:
                for item in data["data"]:
                    if isinstance(item, dict):
                        if item.get("url"):
                            image_url = item["url"]
                            break

            if not image_url:
                # 打印完整响应以便调试
                return (None, f"未找到图片 URL: {json.dumps(data, ensure_ascii=False)[:300]}", 0)

            # 下载图片
            img_req = Request(image_url)
            with urlopen(img_req, timeout=60) as img_resp:
                img_data = img_resp.read()

            with open(save_path, "wb") as f:
                f.write(img_data)

            elapsed = int(time.time() - t0)
            return (os.path.abspath(save_path), len(img_data) / 1024, elapsed)

        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            return (None, f"HTTP {e.code}: {err_body[:400]}", 0)
        except Exception as e:
            return (None, str(e), 0)

    if batch == 1:
        path, size_kb, elapsed = gen_one()
        if path is None:
            print(f"## 生成失败\n{size_kb}")
            sys.exit(1)
        print(f"## 图片已生成 (~{elapsed}s)\n")
        print(f"![AI Generated Image]({path})\n")
        print(f"**文件**: `{path}`")
    else:
        results = []
        with ThreadPoolExecutor(max_workers=min(batch, 4)) as pool:
            futures = {pool.submit(gen_one, i + 1): i + 1 for i in range(batch)}
            for future in as_completed(futures):
                idx = futures[future]
                path, size_kb, elapsed = future.result()
                results.append((idx, path, size_kb, elapsed))

        results.sort(key=lambda r: r[0])
        ok = [(idx, p, sk, el) for idx, p, sk, el in results if p is not None]
        fail = [(idx, p, sk, el) for idx, p, sk, el in results if p is None]

        if not ok:
            print("## 全部生成失败")
            for idx, _, err, _ in fail:
                print(f"- 第 {idx} 张: {err}")
            sys.exit(1)

        print(f"## {len(ok)} 张图片已生成，请挑选\n")
        for idx, path, size_kb, elapsed in ok:
            print(f"### 第 {idx} 张 (~{elapsed}s)\n")
            print(f"![第{idx}张]({path})\n")

        if fail:
            print(f"\n*{len(fail)} 张生成失败*")

        print(f"\n---\n文件保存在: `{workspace}/`")
        print("告诉我你选哪张。")


def list_sizes():
    print("## 尺寸预设\n")
    print("| 简称 | 尺寸 | 用途 |")
    print("|------|------|------|")
    print("| square（默认） | 1024x1024 | 默认，通用 |")
    print("| landscape | 1536x1024 | 横版 |")
    print("| portrait | 1024x1536 | 竖版 |")


def main():
    parser = argparse.ArgumentParser(description="ChatGPT gpt-image-2 Image Generation")
    parser.add_argument("prompt", nargs="?", help="Image generation prompt")
    parser.add_argument("--size", "-s", default="square",
                        help="Size: square / landscape / portrait (default: square)")
    parser.add_argument("--batch", "-b", type=int, default=1,
                        help="Generate N images to pick from (1-4, default: 1)")
    parser.add_argument("--list-sizes", "-l", action="store_true",
                        help="List available size presets")

    args = parser.parse_args()

    if args.list_sizes:
        list_sizes()
        return

    if not args.prompt:
        parser.print_help()
        print("\nExamples:")
        print('  python3 scripts/generate.py "金色猫咪在阳光下"')
        print('  python3 scripts/generate.py "赛博朋克城市" --size landscape')
        print('  python3 scripts/generate.py "水墨山水" --batch 3')
        print("\n首次使用请先运行: codex login --device-auth")
        sys.exit(1)

    generate_image(
        prompt=args.prompt,
        size=args.size,
        batch=args.batch,
    )


if __name__ == "__main__":
    main()
