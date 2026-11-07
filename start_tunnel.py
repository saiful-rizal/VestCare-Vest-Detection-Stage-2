"""Run a Cloudflare Tunnel only after confirming API authentication is configured."""
import os
import re
import shutil
import subprocess

from config_env import ROOT, api_key_is_configured, load_project_env

URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
PUBLIC_URL_PATH = ROOT / "data" / "public_url.txt"


def _simpan_url_publik(url: str) -> None:
    PUBLIC_URL_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_URL_PATH.write_text(url + "\n", encoding="utf-8")
    print("")
    print(f"[INFO] URL publik Cloudflare: {url}")
    print(f"[INFO] URL disimpan di    : {PUBLIC_URL_PATH}")
    print("[INFO] Buka URL tersebut dengan akhiran /app untuk halaman kamera.")
    print("")


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
        return subprocess.call(command, cwd=ROOT)

    host = os.environ.get("VEST_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.environ.get("VEST_PORT", "8000").strip() or "8000"
    origin_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    origin = f"http://{origin_host}:{port}"

    command = [cloudflared, "tunnel", "--url", origin]
    print(f"[INFO] Menjalankan Quick Tunnel untuk {origin} ...")
    print("[INFO] URL sementara akan muncul setelah tunnel terhubung.")

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None

    url_ditemukan = False
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            if not url_ditemukan:
                match = URL_PATTERN.search(line)
                if match:
                    _simpan_url_publik(match.group(0))
                    url_ditemukan = True
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        return 130

    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
