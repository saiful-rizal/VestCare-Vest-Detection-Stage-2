"""Entry point training sekali-jalan untuk gabungan lima kelas Vestcare."""
from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def main():
    if VENV_PYTHON.is_file() and os.path.normcase(sys.executable) != os.path.normcase(str(VENV_PYTHON)):
        return subprocess.call([str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT)

    os.chdir(ROOT)
    from train_semua import main as train_all_classes

    train_all_classes()


if __name__ == "__main__":
    raise SystemExit(main())
