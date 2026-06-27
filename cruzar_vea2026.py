"""
Descarga todos los desaparecidos de vea2026.com y los cruza con
la base de datos local de pacientes hospitalizados.

Uso:
    python cruzar_vea2026.py
    python cruzar_vea2026.py --exportar-csv resultados.csv
"""

import json
import sqlite3
import argparse
import csv
import sys
import urllib.request
import urllib.error
from pathlib import Path
from rapidfuzz import fuzz, process

DB_PATH = str(Path(__file__).parent / "hospital_data.db")
CONVEX_URL = "https://jovial-shepherd-115.convex.cloud/api/query"
UMBRAL = 80


def descargar_desaparecidos():
    """Descarga todos los registros de vea2026.com paginando la API."""
    personas = []
    cursor = None
    pagina = 0

    while True:
        pagina += 1
        payload = json.dumps({
            "path": "people:list",
            "args": {
                "paginationOpts": {"cursor": cursor, "id": pagina, "numItems": 200},
                "status": "missing"
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            CONVEX_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.URLError as e:
            print(f"Error de red en página {pagina}: {e}")
            break

        if data.get("status") != "success":
            print(f"Error en API: {data.get('errorMessage')}")
            break

        valor = data["value"]
        page = valor.get("page", [])
        personas.extend(page)

        print(f"  Descargados: {len(personas)} desaparecidos...", end="\r")

        if valor.get("isDone"):
            break
        cursor = valor.get("continueCursor")
        if not cursor:
            break

    print(f"\n  Total descargados: {len(personas)} desaparecidos")
    return personas


def cargar_hospitalizados():
    """Carga todos los pacientes de la base de datos local."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT nombre_completo, cedula, edad, sexo, hospital, fecha_lista FROM registros"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def cruzar(desaparecidos, hospitalizados):
    """Cruza ambas listas y devuelve coincidencias."""
    if not hospitalizados:
        print("La base de datos local está vacía.")
        return []

    nombres_hosp = [r["nombre_completo"] or "" for r in hospitalizados]
    coincidencias = []

    for d in desaparecidos:
        nombre_d = d.get("fullName", "") or ""
        cedula_d = d.get("documentId", "") or ""

        # Primero busca por cédula exacta si existe
        if cedula_d:
            for h in hospitalizados:
                if h.get("cedula") and h["cedula"].strip() == cedula_d.strip():
                    coincidencias.append({
                        "desaparecido": nombre_d,
                        "cedula_desaparecido": cedula_d,
                        "hospitalizado": h["nombre_completo"],
                        "hospital": h["hospital"],
                        "fecha_lista": h["fecha_lista"],
                        "similitud": 100,
                        "tipo": "cédula exacta"
                    })
                    continue

        # Luego busca por nombre fuzzy
        matches = process.extract(nombre_d, nombres_hosp, scorer=fuzz.token_sort_ratio, limit=1)
        if matches:
            mejor_nombre, score, idx = matches[0]
            if score >= UMBRAL:
                h = hospitalizados[idx]
                coincidencias.append({
                    "desaparecido": nombre_d,
                    "cedula_desaparecido": cedula_d,
                    "hospitalizado": h["nombre_completo"],
                    "hospital": h["hospital"],
                    "fecha_lista": h["fecha_lista"],
                    "similitud": round(score),
                    "tipo": "nombre aproximado" if score < 100 else "nombre exacto"
                })

    return sorted(coincidencias, key=lambda x: x["similitud"], reverse=True)


def main():
    parser = argparse.ArgumentParser(description="Cruza desaparecidos de vea2026.com con hospitalizados locales")
    parser.add_argument("--exportar-csv", metavar="ARCHIVO", help="Exporta resultados a CSV")
    args = parser.parse_args()

    print("Descargando desaparecidos de vea2026.com...")
    desaparecidos = descargar_desaparecidos()

    print("Cargando pacientes hospitalizados...")
    hospitalizados = cargar_hospitalizados()
    print(f"  {len(hospitalizados)} pacientes en la base de datos local")

    if not hospitalizados:
        print("No hay pacientes en la base de datos. Sube listas hospitalarias primero.")
        sys.exit(1)

    print(f"\nCruzando {len(desaparecidos)} desaparecidos con {len(hospitalizados)} hospitalizados...")
    coincidencias = cruzar(desaparecidos, hospitalizados)

    if not coincidencias:
        print("No se encontraron coincidencias.")
        return

    print(f"\n{'='*60}")
    print(f"COINCIDENCIAS ENCONTRADAS: {len(coincidencias)}")
    print(f"{'='*60}\n")

    for c in coincidencias:
        print(f"[{c['tipo'].upper()} — {c['similitud']}%]")
        print(f"  Buscado:      {c['desaparecido']}  (CI: {c['cedula_desaparecido'] or 'N/D'})")
        print(f"  Hospitalizado: {c['hospitalizado']}")
        print(f"  Hospital:     {c['hospital']}")
        print(f"  Fecha lista:  {c['fecha_lista']}")
        print()

    if args.exportar_csv:
        with open(args.exportar_csv, "w", newline="", encoding="utf-8") as f:
            campos = ["tipo", "similitud", "desaparecido", "cedula_desaparecido", "hospitalizado", "hospital", "fecha_lista"]
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(coincidencias)
        print(f"Exportado a {args.exportar_csv}")


if __name__ == "__main__":
    main()
