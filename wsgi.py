import sys
import os
from pathlib import Path

# Ruta del proyecto en PythonAnywhere — ajusta 'tuusuario' y 'OCR_A_Mano'
project_home = str(Path(__file__).parent)
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Variables de entorno — también se pueden poner en el panel web de PythonAnywhere
# os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-...'
# os.environ['ADMIN_PASSWORD'] = 'julett'
# os.environ['SECRET_KEY'] = 'una-clave-secreta-larga'

from app import app as application
