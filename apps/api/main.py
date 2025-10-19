# apps/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from os import getenv

from .routers import auth, preferences, uploads, analyses, videos, redactions

app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None, title="Censorly API")

ALLOWED_ORIGINS = [o.strip() for o in getenv("CORS_ALLOW_ORIGINS","https://censorly.site").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,    # gerekirse geçici olarak ["*"] yapabilirsin
    allow_credentials=(getenv("CORS_ALLOW_CREDENTIALS","true").lower()=="true"),          # cookie kullanmıyoruz; Bearer header var
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