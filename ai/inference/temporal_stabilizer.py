# temporal_stabilizer.py
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import math

# ====== Yardımcı tipler ======
# Beklenen detection formatı: (x1, y1, x2, y2, score, cls_id)
Det = Tuple[float, float, float, float, float, int]

def iou(a: Det, b: Det) -> float:
    ax1, ay1, ax2, ay2 = a[:4]; bx1, by1, bx2, by2 = b[:4]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aw = max(0.0, ax2 - ax1); ah = max(0.0, ay2 - ay1)
    bw = max(0.0, bx2 - bx1); bh = max(0.0, by2 - by1)
    den = aw * ah + bw * bh - inter + 1e-9
    return inter / den

@dataclass
class Track:
    tid: int
    det: Det                       # son bbox+score+cls
    cls_state: int = -1            # kilitli sınıf (-1: none)
    lock_until_ms: int = 0
    last_seen_ms: int = 0
    score_hist: List[float] = field(default_factory=list)
    cls_hist:   List[int]   = field(default_factory=list)
    confirmed: bool = False

# ====== Ana sınıf ======
class TemporalStabilizer:
    """
    - IoU tabanlı basit track-by-detect
    - Histerezis: enter/exit eşikleri
    - N-of-M: son M adımda >=N tekrar varsa 'confirmed'
    - Hold/Grace: kararları zaman içinde tut
    """
    def __init__(
        self,
        enter_thr: Dict[int, float],     # sınıfa girmek için conf eşiği
        exit_thr:  Dict[int, float],     # sınıftan düşmek için conf
        n_of_m: Dict[int, Tuple[int,int]] = None,  # {cls:(N,M)}
        hold_gap_ms: int = 600,
        grace_ms: int = 250,
        iou_match_thr: float = 0.4,
        min_box_area_frac: float = 0.0015,  # çok küçük kutuları ele (opsiyonel)
        min_conf_map: Dict[int, float] = None,      # son çıkış filtresi
    ):
        self.enter_thr = enter_thr
        self.exit_thr  = exit_thr
        self.n_of_m    = n_of_m or {0:(3,5), 1:(2,5), 2:(2,5)}  # 0:Clown,1:Snake,2:Spider
        self.hold_gap_ms = hold_gap_ms
        self.grace_ms = grace_ms
        self.iou_thr = iou_match_thr
        self.min_area = min_box_area_frac
        self.min_conf_map = min_conf_map or {0:0.60, 1:0.55, 2:0.58}
        self.tracks: Dict[int, Track] = {}
        self.next_tid = 1
        self.frame_area = None  # opsiyonel: set_frame_size(w,h)

    # opsiyonel: kare boyutu ver, alan filtresi daha anlamlı çalışır
    def set_frame_size(self, width: int, height: int):
        self.frame_area = float(width * height)

    def _associate(self, dets: List[Det]) -> Dict[int, Det]:
        assigned = {}
        used = set()
        # greedy IoU eşleştirme
        for tid, trk in self.tracks.items():
            best_iou, best_j = 0.0, -1
            for j, d in enumerate(dets):
                if j in used: 
                    continue
                i = iou(trk.det, d)
                if i > best_iou:
                    best_iou, best_j = i, j
            if best_iou >= self.iou_thr and best_j >= 0:
                assigned[tid] = dets[best_j]
                used.add(best_j)
        # eşleşmeyenler → yeni track
        for j, d in enumerate(dets):
            if j in used:
                continue
            tid = self.next_tid; self.next_tid += 1
            self.tracks[tid] = Track(tid=tid, det=d)
            assigned[tid] = d
        return assigned

    def _area_ok(self, det: Det) -> bool:
        if not self.frame_area:
            return True
        x1,y1,x2,y2 = det[:4]
        area = max(0.0,(x2-x1))*max(0.0,(y2-y1))
        return (area / self.frame_area) >= self.min_area

    def update(self, t_ms: int, dets: List[Det]) -> List[Det]:
        # 1) küçük kutuları ön ele
        dets = [d for d in dets if self._area_ok(d)]
        # 2) track eşleştir
        assigned = self._associate(dets)

        out: List[Det] = []
        for tid, trk in list(self.tracks.items()):
            if tid in assigned:
                trk.det = assigned[tid]
                trk.last_seen_ms = t_ms
                x1,y1,x2,y2,score,cls_id = trk.det
                trk.score_hist.append(score)
                trk.cls_hist.append(cls_id)

                # Histerezis
                if trk.cls_state == -1:
                    if score >= self.enter_thr.get(cls_id, 0.6):
                        trk.cls_state = cls_id
                        trk.lock_until_ms = t_ms + self.grace_ms
                else:
                    # kilit süresi içinde etiketi koru
                    if t_ms < trk.lock_until_ms:
                        pass
                    else:
                        # sınıftan düşmek için daha düşük eşik
                        if score < self.exit_thr.get(trk.cls_state, 0.45):
                            trk.cls_state = -1
                        else:
                            # aynı sınıfta kalıyorsa lock'u hafif uzat
                            trk.lock_until_ms = t_ms + self.grace_ms

                # N-of-M onayı
                if trk.cls_state != -1:
                    N,M = self.n_of_m.get(trk.cls_state, (2,5))
                    recent = trk.cls_hist[-M:]
                    trk.confirmed = recent.count(trk.cls_state) >= N

                # Çıkış filtresi: confirmed + min_conf_map
                if trk.cls_state != -1 and trk.confirmed:
                    minc = self.min_conf_map.get(trk.cls_state, 0.5)
                    if score >= minc:
                        out.append((x1,y1,x2,y2,score, trk.cls_state))
            else:
                # görünmez oldu → hold süresi içinde son kararını taşı
                if (t_ms - trk.last_seen_ms) <= self.hold_gap_ms and trk.cls_state != -1 and trk.confirmed:
                    x1,y1,x2,y2,score,cls_id = trk.det
                    out.append((x1,y1,x2,y2,score, trk.cls_state))
                else:
                    # çok süredir görünmüyor → track'i sil
                    if (t_ms - trk.last_seen_ms) > max(self.hold_gap_ms, 2000):
                        self.tracks.pop(tid, None)

        return out