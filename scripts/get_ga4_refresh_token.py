"""
Helper: Obtine Refresh Token pentru Google Analytics 4 Data API
================================================================
Ruleaza o singura data, dupa ce ai:
  1. client_id si client_secret completate in config/ga4.ini (sectiunea [ga4])
  2. Google Analytics Data API activat pe proiectul OAuth respectiv
  3. Userul Google folosit la autorizare are acces la property-ul GA4 FGO

Prerequisite:
    pip install requests

Utilizare:
    python Analiza-Campanii/get_ga4_refresh_token.py

Ce se intampla:
    1. Scriptul citeste client_id / client_secret din config/ga4.ini
    2. Afiseaza un URL de autorizare - il deschizi in browser
    3. Accepti permisiunile (scope analytics.readonly)
    4. Google redirecteaza catre http://localhost/?code=...&scope=...
       (pagina nu se incarca - NORMAL, localhost nu ruleaza)
    5. Copiezi URL-ul din bara de adrese si-l lipesti la prompt-ul scriptului
       (NU il rula in CMD - "&" e separator de comenzi si da eroare "scope is not recognized")
    6. Scriptul schimba code-ul pe refresh_token si se ofera sa-l scrie
       automat in config/ga4.ini

Best practice: credentialele NU se hardcodeaza in sursa. Toate vin din
config/ga4.ini (gitignored). Daca un secret ajunge pe github, Google il
revoca automat -> "invalid_client".
"""

import sys
import urllib.parse
import configparser
from pathlib import Path

try:
    import requests
except ImportError:
    print("[!] Libraria requests nu e instalata. Ruleaza: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
CONFIG_FILE = ROOT / "config" / "ga4.ini"
TEMPLATE_FILE = ROOT / "config" / "ga4.template.ini"

REDIRECT_URI = "http://localhost"
SCOPES = "https://www.googleapis.com/auth/analytics.readonly"

# Property ID default (citit din config/ga4.ini; suprascrie aici doar pt fallback)
DEFAULT_PROPERTY_ID = "0"


def _is_placeholder(v: str) -> bool:
    if not v:
        return True
    v = v.strip()
    if not v:
        return True
    for marker in ("YOUR_", "PASTE_", ".apps.googleusercontent.com"):
        # ".apps.googleusercontent.com" apare si in valorile reale; verificam
        # doar cazul in care valoarea e DOAR sufixul (placeholder "YOUR_CLIENT_ID.apps...")
        pass
    if v.startswith("YOUR_") or v.startswith("PASTE_"):
        return True
    if v == "YOUR_CLIENT_ID.apps.googleusercontent.com":
        return True
    return False


def load_oauth_credentials():
    if not CONFIG_FILE.exists():
        print(f"[!] Lipseste {CONFIG_FILE}")
        print(f"    Ruleaza: cp {TEMPLATE_FILE} {CONFIG_FILE}")
        print("    Apoi completeaza client_id si client_secret din Google Cloud Console.")
        sys.exit(1)

    cp = configparser.ConfigParser(interpolation=None)
    cp.read(str(CONFIG_FILE), encoding="utf-8")
    if not cp.has_section("ga4"):
        print(f"[!] Sectiunea [ga4] lipseste din {CONFIG_FILE}")
        sys.exit(1)

    cid = cp["ga4"].get("client_id", "").strip().strip('"')
    csec = cp["ga4"].get("client_secret", "").strip().strip('"')

    missing = []
    if _is_placeholder(cid):
        missing.append("client_id")
    if _is_placeholder(csec):
        missing.append("client_secret")
    if missing:
        print(f"[!] Completeaza in {CONFIG_FILE} [ga4]: {', '.join(missing)}")
        print("    Google Cloud Console > APIs & Credentials > OAuth 2.0 Client IDs")
        print("    (Desktop app). Daca secretul e respins ca 'invalid_client', regenereaza-l")
        print("    - probabil a fost revocat de Google Secret Scanner daca a ajuns pe github.")
        sys.exit(1)

    return cp, cid, csec


def write_refresh_token(cp: configparser.ConfigParser, refresh_token: str):
    """Scrie refresh_token (si property_id default daca lipseste) in config/ga4.ini."""
    cp["ga4"]["refresh_token"] = refresh_token
    current_pid = cp["ga4"].get("property_id", "").strip()
    if not current_pid or current_pid == "0":
        cp["ga4"]["property_id"] = DEFAULT_PROPERTY_ID
        print(f"  property_id setat la default FGO: {DEFAULT_PROPERTY_ID}")
    with open(str(CONFIG_FILE), "w", encoding="utf-8") as f:
        cp.write(f)
    print(f"  Scris in {CONFIG_FILE}")


def main():
    cp, client_id, client_secret = load_oauth_credentials()

    auth_url = (
        "https://accounts.google.com/o/oauth2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"scope={urllib.parse.quote(SCOPES)}&"
        "response_type=code&"
        "access_type=offline&"
        "prompt=consent"
    )

    print("=" * 60)
    print("GOOGLE ANALYTICS 4 - OBTINERE REFRESH TOKEN")
    print("=" * 60)
    print()
    print("PASUL 1: Deschide acest link in BROWSER (NU in CMD!):")
    print()
    print(auth_url)
    print()
    print("IMPORTANT: foloseste contul Google cu acces la property-ul GA4 FGO")
    print("           (adauga &authuser=0 sau &authuser=1 daca ai mai multe conturi)")
    print()
    print("PASUL 2: Logheaza-te si accepta permisiunile.")
    print()
    print("PASUL 3: Browser-ul te va redirecta catre:")
    print("           http://localhost/?code=4/0XXXXX...&scope=...")
    print("         Pagina NU se incarca (normal). Copiaza URL-ul din bara de adrese.")
    print()

    try:
        redirect_response = input("Lipeste URL-ul aici: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAnulat.")
        sys.exit(1)

    try:
        parsed = urllib.parse.urlparse(redirect_response)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params["code"][0]
    except (KeyError, IndexError):
        print("[!] Nu am gasit parametrul 'code' in URL. Asigura-te ca ai copiat")
        print("    INTREGUL URL (incepe cu http://localhost/?code=...).")
        sys.exit(1)

    print()
    print("Se obtine refresh token-ul...")

    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )

    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
        err_code = err.get("error", "")
        print(f"[!] Eroare la obtinerea token-ului: {err}")
        if err_code == "invalid_client":
            print()
            print("    'invalid_client' inseamna ca client_id sau client_secret sunt gresite.")
            print("    Cauze tipice:")
            print("      - secretul a fost revocat de Google (scan public github)")
            print("      - nu ai copiat valoarea completa din Cloud Console")
            print("      - OAuth client sters sau intr-un alt proiect")
            print("    Fix: Cloud Console > APIs & Credentials > OAuth client > Reset secret")
            print("         apoi copiaza NOUA valoare in config/ga4.ini si reruleaza.")
        sys.exit(1)

    tokens = r.json()
    refresh_token = tokens.get("refresh_token")

    if not refresh_token:
        print(f"[!] Raspunsul nu contine refresh_token: {tokens}")
        print("    Probabil ai mai autorizat app-ul inainte. Fortam consent-ul - am")
        print("    inclus prompt=consent in URL; revoca accesul existent din")
        print("    https://myaccount.google.com/permissions si reia pasul 1.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("REFRESH TOKEN GA4 OBTINUT!")
    print("=" * 60)
    print(f"  {refresh_token}")
    print()

    try:
        answer = input(f"Scriu automat in {CONFIG_FILE}? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("", "y", "yes", "da", "d"):
        write_refresh_token(cp, refresh_token)
        print()
        print("Gata. Poti rula: python Analiza-Campanii/run_GA4.py funnel")
    else:
        print()
        print("Nu am scris nimic. Adauga manual in config/ga4.ini:")
        print("  [ga4]")
        print(f"  refresh_token = {refresh_token}")
        print(f"  property_id = {DEFAULT_PROPERTY_ID}")


if __name__ == "__main__":
    main()
