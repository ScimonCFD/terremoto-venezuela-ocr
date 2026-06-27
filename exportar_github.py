"""
Exporta la base de datos a JSON para GitHub Pages y hace push.
Correr después de sync_subir.py:

    python exportar_github.py
"""
import json
import sqlite3
import subprocess
from pathlib import Path

DB_PATH = Path(__file__).parent / "hospital_data.db"
DOCS_DIR = Path(__file__).parent / "docs"
JSON_PATH = DOCS_DIR / "data.json"


def exportar():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT nombre_completo, cedula, edad, sexo, diagnostico,
               hospital, fecha_lista, fuente_url
        FROM registros
        ORDER BY hospital, nombre_completo
    """).fetchall()
    con.close()

    registros = []
    for r in rows:
        registros.append({
            "n": r["nombre_completo"] or "",
            "h": r["hospital"] or "",
            "ci": r["cedula"] or "",
            "e": r["edad"] or "",
            "s": r["sexo"] or "",
            "d": r["diagnostico"] or "",
            "f": r["fecha_lista"] or "",
            "u": ("https://listashospitalarias.pythonanywhere.com" + r["fuente_url"]) if r["fuente_url"] else "",
        })

    DOCS_DIR.mkdir(exist_ok=True)
    JSON_PATH.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    print(f"Exportados {len(registros)} registros a {JSON_PATH}")
    return len(registros)


def push_github(total):
    repo = Path(__file__).parent
    subprocess.run(["git", "add", "docs/data.json", "docs/index.html"], cwd=repo)
    subprocess.run(["git", "commit", "-m", f"Actualiza datos: {total} personas"], cwd=repo)
    resultado = subprocess.run(["git", "push"], cwd=repo, capture_output=True, text=True)
    if resultado.returncode == 0:
        print("Push exitoso a GitHub Pages")
    else:
        print(f"Error en push: {resultado.stderr}")


def main():
    total = exportar()
    print("Subiendo a GitHub Pages...")
    push_github(total)
    print(f"\nListo. Disponible en:")
    print(f"  https://scimoncfd.github.io/terremoto-venezuela-ocr")


if __name__ == "__main__":
    main()
