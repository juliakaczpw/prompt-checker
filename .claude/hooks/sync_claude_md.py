#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from datetime import datetime

PROJECT_DIR = "/home/juliak/DF/TryPrompt/prompt-checker"
TARGET_FILE = os.path.join(PROJECT_DIR, "main.py")
CLAUDE_MD = os.path.join(PROJECT_DIR, "CLAUDE.md")
LOG_FILE = os.path.join(PROJECT_DIR, ".claude", "hooks", "sync_claude_md.log")

FUNC_DEF_RE = re.compile(r"^[+-]\s*def\s")
# Dopasowuje dowolny zmieniony element listy `cmd` wyglądający jak flaga/nazwa
# polecenia CLI (np. "--tools", "-p", "claude"), a nie tylko z góry znaną listę
# flag - żeby wykryć też DODANIE nowej, nieznanej wcześniej flagi.
FLAG_ITEM_RE = re.compile(r'^[+-]\s*"(-{1,2}[\w-]+|claude)"')


def log(message: str) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")


def is_significant(diff_text: str) -> bool:
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if not (line.startswith("+") or line.startswith("-")):
            continue
        if FUNC_DEF_RE.match(line) or FLAG_ITEM_RE.match(line):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0

    if os.path.realpath(file_path) != os.path.realpath(TARGET_FILE):
        return 0

    diff_proc = subprocess.run(
        ["git", "diff", "HEAD", "--", "main.py"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    diff_text = diff_proc.stdout
    if not diff_text.strip():
        return 0

    if not is_significant(diff_text):
        log("Zmiana main.py nieistotna - CLAUDE.md bez zmian.")
        return 0

    log("Wykryto istotna zmiane main.py - wywoluje claude -p do aktualizacji CLAUDE.md.")

    prompt = (
        "Poniższy fragment to `git diff` pliku main.py (względem ostatniego commita) "
        "w projekcie prompt-checker. Ta zmiana została automatycznie uznana za istotną "
        "(zmiana sygnatury funkcji lub zmiana listy flag wywołania claude -p w "
        "run_claude_interpretation()).\n\n"
        f"Zaktualizuj plik CLAUDE.md ({CLAUDE_MD}) tak, aby dokładnie odzwierciedlał tę "
        "zmianę: zaktualizuj opisy zmienionych flag/funkcji oraz odwołania do numerów "
        "linii main.py, jeśli się przesunęły. Nie zmieniaj treści niezwiązanych z tym "
        "diffem i nie twórz nowych sekcji, jeśli nie są potrzebne.\n\n"
        f"DIFF:\n{diff_text}"
    )

    result = subprocess.run(
        [
            "claude", "-p",
            "--add-dir", PROJECT_DIR,
            "--allowedTools", "Read Edit",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--no-session-persistence",
            "--append-system-prompt",
            (
                "Możesz używać wyłącznie narzędzi Read i Edit, i wyłącznie na pliku "
                f"{CLAUDE_MD}. Twoim jedynym zadaniem jest zaktualizowanie tego jednego "
                "pliku zgodnie z otrzymanym diffem main.py. Nie edytuj, nie twórz i nie "
                f"czytaj żadnych innych plików - w szczególności NIGDY nie edytuj main.py "
                "ani żadnego pliku .py."
            ),
        ],
        input=prompt,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=150,
    )

    log(f"claude -p exit code: {result.returncode}")
    if result.stdout.strip():
        log(f"stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        log(f"stderr: {result.stderr.strip()}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"Blad hooka: {exc}")
        sys.exit(0)
