"""
AI/Pipeline arayüzleri — Dependency Inversion için sözleşmeler.
Gerçek implementasyonlar bu arayüzleri uygular.
"""
from typing import Protocol, Iterable, List, Dict, Any

class IModel(Protocol):
    """Bir kareyi (frame) alır, algılama sonuçlarını döner.
    Girdi: image (np.ndarray veya PIL.Image)
    Çıktı: List[Detection] -> {"ts": ms, "bbox": [x,y,w,h], "label": "kan|alkol|...","score": float}
    """
    def predict(self, image: Any) -> List[Dict[str, Any]]: ...

class IFrameExtractor(Protocol):
    """Videodan kare üretir. performans için stride/resize ayarları içerir."""
    def iter_frames(self, video_path: str) -> Iterable[Dict[str, Any]]: ...  # {"ts": ms, "image": Any}

class IPolicyEngine(Protocol):
    """Kullanıcı tercihleri + algılamalara göre sansür planı üretir."""
    def build_plan(self, detections: List[Dict[str, Any]], user_prefs: Dict[str, Any]) -> Dict[str, Any]: ...

class IRedactionOperator(Protocol):
    """Sansür planını uygular (blur/skip/uyarı)."""
    def apply(self, video_path: str, plan: Dict[str, Any], out_path: str) -> None: ...
