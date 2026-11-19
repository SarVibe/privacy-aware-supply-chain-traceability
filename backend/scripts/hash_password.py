import getpass
from pathlib import Path
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    from backend.app.auth import hash_password

    password = getpass.getpass("New application password (12+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
