"""
Aplicación web para digitalización y búsqueda de listas hospitalarias.
Terremoto Venezuela 2026.

Uso:
    export ANTHROPIC_API_KEY='sk-ant-...'
    python app.py
"""

import os
import hashlib
import json
import base64
import sqlite3
import uuid
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

import anthropic
from flask import Flask, render_template, request, redirect, url_for, flash, g, session
from rapidfuzz import fuzz, process
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "terremoto-vzla-2026")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "julett")

BASE_DIR = Path(__file__).parent
DB_PATH = str(BASE_DIR / "hospital_data.db")
UPLOAD_FOLDER = BASE_DIR / "imagenes_web"
EXTENSIONES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
UPLOAD_FOLDER.mkdir(exist_ok=True)

PROMPT_EXTRACCION = """Eres un asistente que extrae datos de listas médicas de hospitales venezolanos escritas a mano o en pizarra.

Analiza esta imagen y extrae TODOS los registros de personas que puedas ver, sin omitir ninguno.

Para cada persona extrae estos campos (usa null si no está visible):
- nombre_completo: nombre y apellido tal como aparece
- cedula: número de cédula (solo dígitos, sin puntos ni espacios)
- edad: edad si aparece
- sexo: "F" o "M" si aparece
- diagnostico: diagnóstico o condición médica si aparece
- notas: cualquier símbolo especial (* , subrayado, cruz, etc.)

Responde ÚNICAMENTE con JSON válido, sin texto adicional:
{
  "registros": [
    {
      "nombre_completo": "...",
      "cedula": "...",
      "edad": "...",
      "sexo": "...",
      "diagnostico": "...",
      "notas": "..."
    }
  ]
}"""


# ── Base de datos ──────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_completo TEXT,
            cedula          TEXT,
            edad            TEXT,
            sexo            TEXT,
            diagnostico     TEXT,
            notas           TEXT,
            hospital        TEXT NOT NULL,
            fecha_lista     TEXT,
            fuente_imagen   TEXT,
            procesado_en    TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS imagenes_procesadas (
            hash        TEXT PRIMARY KEY,
            ruta        TEXT,
            hospital    TEXT,
            procesado_en TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_cedula ON registros(cedula)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_nombre ON registros(nombre_completo)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hospital ON registros(hospital)")
    con.commit()
    con.close()


# ── OCR ───────────────────────────────────────────────────────────────────────

def hash_archivo(ruta):
    with open(ruta, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def imagen_a_base64(ruta):
    sufijo = Path(ruta).suffix.lower()
    tipos = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".png": "image/png", ".webp": "image/webp"}
    media_type = tipos.get(sufijo, "image/jpeg")
    with open(ruta, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def extraer_con_ocr(ruta):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    cliente = anthropic.Anthropic(api_key=api_key)
    img_data, media_type = imagen_a_base64(ruta)

    respuesta = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
                {"type": "text", "text": PROMPT_EXTRACCION}
            ],
        }],
    )

    texto = respuesta.content[0].text.strip()
    if texto.startswith("```"):
        lineas = texto.split("\n")
        texto = "\n".join(lineas[1:-1] if lineas[-1].strip() == "```" else lineas[1:])

    return json.loads(texto)


def solo_ocr(ruta, hospital):
    con = sqlite3.connect(DB_PATH)
    h = hash_archivo(ruta)
    ya_procesada = con.execute(
        "SELECT hospital FROM imagenes_procesadas WHERE hash = ?", (h,)
    ).fetchone()
    con.close()
    if ya_procesada:
        return None, ya_procesada[0]
    datos = extraer_con_ocr(ruta)
    return datos.get("registros", []), None


def guardar_registros_confirmados(ruta, hospital, fecha, registros):
    con = sqlite3.connect(DB_PATH)
    h = hash_archivo(ruta)
    ahora = datetime.now().isoformat()
    fecha_lista = fecha or datetime.now().strftime("%Y-%m-%d")
    insertados = 0
    duplicados = 0

    for r in registros:
        cedula = r.get("cedula") or None
        nombre = r.get("nombre_completo", "").strip()
        if not nombre:
            continue
        if cedula:
            ya_existe = con.execute(
                "SELECT 1 FROM registros WHERE cedula = ? AND hospital = ?", (cedula, hospital)
            ).fetchone()
        else:
            ya_existe = con.execute(
                "SELECT 1 FROM registros WHERE nombre_completo = ? AND hospital = ?", (nombre, hospital)
            ).fetchone()
        if ya_existe:
            duplicados += 1
            continue
        con.execute("""
            INSERT INTO registros (nombre_completo, cedula, edad, sexo, diagnostico, notas, hospital, fecha_lista, fuente_imagen, procesado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (nombre, cedula, r.get("edad"), r.get("sexo"), r.get("diagnostico"), r.get("notas"), hospital, fecha_lista, str(ruta), ahora))
        insertados += 1

    con.execute(
        "INSERT OR IGNORE INTO imagenes_procesadas (hash, ruta, hospital, procesado_en) VALUES (?, ?, ?, ?)",
        (h, str(ruta), hospital, ahora)
    )
    con.commit()
    con.close()
    return insertados, duplicados


# ── Búsqueda ──────────────────────────────────────────────────────────────────

def normalizar(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def buscar_nombre(nombre, umbral=70):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    todos = con.execute(
        "SELECT nombre_completo, cedula, edad, sexo, diagnostico, hospital, fecha_lista FROM registros"
    ).fetchall()
    con.close()

    if not todos:
        return []

    nombres = [r["nombre_completo"] or "" for r in todos]
    query = normalizar(nombre)
    nombres_norm = [normalizar(n) for n in nombres]

    resultados = []
    vistos = set()
    for i, n in enumerate(nombres_norm):
        score = max(
            fuzz.token_sort_ratio(query, n),
            fuzz.partial_ratio(query, n)
        )
        if score >= umbral and i not in vistos:
            vistos.add(i)
            r = dict(todos[i])
            r["similitud"] = round(score)
            resultados.append(r)

    return sorted(resultados, key=lambda x: x["similitud"], reverse=True)[:10]


def hospitales_existentes():
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT DISTINCT hospital FROM registros ORDER BY hospital").fetchall()
    con.close()
    return [r[0] for r in rows]


# ── Rutas ─────────────────────────────────────────────────────────────────────

def admin_autenticado():
    return session.get("admin") is True


@app.route("/")
def index():
    con = sqlite3.connect(DB_PATH)
    total = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    total_hospitales = con.execute("SELECT COUNT(DISTINCT hospital) FROM registros").fetchone()[0]
    con.close()
    return render_template("buscar.html", query="", resultados=[], total=total, total_hospitales=total_hospitales)


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if admin_autenticado():
        return redirect(url_for("subir"))
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("subir"))
        flash("Contraseña incorrecta.")
    return render_template("admin_login.html")


@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("index"))


def _ocr_y_revisar(ruta_str):
    ruta = Path(ruta_str)
    try:
        registros, hospital_original = solo_ocr(ruta, "")
    except Exception as e:
        flash(f"Error procesando {ruta.name}: {str(e)}")
        return _siguiente_en_cola()

    if registros is None:
        session["resumen"] = session.get("resumen", []) + [
            {"hospital": hospital_original, "insertados": 0, "duplicados": 0, "omitida": True}
        ]
        session["procesadas"] = session.get("procesadas", 0) + 1
        return _siguiente_en_cola()

    token = uuid.uuid4().hex
    ruta_temp = Path(tempfile.gettempdir()) / f"ocr_{token}.json"
    ruta_temp.write_text(json.dumps({
        "ruta": ruta_str, "registros": registros
    }, ensure_ascii=False))
    return redirect(url_for("revisar", token=token))


def _siguiente_en_cola():
    cola = session.get("cola", [])
    if cola:
        session["cola"] = cola[1:]
        return _ocr_y_revisar(cola[0])
    return redirect(url_for("resumen_final"))


@app.route("/subir", methods=["GET", "POST"])
def subir():
    if not admin_autenticado():
        return redirect(url_for("admin_login"))

    if request.method == "GET":
        return render_template("subir.html", hospitales=hospitales_existentes())

    fotos = request.files.getlist("fotos")
    fotos = [f for f in fotos if f.filename]

    if not fotos:
        flash("Selecciona al menos una foto.")
        return render_template("subir.html", hospitales=hospitales_existentes())

    if not os.environ.get("ANTHROPIC_API_KEY"):
        flash("Error de configuración: API key no definida.")
        return render_template("subir.html", hospitales=hospitales_existentes())

    rutas = []
    for foto in fotos:
        sufijo = Path(foto.filename).suffix.lower()
        if sufijo not in EXTENSIONES_PERMITIDAS:
            continue
        nombre_archivo = f"{uuid.uuid4().hex}{sufijo}"
        ruta = UPLOAD_FOLDER / nombre_archivo
        foto.save(ruta)
        rutas.append(str(ruta))

    if not rutas:
        flash("Ningún archivo tiene formato válido (JPG, PNG, WEBP).")
        return render_template("subir.html", hospitales=hospitales_existentes())

    session["cola"] = rutas[1:]
    session["total"] = len(rutas)
    session["procesadas"] = 0
    session["resumen"] = []

    return _ocr_y_revisar(rutas[0])


@app.route("/revisar/<token>", methods=["GET", "POST"])
def revisar(token):
    if not admin_autenticado():
        return redirect(url_for("admin_login"))

    ruta_temp = Path(tempfile.gettempdir()) / f"ocr_{token}.json"
    if not ruta_temp.exists():
        flash("Sesión expirada. Sube las fotos de nuevo.")
        return redirect(url_for("subir"))

    datos = json.loads(ruta_temp.read_text())

    if request.method == "POST":
        hospital = request.form.get("hospital", "").strip()
        fecha = request.form.get("fecha", "").strip()
        nombres = request.form.getlist("nombre")
        cedulas = request.form.getlist("cedula")
        edades = request.form.getlist("edad")
        sexos = request.form.getlist("sexo")
        eliminar = request.form.getlist("eliminar")

        if not hospital:
            flash("El nombre del hospital es obligatorio.")
            procesadas = session.get("procesadas", 0)
            total = session.get("total", 1)
            return render_template("revisar.html", datos=datos, token=token,
                                   procesadas=procesadas + 1, total=total,
                                   hospitales=hospitales_existentes())

        registros_confirmados = []
        for i, nombre in enumerate(nombres):
            if str(i) in eliminar or not nombre.strip():
                continue
            registros_confirmados.append({
                "nombre_completo": nombre.strip(),
                "cedula": cedulas[i].strip() or None,
                "edad": edades[i].strip() or None,
                "sexo": sexos[i] or None,
                "diagnostico": None,
                "notas": None,
            })

        insertados, duplicados = guardar_registros_confirmados(
            datos["ruta"], hospital, fecha, registros_confirmados
        )
        ruta_temp.unlink(missing_ok=True)

        session["resumen"] = session.get("resumen", []) + [
            {"hospital": hospital, "insertados": insertados, "duplicados": duplicados, "omitida": False}
        ]
        session["procesadas"] = session.get("procesadas", 0) + 1

        return _siguiente_en_cola()

    procesadas = session.get("procesadas", 0)
    total = session.get("total", 1)
    return render_template("revisar.html", datos=datos, token=token,
                           procesadas=procesadas + 1, total=total,
                           hospitales=hospitales_existentes())


@app.route("/resumen")
def resumen_final():
    if not admin_autenticado():
        return redirect(url_for("admin_login"))
    resumen = session.pop("resumen", [])
    total_insertados = sum(r["insertados"] for r in resumen)
    return render_template("resumen_final.html", resumen=resumen, total_insertados=total_insertados)


@app.route("/buscar")
def buscar():
    query = request.args.get("q", "").strip()
    resultados = []
    if query:
        resultados = buscar_nombre(query)
    return render_template("buscar.html", query=query, resultados=resultados, total=None, total_hospitales=None)


init_db()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=5000)
