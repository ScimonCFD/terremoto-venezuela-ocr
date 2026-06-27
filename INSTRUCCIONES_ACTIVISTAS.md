# Cómo agregar nuevas listas hospitalarias

Estas instrucciones son para las personas autorizadas a actualizar la base de datos.

---

## Lo que necesitas (una sola vez)

1. Una computadora con Windows
2. El instalador del programa (te lo manda Simón por WhatsApp)
3. Dos claves que te manda Simón por WhatsApp:
   - La clave de Anthropic (para leer las fotos)
   - El token de PythonAnywhere (para subir los datos)

---

## Instalación (una sola vez)

1. Descarga el instalador `instalar_windows.bat` que te mandó Simón
2. Haz doble clic en él
3. Sigue las instrucciones en pantalla — te pedirá las dos claves

---

## Cada vez que quieras agregar listas nuevas

### Paso 1 — Descarga las fotos del Drive

1. Abre la carpeta de Google Drive compartida
2. Selecciona todo (Ctrl+A)
3. Haz clic derecho → **Descargar**
4. Google te descargará un archivo ZIP
5. Descomprímelo en cualquier lugar de tu computadora (por ejemplo, en el Escritorio)

### Paso 2 — Corre el programa

1. Haz doble clic en `procesar.bat`
2. Cuando te pregunte la carpeta, escribe la ruta donde descomprimiste el ZIP
   - Ejemplo: `C:\Users\TuNombre\Desktop\listas`
3. El programa hará todo solo:
   - Descarga la base de datos actualizada
   - Procesa solo las fotos nuevas (las que ya procesó antes las ignora)
   - Sube todo a la web
4. Cuando diga **"Listo"**, ya está publicado

---

## Importante

- No cierres la ventana mientras está procesando
- Si dos personas procesan al mismo tiempo puede haber conflictos — coordinen por WhatsApp
- Si el programa dice "CANCELADO: tu base de datos tiene menos registros", no pasó nada malo — simplemente vuelve a correr `procesar.bat`

---

## ¿Dónde se ve el resultado?

- **Venezuela (sin VPN):** https://scimoncfd.github.io/terremoto-venezuela-ocr
- **Internacional:** https://listashospitalarias.pythonanywhere.com
