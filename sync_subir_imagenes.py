"""
Sube las imágenes y PDFs originales a PythonAnywhere y actualiza la base de datos
con la URL de cada archivo para que aparezca el link "Ver lista original".

Uso:
    python sync_subir_imagenes.py /ruta/al/drive
"""
import sys
import hashlib
import sqlite3
import time
import urllib.request
import urllib.error
from pathlib import Path

PA_USER = "listashospitalarias"
PA_TOKEN_FILE = Path(__file__).parent / "PA_TOKEN.txt"
DB_PATH = Path(__file__).parent / "hospital_data.db"

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".docx"}
MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}


def cargar_token():
    if PA_TOKEN_FILE.exists():
        return PA_TOKEN_FILE.read_text().strip()
    raise SystemExit("Error: no se encontró PA_TOKEN.txt.")


def hash_archivo(ruta):
    return hashlib.md5(Path(ruta).read_bytes()).hexdigest()


def subir_archivo(token, data, nombre_remoto, media_type):
    url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/home/{PA_USER}/terremoto-venezuela-ocr/static/fuentes/{nombre_remoto}/"
    boundary = b"----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="content"; filename="' + nombre_remoto.encode() + b'"\r\n'
        b"Content-Type: " + media_type.encode() + b"\r\n\r\n"
        + data + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Token {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary.decode()}"
    })
    with urllib.request.urlopen(req) as resp:
        return resp.status


def archivo_ya_subido(token, nombre_remoto):
    url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/home/{PA_USER}/terremoto-venezuela-ocr/static/fuentes/{nombre_remoto}/"
    req = urllib.request.Request(url, headers={"Authorization": f"Token {token}"})
    try:
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError:
        return False


def main():
    if len(sys.argv) < 2:
        print("Uso: python sync_subir_imagenes.py /ruta/al/drive")
        sys.exit(1)

    raiz = Path(sys.argv[1])
    if not raiz.exists():
        print(f"Error: {raiz} no existe")
        sys.exit(1)

    token = cargar_token()
    con = sqlite3.connect(str(DB_PATH))

    # Agrega columna fuente_url si no existe
    columnas = [r[1] for r in con.execute("PRAGMA table_info(registros)").fetchall()]
    if "fuente_url" not in columnas:
        con.execute("ALTER TABLE registros ADD COLUMN fuente_url TEXT")
        con.commit()

    archivos = [f for f in raiz.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONES]
    print(f"\nArchivos a subir: {len(archivos)}")

    subidos = 0
    saltados = 0

    for ruta in sorted(archivos):
        ext = ruta.suffix.lower()
        h = hash_archivo(ruta)
        nombre_remoto = f"{h}{ext}"
        url_publica = f"/static/fuentes/{nombre_remoto}"

        if archivo_ya_subido(token, nombre_remoto):
            print(f"  [SKIP] {ruta.name}")
            saltados += 1
        else:
            data = ruta.read_bytes()
            media_type = MEDIA_TYPES.get(ext, "application/octet-stream")
            try:
                subir_archivo(token, data, nombre_remoto, media_type)
                print(f"  [OK] {ruta.name}")
                subidos += 1
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(f"  [ESPERA] Rate limit, reintentando en 10s...")
                    time.sleep(10)
                    try:
                        subir_archivo(token, data, nombre_remoto, media_type)
                        print(f"  [OK] {ruta.name} (reintento)")
                        subidos += 1
                    except Exception as e2:
                        print(f"  [ERROR] {ruta.name}: {e2}")
                        continue
                else:
                    print(f"  [ERROR] {ruta.name}: {e}")
                    continue
            except Exception as e:
                print(f"  [ERROR] {ruta.name}: {e}")
                continue

        time.sleep(0.5)

        # Actualiza todos los registros que vienen de este archivo
        ruta_str = str(ruta)
        con.execute(
            "UPDATE registros SET fuente_url=? WHERE fuente_imagen LIKE ?",
            (url_publica, f"{ruta_str}%")
        )

    con.commit()
    con.close()

    print(f"\nSubidos: {subidos} | Saltados: {saltados}")
    print("Listo. Ahora corre sync_subir.py para actualizar la base de datos en la web.")


if __name__ == "__main__":
    main()
