"""
Descarga la base de datos actual desde PythonAnywhere antes de procesar.
Uso: python sync_bajar.py
"""
import urllib.request
import urllib.error
import shutil
from pathlib import Path

PA_USER = "listashospitalarias"
PA_TOKEN_FILE = Path(__file__).parent / "PA_TOKEN.txt"
PA_DB_PATH = f"/home/{PA_USER}/terremoto-venezuela-ocr/hospital_data.db"
LOCAL_DB = Path(__file__).parent / "hospital_data.db"

URL = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path{PA_DB_PATH}/"


def cargar_token():
    if PA_TOKEN_FILE.exists():
        return PA_TOKEN_FILE.read_text().strip()
    raise SystemExit("Error: no se encontró PA_TOKEN.txt. Pídele el token a Simon.")


def main():
    token = cargar_token()
    print("Descargando base de datos desde PythonAnywhere...")
    req = urllib.request.Request(URL, headers={"Authorization": f"Token {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            if LOCAL_DB.exists():
                shutil.copy(LOCAL_DB, str(LOCAL_DB) + ".bak")
                print(f"  Backup guardado en {LOCAL_DB}.bak")
            LOCAL_DB.write_bytes(resp.read())
        print(f"  Base de datos descargada: {LOCAL_DB}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("  No hay base de datos en PythonAnywhere aún. Empezando desde cero.")
        else:
            print(f"  Error {e.code}: {e.reason}")


if __name__ == "__main__":
    main()
