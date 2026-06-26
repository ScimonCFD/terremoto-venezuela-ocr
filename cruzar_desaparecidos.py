"""
Cruza la lista de desaparecidos con los registros hospitalarios.

Formatos soportados para la lista de desaparecidos:
  - CSV con columnas: nombre_completo, cedula (mínimo)
  - Excel (.xlsx) con las mismas columnas

Uso:
    python cruzar_desaparecidos.py desaparecidos.csv
    python cruzar_desaparecidos.py desaparecidos.xlsx --umbral 80
    python cruzar_desaparecidos.py desaparecidos.csv --salida resultados.csv
"""

import sqlite3
import argparse
import csv
import sys
from pathlib import Path
from rapidfuzz import fuzz, process

DB_PATH = "hospital_data.db"


def leer_desaparecidos(ruta):
    sufijo = ruta.suffix.lower()
    if sufijo == ".csv":
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    elif sufijo in {".xlsx", ".xls"}:
        try:
            import openpyxl
        except ImportError:
            print("Para leer Excel instala: pip install openpyxl")
            sys.exit(1)
        wb = openpyxl.load_workbook(ruta, read_only=True)
        ws = wb.active
        filas = list(ws.iter_rows(values_only=True))
        encabezados = [str(c).strip() if c else f"col{i}" for i, c in enumerate(filas[0])]
        return [dict(zip(encabezados, fila)) for fila in filas[1:] if any(fila)]
    else:
        print(f"Formato no soportado: {sufijo}. Usa .csv o .xlsx")
        sys.exit(1)


def cargar_hospitalizados(con):
    cur = con.execute("SELECT * FROM registros")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def encontrar_columna(fila, candidatos):
    for c in candidatos:
        for k in fila:
            if k.lower().strip() == c.lower():
                return k
    return None


def cruzar(desaparecidos, hospitalizados, umbral):
    nombres_hosp = [h.get("nombre_completo") or "" for h in hospitalizados]
    resultados = []

    for d in desaparecidos:
        col_nombre = encontrar_columna(d, ["nombre_completo", "nombre", "name"])
        col_cedula = encontrar_columna(d, ["cedula", "ci", "cedula_identidad", "id"])

        nombre_d = d.get(col_nombre, "").strip() if col_nombre else ""
        cedula_d = str(d.get(col_cedula, "") or "").replace(".", "").replace("-", "").strip() if col_cedula else ""

        coincidencias_cedula = []
        if cedula_d:
            coincidencias_cedula = [h for h in hospitalizados if h.get("cedula") == cedula_d]

        coincidencias_nombre = []
        if nombre_d and not coincidencias_cedula:
            matches = process.extract(nombre_d, nombres_hosp, scorer=fuzz.token_sort_ratio, limit=3)
            for match_nombre, score, idx in matches:
                if score >= umbral:
                    h = hospitalizados[idx].copy()
                    h["_similitud_nombre"] = score
                    coincidencias_nombre.append(h)

        for h in coincidencias_cedula:
            resultados.append({
                "desaparecido_nombre": nombre_d,
                "desaparecido_cedula": cedula_d,
                "match_tipo": "CEDULA_EXACTA",
                "similitud": 100,
                "hospital_nombre": h.get("nombre_completo"),
                "hospital_cedula": h.get("cedula"),
                "hospital_edad": h.get("edad"),
                "hospital_sexo": h.get("sexo"),
                "hospital_sitio": h.get("sitio"),
                "hospital_diagnostico": h.get("diagnostico"),
                "hospital_notas": h.get("notas"),
                "fuente_imagen": h.get("fuente_imagen"),
            })

        for h in coincidencias_nombre:
            resultados.append({
                "desaparecido_nombre": nombre_d,
                "desaparecido_cedula": cedula_d,
                "match_tipo": "NOMBRE_APROXIMADO",
                "similitud": h["_similitud_nombre"],
                "hospital_nombre": h.get("nombre_completo"),
                "hospital_cedula": h.get("cedula"),
                "hospital_edad": h.get("edad"),
                "hospital_sexo": h.get("sexo"),
                "hospital_sitio": h.get("sitio"),
                "hospital_diagnostico": h.get("diagnostico"),
                "hospital_notas": h.get("notas"),
                "fuente_imagen": h.get("fuente_imagen"),
            })

    return resultados


def guardar_csv(resultados, ruta):
    if not resultados:
        return
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=resultados[0].keys())
        writer.writeheader()
        writer.writerows(resultados)


def main():
    parser = argparse.ArgumentParser(description="Cruzar desaparecidos con registros hospitalarios")
    parser.add_argument("desaparecidos", type=Path, help="Archivo CSV o Excel con lista de desaparecidos")
    parser.add_argument("--db", default=DB_PATH, help=f"Base de datos (default: {DB_PATH})")
    parser.add_argument("--umbral", type=int, default=80, help="Similitud mínima por nombre 0-100 (default: 80)")
    parser.add_argument("--salida", default="coincidencias.csv", help="Archivo de salida (default: coincidencias.csv)")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    desaparecidos = leer_desaparecidos(args.desaparecidos)
    hospitalizados = cargar_hospitalizados(con)
    con.close()

    print(f"Desaparecidos a buscar: {len(desaparecidos)}")
    print(f"Registros hospitalarios: {len(hospitalizados)}")
    print(f"Umbral de similitud: {args.umbral}%\n")

    resultados = cruzar(desaparecidos, hospitalizados, args.umbral)

    exactas = [r for r in resultados if r["match_tipo"] == "CEDULA_EXACTA"]
    aproximadas = [r for r in resultados if r["match_tipo"] == "NOMBRE_APROXIMADO"]

    print(f"Coincidencias por cédula exacta: {len(exactas)}")
    print(f"Coincidencias por nombre aproximado: {len(aproximadas)}")
    print(f"Total: {len(resultados)}\n")

    if resultados:
        guardar_csv(resultados, args.salida)
        print(f"Resultados guardados en: {args.salida}")

        print("\n=== COINCIDENCIAS POR CÉDULA ===")
        for r in exactas:
            print(f"  {r['desaparecido_nombre']} (CI: {r['desaparecido_cedula']}) → {r['hospital_nombre']} | {r['hospital_sitio']} | {r['hospital_diagnostico']}")

        if aproximadas:
            print("\n=== COINCIDENCIAS POR NOMBRE (verificar manualmente) ===")
            for r in aproximadas:
                print(f"  {r['desaparecido_nombre']} → {r['hospital_nombre']} [{r['similitud']}%] | {r['hospital_sitio']}")
    else:
        print("No se encontraron coincidencias.")


if __name__ == "__main__":
    main()
