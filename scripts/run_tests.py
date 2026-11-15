#!/usr/bin/env python3
"""
Runs the unit tests of every service, then the frontend type check.

    python scripts/run_tests.py                   # everything
    python scripts/run_tests.py --only like-service
    python scripts/run_tests.py --install         # install dependencies first (pip / npm)

Python services use pytest (pip install -r requirements.txt -r requirements-dev.txt).
Node services use "npm test". Missing npm packages are installed automatically.
Exit code is 0 only if everything passed, so it can be used in a CI pipeline.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def discover():
    found = []
    services = ROOT / "services"
    if services.is_dir():
        for folder in sorted(services.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            if (folder / "package.json").exists():
                found.append((folder.name, folder, "node"))
            elif (folder / "requirements.txt").exists():
                found.append((folder.name, folder, "python"))
    if (ROOT / "frontend" / "package.json").exists():
        found.append(("frontend (type check)", ROOT / "frontend", "frontend"))
    return found


def run(command, cwd):
    print("  $ " + " ".join(str(part) for part in command))
    try:
        return subprocess.call(command, cwd=cwd)
    except FileNotFoundError as err:
        print(f"  cannot run: {err}")
        return 1


def run_one(kind, folder, install):
    if kind == "python":
        if install:
            code = run([sys.executable, "-m", "pip", "install", "-q",
                        "-r", "requirements.txt", "-r", "requirements-dev.txt"], folder)
            if code != 0:
                return False
        code = run([sys.executable, "-m", "pytest", "-q"], folder)
        if code != 0 and not install:
            print("  (if pytest or a package is missing, run again with --install)")
        return code == 0

    npm = shutil.which("npm")
    if npm is None:
        print("  npm was not found. Install Node.js 20 or newer.")
        return False
    if install or not (folder / "node_modules").exists():
        if run([npm, "install", "--no-audit", "--no-fund"], folder) != 0:
            return False
    return run([npm, "run", "typecheck"] if kind == "frontend" else [npm, "test"], folder) == 0


def main():
    parser = argparse.ArgumentParser(description="Run all MiniTweet tests")
    parser.add_argument("--only", help="run just one service, for example like-service")
    parser.add_argument("--install", action="store_true", help="install dependencies first")
    args = parser.parse_args()

    targets = discover()
    if args.only:
        targets = [t for t in targets if t[0].startswith(args.only)]
    if not targets:
        print("Nothing to test here. Run this from the minitweet folder.")
        return 1

    results = []
    for name, folder, kind in targets:
        print(f"\n=== {name} ===")
        results.append((name, run_one(kind, folder, args.install)))

    print("\n=== summary ===")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
