# ERA5-Land al punto (Chile) — Copernicus CDS

Consulta **ERA5-Land** (reanálisis horario, ~9 km / 0.1°) en **lat -41.425382, lon -73.095492** vía el [Climate Data Store](https://cds.climate.copernicus.eu/).

Esto **no son pronósticos HRES** (1–7 días). CDS público no entrega el archivo operativo de MARS. ERA5-Land es el mejor estimado de lo que ocurrió en superficie, útil igual como features de ML. Primera entrega: **enero 2016**, horario.

Variables: temperatura 2 m, viento 10 m (u/v), precipitación total, radiación solar incidente.

## Recorte al punto

ERA5-Land es global a 0.1°. El request manda `area = [N, W, S, E]` (una cajita de ±0.05° alrededor del sitio). CDS recorta en el servidor; el extractor toma la celda más cercana. No se baja el globo.

## Credenciales CDS

1. Cuenta en [cds.climate.copernicus.eu](https://cds.climate.copernicus.eu/)
2. Token en [How to API](https://cds.climate.copernicus.eu/how-to-api) → `.env` como `CDS_API_KEY` (URL `https://cds.climate.copernicus.eu/api`)
3. **Aceptá la licencia** del dataset (una vez, logueado): [ERA5-Land hourly](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=download) — sin eso la API responde 403

También sirve `%USERPROFILE%\.cdsapirc`:

```
url: https://cds.climate.copernicus.eu/api
key: <PERSONAL-ACCESS-TOKEN>
```

## Entorno

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
pip install -e .
python -m ipykernel install --user --name ecmwf-ml --display-name "ecmwf-ml"
```

## Notebooks

1. `notebooks/01_probe_one_day.ipynb` — 2016-01-01, 24 horas, validar punto
2. `notebooks/02_download_month.ipynb` — enero 2016
3. `notebooks/03_visualize_and_export.ipynb` — series y parquet

Salida: `data/raw/*.nc` (gitignored) y `data/processed/era5land_point_2016-01.parquet`.

En ERA5-Land, `tp` y `ssrd` se **acumulan desde las 00 UTC** (el valor de las 00 UTC es el total de las 24 h anteriores). El extractor desacumula a incremento horario, pasa precip a mm y radiación a W/m² (joule de esa hora / 3600). La primera 00 UTC de la serie queda en NaN: no hay un 23 UTC previo.

Documentación: [CDS API](https://cds.climate.copernicus.eu/how-to-api), [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land).
