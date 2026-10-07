# Cartly — Food Delivery Intelligence

Cartly is a Python-based historical intelligence layer for food-delivery market comparison. It preserves the existing FastAPI + SQLite structure and focuses on evidence-based intelligence rather than fake demand or speculative customer metrics.

## Architecture

- `main.py`: collection entry point and scheduler-ready runner
- `database.py`: persistence, matching, historical intelligence, and reporting
- `api.py`: FastAPI endpoints for analysis and operational workflows
- `collectors/`: platform-specific collectors for Talabat and Noon Food
- `configurations.py`: verified restaurant/platform/location catalog
- `generate_report.py`: lightweight HTML restaurant parity report

## Setup

1. Create and activate the virtual environment.
2. Install dependencies from `requirements.txt`.
3. Run the app or collection commands from the project root.

## Full collection command

Daily full collection is supported through the existing configuration catalog:

```bash
python main.py --all
```

Single-restaurant collection remains supported:

```bash
python main.py --platform "Talabat" --country "UAE" --city "Dubai" --restaurant "McDonald's" --location "Dubai Silicon Oasis"
```

## Scheduler guidance

Use an OS scheduler for daily runs. For Windows Task Scheduler, schedule `python main.py --all` once per day. This keeps the project scheduler-ready without introducing a heavy dependency.

## Analysis and report commands

```bash
python generate_report.py --restaurant "McDonald's" --country "UAE" --city "Dubai" --location "Dubai Silicon Oasis" --output "reports/mcdonalds.html"
```

## API coverage

Key endpoints include:

- `/market-analysis`
- `/data-quality`
- `/collection-runs`
- `/item-matches`
- `/item-matching/evaluation`
- `/menu-parity`
- `/price-history`
- `/deal-intelligence`
- `/competitive-price`
- `/menu-intelligence`
- `/cart/compare`
- `/checkout-feedback`
- `/saved-baskets`
- `/restaurant-parity`

## Data pipeline

The pipeline records snapshots, menu items, collection runs, canonical items, and deterministic item mappings. Unknown values remain `NULL` and are never fabricated.

## Intelligence layer

The project supports:

- collection logging and retry-friendly execution
- exact normalized item matching
- market and price-gap analysis
- deal intelligence against historical observations
- menu parity and basket comparison
- trust feedback and saved-basket foundations
- restaurant parity monitoring

## Limitations

This project does not claim:

- fake demand or popularity
- fake profitability
- customer preference
- live checkout accuracy without actual checkout data
- automatic AI matching

It also avoids cross-location or cross-restaurant mixing, and does not fabricate historical observations.
