"""
Búsqueda en la base de datos de pacientes hospitalarios.
Soporta búsqueda por nombre (aproximada/fuzzy) o por cédula exacta.

Uso:
    python buscar.py "Maria Gonzalez"
    python buscar.py --cedula 12345678
    python buscar.py --listar-todo
"""

import sqlite3
import argparse
import csv
import sys
import unicodedata
from rapidfuzz import fuzz, process

DB_PATH = "hospital_data.db"


def normalizar(texto):
    """Minúsculas, sin acentos, sin caracteres especiales."""
    if not texto:
        return ""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto


def cargar_todos(con):
    cur = con.execute("SELECT * FROM registros")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def buscar_por_cedula(con, cedula):
    cedula_limpia = cedula.replace(".", "").replace("-", "").replace(" ", "")
    cur = con.execute(
        "SELECT * FROM registros WHERE cedula = ?", (cedula_limpia,)
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def buscar_por_nombre(con, nombre, umbral=75):
    todos = cargar_todos(con)
    nombres = [r["nombre_completo"] or "" for r in todos]

    query = normalizar(nombre)
    nombres_norm = [normalizar(n) for n in nombres]

    encontrados = []
    vistos = set()
    for i, n in enumerate(nombres_norm):
        score = max(
            fuzz.token_sort_ratio(query, n),
            fuzz.partial_ratio(query, n)
        )
        if score >= umbral and i not in vistos:
            vistos.add(i)
            r = todos[i].copy()
            r["_similitud"] = score
            encontrados.append(r)

    return sorted(encontrados, key=lambda x: x["_similitud"], reverse=True)[:10]


def imprimir_registro(r):
    similitud = r.pop("_similitud", None)
    linea_sim = f" [similitud: {similitud}%]" if similitud is not None else ""
    print(f"\n{'─'*50}")
    print(f"NOMBRE:      {r.get('nombre_completo') or '—'}{linea_sim}")
    print(f"CÉDULA:      {r.get('cedula') or '—'}")
    print(f"EDAD:        {r.get('edad') or '—'}   SEXO: {r.get('sexo') or '—'}")
    print(f"SITIO:       {r.get('sitio') or '—'}")
    print(f"DIAGNÓSTICO: {r.get('diagnostico') or '—'}")
    print(f"MED:         {r.get('med') or '—'}")
    if r.get("notas"):
        print(f"NOTAS:       {r['notas']}")
    print(f"LISTA:       {r.get('titulo_lista') or '—'}  |  HOSPITAL: {r.get('hospital') or '—'}")
    print(f"FUENTE:      {r.get('fuente_imagen') or '—'}")


def exportar_csv(con, ruta):
    registros = cargar_todos(con)
    if not registros:
        print("No hay registros para exportar.")
        return
    campos = ["nombre_completo", "cedula", "edad", "sexo", "sitio", "diagnostico",
              "med", "notas", "titulo_lista", "hospital", "fecha_lista", "fuente_imagen"]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(registros)
    print(f"Exportados {len(registros)} registros a: {ruta}")


def main():
    parser = argparse.ArgumentParser(description="Buscar pacientes en base de datos hospitalaria")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("nombre", nargs="?", help="Nombre a buscar (búsqueda aproximada)")
    grupo.add_argument("--cedula", help="Cédula exacta a buscar")
    grupo.add_argument("--listar-todo", action="store_true", help="Mostrar todos los registros")
    grupo.add_argument("--exportar-csv", metavar="ARCHIVO.csv", help="Exportar toda la base de datos a CSV")
    parser.add_argument("--db", default=DB_PATH, help=f"Base de datos (default: {DB_PATH})")
    parser.add_argument("--umbral", type=int, default=75, help="Similitud mínima 0-100 (default: 75)")
    args = parser.parse_args()

    try:
        con = sqlite3.connect(args.db)
    except Exception as e:
        print(f"ERROR abriendo base de datos: {e}")
        sys.exit(1)

    total_db = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    print(f"Base de datos: {total_db} registros totales")

    if args.exportar_csv:
        exportar_csv(con, args.exportar_csv)

    elif args.listar_todo:
        registros = cargar_todos(con)
        for r in registros:
            imprimir_registro(r)
        print(f"\n{'─'*50}")
        print(f"Total mostrados: {len(registros)}")

    elif args.cedula:
        registros = buscar_por_cedula(con, args.cedula)
        if registros:
            for r in registros:
                imprimir_registro(r)
        else:
            print(f"No se encontró cédula: {args.cedula}")

    elif args.nombre:
        registros = buscar_por_nombre(con, args.nombre, args.umbral)
        if registros:
            print(f"Resultados para '{args.nombre}':")
            for r in registros:
                imprimir_registro(r)
        else:
            print(f"No se encontraron coincidencias para '{args.nombre}' (umbral: {args.umbral}%)")
            print("Prueba con --umbral 60 para resultados más amplios")

    con.close()


if __name__ == "__main__":
    main()
