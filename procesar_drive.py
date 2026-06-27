"""
Procesamiento batch del Drive de hospital.
Uso:
    python procesar_drive.py /ruta/al/drive
    python procesar_drive.py /ruta/al/drive --seco   (solo muestra qué procesaría, sin OCR)
"""

import os
import sys
import json
import hashlib
import base64
import sqlite3
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

import anthropic
import fitz  # pymupdf
import docx

DB_PATH = str(Path(__file__).parent / "hospital_data.db")

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}

PROMPT_IMAGEN = """Eres un asistente que extrae datos de listas médicas de hospitales venezolanos escritas a mano o impresas.

Analiza esta imagen y extrae TODOS los registros de personas que puedas ver, sin omitir ninguno.

Para cada persona extrae (usa null si no está visible):
- nombre_completo
- cedula (solo dígitos)
- edad
- sexo ("F" o "M")
- diagnostico
- notas
- hospital (nombre del hospital si aparece en la imagen para ese registro, si no null)

Responde ÚNICAMENTE con JSON válido:
{"registros": [{"nombre_completo": "...", "cedula": "...", "edad": "...", "sexo": "...", "diagnostico": "...", "notas": "...", "hospital": "..."}]}"""

PROMPT_TEXTO = """Eres un asistente que extrae datos de listas médicas de hospitales venezolanos.

Analiza este texto y extrae TODOS los registros de personas que puedas encontrar.

Si el texto menciona el nombre del hospital para cada persona, inclúyelo en el campo hospital.
Si no se menciona hospital, usa null.

Para cada persona extrae (usa null si no está visible):
- nombre_completo
- cedula (solo dígitos)
- edad
- sexo ("F" o "M")
- diagnostico
- notas
- hospital (si aparece en el texto, si no null)

Responde ÚNICAMENTE con JSON válido:
{"registros": [{"nombre_completo": "...", "cedula": "...", "edad": "...", "sexo": "...", "diagnostico": "...", "notas": "...", "hospital": "..."}]}"""


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS registros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_completo TEXT, nombre_normalizado TEXT, cedula TEXT, edad TEXT, sexo TEXT,
        diagnostico TEXT, notas TEXT, hospital TEXT NOT NULL,
        fecha_lista TEXT, fuente_imagen TEXT, procesado_en TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS imagenes_procesadas (
        hash TEXT PRIMARY KEY, ruta TEXT, hospital TEXT, procesado_en TEXT)""")
    # Agrega columna si la BD existente no la tiene
    columnas = [r[1] for r in con.execute("PRAGMA table_info(registros)").fetchall()]
    if "nombre_normalizado" not in columnas:
        con.execute("ALTER TABLE registros ADD COLUMN nombre_normalizado TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_nombre ON registros(nombre_completo)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_nombre_norm ON registros(nombre_normalizado)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hospital ON registros(hospital)")
    con.commit()
    con.close()


def normalizar(texto):
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def hash_bytes(data):
    return hashlib.md5(data).hexdigest()


def ya_procesado(h):
    con = sqlite3.connect(DB_PATH)
    r = con.execute("SELECT 1 FROM imagenes_procesadas WHERE hash=?", (h,)).fetchone()
    con.close()
    return r is not None


def marcar_procesado(h, ruta, hospital):
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT OR IGNORE INTO imagenes_procesadas (hash,ruta,hospital,procesado_en) VALUES (?,?,?,?)",
                (h, ruta, hospital, datetime.now().isoformat()))
    con.commit()
    con.close()


def guardar_registros(registros, hospital, fuente):
    con = sqlite3.connect(DB_PATH)
    insertados = duplicados = 0
    ahora = datetime.now().isoformat()
    hoy = datetime.now().strftime("%Y-%m-%d")

    for r in registros:
        nombre = (r.get("nombre_completo") or "").strip()
        if not nombre:
            continue
        # Para archivos consolidados, usar el hospital que Claude extrajo de la imagen
        # Para carpetas de hospital específico, siempre usar el nombre de la carpeta
        if hospital == "CONSOLIDADO":
            hosp = (r.get("hospital") or hospital or "").strip() or hospital
        else:
            hosp = hospital
        cedula = r.get("cedula") or None

        if cedula:
            existe = con.execute("SELECT 1 FROM registros WHERE cedula=? AND hospital=?", (cedula, hosp)).fetchone()
        else:
            existe = con.execute(
                "SELECT 1 FROM registros WHERE nombre_normalizado=? AND hospital=?",
                (normalizar(nombre), hosp)
            ).fetchone()

        if existe:
            duplicados += 1
            continue

        con.execute("""INSERT INTO registros
            (nombre_completo,nombre_normalizado,cedula,edad,sexo,diagnostico,notas,hospital,fecha_lista,fuente_imagen,procesado_en)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (nombre, normalizar(nombre), cedula, r.get("edad"), r.get("sexo"),
             r.get("diagnostico"), r.get("notas"), hosp, hoy, fuente, ahora))
        insertados += 1

    con.commit()
    con.close()
    return insertados, duplicados


def ocr_imagen_bytes(cliente, img_bytes, media_type):
    img_b64 = base64.standard_b64encode(img_bytes).decode()
    resp = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
            {"type": "text", "text": PROMPT_IMAGEN}
        ]}]
    )
    texto = resp.content[0].text.strip()
    if texto.startswith("```"):
        lineas = texto.split("\n")
        texto = "\n".join(lineas[1:-1] if lineas[-1].strip() == "```" else lineas[1:])
    return json.loads(texto).get("registros", [])


def ocr_texto(cliente, texto):
    resp = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": f"{PROMPT_TEXTO}\n\nTEXTO:\n{texto}"}]
    )
    t = resp.content[0].text.strip()
    if t.startswith("```"):
        lineas = t.split("\n")
        t = "\n".join(lineas[1:-1] if lineas[-1].strip() == "```" else lineas[1:])
    return json.loads(t).get("registros", [])


def procesar_imagen(cliente, ruta, hospital, seco):
    data = ruta.read_bytes()
    h = hash_bytes(data)
    if ya_procesado(h):
        print(f"  [SKIP] {ruta.name} (ya procesada)")
        return 0, 0

    if seco:
        print(f"  [SECO] OCR imagen: {ruta.name} → hospital: {hospital}")
        return 0, 0

    sufijo = ruta.suffix.lower()
    tipos = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    media_type = tipos.get(sufijo, "image/jpeg")

    try:
        registros = ocr_imagen_bytes(cliente, data, media_type)
        ins, dup = guardar_registros(registros, hospital, str(ruta))
        marcar_procesado(h, str(ruta), hospital)
        print(f"  [OK] {ruta.name} → {ins} nuevos, {dup} duplicados")
        return ins, dup
    except Exception as e:
        print(f"  [ERROR] {ruta.name}: {e}")
        return 0, 0


def procesar_pdf(cliente, ruta, hospital, seco):
    data = ruta.read_bytes()
    h = hash_bytes(data)

    doc = fitz.open(stream=data, filetype="pdf")
    total_ins = total_dup = 0

    for i, pagina in enumerate(doc):
        h_pag = hash_bytes(f"{h}_pag{i}".encode())
        if ya_procesado(h_pag):
            print(f"  [SKIP] {ruta.name} pág {i+1} (ya procesada)")
            continue

        if seco:
            print(f"  [SECO] OCR PDF: {ruta.name} pág {i+1} → hospital: {hospital}")
            continue

        try:
            # Renderiza la página como imagen PNG
            mat = fitz.Matrix(2, 2)  # 2x zoom para mejor calidad
            pix = pagina.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            registros = ocr_imagen_bytes(cliente, img_bytes, "image/png")
            ins, dup = guardar_registros(registros, hospital, f"{ruta} pág {i+1}")
            marcar_procesado(h_pag, f"{ruta} pág {i+1}", hospital)
            print(f"  [OK] {ruta.name} pág {i+1} → {ins} nuevos, {dup} duplicados")
            total_ins += ins
            total_dup += dup
        except Exception as e:
            print(f"  [ERROR] {ruta.name} pág {i+1}: {e}")

    doc.close()
    return total_ins, total_dup


def procesar_docx(cliente, ruta, hospital, seco):
    data = ruta.read_bytes()
    h = hash_bytes(data)
    if ya_procesado(h):
        print(f"  [SKIP] {ruta.name} (ya procesado)")
        return 0, 0

    if seco:
        print(f"  [SECO] Texto DOCX: {ruta.name} → hospital: {hospital}")
        return 0, 0

    try:
        doc = docx.Document(str(ruta))
        texto = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if len(texto) < 20:
            print(f"  [SKIP] {ruta.name} sin texto útil")
            return 0, 0

        registros = ocr_texto(cliente, texto)
        ins, dup = guardar_registros(registros, hospital, str(ruta))
        marcar_procesado(h, str(ruta), hospital)
        print(f"  [OK] {ruta.name} → {ins} nuevos, {dup} duplicados")
        return ins, dup
    except Exception as e:
        print(f"  [ERROR] {ruta.name}: {e}")
        return 0, 0


def hospital_de_ruta(ruta, raiz):
    """Usa el nombre de la carpeta padre como hospital. Si está en la raíz, usa 'CONSOLIDADO'."""
    padre = ruta.parent
    if padre == raiz:
        return "CONSOLIDADO"
    return padre.name.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("carpeta", help="Ruta a la carpeta del Drive descargada")
    parser.add_argument("--seco", action="store_true", help="Solo muestra qué procesaría sin hacer OCR")
    args = parser.parse_args()

    raiz = Path(args.carpeta)
    if not raiz.exists():
        print(f"Error: {raiz} no existe")
        sys.exit(1)

    init_db()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.seco:
        print("Error: ANTHROPIC_API_KEY no definida")
        sys.exit(1)

    cliente = anthropic.Anthropic(api_key=api_key) if not args.seco else None

    archivos = sorted(raiz.rglob("*"))
    archivos = [f for f in archivos if f.is_file()]

    # Filtra archivos que no son datos (solo links, etc.)
    ignorar = {"link busca y registra personas"}
    archivos = [f for f in archivos if f.stem.lower() not in ignorar]

    print(f"\nArchivos a procesar: {len(archivos)}")
    print(f"Base de datos: {DB_PATH}\n")

    total_ins = total_dup = 0

    for archivo in archivos:
        hospital = hospital_de_ruta(archivo, raiz)
        ext = archivo.suffix.lower()

        if ext in EXTENSIONES_IMAGEN:
            ins, dup = procesar_imagen(cliente, archivo, hospital, args.seco)
        elif ext == ".pdf":
            ins, dup = procesar_pdf(cliente, archivo, hospital, args.seco)
        elif ext == ".docx":
            ins, dup = procesar_docx(cliente, archivo, hospital, args.seco)
        else:
            print(f"  [IGNORADO] {archivo.name}")
            continue

        total_ins += ins
        total_dup += dup

    print(f"\n{'='*50}")
    print(f"TOTAL: {total_ins} registros nuevos, {total_dup} duplicados")
    print(f"Base de datos: {DB_PATH}")


if __name__ == "__main__":
    main()
