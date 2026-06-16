"""Buyurtmalarni yetkazish tartibini hisoblash (oddiy marshrut yordamchisi).

Kuryerda bir nechta bajarilmagan buyurtma bo'lsa, ularni yaqinlik bo'yicha
tartiblaydi: avval eng uzoq nuqta (anchor), keyin unga eng yaqinlaridan
ketma-ket (nearest-neighbor). Bir-biriga juda yaqin tushgan buyurtmalar
"yo'l-yo'lakay" deb belgilanadi — ya'ni bitta chiqishda yetkazsa bo'ladi.

Misol: avval uzoq yo'ldagi buyurtma tushdi, 20 daqiqadan keyin shu yo'l
ustidagi yangi buyurtma tushdi — ikkinchisi "yo'l-yo'lakay" sifatida
belgilanadi va marshrutda mos joyga qo'yiladi.
"""
from __future__ import annotations

import math
from typing import Sequence

# Shu masofadan yaqin (km) bo'lsa — "yo'l-yo'lakay" (bitta chiqishda)
ENROUTE_KM = 3.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Ikki koordinata orasidagi masofa (km)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _coords(o) -> tuple[float, float] | None:
    lat = getattr(o, "latitude", None)
    lon = getattr(o, "longitude", None)
    if lat is None or lon is None:
        u = getattr(o, "user", None)
        if u is not None:
            lat = getattr(u, "latitude", None)
            lon = getattr(u, "longitude", None)
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def order_route(orders: Sequence, enroute_km: float = ENROUTE_KM) -> list:
    """Buyurtmalarni marshrut tartibida qaytaradi.

    Har bir buyurtma obyektiga qo'shimcha (mapped bo'lmagan) atributlar qo'yiladi:
      seq      -> tartib raqami (1, 2, 3, ...)
      leg_km   -> oldingi nuqtadan masofa (km, birinchisi uchun None)
      enroute  -> True bo'lsa "yo'l-yo'lakay" (oldingisiga juda yaqin)
      has_geo  -> koordinatasi bormi
    """
    pts = []      # (order, lat, lon)
    no_geo = []
    for o in orders:
        c = _coords(o)
        if c is None:
            o.has_geo = False
            no_geo.append(o)
        else:
            o.has_geo = True
            pts.append((o, c[0], c[1]))

    ordered: list = []
    if pts:
        # markaz (centroid) va undan eng uzoq nuqtani anchor qilamiz
        clat = sum(p[1] for p in pts) / len(pts)
        clon = sum(p[2] for p in pts) / len(pts)
        anchor = max(pts, key=lambda p: haversine_km(clat, clon, p[1], p[2]))
        remaining = [p for p in pts if p is not anchor]
        cur = anchor
        ordered.append((anchor, None))
        while remaining:
            nxt = min(remaining, key=lambda p: haversine_km(cur[1], cur[2], p[1], p[2]))
            d = haversine_km(cur[1], cur[2], nxt[1], nxt[2])
            ordered.append((nxt, d))
            remaining.remove(nxt)
            cur = nxt

    out: list = []
    seq = 0
    for (p, d) in ordered:
        seq += 1
        o = p[0]
        o.seq = seq
        o.leg_km = round(d, 1) if d is not None else None
        o.enroute = d is not None and d <= enroute_km
        out.append(o)
    # koordinatasizlar oxirida
    for o in no_geo:
        seq += 1
        o.seq = seq
        o.leg_km = None
        o.enroute = False
        out.append(o)
    return out
