# ai/inference/yolo_wrapper.py
from __future__ import annotations
from ultralytics import YOLO
from pathlib import Path

class YOLODetector:
    def __init__(
        self,
        label_name: str,
        weights_path: str,
        conf: float = 0.65,
        iou: float = 0.45,
        imgsz: int = 960,
        exclude_labels: set[str] | None = None,   # <-- yeni
    ):
        self.label = label_name
        self.weights_path = str(weights_path)
        self.weights_name = Path(weights_path).name
        self.model = YOLO(weights_path)
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.exclude_labels = set(exclude_labels or [])

    def infer_one(self, frame_bgr):
        """
        Dönen: list[ {score: float, bbox: [cx,cy,w,h], sub_label?: str} ]
        sub_label varsa pipeline bunu 'label' olarak kullanır.
        """
        results = self.model.predict(
            source=frame_bgr,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            verbose=False,
        )
        out = []
        for r in results:
            h, w = r.orig_shape
            names = getattr(r, "names", None)  # YOLO sınıf adları sözlüğü olabilir

            for b in r.boxes:
                score = float(b.conf.item())

                # xyxy -> normalized cx,cy,w,h
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                nx = ((x1 + x2) / 2.0) / w
                ny = ((y1 + y2) / 2.0) / h
                nw = (x2 - x1) / w
                nh = (y2 - y1) / h

                sub_label = None
                # Çok sınıflı modellerde b.cls mevcutsa sınıf adını alalım
                if hasattr(b, "cls") and b.cls is not None and len(b.cls) > 0 and names is not None:
                    try:
                        cls_id = int(b.cls[0].item())
                        # names bazen dict, bazen list olabilir
                        if isinstance(names, dict):
                            sub_label = names.get(cls_id)
                        else:
                            sub_label = names[cls_id]
                    except Exception:
                        sub_label = None

                # İstenmeyen sınıfları atla (örn. FACE_FEMALE, FACE_MALE)
                if sub_label and sub_label in self.exclude_labels:
                    continue

                rec = {"score": score, "bbox": [nx, ny, nw, nh]}
                if sub_label:
                    rec["sub_label"] = sub_label
                out.append(rec)

        return out
