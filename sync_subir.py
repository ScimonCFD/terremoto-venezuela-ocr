"""
Sube la base de datos actualizada a PythonAnywhere después de procesar.
Uso: python sync_subir.py
"""
import urllib.request
import sqlite3
from pathlib import Path

PA_USER = "listashospitalarias"
PA_TOKEN = "23f288f50b22d62690c70ff69d46ca18a155ba8c"
PA_DB_PATH = f"/home/{PA_USER}/terremoto-venezuela-ocr/hospital_data.db"
LOCAL_DB = Path(__file__).parent / "hospital_data.db"

URL = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path{PA_DB_PATH}/"
RELOAD_URL = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/webapps/{PA_USER}.pythonanywhere.com/reload/"

def contar_registros():
    con = sqlite3.connect(str(LOCAL_DB))
    n = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    con.close()
    return n

def main():
    if not LOCAL_DB.exists():
        print("Error: no existe la base de datos local.")
        return

    total = contar_registros()
    print(f"Subiendo base de datos ({total} registros) a PythonAnywhere...")

    file_data = LOCAL_DB.read_bytes()
    boundary = b"----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="content"; filename="hospital_data.db"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + file_data + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    req = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Token {PA_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"  Base de datos subida ({resp.status})")
    except urllib.error.HTTPError as e:
        print(f"  Error subiendo: {e.code} {e.reason}")
        return

    # Recarga la web app para que tome los nuevos datos
    print("  Recargando web app...")
    req2 = urllib.request.Request(
        RELOAD_URL,
        data=b"",
        method="POST",
        headers={"Authorization": f"Token {PA_TOKEN}"}
    )
    try:
        with urllib.request.urlopen(req2) as resp:
            print(f"  Web app recargada ({resp.status})")
    except urllib.error.HTTPError as e:
        print(f"  Error recargando: {e.code} {e.reason}")

    print(f"\nListo. {total} registros disponibles en listashospitalarias.pythonanywhere.com")

if __name__ == "__main__":
    main()
