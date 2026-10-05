from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ecmwf_ml.config import CDS_API_URL, Settings, get_settings, netcdf_name


def load_credentials(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    load_dotenv(settings.repo_root / ".env")


def _cds_key() -> str:
    load_credentials()
    for name in ("CDS_API_KEY", "CDS_API_KE"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise RuntimeError(
        "Falta CDS_API_KEY en .env (Personal Access Token de "
        "https://cds.climate.copernicus.eu/how-to-api)."
    )


def _cds_url() -> str:
    load_credentials()
    return os.environ.get("CDS_API_URL", CDS_API_URL).strip() or CDS_API_URL


def get_client():
    """CDS client using .env, or ~/.cdsapirc if the key is not set."""
    import cdsapi

    load_credentials()
    kwargs: dict[str, Any] = {}
    try:
        kwargs["key"] = _cds_key()
        kwargs["url"] = _cds_url()
    except RuntimeError:
        pass
    return cdsapi.Client(**kwargs)


def _dates(date_from: date, date_to: date) -> list[date]:
    days: list[date] = []
    cursor = date_from
    while cursor <= date_to:
        days.append(cursor)
        cursor += timedelta(days=1)
    if not days:
        raise ValueError("date_from must be on or before date_to")
    return days


def build_retrieve_request(
    date_from: date,
    date_to: date,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    days = _dates(date_from, date_to)
    years = sorted({f"{d.year}" for d in days})
    months = sorted({f"{d.month:02d}" for d in days})
    return {
        "variable": list(settings.variables),
        "year": years,
        "month": months,
        "day": [f"{d.day:02d}" for d in days],
        "time": list(settings.times),
        "area": settings.area,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def target_path(
    date_from: date,
    date_to: date,
    settings: Settings | None = None,
) -> Path:
    settings = settings or get_settings()
    settings.data_raw.mkdir(parents=True, exist_ok=True)
    return settings.data_raw / netcdf_name(
        date_from, date_to, lat=settings.lat, lon=settings.lon
    )


def retrieve(
    date_from: date,
    date_to: date,
    *,
    settings: Settings | None = None,
    overwrite: bool = False,
    client: Any | None = None,
) -> Path:
    """Download ERA5-Land NetCDF for [date_from, date_to]. Skips if the file exists."""
    settings = settings or get_settings()
    dest = target_path(date_from, date_to, settings)
    if dest.exists() and dest.stat().st_size > 0 and not overwrite:
        return dest

    request = build_retrieve_request(date_from, date_to, settings)
    cds = client or get_client()
    cds.retrieve(settings.dataset, request, str(dest))
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"CDS finished but {dest} is missing or empty")
    return dest
