from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

CDS_DATASET = "reanalysis-era5-land"
CDS_API_URL = "https://cds.climate.copernicus.eu/api"

VARIABLES: tuple[str, ...] = (
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation",
    "surface_solar_radiation_downwards",
)

HOURS: tuple[str, ...] = tuple(f"{hour:02d}:00" for hour in range(24))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    lat: float = -41.425382
    lon: float = -73.095492
    area_half_deg: float = 0.05
    dataset: str = CDS_DATASET
    variables: tuple[str, ...] = VARIABLES
    times: tuple[str, ...] = HOURS
    probe_date: date = date(2016, 1, 1)
    month_start: date = date(2016, 1, 1)
    month_end: date = date(2016, 1, 31)
    repo_root: Path = field(default_factory=_repo_root)

    @property
    def area(self) -> list[float]:
        """CDS area as [North, West, South, East] around the target point.

        ERA5-Land is 0.1°. A 0.05° box keeps a single cell without a global extract.
        """
        d = self.area_half_deg
        return [self.lat + d, self.lon - d, self.lat - d, self.lon + d]

    @property
    def data_raw(self) -> Path:
        return self.repo_root / "data" / "raw"

    @property
    def data_processed(self) -> Path:
        return self.repo_root / "data" / "processed"


def get_settings() -> Settings:
    return Settings()


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def netcdf_name(
    date_from: date,
    date_to: date,
    *,
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    stem = f"era5land_{date_from:%Y-%m-%d}_{date_to:%Y-%m-%d}"
    if lat is not None and lon is not None:
        stem += f"_lat{lat:.2f}_lon{lon:.2f}"
    return f"{stem}.nc"
