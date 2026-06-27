"""
Descarga todos los desaparecidos de vea2026.com y los guarda en CSV.

Uso:
    python descargar_vea2026.py
    python descargar_vea2026.py --salida mis_desaparecidos.csv
"""

import json
import csv
import argparse
import urllib.request
import urllib.error
from datetime import datetime

CONVEX_URL = "https://jovial-shepherd-115.convex.cloud/api/query"


def descargar_todos():
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
            print(f"Error de red: {e}")
            break

        if data.get("status") != "success":
            print(f"Error en API: {data.get('errorMessage')}")
            break

        valor = data["value"]
        page = valor.get("page", [])
        personas.extend(page)
        print(f"  Descargados: {len(personas)}...", end="\r")

        if valor.get("isDone"):
            break
        cursor = valor.get("continueCursor")
        if not cursor:
            break

    print(f"\n  Total: {len(personas)} personas")
    return personas


def guardar_csv(personas, ruta):
    campos = [
        "nombre", "cedula", "edad", "genero",
        "ultima_ubicacion", "sin_contacto_desde",
        "descripcion", "zona", "estado", "fecha_reporte"
    ]

    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for p in personas:
            ts = p.get("reportedAt")
            if ts:
                fecha = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
            else:
                fecha = ""
            writer.writerow({
                "nombre": p.get("fullName", ""),
                "cedula": p.get("documentId", ""),
                "edad": p.get("age", ""),
                "genero": p.get("gender", ""),
                "ultima_ubicacion": p.get("lastSeenLocation", ""),
                "sin_contacto_desde": p.get("noContactSince", ""),
                "descripcion": p.get("description", ""),
                "zona": p.get("zone", ""),
                "estado": p.get("status", ""),
                "fecha_reporte": fecha,
            })


def main():
    parser = argparse.ArgumentParser(description="Descarga desaparecidos de vea2026.com")
    parser.add_argument("--salida", default="desaparecidos_vea2026.csv", help="Nombre del archivo CSV")
    args = parser.parse_args()

    print("Descargando desaparecidos de vea2026.com...")
    personas = descargar_todos()

    print(f"Guardando en {args.salida}...")
    guardar_csv(personas, args.salida)
    print(f"Listo. {len(personas)} personas guardadas en {args.salida}")


if __name__ == "__main__":
    main()
