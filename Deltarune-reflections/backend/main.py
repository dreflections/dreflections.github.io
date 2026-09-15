"""
Backend per il bottone "Support" di Reflections.

API JSON pura: il frontend (supporters.html, pagina statica) fa fetch
da JavaScript per leggere/scrivere i supporter.

Endpoint:
  GET  /api/supporters   -> lista di tutti i supporter (JSON)
  POST /api/support      -> aggiunge un nickname, ritorna il suo user_id

Regole:
  - nickname validato con whitelist (niente <, >, ", ', tag HTML ecc.)
  - nickname UNIVOCO
  - 1 supporto per visitatore: il frontend genera un visitor_id casuale
    salvato in un cookie; qui viene hashato (SHA-256 + pepper) e salvato
    come visitor_hash, con vincolo UNIQUE. Così anche cancellando il
    localStorage (ma non il cookie) il server rifiuta un secondo nome,
    e nel database non resta un id in chiaro riutilizzabile.

Setup:
  pip install -r requirements.txt
  Imposta le variabili d'ambiente DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, SECRET_PEPPER
  uvicorn main:app --reload
"""

import os
import re
import hashlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, declarative_base


# =========================================================
# CONFIG
# =========================================================
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "reflections")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

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
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
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
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in produzione: metti il dominio del tuo sito al posto di *
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/supporters")
def list_supporters():
    db = SessionLocal()
    supporters = db.query(Supporter).order_by(Supporter.user_id.desc()).all()
    db.close()

    return [
        {
            "user_id": s.user_id,
            "nickname": s.nickname,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in supporters
    ]


@app.post("/api/support")
async def add_supporter(request: Request):
    data = await request.json()
    nickname = (data.get("nickname") or "").strip()
    visitor_id = (data.get("visitor_id") or "").strip()

    if not NICKNAME_PATTERN.match(nickname):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Invalid nickname: only letters, numbers, spaces, - and _ (max 30 characters)."
            },
        )

    if not visitor_id:
        return JSONResponse(status_code=400, content={"detail": "Missing visitor id."})

    visitor_hash = hash_visitor_id(visitor_id)

    db = SessionLocal()

    # Controllo esplicito prima dell'insert, per dare un messaggio d'errore preciso
    if db.query(Supporter).filter_by(visitor_hash=visitor_hash).first():
        db.close()
        return JSONResponse(
            status_code=409,
            content={"detail": "You already supported this project."},
        )

    if db.query(Supporter).filter_by(nickname=nickname).first():
        db.close()
        return JSONResponse(
            status_code=409,
            content={"detail": "This nickname is already taken."},
        )

    supporter = Supporter(nickname=nickname, visitor_hash=visitor_hash)
    db.add(supporter)
    try:
        db.commit()
    except IntegrityError:
        # Backstop in caso di richieste quasi simultanee (race condition)
        db.rollback()
        db.close()
        return JSONResponse(
            status_code=409,
            content={"detail": "Something went wrong, please try again."},
        )

    db.refresh(supporter)
    user_id = supporter.user_id
    db.close()

    return JSONResponse(
        status_code=200,
        content={"user_id": user_id, "nickname": nickname},
    )
