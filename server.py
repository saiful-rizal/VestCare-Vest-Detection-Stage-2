from __future__ import annotations

import hashlib
import hmac
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn

# server.py sudah menjalankan discovery UDP sendiri (termasuk URL Cloudflare
# yang berubah dinamis). Matikan discovery bawaan aplikasi agar port 4211 tidak
# dibuka dua kali saat mode lokal.
os.environ.setdefault("VEST_ENABLE_LAN_DISCOVERY", "0")

from server_rest_api import (
    API_KEY,
    API_KEY_CONFIGURED,
    PORT,
    ROOT,
    app,
    engine,
    engine_error,
)

HOST = os.environ.get("VEST_HOST", "0.0.0.0")
DISCOVERY_PORT = 4211
DISCOVERY_REQUEST = "VESTCARE_DISCOVER_V1"
DISCOVERY_RESPONSE = "VESTCARE_URL_V1"
CLOUDFLARE_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def _server_lokal_aktif(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/status", timeout=1) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _endpoint_lokal_ada(port: int, path: str) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
            return response.status != 404
    except HTTPError as error:
        return error.code != 404
    except (OSError, URLError):
        return False


def _simpan_url_publik(url: str) -> Path:
    path = ROOT / "data" / "runtime" / "public_url.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(url + "\n", encoding="utf-8")
    return path


def _tanda_tangan_discovery(nonce: str, public_url: str) -> str:
    pesan = f"{nonce}\n{public_url}".encode("utf-8")
    return hmac.new(API_KEY.encode("utf-8"), pesan, hashlib.sha256).hexdigest()


def _layani_discovery(
    discovery_socket: socket.socket,
    dapatkan_url: Callable[[], Optional[str]],
    berhenti: threading.Event,
) -> None:
    discovery_socket.settimeout(0.5)
    while not berhenti.is_set():
        try:
            data, alamat = discovery_socket.recvfrom(128)
        except socket.timeout:
            continue
        except OSError:
            if not berhenti.is_set():
                print("[WARN] Listener UDP discovery berhenti karena socket error.")
            return

        try:
            permintaan = data.decode("ascii").strip().split()
        except UnicodeDecodeError:
            continue
        if (
            len(permintaan) != 2
            or permintaan[0] != DISCOVERY_REQUEST
            or not re.fullmatch(r"[0-9a-f]{32}", permintaan[1])
        ):
            continue

        public_url = dapatkan_url()
        if public_url is None:
            continue

        nonce = permintaan[1]
        signature = _tanda_tangan_discovery(nonce, public_url)
        respons = f"{DISCOVERY_RESPONSE}\n{nonce}\n{public_url}\n{signature}\n"
        try:
            discovery_socket.sendto(respons.encode("ascii"), alamat)
        except OSError as error:
            print(f"[WARN] Gagal membalas discovery UDP: {error}")


def _pantau_cloudflared(
    proses: subprocess.Popen[str],
    atur_url: Callable[[str], None],
    url_siap: threading.Event,
) -> None:
    if proses.stdout is None:
        return
    for baris in proses.stdout:
        baris = baris.rstrip()
        if baris:
            print(f"[CLOUDFLARED] {baris}")
        cocok = CLOUDFLARE_URL_PATTERN.search(baris)
        if cocok:
            atur_url(cocok.group(0))
            url_siap.set()


def _mulai_cloudflared(
    executable: str,
    port: int,
    atur_url: Callable[[str], None],
) -> tuple[subprocess.Popen[str], threading.Event]:
    proses = subprocess.Popen(
        [
            executable,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--no-autoupdate",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    url_siap = threading.Event()
    threading.Thread(
        target=_pantau_cloudflared,
        args=(proses, atur_url, url_siap),
        daemon=True,
        name="VestCareCloudflaredOutput",
    ).start()
    return proses, url_siap


def main() -> None:
    if not API_KEY_CONFIGURED:
        raise SystemExit(
            "VEST_API_KEY belum aman/valid. Isi .env dengan kunci acak minimal 32 karakter."
        )
    if engine is None:
        raise SystemExit(f"Engine deteksi gagal dimuat: {engine_error}")

    cloudflared_command = os.environ.get("CLOUDFLARED_EXECUTABLE", "cloudflared")
    executable = shutil.which(cloudflared_command)
    if executable is None and "CLOUDFLARED_EXECUTABLE" not in os.environ:
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        installed_path = Path(program_files_x86) / "cloudflared" / "cloudflared.exe"
        if installed_path.is_file():
            executable = str(installed_path)
    if executable is None:
        raise SystemExit(
            "cloudflared tidak ditemukan. Instal Cloudflare Tunnel atau set "
            "CLOUDFLARED_EXECUTABLE ke path cloudflared.exe."
        )

    server: Optional[uvicorn.Server] = None
    server_thread: Optional[threading.Thread] = None
    if _server_lokal_aktif(PORT):
        required_endpoints = (
            "/api/deteksi/latest",
            "/api/esp32/frame/latest",
        )
        missing_endpoints = [
            path for path in required_endpoints
            if not _endpoint_lokal_ada(PORT, path)
        ]
        if missing_endpoints:
            raise SystemExit(
                "Server API lama masih aktif dan belum memiliki endpoint kamera "
                f"{', '.join(missing_endpoints)}. Hentikan proses API lama agar "
                f"port {PORT} bebas, lalu jalankan `python server.py` kembali; "
                "server.py tidak dapat memuat ulang proses lama secara otomatis."
            )
        print(
            f"[INFO] Server VestCare sudah aktif di http://127.0.0.1:{PORT}; "
            "memakai proses yang ada."
        )
    else:
        server = uvicorn.Server(
            uvicorn.Config(app, host=HOST, port=PORT, reload=False)
        )
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not server_thread.is_alive():
                raise SystemExit(
                    f"Server API berhenti sebelum siap (port {PORT} mungkin dipakai proses lain)."
                )
            if _server_lokal_aktif(PORT):
                break
            time.sleep(0.25)
        else:
            raise SystemExit(f"Server API tidak siap dalam 30 detik pada port {PORT}.")

    url_lock = threading.Lock()
    url_state: dict[str, Optional[str]] = {"value": None}

    def dapatkan_url() -> Optional[str]:
        with url_lock:
            return url_state["value"]

    def atur_url(public_url: Optional[str]) -> None:
        with url_lock:
            url_state["value"] = public_url

    discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        discovery_socket.bind(("0.0.0.0", DISCOVERY_PORT))
    except OSError as error:
        discovery_socket.close()
        raise SystemExit(
            f"Tidak dapat membuka UDP port {DISCOVERY_PORT} untuk discovery ESP32: {error}"
        ) from error

    discovery_stop = threading.Event()
    discovery_thread = threading.Thread(
        target=_layani_discovery,
        args=(discovery_socket, dapatkan_url, discovery_stop),
        daemon=True,
        name="VestCareCloudflareDiscovery",
    )
    discovery_thread.start()

    tunnel: Optional[subprocess.Popen[str]] = None
    try:
        try:
            tunnel, url_siap = _mulai_cloudflared(executable, PORT, atur_url)
        except OSError as error:
            print(f"[WARN] Gagal menjalankan cloudflared: {error}")
            url_siap = None

        public_url = dapatkan_url()
        if tunnel is not None:
            print("[INFO] Menunggu URL HTTPS Cloudflare Quick Tunnel...")
            batas_url = time.monotonic() + 60
            while time.monotonic() < batas_url:
                if tunnel.poll() is not None:
                    print(f"[WARN] cloudflared berhenti dengan kode {tunnel.returncode}.")
                    break
                if url_siap is not None and url_siap.wait(timeout=0.5):
                    break
            public_url = dapatkan_url()

        if public_url is None:
            print("[WARN] URL Quick Tunnel belum tersedia; server akan mencoba lagi.")
            if tunnel is not None and tunnel.poll() is None:
                tunnel.terminate()
                try:
                    tunnel.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait()
            tunnel = None
            _simpan_url_publik("")
        else:
            path_url = _simpan_url_publik(public_url)
            print(f"[INFO] Dashboard publik : {public_url}")
            print(f"[INFO] Dokumentasi API  : {public_url}/docs")
            print(f"[INFO] URL disimpan di  : {path_url}")
            print(
                f"[INFO] Discovery ESP32  : UDP 4211; "
                "pastikan firewall Windows mengizinkan Python pada jaringan Private."
            )

        print(f"[INFO] Dashboard lokal  : http://127.0.0.1:{PORT}")
        jeda_restart = 3
        while True:
            if server_thread is not None and not server_thread.is_alive():
                print("[WARN] Server API berhenti; pemantauan tunnel dihentikan.")
                break
            if tunnel is not None and tunnel.poll() is not None:
                print(
                    f"[WARN] Cloudflare Tunnel berhenti (kode {tunnel.returncode}); "
                    "mencoba menyambungkan ulang."
                )
                atur_url(None)
                tunnel = None
                _simpan_url_publik("")

            if tunnel is None:
                time.sleep(jeda_restart)
                if server_thread is not None and not server_thread.is_alive():
                    break
                try:
                    tunnel, url_siap = _mulai_cloudflared(
                        executable,
                        PORT,
                        atur_url,
                    )
                except OSError as error:
                    print(f"[WARN] Gagal menjalankan ulang cloudflared: {error}")
                    jeda_restart = min(jeda_restart * 2, 30)
                    continue

                print("[INFO] Menunggu URL Cloudflare setelah koneksi ulang...")
                batas_url = time.monotonic() + 60
                while time.monotonic() < batas_url:
                    if tunnel.poll() is not None:
                        break
                    if url_siap.wait(timeout=0.5):
                        break

                public_url = dapatkan_url()
                if public_url is None:
                    print("[WARN] URL tunnel belum tersedia; akan mencoba lagi.")
                    if tunnel.poll() is None:
                        tunnel.terminate()
                        try:
                            tunnel.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            tunnel.kill()
                            tunnel.wait()
                    tunnel = None
                    jeda_restart = min(jeda_restart * 2, 30)
                    continue

                path_url = _simpan_url_publik(public_url)
                print(f"[INFO] URL tunnel aktif : {public_url}")
                print(f"[INFO] URL disimpan di  : {path_url}")
                print(
                    "[INFO] URL Quick Tunnel baru mungkin berubah; "
                    "perbarui URL ESP32 jika perangkat tidak satu LAN dengan server."
                )
                jeda_restart = 3
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()
        discovery_stop.set()
        discovery_socket.close()
        discovery_thread.join(timeout=2)
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=10)


if __name__ == "__main__":
    main()
