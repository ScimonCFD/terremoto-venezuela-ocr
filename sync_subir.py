"""
Sube la base de datos actualizada a PythonAnywhere después de procesar.
Uso: python sync_subir.py
"""
import urllib.request
import urllib.error
import sqlite3
import tempfile
from pathlib import Path

PA_USER = "listashospitalarias"
PA_TOKEN_FILE = Path(__file__).parent / "PA_TOKEN.txt"
PA_DB_PATH = f"/home/{PA_USER}/terremoto-venezuela-ocr/hospital_data.db"
LOCAL_DB = Path(__file__).parent / "hospital_data.db"

URL = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path{PA_DB_PATH}/"
RELOAD_URL = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/webapps/{PA_USER}.pythonanywhere.com/reload/"


def cargar_token():
    if PA_TOKEN_FILE.exists():
        return PA_TOKEN_FILE.read_text().strip()
    raise SystemExit("Error: no se encontró PA_TOKEN.txt. Pídele el token a Simon.")


def contar_local():
    con = sqlite3.connect(str(LOCAL_DB))
    n = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    con.close()
    return n


def contar_remoto(token):
    """Descarga la BD remota a un archivo temporal y cuenta los registros."""
    req = urllib.request.Request(URL, headers={"Authorization": f"Token {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        con = sqlite3.connect(tmp_path)
        n = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        con.close()
        Path(tmp_path).unlink()
        return n
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 0  # No existe aún, es la primera vez
        raise


def subir(token, file_data):
    boundary = b"----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="content"; filename="hospital_data.db"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + file_data + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    req = urllib.request.Request(
        URL, data=body, method="POST",
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status


def recargar(token):
    req = urllib.request.Request(
        RELOAD_URL, data=b"", method="POST",
        headers={"Authorization": f"Token {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--forzar", action="store_true", help="Sube aunque tenga menos registros (para deduplicación)")
    args = parser.parse_args()

    if not LOCAL_DB.exists():
        print("Error: no existe la base de datos local.")
        return

    token = cargar_token()
    total_local = contar_local()

    print(f"Base de datos local: {total_local} registros")
    print("Verificando base de datos en la web...")

    total_remoto = contar_remoto(token)
    print(f"Base de datos en la web: {total_remoto} registros")

    if total_local < total_remoto and not args.forzar:
        print(f"\n[!] CANCELADO: tu base de datos tiene menos registros ({total_local}) que la de la web ({total_remoto}).")
        print("    Corre sync_bajar.py primero y vuelve a procesar.")
        print("    Si eliminaste duplicados intencionalmente, usa: python sync_subir.py --forzar")
        return

    print(f"\nSubiendo {total_local} registros a PythonAnywhere...")
    try:
        status = subir(token, LOCAL_DB.read_bytes())
        print(f"  Subida exitosa ({status})")
    except urllib.error.HTTPError as e:
        print(f"  Error subiendo: {e.code} {e.reason}")
        return

    print("  Recargando web app...")
    try:
        status = recargar(token)
        print(f"  Web app recargada ({status})")
    except urllib.error.HTTPError as e:
        print(f"  Error recargando: {e.code} {e.reason}")

    print(f"\nListo. {total_local} registros disponibles en listashospitalarias.pythonanywhere.com")


if __name__ == "__main__":
    main()
