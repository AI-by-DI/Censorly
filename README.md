# Censorly Demo — Project Skeleton 

**Amaç:** Dizi/film platformu içeriklerine sansür uygulayabilen demo web sitesi.
Bu iskelet; *FastAPI (API)*, *React+TS (Web)*, *Worker (arka plan)* ve *AI/Inference* katmanlarını ayırır.


## Teknoloji Önerileri
- Backend: FastAPI (Python 3.12+), SQLAlchemy + Alembic
- Frontend: React + TypeScript + Tailwind (Vite önerilir)
- Worker: RQ veya Celery (Redis), opsiyonel
- DB: Geliştirmede SQLite, üretimde PostgreSQL önerilir
- Video işleme: FFmpeg
- Modeller: YOLO (best.pt dosyaları `ai/models/` altında)

## Dizin Yapısı (özet)
- **apps/**
  - **api/** FastAPI uygulaması (router/service/repo ayrımı, SOLID)
  - **web/** React+TS demosu (kullanıcı girişi, tercih seçimi, video listesi)
  - **worker/** Arka plan görevleri (analiz/sansür uygulama pipeline tetikleyicileri)
- **ai/** Model sarıcıları ve pipeline (analiz/redaksiyon)
- **db/** ORM şemaları ve migrasyon yapılandırmaları
- **data/** (geliştirme amaçlı) video/çerçeve/çıktılar
- **notebooks/** Eğitim not defterleriniz
- **configs/** .env örnekleri
- **docker/** Docker dosyaları

---

> Bu iskelet, **Dependency Inversion** gözetilerek arayüz katmanları (`ai/inference/interfaces.py`) üzerinden bağımlılıkları tersine çevirir. API/Worker katmanları bu arayüzler üzerinden AI/pipeline bileşenleriyle konuşur.

