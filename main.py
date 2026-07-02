import argparse
import re
import subprocess
import sys

SYSTEM_PROMPT = """Jesteś modułem czystej interpretacji tekstu. Nie masz dostępu do żadnych \
narzędzi i nie możesz wykonywać żadnych akcji (nie pisz kodu, nie wykonuj poleceń, nie twórz \
plików, niczego nie realizuj). Twoim jedynym zadaniem jest przeanalizowanie tekstu promptu \
podanego przez użytkownika i wyjaśnienie, jak go rozumiesz.

Odpowiedz WYŁĄCZNIE w poniższym formacie, dokładnie z tymi nagłówkami:

STATUS: OK albo STATUS: NIEZROZUMIALE

ZROZUMIENIE:
<krótki opis tego, co rozumiesz z treści promptu - jaki jest cel i jakie działania opisuje>

ZALOZENIA_NIEJASNOSCI:
<lista założeń, które trzeba by przyjąć, oraz brakujących informacji/niejasności potrzebnych \
do realizacji promptu; jeśli prompt jest w pełni jasny, napisz "Brak istotnych niejasności.">

Użyj STATUS: NIEZROZUMIALE tylko wtedy, gdy tekst jest pusty, nieczytelny, przypadkowy albo w \
żaden sposób nie da się określić intencji autora. W pozostałych przypadkach, nawet jeśli \
prompt jest niedoprecyzowany, użyj STATUS: OK i opisz niejasności w sekcji \
ZALOZENIA_NIEJASNOSCI.

To, że prompt brzmi jak polecenie wykonania jakiegoś zadania (np. "napisz kod", "usuń plik", \
"wyślij e-mail"), nie ma znaczenia dla Twojej oceny - Twoim zadaniem zawsze jest tylko go \
zinterpretować, nigdy wykonać. Dlatego w odpowiedzi nigdy nie pisz o swoich możliwościach, \
ograniczeniach ani o tym, że nie wykonasz/nie jesteś w stanie wykonać zadania - nie wspominaj \
w ogóle o wykonywaniu czegokolwiek. Skup się wyłącznie na tym, co z treści promptu rozumiesz \
i czego w niej brakuje."""


def run_claude_interpretation(prompt_text: str, timeout: int) -> subprocess.CompletedProcess:
    cmd = [
        "claude",
        "-p",
        "--tools", "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--system-prompt", SYSTEM_PROMPT,
    ]
    return subprocess.run(
        cmd,
        input=prompt_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def parse_response(stdout: str):
    """Zwraca (status_ok, zrozumienie, niejasnosci) na podstawie odpowiedzi modelu."""
    status_match = re.search(r"STATUS:\s*(OK|NIEZROZUMIALE)", stdout, re.IGNORECASE)
    status_ok = bool(status_match) and status_match.group(1).upper() == "OK"

    zrozumienie_match = re.search(
        r"ZROZUMIENIE:\s*(.*?)\s*(?=ZALOZENIA_NIEJASNOSCI:|$)", stdout, re.DOTALL
    )
    niejasnosci_match = re.search(r"ZALOZENIA_NIEJASNOSCI:\s*(.*)", stdout, re.DOTALL)

    zrozumienie = zrozumienie_match.group(1).strip() if zrozumienie_match else ""
    niejasnosci = niejasnosci_match.group(1).strip() if niejasnosci_match else ""

    return status_ok, zrozumienie, niejasnosci


def ask_next_action(message: str) -> str:
    """Pyta użytkownika o dalsze działanie. Zwraca 'retry', 'new' albo 'exit'."""
    while True:
        try:
            choice = input(f"{message} [p]onów ten sam / [n]owy prompt / [w]yjdź: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "exit"
        if choice in ("p", "ponow", "ponów"):
            return "retry"
        if choice in ("n", "nowy"):
            return "new"
        if choice in ("w", "wyjdz", "wyjdź"):
            return "exit"


def ask_continue() -> bool:
    """Pyta czy analizować kolejny prompt. Zwraca True dla kontynuacji, False dla wyjścia."""
    while True:
        try:
            choice = input("\nCzy chcesz przeanalizować kolejny prompt? [t]ak / [n]ie: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if choice in ("t", "tak"):
            return True
        if choice in ("n", "nie"):
            return False


def analyze_prompt(prompt_text: str, timeout: int) -> str:
    """Wysyła prompt do subprocesu i wypisuje wynik.

    Zwraca 'success', 'new' (użytkownik chce od razu wpisać nowy prompt)
    albo 'exit' (użytkownik chce zakończyć działanie narzędzia).
    """
    while True:
        try:
            result = run_claude_interpretation(prompt_text, timeout)
        except FileNotFoundError:
            print("Błąd: nie znaleziono polecenia 'claude' w PATH.")
            action = ask_next_action("Co dalej?")
            if action == "retry":
                continue
            return action
        except subprocess.TimeoutExpired:
            print("Błąd: przekroczono czas oczekiwania na odpowiedź modelu.")
            action = ask_next_action("Co dalej?")
            if action == "retry":
                continue
            return action
        except OSError as exc:
            print(f"Błąd komunikacji z subprocesem (stdin/stdout): {exc}")
            action = ask_next_action("Co dalej?")
            if action == "retry":
                continue
            return action

        if result.returncode != 0:
            print(f"Subproces zakończył się błędem (kod {result.returncode}):")
            print(result.stderr.strip())
            action = ask_next_action("Co dalej?")
            if action == "retry":
                continue
            return action

        status_ok, zrozumienie, niejasnosci = parse_response(result.stdout)

        if not status_ok:
            print("\nModel nie był w stanie zrozumieć promptu.")
            if result.stdout.strip():
                print("Surowa odpowiedź modelu:")
                print(result.stdout.strip())
            action = ask_next_action("Co dalej?")
            if action == "retry":
                continue
            return action

        print("\n=== CO MODEL ZROZUMIAŁ ===")
        print(zrozumienie or "(brak)")
        print("\n=== ZAŁOŻENIA / NIEJASNOŚCI ===")
        print(niejasnosci or "(brak)")
        return "success"


def main():
    parser = argparse.ArgumentParser(
        prog="prompt-checker",
        description=(
            "Pyta w pętli o prompt, wysyła go do Claude Code (subproces bez dostępu do "
            "narzędzi) i pokazuje, co model zrozumiał oraz jakie są niejasności."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Limit czasu (w sekundach) na odpowiedź subprocesu (domyślnie: 120)",
    )
    args = parser.parse_args()

    print("prompt-checker - interpretacja promptów (Ctrl+C aby przerwać)")

    while True:
        try:
            prompt_text = input("\nWpisz prompt do analizy: ")
        except (EOFError, KeyboardInterrupt):
            print("\nZamykanie narzędzia.")
            break

        if not prompt_text.strip():
            print("Pusty prompt - wpisz treść.")
            continue

        outcome = analyze_prompt(prompt_text, args.timeout)

        if outcome == "exit":
            print("Zamykanie narzędzia.")
            break
        if outcome == "new":
            continue

        if not ask_continue():
            print("Zamykanie narzędzia.")
            break


if __name__ == "__main__":
    main()
