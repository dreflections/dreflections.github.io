"""
Backend per il bottone "Support" di Reflections (Flask + SQLite / PythonAnywhere).

API JSON pura: il frontend (supporters.html, pagina statica) fa fetch
da JavaScript per leggere/scrivere i supporter. Contratto IDENTICO alla
versione FastAPI: stessi URL, stessi metodi, stessi JSON, stessi status code.

Endpoint:
  GET  /api/supporters   -> lista di tutti i supporter (JSON)
  POST /api/support      -> aggiunge un nickname, ritorna il suo user_id

Regole:
  - nickname validato con whitelist (niente <, >, ", ', tag HTML ecc.)
  - nickname UNIVOCO
  - 1 supporto per visitatore: il frontend genera un visitor_id casuale
    salvato in un cookie; qui viene hashato (SHA-256 + pepper) e salvato
    come visitor_hash, con vincolo UNIQUE.

Database: file SQLite locale (supporters.db) creato automaticamente
accanto a main.py. Percorso modificabile con la variabile d'ambiente DB_PATH.

Setup:
  pip install -r requirements.txt
  Variabile d'ambiente SECRET_PEPPER (e opzionale DB_PATH), vedi file WSGI.
"""

import os
import re
import hashlib

from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, declarative_base


# =========================================================
# CONFIG
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Percorso ASSOLUTO del file SQLite (su PythonAnywhere la cartella di lavoro
# non coincide con quella del progetto, quindi un percorso relativo sbaglierebbe posto).
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "supporters.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# "Pepper": stringa segreta aggiunta prima dell'hash, così anche se qualcuno
# vede il database non può ricostruire l'hash partendo da un visitor_id noto.
SECRET_PEPPER = os.environ.get("SECRET_PEPPER", "cambia-questo-pepper-in-produzione")

# Whitelist per il nickname: solo lettere, numeri, spazi, - e _
NICKNAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]{1,30}$")


def hash_visitor_id(visitor_id: str) -> str:
    return hashlib.sha256((visitor_id + SECRET_PEPPER).encode("utf-8")).hexdigest()


# =========================================================
# MODELS (SQLAlchemy)
# =========================================================
# check_same_thread=False: Flask può usare la connessione da thread diversi.
# timeout=30: se il file è bloccato da un'altra scrittura, aspetta fino a 30s.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Supporter(Base):
    __tablename__ = "supporters"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    nickname = Column(String(30), nullable=False, unique=True)      # niente nomi duplicati
    visitor_hash = Column(String(64), nullable=False, unique=True)  # 1 supporto per visitatore
    created_at = Column(DateTime, server_default=func.now())


Base.metadata.create_all(engine)


# =========================================================
# APP
# =========================================================
app = Flask(__name__)

# in produzione: metti il dominio del tuo sito al posto di "*"
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    methods=["GET", "POST"],
    allow_headers=["*"],
)


def error(status_code: int, detail: str):
    # Stesso formato errori di FastAPI: {"detail": "..."}  -> il frontend non cambia
    return jsonify({"detail": detail}), status_code


@app.get("/api/supporters")
def list_supporters():
    db = SessionLocal()
    try:
        supporters = db.query(Supporter).order_by(Supporter.user_id.desc()).all()
        return jsonify(
            [
                {
                    "user_id": s.user_id,
                    "nickname": s.nickname,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in supporters
            ]
        )
    finally:
        db.close()


@app.post("/api/support")
def add_supporter():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    nickname = data.get("nickname") or ""
    visitor_id = data.get("visitor_id") or ""
    if not isinstance(nickname, str) or not isinstance(visitor_id, str):
        return error(400, "Invalid request.")
    nickname = nickname.strip()
    visitor_id = visitor_id.strip()

    if not NICKNAME_PATTERN.match(nickname):
        return error(
            400,
            "Invalid nickname: only letters, numbers, spaces, - and _ (max 30 characters).",
        )

    if not visitor_id:
        return error(400, "Missing visitor id.")

    visitor_hash = hash_visitor_id(visitor_id)

    db = SessionLocal()
    try:
        # Controllo esplicito prima dell'insert, per dare un messaggio d'errore preciso
        if db.query(Supporter).filter_by(visitor_hash=visitor_hash).first():
            return error(409, "You already supported this project.")

        if db.query(Supporter).filter_by(nickname=nickname).first():
            return error(409, "This nickname is already taken.")

        supporter = Supporter(nickname=nickname, visitor_hash=visitor_hash)
        db.add(supporter)
        try:
            db.commit()
        except IntegrityError:
            # Backstop in caso di richieste quasi simultanee (race condition)
            db.rollback()
            return error(409, "Something went wrong, please try again.")

        db.refresh(supporter)
        return jsonify({"user_id": supporter.user_id, "nickname": nickname}), 200
    finally:
        db.close()


if __name__ == "__main__":
    # Solo per test locale: python main.py  (su PythonAnywhere lo avvia il WSGI)
    app.run(debug=True)
