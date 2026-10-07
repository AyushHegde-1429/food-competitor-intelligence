# Cartly methodology

## Collection methodology

The project collects the latest available menu and metadata for the configured restaurant/platform/location combinations. Each collection run is logged in the `collection_runs` table with the runtime fields required for operational visibility: platform, restaurant, country, city, location, start/end timestamps, status, items collected, and errors.

A full daily run is performed via:

```bash
python main.py --all
```

This keeps the system scheduler-ready without introducing a heavy processing framework.

## Known total definition

Known totals include only the item subtotal plus any non-NULL fee, discount, or tax values stored in the snapshot. Unknown components remain `NULL` and are not assumed to be zero. Cartly therefore distinguishes clearly between item subtotal, delivery fee, service fee, tax, discount, known total, and unknown components.

## Freshness methodology

Snapshot freshness is evaluated from the collection timestamp. The basket comparison logic keeps fresh, recent, aging, and stale states explicit and deterministically derived from the data in the snapshot. Stale data is reported, not silently replaced.

## Menu parity

Menu parity compares exact normalized item names across available full-menu snapshots for the same restaurant and location. It does not infer demand, popularity, or profitability. It reports shared items, platform-only items, and a parity score based on the overlap of usable items.

## Item matching

Item matching is deterministic and exact-normalized by design. The system uses canonical item tables, platform item mappings, and review/reject states. Supported methods are `exact_normalized`, `deterministic_rule`, and `manual`.

The system explicitly avoids embeddings, LLM matching, and fuzzy AI matching.

## Price-gap methodology

Price-gap and market analysis use only real observations from comparable menu items across the same restaurant and location. The analysis distinguishes between observed item-price differences, fee differences, and known-total differences without claiming causality.

It returns insufficient data when the evidence is too weak.

## Winner analysis

Winner analysis reports the frequency with which a platform is the cheapest observed platform for comparable items and tracks winner stability across observations. It is a descriptive summary only and does not infer customer preference or success.

## Limitations

The system does not claim:

- live pricing unless the data was newly collected
- demand or popularity without separate research
- profitability without operational data
- customer preference without behavioral evidence
- checkout accuracy unless actual checkout feedback exists

Unknown values are never converted to zero, and no fabricated historical observations are introduced.
