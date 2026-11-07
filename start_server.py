"""Start the local FastAPI service after validating runtime configuration."""
import os

import uvicorn

from config_env import api_key_is_configured, load_project_env


def main() -> None:
    load_project_env()
    if not api_key_is_configured(os.environ.get("VEST_API_KEY")):
        raise SystemExit(
            "VEST_API_KEY belum aman/valid. Salin .env.example menjadi .env "
            "dan isi kunci acak minimal 32 karakter."
        )

    from server_rest_api import ENGINE, ENGINE_ERROR, HOST, PORT

    if ENGINE is None:
        raise SystemExit(f"Engine deteksi gagal dimuat: {ENGINE_ERROR}")
    uvicorn.run("server_rest_api:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
