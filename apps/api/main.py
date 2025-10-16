# apps/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# routers dizinindeki tüm modülleri dahil et
from .routers import (
    auth,
    preferences,
    uploads,
    analyses,
    videos,
    redactions,   # ✅ yeni ekleme
)

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
app.include_router(uploads.router)
app.include_router(analyses.router)
app.include_router(videos.router)       # ✅ bu da importtan sonra aktif olur
app.include_router(redactions.router)   # ✅ artık Swagger'da gözükecek