# apps/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, preferences, uploads, analyses, videos, redactions

app = FastAPI(title="Censorly API")

ALLOWED_ORIGINS = [
    "http://localhost:5173",         # local dev
    "http://127.0.0.1:5173",         # local dev alternatif
    "http://194.146.50.83:8101",     # prod web (nginx)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,    # gerekirse geçici olarak ["*"] yapabilirsin
    allow_credentials=False,          # cookie kullanmıyoruz; Bearer header var
    allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
    allow_headers=["*"],              # Authorization, Content-Type vs. hepsi geçsin
    max_age=600,
)

app.include_router(auth.router)
app.include_router(preferences.router)
app.include_router(uploads.router)
app.include_router(analyses.router)
app.include_router(videos.router)
app.include_router(redactions.router)