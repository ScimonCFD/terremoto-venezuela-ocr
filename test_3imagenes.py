"""Prueba con las primeras 3 imágenes del Hospital Luciani."""
import os, sys
from pathlib import Path

DRIVE = Path("/home/simon/Documents/Terremoto_Venezuela_2026/drive_v0/drive-download-20260626T230735Z-3-001")
sys.path.insert(0, str(Path(__file__).parent))

# Importa funciones del script principal
from procesar_drive import init_db, procesar_imagen, guardar_registros
import anthropic

init_db()
cliente = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

imagenes = sorted((DRIVE / "HOSPITAL LUCIANI CARACAS").glob("*.jpg"))[:3]
print(f"Procesando {len(imagenes)} imágenes de prueba...\n")

total_ins = total_dup = 0
for ruta in imagenes:
    ins, dup = procesar_imagen(cliente, ruta, "HOSPITAL LUCIANI CARACAS", False)
    total_ins += ins
    total_dup += dup

print(f"\nRESULTADO: {total_ins} registros nuevos, {total_dup} duplicados")
