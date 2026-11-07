"""Run a Cloudflare Tunnel only after confirming API authentication is configured."""
import os
import shutil
import subprocess
import sys

from config_env import ROOT, api_key_is_configured, load_project_env


def main() -> int:
    load_project_env()
    if not api_key_is_configured(os.environ.get("VEST_API_KEY")):
        raise SystemExit(
            "VEST_API_KEY belum aman/valid. Isi .env dengan kunci acak minimal 32 karakter."
        )

    cloudflared = shutil.which("cloudflared")
    if cloudflared is None:
        raise SystemExit(
            "cloudflared tidak ditemukan. Install Cloudflare Tunnel lalu ulangi."
        )

    token = os.environ.get("CLOUDFLARED_TOKEN", "").strip()
    if token:
        command = [cloudflared, "tunnel", "run", "--token", token]
        print("[INFO] Menjalankan tunnel terkelola Cloudflare.")
    else:
        command = [cloudflared, "tunnel", "--url", "http://127.0.0.1:8000"]
        print("[INFO] Menjalankan Quick Tunnel; URL sementara akan muncul dari cloudflared.")
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
