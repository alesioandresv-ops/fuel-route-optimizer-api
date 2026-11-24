# Fuel Route Optimizer API

A REST API built with Django and Python to calculate driving routes, identify fuel stations along the route, and optimize refueling stops according to vehicle range and fuel efficiency.

The project focuses on route feasibility, transparent distance estimation, and data quality.

## Features

- Driving route calculation using HeiGIT / openrouteservice.
- Fuel station discovery using HeiGIT OpenPOIService and OpenStreetMap data.
- Route geometry and distance calculation.
- Vehicle range and fuel consumption configuration.
- Refueling stop optimization based on route feasibility.
- Partial initial fuel support.
- Geographic station normalization and validation.
- Explicit handling of unavailable or unverified fuel prices.
- Automated tests for services, serializers, optimization logic, and API behavior.

## Technology Stack

- Python 3.13
- Django 6.1.3
- Django REST Framework
- HTTPX
- python-dotenv
- Pytest
- HeiGIT API
- OpenStreetMap data

## Vehicle Model

The default vehicle parameters are:

| Parameter | Default |
|---|---:|
| Maximum range | 500 miles |
| Fuel efficiency | 10 MPG |
| Initial fuel | Full calculated capacity |
| Calculated capacity | 50 gallons |

**Important:** The 50-gallon capacity is a mathematical assumption derived from maximum range divided by fuel efficiency. It is not a verified physical tank capacity.

Vehicle parameters can be customized in the API request.

## Installation

Clone the repository:

```bash
git clone https://github.com/alesioandresv-ops/fuel-route-optimizer-api.git
cd fuel-route-optimizer-api
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Configuration

Create a `.env` file in the project root:

```env
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
HEIGIT_API_KEY=your-heigit-api-key
```

Obtain an API key from the HeiGIT service and configure it in `HEIGIT_API_KEY`.

Never commit your `.env` file or expose API credentials.

## Database Setup

Apply Django migrations:

```bash
python manage.py migrate
```

Check the project configuration:

```bash
python manage.py check
```

## Running the API

Start the development server:

```bash
python manage.py runserver
```

The API will be available at:

```text
http://127.0.0.1:8000/
```

## API Endpoint

### Optimize Route

`POST /api/v1/trips/optimize/`

Content-Type: `application/json`

Example request:

```json
{
  "origin": {
    "longitude": -80.1918,
    "latitude": 25.7617
  },
  "destination": {
    "longitude": -81.3792,
    "latitude": 28.5383
  },
  "vehicle": {
    "max_range_miles": 500,
    "mpg": 10,
    "initial_fuel_gallons": 50
  }
}
```

The `vehicle` object is optional. If omitted, the API uses the default vehicle parameters.

### Response

The response includes:

- Route distance, duration, and GeoJSON geometry.
- Vehicle configuration and calculated capacity assumption.
- Optimization feasibility and recommended stops.
- Geographic fuel stations discovered along the route.
- Separately identified priced stations.
- Fuel cost information when verified prices are available.
- Data quality warnings and external API call information.

## Optimization Approach

The optimization service is independent of external data providers.

It evaluates candidate stations according to their position along the route, lateral distance, vehicle range, and available fuel.

The current implementation uses geometric distance approximations to estimate station detours. It does not calculate actual road distances for each detour.

The optimizer prioritizes feasible refueling plans with fewer stops and then lower estimated geometric detour distance.

## Fuel Price Data Quality

The assessment CSV is analyzed separately from geographic OpenStreetMap data.

Original price observations are preserved, including duplicate observations and source row references.

For station-level price summaries, the median is calculated using distinct observed price values to prevent duplicate entries from disproportionately affecting the estimate. All original observations remain preserved, and the observation count, source rows, minimum, and maximum reflect the original records.

Station prices are not associated with geographic stations unless a sufficiently reliable match can be established.

When no verified price matches are available:

- Geographic stations are still returned.
- Fuel prices remain `null`.
- Fuel cost remains unavailable.
- The API reports `no_verified_price_matches`.

Currency and fuel type remain unspecified when the source data does not establish them.

The original assessment dataset and research snapshots are excluded from this repository.

## Research Scripts

The `scripts/` directory contains exploratory tools used to analyze geographic station data and investigate potential matches between OpenStreetMap stations and the assessment dataset.

| Script | Purpose |
|---|---|
| `inspect_fuel_data.py` | Inspects the original fuel price dataset. |
| `analyze_osm_matches.py` | Analyzes matches between OSM identifiers and geographic snapshots. |
| `inspect_florida_matches.py` | Investigates potential station matches in Florida. |
| `inspect_station_data.py` | Inspects station tags and geographic data. |

These scripts require corresponding local input files in `data/`, which are not included in the repository.

## Running Tests

Run the complete test suite:

```bash
pytest -v
```

The current test suite contains 84 automated tests covering:

- Fuel price CSV processing.
- Route optimization.
- Routing and POI service integrations.
- Request validation.
- Geographic station normalization.
- API endpoint behavior and provider errors.

## Current Limitations

- No fuel price-to-location matches have been verified yet.
- Actual road detour distances are not calculated.
- Vehicle tank capacity is an assumption derived from range and MPG.
- Fuel currency and product type are unspecified when not established by the source dataset.
- External API availability and rate limits may affect live requests.

## Project Status

Core API implementation and automated tests are complete for the current development stage.

The real routing and fuel station discovery integrations have been tested using a Miami–Orlando route.

Further work can improve geographic enrichment, verified price matching, and road-based detour calculations.