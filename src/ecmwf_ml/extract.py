from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from ecmwf_ml.config import Settings, get_settings

VAR_ALIASES: dict[str, tuple[str, ...]] = {
    "t2m_k": ("t2m", "2t"),
    "u10": ("u10", "10u"),
    "v10": ("v10", "10v"),
    "tp": ("tp",),
    "ssrd": ("ssrd",),
}


def _extract_nc(path: Path) -> Path:
    if not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith((".nc", ".nc4"))]
        if not names:
            raise ValueError(f"ZIP {path} does not contain a NetCDF file")
        target = path.with_suffix(".nc")
        with archive.open(names[0]) as src, target.open("wb") as dest:
            dest.write(src.read())
    return target


def _open_dataset(path: Path) -> xr.Dataset:
    path = _extract_nc(Path(path))
    dataset = xr.open_dataset(path)
    rename = {}
    if "lat" in dataset.coords and "latitude" not in dataset.coords:
        rename["lat"] = "latitude"
    if "lon" in dataset.coords and "longitude" not in dataset.coords:
        rename["lon"] = "longitude"
    if "valid_time" in dataset.coords and "time" not in dataset.coords:
        rename["valid_time"] = "time"
    if rename:
        dataset = dataset.rename(rename)
    for extra in ("expver", "number"):
        if extra in dataset.dims:
            dataset = dataset.isel({extra: 0}, drop=True)
        elif extra in dataset.coords:
            dataset = dataset.drop_vars(extra, errors="ignore")
    return dataset


def _request_lon(ds: xr.Dataset, lon: float) -> float:
    if "longitude" not in ds.coords:
        return lon
    values = np.asarray(ds["longitude"].values)
    if values.size and values.min() >= 0 and lon < 0:
        return lon + 360.0
    return lon


def _nearest_point(ds: xr.Dataset, lat: float, lon: float) -> xr.Dataset:
    kwargs: dict[str, object] = {}
    if "latitude" in ds.dims:
        kwargs["latitude"] = lat
    if "longitude" in ds.dims:
        kwargs["longitude"] = _request_lon(ds, lon)
    if kwargs:
        ds = ds.sel(**kwargs, method="nearest")
    return ds.squeeze(drop=False)


def _coord_value(ds: xr.Dataset, name: str) -> float | None:
    if name not in ds.coords:
        return None
    values = np.asarray(ds[name].values).reshape(-1)
    if values.size == 0:
        return None
    return float(values[0])


def _hourly_from_accum(raw: pd.Series, times: pd.Series) -> pd.Series:
    """Turn ERA5-Land accumulations into the increment of the hour ending at ``times``.

    The land forecast starts at 00 UTC. Steps 01–23 UTC accumulate from that
    00 UTC. The 00 UTC value itself is the previous day's 24 h total, not one
    hour. A naive ``value / 3600`` therefore yields ~8–9 kW/m² at midnight.

    Hourly amount = diff vs the previous step; at 01 UTC the raw value is
    already the 00–01 increment (the accumulator reset). The first 00 UTC in
    the series has no previous 23 UTC, so it is left as NaN.
    """
    values = raw.astype("float64")
    clock = pd.to_datetime(times, utc=True)
    hourly = values.diff()
    hourly = hourly.mask(clock.dt.hour.eq(1), values)
    if len(hourly) == 0:
        return hourly
    if clock.dt.hour.iloc[0] == 0:
        hourly.iloc[0] = np.nan
    elif pd.isna(hourly.iloc[0]):
        hourly.iloc[0] = values.iloc[0]
    return hourly.clip(lower=0)


def to_frame(path: str | Path, settings: Settings | None = None) -> pd.DataFrame:
    """Convert a point NetCDF into an hourly tidy table."""
    settings = settings or get_settings()
    dataset = _open_dataset(Path(path))
    point = _nearest_point(dataset, settings.lat, settings.lon)
    actual_lat = _coord_value(point, "latitude")
    actual_lon = _coord_value(point, "longitude")

    frame = point.to_dataframe().reset_index()
    if "time" not in frame.columns:
        raise ValueError(f"NetCDF missing time; columns={list(frame.columns)}")
    frame["time"] = pd.to_datetime(frame["time"], utc=True)

    for dest, aliases in VAR_ALIASES.items():
        for alias in aliases:
            if alias in frame.columns:
                frame = frame.rename(columns={alias: dest})
                break

    keep = ["time", *VAR_ALIASES]
    frame = frame[[col for col in keep if col in frame.columns]].drop_duplicates(
        subset=["time"], keep="first"
    )
    frame["latitude"] = actual_lat
    frame["longitude"] = actual_lon
    frame = frame.sort_values("time").reset_index(drop=True)

    if "t2m_k" in frame.columns:
        frame["t2m_c"] = frame["t2m_k"] - 273.15
    if {"u10", "v10"} <= set(frame.columns):
        frame["wind_speed"] = np.sqrt(frame["u10"] ** 2 + frame["v10"] ** 2)
        frame["wind_dir_from"] = (
            np.degrees(np.arctan2(-frame["u10"], -frame["v10"])) % 360
        )
    if "tp" in frame.columns:
        frame["tp"] = _hourly_from_accum(frame["tp"], frame["time"])
        frame["tp_mm"] = (frame["tp"] * 1000.0).clip(lower=0)
    if "ssrd" in frame.columns:
        frame["ssrd"] = _hourly_from_accum(frame["ssrd"], frame["time"])
        frame["ssrd_wm2"] = (frame["ssrd"] / 3600.0).clip(lower=0)

    ordered = [
        "time",
        "latitude",
        "longitude",
        "t2m_k",
        "t2m_c",
        "u10",
        "v10",
        "wind_speed",
        "wind_dir_from",
        "tp",
        "tp_mm",
        "ssrd",
        "ssrd_wm2",
    ]
    existing = [col for col in ordered if col in frame.columns]
    rest = [col for col in frame.columns if col not in existing]
    return frame[existing + rest]


def daily_frame(hourly: pd.DataFrame) -> pd.DataFrame:
    """Calendar-day aggregates in UTC (sum precip, mean the rest)."""
    work = hourly.copy()
    work["date"] = work["time"].dt.tz_convert("UTC").dt.floor("D")
    agg: dict[str, str] = {}
    if "t2m_c" in work.columns:
        agg["t2m_c"] = "mean"
    if "wind_speed" in work.columns:
        agg["wind_speed"] = "mean"
    if "u10" in work.columns:
        agg["u10"] = "mean"
    if "v10" in work.columns:
        agg["v10"] = "mean"
    if "tp_mm" in work.columns:
        agg["tp_mm"] = "sum"
    if "ssrd_wm2" in work.columns:
        agg["ssrd_wm2"] = "mean"
    daily = work.groupby("date", as_index=False).agg(agg)
    if {"u10", "v10"} <= set(daily.columns):
        daily["wind_dir_from"] = (
            np.degrees(np.arctan2(-daily["u10"], -daily["v10"])) % 360
        )
    return daily


def write_parquet(
    frame: pd.DataFrame,
    dest: str | Path | None = None,
    settings: Settings | None = None,
) -> Path:
    settings = settings or get_settings()
    settings.data_processed.mkdir(parents=True, exist_ok=True)
    dest_path = Path(dest) if dest else settings.data_processed / (
        f"era5land_point_{settings.month_start:%Y-%m}.parquet"
    )
    frame.to_parquet(dest_path, index=False)
    return dest_path
