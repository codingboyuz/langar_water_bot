"""Lokatsiyadan manzilni avtomatik o'qish (reverse geocoding).

GOOGLE_MAPS_API_KEY bo'lsa — Google Maps ishlatiladi (aniqroq).
Bo'lmasa — bepul OpenStreetMap Nominatim (kalit talab qilmaydi).
"""
from __future__ import annotations

import httpx

from app.config import settings


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
    headers = {"User-Agent": "LangarWaterBot/1.0"}
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            r = await client.get(url, params=params)
            data = r.json()
            return data.get("display_name")
    except Exception:
        return None
