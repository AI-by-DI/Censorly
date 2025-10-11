# apps/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Bu dosya apps/api/main.py ise relative import doğru:
from .routers import auth, preferences, uploads, analyses

app = FastAPI(title="Censorly API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # gerekiyorsa "*" yap
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

# Router’lar
app.include_router(auth.router)
app.include_router(preferences.router)
app.include_router(uploads.router)    # <-- upload & pipeline tetikleme
app.include_router(analyses.router)   # <-- job start/ingest/finish & status