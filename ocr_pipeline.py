"""
OCR pipeline para listas hospitalarias del terremoto Venezuela 2026.
Procesa imágenes (pizarras o papel) y extrae datos de pacientes a SQLite.

Uso:
    python ocr_pipeline.py --imagenes carpeta/con/fotos
    python ocr_pipeline.py --imagen foto_individual.jpg
"""

import anthropic
import base64
import hashlib
import json
import sqlite3
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = "hospital_data.db"
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

PROMPT_EXTRACCION = """Eres un asistente que extrae datos de listas médicas de hospitales venezolanos escritas a mano o en pizarra.

Analiza esta imagen y extrae TODOS los registros de personas que puedas ver, sin omitir ninguno.

Para cada persona extrae estos campos (usa null si no está visible):
- nombre_completo: nombre y apellido tal como aparece
- cedula: número de cédula (solo dígitos, sin puntos ni espacios)
- edad: edad si aparece
- sexo: "F" o "M" si aparece
- med: contenido de columna MED o nombre médico/doctor si aparece
- diagnostico: diagnóstico o condición médica si aparece
- sitio: lugar, estado o municipio si aparece
- notas: cualquier símbolo especial (* , subrayado, cruz, etc.) o anotación adicional

Responde ÚNICAMENTE con JSON válido, sin texto adicional:
{
  "titulo": "título o encabezado de la lista (ej: INGRESOS, UCI, etc.)",
  "hospital": "nombre del hospital si aparece",
  "fecha_lista": "fecha si aparece en la imagen",
  "registros": [
    {
      "nombre_completo": "...",
      "cedula": "...",
      "edad": "...",
      "sexo": "...",
      "med": "...",
      "diagnostico": "...",
      "sitio": "...",
      "notas": "..."
    }
  ]
}"""


def init_db(db_path: str = DB_PATH):
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_completo TEXT,
            cedula          TEXT,
            edad            TEXT,
            sexo            TEXT,
            med             TEXT,
            diagnostico     TEXT,
            sitio           TEXT,
            notas           TEXT,
            titulo_lista    TEXT,
            hospital        TEXT,
            fecha_lista     TEXT,
            fuente_imagen   TEXT,
            procesado_en    TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS imagenes_procesadas (
            hash TEXT PRIMARY KEY,
            ruta TEXT,
            procesado_en TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_cedula ON registros(cedula)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_nombre ON registros(nombre_completo)")
    con.commit()
    return con


def hash_imagen(ruta: Path) -> str:
    with open(ruta, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def imagen_ya_procesada(con, h: str) -> bool:
    return con.execute("SELECT 1 FROM imagenes_procesadas WHERE hash = ?", (h,)).fetchone() is not None


def registrar_imagen(con, h: str, ruta: Path):
    con.execute(
        "INSERT INTO imagenes_procesadas (hash, ruta, procesado_en) VALUES (?, ?, ?)",
        (h, str(ruta), datetime.now().isoformat())
    )
    con.commit()


def imagen_a_base64(ruta: Path):
    sufijo = ruta.suffix.lower()
    tipos = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
    media_type = tipos.get(sufijo, "image/jpeg")
    with open(ruta, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def extraer_datos_imagen(cliente: anthropic.Anthropic, ruta: Path) -> dict:
    print(f"  Procesando: {ruta.name}")
    img_data, media_type = imagen_a_base64(ruta)

    respuesta = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_data,
                    },
                },
                {
                    "type": "text",
                    "text": PROMPT_EXTRACCION
                }
            ],
        }],
    )

    texto = respuesta.content[0].text.strip()

    # Limpiar si el modelo envuelve en ```json ... ```
    if texto.startswith("```"):
        lineas = texto.split("\n")
        texto = "\n".join(lineas[1:-1] if lineas[-1].strip() == "```" else lineas[1:])

    return json.loads(texto)


def guardar_registros(con, datos: dict, fuente: str):
    ahora = datetime.now().isoformat()
    titulo = datos.get("titulo")
    hospital = datos.get("hospital")
    fecha_lista = datos.get("fecha_lista")
    insertados = 0
    duplicados = 0

    for r in datos.get("registros", []):
        cedula = r.get("cedula")
        nombre = r.get("nombre_completo")

        # Si tiene cédula, no insertar si ya existe
        if cedula:
            ya_existe = con.execute(
                "SELECT 1 FROM registros WHERE cedula = ?", (cedula,)
            ).fetchone()
            if ya_existe:
                duplicados += 1
                continue

        # Sin cédula: no insertar si ya existe el mismo nombre exacto
        elif nombre:
            ya_existe = con.execute(
                "SELECT 1 FROM registros WHERE nombre_completo = ? AND cedula IS NULL",
                (nombre,)
            ).fetchone()
            if ya_existe:
                duplicados += 1
                continue

        con.execute("""
            INSERT INTO registros
                (nombre_completo, cedula, edad, sexo, med, diagnostico,
                 sitio, notas, titulo_lista, hospital, fecha_lista,
                 fuente_imagen, procesado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nombre, cedula,
            r.get("edad"), r.get("sexo"), r.get("med"), r.get("diagnostico"),
            r.get("sitio"), r.get("notas"),
            titulo, hospital, fecha_lista, fuente, ahora,
        ))
        insertados += 1

    con.commit()
    if duplicados:
        print(f"  {duplicados} duplicados ignorados")
    return insertados


def procesar_imagen(cliente, con, ruta: Path):
    h = hash_imagen(ruta)
    if imagen_ya_procesada(con, h):
        print(f"  OMITIDA (ya procesada): {ruta.name}")
        return 0
    try:
        datos = extraer_datos_imagen(cliente, ruta)
        n = guardar_registros(con, datos, str(ruta))
        registrar_imagen(con, h, ruta)
        print(f"  OK: {n} registros nuevos de {ruta.name}")
        return n
    except json.JSONDecodeError as e:
        print(f"  ERROR JSON en {ruta.name}: {e}")
        return 0
    except Exception as e:
        print(f"  ERROR en {ruta.name}: {e}")
        return 0


def procesar_carpeta(cliente, con, carpeta: Path):
    imagenes = [p for p in sorted(carpeta.rglob("*")) if p.suffix.lower() in EXTENSIONES]
    if not imagenes:
        print(f"No se encontraron imágenes en {carpeta}")
        return
    print(f"\nEncontradas {len(imagenes)} imágenes en {carpeta}\n")
    total = 0
    for img in imagenes:
        total += procesar_imagen(cliente, con, img)
    print(f"\nTotal: {total} registros guardados en {DB_PATH}")


def main():
    parser = argparse.ArgumentParser(description="OCR de listas hospitalarias Venezuela 2026")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--imagenes", type=Path, help="Carpeta con imágenes a procesar")
    grupo.add_argument("--imagen", type=Path, help="Imagen individual a procesar")
    parser.add_argument("--db", default=DB_PATH, help=f"Ruta de la base de datos (default: {DB_PATH})")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: define la variable de entorno ANTHROPIC_API_KEY")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    cliente = anthropic.Anthropic(api_key=api_key)
    con = init_db(args.db)

    if args.imagen:
        procesar_imagen(cliente, con, args.imagen)
    else:
        procesar_carpeta(cliente, con, args.imagenes)

    con.close()


if __name__ == "__main__":
    main()
