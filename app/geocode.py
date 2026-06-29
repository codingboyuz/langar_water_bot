"""Lokatsiyadan manzilni avtomatik o'qish (reverse geocoding) va
matn/havoladan lokatsiyani aniqlash (Telegram Web/Desktop uchun).

GOOGLE_MAPS_API_KEY bo'lsa — Google Maps ishlatiladi (aniqroq).
Bo'lmasa — bepul OpenStreetMap Nominatim (kalit talab qilmaydi).
"""
from __future__ import annotations

import re

import httpx

from app.config import settings

_HEADERS = {"User-Agent": "LangarWaterBot/1.0"}


async def reverse_geocode(lat: float, lon: float) -> str | None:
    if settings.google_maps_api_key:
        addr = await _google(lat, lon)
        if addr:
            return addr
    return await _nominatim(lat, lon)


async def _google(lat: float, lon: float) -> str | None:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lon}",
        "key": settings.google_maps_api_key,
        "language": "uz",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                return data["results"][0]["formatted_address"]
    except Exception:
        return None
    return None


async def _nominatim(lat: float, lon: float) -> str | None:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "json", "accept-language": "uz"}
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            r = await client.get(url, params=params)
            data = r.json()
            return data.get("display_name")
    except Exception:
        return None


# ============================ MATN -> LOKATSIYA ============================
# Telegram Web/Desktop'da `request_location` tugmasi ishlamaydi. Shu sabab
# foydalanuvchi lokatsiyani xarita havolasi (Google/Yandex/OSM), koordinata
# yoki manzil matni ko'rinishida ham yuborishi mumkin — shu yerda yechamiz.

_FLOAT = r"-?\d{1,3}(?:\.\d+)?"


def _valid(lat: float, lon: float) -> tuple[float, float] | None:
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        return lat, lon
    return None


def parse_coords_from_text(text: str) -> tuple[float, float] | None:
    """Matn yoki xarita havolasidan (lat, lon) ni ajratadi. Topolmasa — None."""
    if not text:
        return None
    s = text.strip()
    low = s.lower()

    # 1) OpenStreetMap: aniq nomlangan mlat / mlon
    mlat = re.search(rf"mlat=({_FLOAT})", s)
    mlon = re.search(rf"mlon=({_FLOAT})", s)
    if mlat and mlon:
        return _valid(float(mlat.group(1)), float(mlon.group(1)))

    # 2) Yandex Maps: ll= / pt= — tartibi TESKARI (lon,lat)
    if "yandex" in low:
        ym = re.search(rf"[?&](?:ll|pt)=({_FLOAT})[,;]({_FLOAT})", low)
        if ym:
            return _valid(float(ym.group(2)), float(ym.group(1)))

    # 3) Google Maps (@lat,lon yoki q=lat,lon) va OSM (#map=z/lat/lon)
    gm = re.search(rf"[@=/]({_FLOAT}),({_FLOAT})", s)
    if gm:
        return _valid(float(gm.group(1)), float(gm.group(2)))

    # 4) Toza "lat, lon" matn (masalan: 41.31, 69.24)
    rm = re.fullmatch(rf"\s*({_FLOAT})\s*[,; ]\s*({_FLOAT})\s*", s)
    if rm:
        return _valid(float(rm.group(1)), float(rm.group(2)))

    return None


async def _expand_short_url(url: str) -> str:
    """Qisqartirilgan havolani (goo.gl, maps.app, yandex -/) ochib, yakuniy
    manzilini qaytaradi (koordinata ko'pincha shu yerda bo'ladi)."""
    try:
        async with httpx.AsyncClient(
            timeout=10, headers=_HEADERS, follow_redirects=True
        ) as client:
            r = await client.get(url)
            return str(r.url)
    except Exception:
        return url


async def forward_geocode(query: str) -> tuple[float, float, str] | None:
    """Manzil matnidan (lat, lon, to'liq_manzil) ni topadi. Topolmasa — None."""
    query = (query or "").strip()
    if len(query) < 4:
        return None
    if settings.google_maps_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": query, "key": settings.google_maps_api_key, "language": "uz"},
                )
                data = r.json()
                if data.get("status") == "OK" and data.get("results"):
                    res = data["results"][0]
                    loc = res["geometry"]["location"]
                    return loc["lat"], loc["lng"], res["formatted_address"]
        except Exception:
            pass
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "accept-language": "uz"},
            )
            data = r.json()
            if data:
                item = data[0]
                return float(item["lat"]), float(item["lon"]), item.get("display_name", query)
    except Exception:
        pass
    return None


async def resolve_text_location(text: str) -> tuple[float, float, str] | None:
    """Foydalanuvchi yuborgan matndan yetkazish nuqtasini aniqlaydi.

    Qaytaradi: (lat, lon, manzil) yoki None. Tartib:
      1) matn/havoladan koordinata;
      2) qisqartirilgan havola bo'lsa — ochib qayta urinish;
      3) aks holda — manzil matnini qidirish (forward geocode).
    """
    if not text:
        return None
    s = text.strip()

    coords = parse_coords_from_text(s)
    if coords is None and re.search(r"https?://\S+", s):
        url = re.search(r"https?://\S+", s).group(0)
        coords = parse_coords_from_text(await _expand_short_url(url))

    if coords:
        lat, lon = coords
        address = await reverse_geocode(lat, lon) or f"{lat:.5f}, {lon:.5f}"
        return lat, lon, address

    return await forward_geocode(s)
