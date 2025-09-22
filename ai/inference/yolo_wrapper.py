# ai/inference/yolo_wrapper.py
from __future__ import annotations
from ultralytics import YOLO
from pathlib import Path

class YOLODetector:
    def __init__(self, label_name: str, weights_path: str, conf: float = 0.5, iou: float = 0.5, imgsz: int = 640):
        self.label = label_name
        self.weights_path = str(weights_path)                 # <— EKLENDİ
        self.weights_name = Path(weights_path).name
        self.model = YOLO(weights_path)
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz

    def infer_one(self, frame_bgr):
        """
        Dönen yapı: list[ {score: float, bbox: [x,y,w,h] (normalized)} ]
        """
        results = self.model.predict(source=frame_bgr, conf=self.conf, iou=self.iou, imgsz=self.imgsz, verbose=False)
        out = []
        for r in results:
            h, w = r.orig_shape
            for b in r.boxes:
                score = float(b.conf.item())
                # xywh normalized
                xyxy = b.xyxy[0].tolist()
                x1, y1, x2, y2 = xyxy
                nx, ny, nw, nh = ( (x1+x2)/2.0 / w, (y1+y2)/2.0 / h, (x2-x1)/w, (y2-y1)/h )
                out.append({"score": score, "bbox": [nx, ny, nw, nh]})
        return out
