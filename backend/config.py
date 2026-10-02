# =========================================================
# File WSGI di PythonAnywhere
# Si apre dalla tab "Web" -> sezione "Code" -> link "WSGI configuration file"
# Sostituisci TUTTO il contenuto del file con questo.
# =========================================================

import os
import sys

# ---------------------------------------------------------
# DA MODIFICARE
# ---------------------------------------------------------
USERNAME = "N1GH7M4R3"               # username PythonAnywhere
PROJECT_FOLDER = "reflections"             # cartella in /home/USERNAME/ dove sta main.py
SECRET_PEPPER = "hwiooi389y3891rg192e8doefieir3iiowoe5w5ef54w4e5e"  # non cambiarla dopo il lancio
# ---------------------------------------------------------

# Da qui in giù non serve toccare nulla
PROJECT_DIR = f"/home/{USERNAME}/{PROJECT_FOLDER}"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Le variabili d'ambiente DEVONO essere impostate PRIMA di importare main
os.environ["SECRET_PEPPER"] = SECRET_PEPPER
# Opzionale: sposta il file del database (default: supporters.db accanto a main.py)
# os.environ["DB_PATH"] = f"/home/{USERNAME}/data/supporters.db"

# PythonAnywhere cerca una variabile chiamata "application"
from main import app as application  # noqa: E402
