from pathlib import Path
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    from backend.app.local_chain import main as run_local_chain

    run_local_chain()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
