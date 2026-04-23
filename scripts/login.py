#!/usr/bin/env python3
"""
ChatGPT OAuth Device Flow 登录脚本。
使用 RFC 8628 Device Authorization Grant 完成 OAuth 登录。
只需运行一次，之后 token 会保存在本地。
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

AUTH_DIR = Path.home() / ".chatgpt-image-2"
TOKEN_FILE = AUTH_DIR / "token.json"
CLIENT_ID = "app_EMoaEEZ73f0CkXaXp7hrann"
DEVICE_AUTH_URL = "https://auth0.openai.com/oauth/device/code"
TOKEN_URL = "https://auth0.openai.com/oauth/token"
SCOPES = "openid email profile offline_access"

# 模型映射（gpt-image-2 支持的模型）
IMAGE_MODELS = {
    "gpt-image-2": "gpt-image-2",
}


def save_token(token_data):
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    print(f"Token 已保存到 {TOKEN_FILE}")


def load_token():
    if not TOKEN_FILE.exists():
        return None
    with open(TOKEN_FILE) as f:
        return json.load(f)


def is_token_valid(token_data):
    if not token_data:
        return False
    # 检查 access_token 是否存在
    if "access_token" not in token_data:
        return False
    # 检查是否过期（exp 是 Unix 时间戳）
    if "exp" in token_data:
        return time.time() < token_data["exp"]
    return True


def refresh_access_token(refresh_token):
    """用 refresh_token 刷新 access_token。"""
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            token_data = json.loads(resp.read().decode())
            # 保存新 token
            existing = load_token() or {}
            existing.update(token_data)
            if "exp" not in existing and "expires_in" in token_data:
                existing["exp"] = time.time() + token_data["expires_in"]
            save_token(existing)
            print("Token 刷新成功！")
            return token_data
    except Exception as e:
        print(f"Token 刷新失败: {e}")
        return None


def do_device_flow():
    """执行 OAuth Device Authorization Grant 流程。"""
    print("=== ChatGPT OAuth 登录 ===\n")

    # Step 1: 请求 device code
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": SCOPES,
    }).encode()

    req = urllib.request.Request(
        DEVICE_AUTH_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            device_data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"请求 device code 失败: {e}")
        print("\n可能原因：网络被 Cloudflare 拦截或需要代理。")
        print("提示：在某些环境（如 Cloudflare WARP）下可能无法直接访问 auth0.openai.com。")
        print("替代方案：使用 'codex login --device-auth' 完成登录（Codex CLI 已配置好 OAuth）。")
        return None

    device_code = device_data.get("device_code")
    user_code = device_data.get("user_code")
    verification_uri = device_data.get("verification_uri")
    interval = device_data.get("interval", 5)
    expires_in = device_data.get("expires_in", 300)

    print(f"请在浏览器打开以下网址：\n")
    print(f"  {verification_uri}")
    print(f"\n或直接访问: https://chat.openai.com/")
    print(f"\n输入验证码: {user_code}")
    print(f"\n（验证码 {expires_in // 60} 分钟内有效）")
    print("\n在浏览器中完成登录后，此脚本会自动继续...")
    print("-" * 40)

    # Step 2: 轮询 token endpoint
    start = time.time()
    while time.time() - start < expires_in:
        time.sleep(interval)

        poll_data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "user_code": user_code,
            "client_id": CLIENT_ID,
        }).encode()

        poll_req = urllib.request.Request(
            TOKEN_URL,
            data=poll_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(poll_req, timeout=30) as resp:
                token_data = json.loads(resp.read().decode())
                # 添加过期时间
                if "expires_in" in token_data:
                    token_data["exp"] = time.time() + token_data["expires_in"]
                save_token(token_data)
                print("\n✅ 登录成功！Token 已保存。")
                return token_data
        except urllib.error.HTTPError as e:
            error_data = json.loads(e.read().decode())
            error = error_data.get("error")
            if error == "authorization_pending":
                sys.stdout.write(".")
                sys.stdout.flush()
                continue
            elif error == "slow_down":
                interval += 1
                continue
            else:
                print(f"\n登录失败: {error} - {error_data.get('error_description', '')}")
                return None

    print("\n登录超时，请重试。")
    return None


def logout():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print("已清除本地 token。")
    else:
        print("没有找到本地 token。")


def status():
    token = load_token()
    if not token:
        print("未登录（无 token 文件）")
        return

    if is_token_valid(token):
        exp = token.get("exp", 0)
        remaining = exp - time.time()
        email = token.get("id_token_claims", {}).get("email", "未知")
        print(f"✅ 已登录（email: {email}）")
        print(f"   token 剩余有效期: {remaining / 60:.1f} 分钟")
    else:
        refresh = token.get("refresh_token")
        if refresh:
            print("token 已过期，尝试刷新...")
            refresh_access_token(refresh)
        else:
            print("token 已过期且无 refresh_token，请重新登录。")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status()
    elif len(sys.argv) > 1 and sys.argv[1] == "logout":
        logout()
    else:
        token = load_token()
        if token and is_token_valid(token):
            print("已经登录了！token 仍然有效。")
            status()
        elif token and not is_token_valid(token):
            refresh = token.get("refresh_token")
            if refresh:
                print("token 已过期，正在刷新...")
                refresh_access_token(refresh)
            else:
                print("token 已过期，请重新登录。")
                do_device_flow()
        else:
            do_device_flow()


if __name__ == "__main__":
    main()
