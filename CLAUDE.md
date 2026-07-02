# prompt-checker

CLI, które w pętli pyta użytkownika o prompt, wysyła go do subprocesu `claude -p`
skonfigurowanego jako "czysty interpreter" (nie wykonuje żadnych akcji, tylko
analizuje tekst) i wypisuje, co model zrozumiał oraz jakie są niejasności/założenia.

## Wywołanie subprocesu

Komenda budowana w `run_claude_interpretation()` (`main.py:35-52`):

```
claude -p --tools "" --disable-slash-commands --no-session-persistence \
  --strict-mcp-config --setting-sources "" --system-prompt SYSTEM_PROMPT
```

Prompt użytkownika trafia na stdin subprocesu, nie jako argument.

Poza `-p` (tryb print, nieinteraktywny) używanych jest 6 dodatkowych flag,
które celowo ograniczają subproces do samej interpretacji tekstu:

- **`--tools ""`** — wyłącza wszystkie wbudowane narzędzia (Bash, Edit, Read
  itd.). Subproces nie może niczego wykonać, wyedytować ani przeczytać poza
  interpretacją podanego tekstu. To kluczowe wymaganie tego narzędzia — prompt
  użytkownika ma być tylko analizowany, nigdy realizowany.
- **`--disable-slash-commands`** — wyłącza skille/slash-commands, żeby treść
  promptu użytkownika nie mogła przypadkiem wywołać jakiejś automatyzacji.
- **`--no-session-persistence`** — sesja subprocesu nie jest zapisywana na
  dysk i nie da się jej później wznowić.
- **`--strict-mcp-config`** — subproces nie ładuje żadnych serwerów MCP poza
  jawnie podanymi przez `--mcp-config` (tu żadne nie są podawane, więc MCP
  jest całkowicie wyłączone).
- **`--setting-sources ""`** — subproces nie wczytuje ustawień user/project/
  local, działa w izolacji od konfiguracji repo (hooki, uprawnienia itd.).
- **`--system-prompt SYSTEM_PROMPT`** — całkowicie zastępuje domyślny system
  prompt Claude Code stałą `SYSTEM_PROMPT` (`main.py:6-32`). Ta instrukcja
  każe modelowi wyłącznie interpretować tekst i odpowiadać w ściśle
  ustalonym formacie: `STATUS: OK|NIEZROZUMIALE`, `ZROZUMIENIE:`,
  `ZALOZENIA_NIEJASNOSCI:`. Zawiera też jawny zakaz komentowania własnych
  możliwości/ograniczeń wykonawczych — nawet gdy prompt użytkownika brzmi
  jak polecenie zadania (np. "napisz kod", "usuń plik"), subproces ma się
  skupić wyłącznie na interpretacji treści, a nie pisać o tym, że czegoś
  "nie może wykonać".

## Kruchość parsowania odpowiedzi

`parse_response()` (`main.py:55-68`) regexem wyciąga status, zrozumienie i
niejasności z odpowiedzi modelu, polegając na tym, że model trzyma się
formatu ze `SYSTEM_PROMPT`. Zmiana treści `SYSTEM_PROMPT` (np. nagłówków
sekcji) wymaga równoległej aktualizacji regexów w `parse_response()`,
inaczej parsowanie się zepsuje.
