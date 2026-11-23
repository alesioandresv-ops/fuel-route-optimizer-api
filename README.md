
# Fuel Route Optimizer API

Backend REST API for fuel-efficient route planning and optimal refueling stops.

## Technology Stack

- Python 3.13
- Django 6.1.3
- Django REST Framework
- HTTPX
- Pytest

## Project Status

Initial development — environment configured.

## Objective

Calculate driving routes within the United States and recommend
fuel stops that minimize total fuel costs while respecting
vehicle range and fuel efficiency constraints.

## Vehicle Parameters

- Maximum range: 500 miles
- Fuel efficiency: 10 MPG
- Initial fuel level: Full tank (design assumption)
- Vehicle type: Unspecified

## Installation

```bash
git clone https://github.com/alesioandresv-ops/fuel-route-optimizer-api.git
cd fuel-route-optimizer-api

python -m venv .venv
```

Activate the virtual environment and install dependencies:

```bash
pip install -r requirements.txt
```

## Development Status

Under development.
