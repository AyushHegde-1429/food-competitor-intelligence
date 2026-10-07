import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any


DB_NAME = "food_competitor.db"


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any(column[1] == column_name for column in columns):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def conn_execute(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    return cursor


def create_database() -> None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurant_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            location TEXT,
            rating REAL,
            delivery_fee_aed REAL,
            service_fee_aed REAL,
            discount_aed REAL,
            eta_minutes TEXT,
            collected_at TEXT NOT NULL,
            restaurant_status TEXT,
            busy_status TEXT,
            store_open INTEGER,
            promotion_text TEXT,
            promotion_type TEXT,
            raw_status TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS item_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            price_aed REAL,
            FOREIGN KEY (snapshot_id)
                REFERENCES restaurant_snapshots(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            price_aed REAL,
            category TEXT,
            available INTEGER,
            platform_item_id TEXT,
            FOREIGN KEY (snapshot_id)
                REFERENCES restaurant_snapshots(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            location TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            duration_seconds REAL,
            status TEXT NOT NULL,
            snapshot_id INTEGER,
            items_collected INTEGER,
            error_message TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS canonical_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            category TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS item_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_item_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            platform_item_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            match_method TEXT NOT NULL,
            confidence REAL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (canonical_item_id)
                REFERENCES canonical_items(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkout_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            location TEXT,
            cartly_known_total REAL,
            actual_checkout_total REAL,
            difference REAL,
            difference_percentage REAL,
            classification TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_baskets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            basket_name TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            location TEXT NOT NULL,
            items_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS basket_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            basket_id INTEGER NOT NULL,
            alert_threshold_pct REAL,
            alert_direction TEXT DEFAULT 'lower',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (basket_id) REFERENCES saved_baskets(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fee_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER,
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            location TEXT,
            delivery_fee_aed REAL,
            service_fee_aed REAL,
            discount_aed REAL,
            collected_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS availability_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER,
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            location TEXT,
            item_name TEXT NOT NULL,
            category TEXT,
            available INTEGER,
            collected_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER,
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            location TEXT,
            promotion_text TEXT,
            promotion_type TEXT,
            discount_aed REAL,
            collected_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    _ensure_column(conn, "restaurant_snapshots", "restaurant_status", "TEXT")
    _ensure_column(conn, "restaurant_snapshots", "busy_status", "TEXT")
    _ensure_column(conn, "restaurant_snapshots", "store_open", "INTEGER")
    _ensure_column(conn, "restaurant_snapshots", "promotion_text", "TEXT")
    _ensure_column(conn, "restaurant_snapshots", "promotion_type", "TEXT")
    _ensure_column(conn, "restaurant_snapshots", "raw_status", "TEXT")

    conn.commit()
    conn.close()


def normalize_item_name(name: str) -> str:
    if name is None:
        return ""
    text = str(name).strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[\/_\\]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _classify_checkout_feedback(*, cartly_known_total: float | None, actual_checkout_total: float | None) -> str:
    if cartly_known_total is None or actual_checkout_total is None:
        return "unknown"
    difference = float(actual_checkout_total) - float(cartly_known_total)
    if abs(difference) < 1e-9:
        return "matched"
    if difference > 0:
        return "higher_than_estimate"
    return "lower_than_estimate"


def record_collection_run(
    *,
    platform: str,
    country: str,
    city: str,
    restaurant: str,
    location: str | None,
    started_at: str,
    completed_at: str | None,
    duration_seconds: float | None,
    status: str,
    snapshot_id: int | None,
    items_collected: int = 0,
    error_message: str | None = None,
) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO collection_runs (
            platform, country, city, restaurant, location, started_at,
            completed_at, duration_seconds, status, snapshot_id,
            items_collected, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            platform,
            country,
            city,
            restaurant,
            location,
            started_at,
            completed_at,
            duration_seconds,
            status,
            snapshot_id,
            items_collected,
            error_message,
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": row_id,
        "platform": platform,
        "country": country,
        "city": city,
        "restaurant": restaurant,
        "location": location,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "status": status,
        "snapshot_id": snapshot_id,
        "items_collected": items_collected,
        "error_message": error_message,
    }


def get_collection_runs(*, limit: int = 50) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def record_checkout_feedback(
    *,
    platform: str,
    restaurant: str,
    location: str | None,
    cartly_known_total: float | None,
    actual_checkout_total: float | None,
    difference: float | None = None,
    difference_percentage: float | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    computed_difference = difference
    if computed_difference is None:
        if cartly_known_total is not None and actual_checkout_total is not None:
            computed_difference = float(actual_checkout_total) - float(cartly_known_total)
    computed_percentage = difference_percentage
    if computed_percentage is None and cartly_known_total not in (None, 0):
        if actual_checkout_total is not None and cartly_known_total is not None:
            computed_percentage = ((float(actual_checkout_total) - float(cartly_known_total)) / float(cartly_known_total)) * 100.0
    classification = _classify_checkout_feedback(
        cartly_known_total=cartly_known_total,
        actual_checkout_total=actual_checkout_total,
    )
    timestamp = _current_timestamp()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO checkout_feedback (
            platform, restaurant, location, cartly_known_total, actual_checkout_total,
            difference, difference_percentage, classification, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            platform,
            restaurant,
            location,
            cartly_known_total,
            actual_checkout_total,
            computed_difference,
            computed_percentage,
            classification,
            reason or "reported",
            timestamp,
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": row_id,
        "platform": platform,
        "restaurant": restaurant,
        "location": location,
        "cartly_known_total": cartly_known_total,
        "actual_checkout_total": actual_checkout_total,
        "difference": computed_difference,
        "difference_percentage": computed_percentage,
        "classification": classification,
        "reason": reason or "reported",
        "created_at": timestamp,
    }


def get_checkout_feedback_summary() -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM checkout_feedback ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    if not rows:
        return {
            "status": "insufficient_feedback",
            "sample_count": 0,
            "exact_match_rate": None,
            "mean_absolute_difference": None,
            "median_absolute_difference": None,
            "percentage_within_aed_1": None,
            "percentage_within_5pct": None,
            "samples": [],
        }
    differences = [abs(float(row["difference"])) for row in rows if row["difference"] is not None]
    exact_count = sum(1 for row in rows if row["classification"] == "matched")
    within_one_aed = sum(1 for row in rows if row["difference"] is not None and abs(float(row["difference"])) <= 1.0)
    within_five_pct = sum(
        1
        for row in rows
        if row["difference_percentage"] is not None and abs(float(row["difference_percentage"])) <= 5.0
    )
    summary = {
        "status": "ok",
        "sample_count": len(rows),
        "exact_match_rate": exact_count / len(rows),
        "mean_absolute_difference": (sum(differences) / len(differences)) if differences else None,
        "median_absolute_difference": median(differences) if differences else None,
        "percentage_within_aed_1": (within_one_aed / len(rows)) * 100.0,
        "percentage_within_5pct": (within_five_pct / len(rows)) * 100.0,
        "samples": [dict(row) for row in rows],
    }
    return summary


def save_basket(
    *,
    basket_name: str,
    restaurant: str,
    country: str,
    city: str,
    location: str,
    items: list[dict[str, Any]],
    alert_threshold_pct: float | None = None,
    alert_direction: str = "lower",
) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = _current_timestamp()
    cursor.execute(
        """
        INSERT INTO saved_baskets (
            basket_name, restaurant, country, city, location, items_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            basket_name,
            restaurant,
            country,
            city,
            location,
            json.dumps(items, ensure_ascii=False),
            timestamp,
            timestamp,
        ),
    )
    basket_id = cursor.lastrowid
    if alert_threshold_pct is not None:
        cursor.execute(
            """
            INSERT INTO basket_alerts (basket_id, alert_threshold_pct, alert_direction, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (basket_id, alert_threshold_pct, alert_direction, timestamp, timestamp),
        )
    conn.commit()
    conn.close()
    return int(basket_id)


def get_saved_basket(*, basket_id: int) -> dict[str, Any] | None:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM saved_baskets WHERE id = ?",
        (basket_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return None
    alert_row = conn.execute(
        "SELECT * FROM basket_alerts WHERE basket_id = ? ORDER BY id DESC LIMIT 1",
        (basket_id,),
    ).fetchone()
    result = dict(row)
    result["items"] = json.loads(result["items_json"])
    if alert_row is not None:
        result["alert"] = dict(alert_row)
        result["alert_threshold_pct"] = alert_row["alert_threshold_pct"]
        result["alert_direction"] = alert_row["alert_direction"]
        result["alert_active"] = bool(alert_row["is_active"])
    else:
        result["alert"] = None
        result["alert_threshold_pct"] = None
        result["alert_direction"] = None
        result["alert_active"] = False
    conn.close()
    return result


def list_saved_baskets(*, restaurant: str | None = None, country: str | None = None, city: str | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    where = []
    values: list[Any] = []
    if restaurant:
        where.append("restaurant = ?")
        values.append(restaurant)
    if country:
        where.append("country = ?")
        values.append(country)
    if city:
        where.append("city = ?")
        values.append(city)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"SELECT * FROM saved_baskets{clause} ORDER BY updated_at DESC",
        values,
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["items"] = json.loads(item["items_json"])
        alert_row = conn.execute(
            "SELECT * FROM basket_alerts WHERE basket_id = ? ORDER BY id DESC LIMIT 1",
            (item["id"],),
        ).fetchone()
        if alert_row is not None:
            item["alert_threshold_pct"] = alert_row["alert_threshold_pct"]
            item["alert_direction"] = alert_row["alert_direction"]
            item["alert_active"] = bool(alert_row["is_active"])
        else:
            item["alert_threshold_pct"] = None
            item["alert_direction"] = None
            item["alert_active"] = False
        results.append(item)
    conn.close()
    return results


def update_basket(*, basket_id: int, **kwargs: Any) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    row = conn.execute("SELECT * FROM saved_baskets WHERE id = ?", (basket_id,)).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Saved basket {basket_id} not found")
    timestamp = _current_timestamp()
    if "items" in kwargs:
        cursor.execute(
            "UPDATE saved_baskets SET items_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(kwargs["items"], ensure_ascii=False), timestamp, basket_id),
        )
    if "basket_name" in kwargs:
        cursor.execute("UPDATE saved_baskets SET basket_name = ?, updated_at = ? WHERE id = ?", (kwargs["basket_name"], timestamp, basket_id))
    if "restaurant" in kwargs:
        cursor.execute("UPDATE saved_baskets SET restaurant = ?, updated_at = ? WHERE id = ?", (kwargs["restaurant"], timestamp, basket_id))
    if "country" in kwargs:
        cursor.execute("UPDATE saved_baskets SET country = ?, updated_at = ? WHERE id = ?", (kwargs["country"], timestamp, basket_id))
    if "city" in kwargs:
        cursor.execute("UPDATE saved_baskets SET city = ?, updated_at = ? WHERE id = ?", (kwargs["city"], timestamp, basket_id))
    if "location" in kwargs:
        cursor.execute("UPDATE saved_baskets SET location = ?, updated_at = ? WHERE id = ?", (kwargs["location"], timestamp, basket_id))
    if "alert_threshold_pct" in kwargs or "alert_direction" in kwargs:
        threshold = kwargs.get("alert_threshold_pct")
        direction = kwargs.get("alert_direction", "lower")
        existing = conn.execute(
            "SELECT * FROM basket_alerts WHERE basket_id = ? ORDER BY id DESC LIMIT 1",
            (basket_id,),
        ).fetchone()
        values = (threshold, direction, 1, timestamp, timestamp)
        if existing is None:
            cursor.execute(
                "INSERT INTO basket_alerts (basket_id, alert_threshold_pct, alert_direction, is_active, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)",
                (basket_id, threshold, direction, timestamp, timestamp),
            )
        else:
            cursor.execute(
                "UPDATE basket_alerts SET alert_threshold_pct = ?, alert_direction = ?, is_active = 1, updated_at = ? WHERE id = ?",
                (threshold if threshold is not None else existing["alert_threshold_pct"], direction, timestamp, existing["id"]),
            )
    conn.commit()
    result = get_saved_basket(basket_id=basket_id)
    conn.close()
    return result or {"id": basket_id, "updated": True}


def delete_basket(*, basket_id: int) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM basket_alerts WHERE basket_id = ?", (basket_id,))
    cursor.execute("DELETE FROM saved_baskets WHERE id = ?", (basket_id,))
    conn.commit()
    conn.close()
    return {"deleted": True, "basket_id": basket_id}


def execute_collection_run(
    *,
    configuration: Any,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    from collectors import get_collector

    started = datetime.now(timezone.utc).isoformat()
    try:
        collector = get_collector(configuration.platform)
        result = collector.collect(
            platform=configuration.platform,
            country=configuration.country,
            city=configuration.city,
            restaurant=configuration.restaurant,
            location=configuration.location or "",
            url=configuration.url,
            items=list(configuration.items),
        )
        snapshot_id = save_data(result.to_dict(), location=configuration.location)
        completed = datetime.now(timezone.utc).isoformat()
        duration = (datetime.now(timezone.utc) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
        run = record_collection_run(
            platform=configuration.platform,
            country=configuration.country,
            city=configuration.city,
            restaurant=configuration.restaurant,
            location=configuration.location,
            started_at=started,
            completed_at=completed,
            duration_seconds=duration,
            status="success",
            snapshot_id=snapshot_id,
            items_collected=len(result.menu_items or result.items),
            error_message=None,
        )
        return {"status": "success", "snapshot_id": snapshot_id, "run": run, "configuration": configuration.model_dump() if hasattr(configuration, "model_dump") else vars(configuration)}
    except Exception as exc:
        completed = datetime.now(timezone.utc).isoformat()
        duration = (datetime.now(timezone.utc) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()
        run = record_collection_run(
            platform=configuration.platform,
            country=configuration.country,
            city=configuration.city,
            restaurant=configuration.restaurant,
            location=configuration.location,
            started_at=started,
            completed_at=completed,
            duration_seconds=duration,
            status="failed",
            snapshot_id=None,
            items_collected=0,
            error_message=str(exc),
        )
        if not continue_on_error:
            raise
        return {"status": "failed", "error": str(exc), "run": run, "configuration": configuration.model_dump() if hasattr(configuration, "model_dump") else vars(configuration)}


def collect_all_configurations(*, configurations: list[Any] | None = None, platform: str | None = None, country: str | None = None, city: str | None = None, restaurant: str | None = None, location: str | None = None) -> list[dict[str, Any]]:
    from configurations import get_executable_configurations

    if configurations is None:
        configurations = get_executable_configurations()
    filtered: list[Any] = []
    for configuration in configurations:
        if platform and configuration.platform.strip().lower() != platform.strip().lower():
            continue
        if country and configuration.country.strip().lower() != country.strip().lower():
            continue
        if city and configuration.city.strip().lower() != city.strip().lower():
            continue
        if restaurant and configuration.restaurant.strip().lower() != restaurant.strip().lower():
            continue
        if location and (configuration.location or "").strip().lower() != location.strip().lower():
            continue
        filtered.append(configuration)
    return [execute_collection_run(configuration=configuration, continue_on_error=True) for configuration in filtered]


def ensure_canonical_item(*, restaurant: str, canonical_name: str, category: str | None = None) -> dict[str, Any]:
    normalized_name = normalize_item_name(canonical_name)
    if not normalized_name:
        raise ValueError("canonical_name must not be empty")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT * FROM canonical_items WHERE restaurant = ? AND normalized_name = ?",
        (restaurant, normalized_name),
    ).fetchone()
    if existing is not None:
        conn.close()
        return dict(existing)
    created_at = _current_timestamp()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO canonical_items (restaurant, canonical_name, normalized_name, category, created_at) VALUES (?, ?, ?, ?, ?)",
        (restaurant, canonical_name, normalized_name, category, created_at),
    )
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": item_id,
        "restaurant": restaurant,
        "canonical_name": canonical_name,
        "normalized_name": normalized_name,
        "category": category,
        "created_at": created_at,
    }


def record_item_mapping(*, canonical_item_id: int, platform: str, platform_item_name: str, platform_item_name_normalized: str | None = None, match_method: str = "exact_normalized", confidence: float = 1.0, status: str = "confirmed") -> dict[str, Any]:
    normalized = normalize_item_name(platform_item_name) if platform_item_name_normalized is None else platform_item_name_normalized
    now = _current_timestamp()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO item_mappings (
            canonical_item_id, platform, platform_item_name, normalized_name,
            match_method, confidence, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (canonical_item_id, platform, platform_item_name, normalized, match_method, confidence, status, now, now),
    )
    item_mapping_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": item_mapping_id,
        "canonical_item_id": canonical_item_id,
        "platform": platform,
        "platform_item_name": platform_item_name,
        "normalized_name": normalized,
        "match_method": match_method,
        "confidence": confidence,
        "status": status,
        "created_at": now,
        "updated_at": now,
    }


def record_fee_observation(*, snapshot_id: int | None, platform: str, restaurant: str, country: str | None = None, city: str | None = None, location: str | None = None, delivery_fee_aed: float | None = None, service_fee_aed: float | None = None, discount_aed: float | None = None, collected_at: str | None = None) -> dict[str, Any]:
    ts = collected_at or _current_timestamp()
    country = country or ""
    city = city or ""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO fee_observations (
            snapshot_id, platform, country, city, restaurant, location,
            delivery_fee_aed, service_fee_aed, discount_aed, collected_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            platform,
            country,
            city,
            restaurant,
            location,
            delivery_fee_aed,
            service_fee_aed,
            discount_aed,
            ts,
            _current_timestamp(),
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": row_id,
        "snapshot_id": snapshot_id,
        "platform": platform,
        "country": country,
        "city": city,
        "restaurant": restaurant,
        "location": location,
        "delivery_fee_aed": delivery_fee_aed,
        "service_fee_aed": service_fee_aed,
        "discount_aed": discount_aed,
        "collected_at": ts,
    }


def record_availability_observation(*, snapshot_id: int | None, platform: str, restaurant: str, country: str | None = None, city: str | None = None, item_name: str, location: str | None = None, category: str | None = None, available: bool | int | None = None, collected_at: str | None = None) -> dict[str, Any]:
    ts = collected_at or _current_timestamp()
    country = country or ""
    city = city or ""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO availability_observations (
            snapshot_id, platform, country, city, restaurant, location,
            item_name, category, available, collected_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            platform,
            country,
            city,
            restaurant,
            location,
            item_name,
            category,
            None if available is None else int(bool(available)),
            ts,
            _current_timestamp(),
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": row_id,
        "snapshot_id": snapshot_id,
        "platform": platform,
        "country": country,
        "city": city,
        "restaurant": restaurant,
        "location": location,
        "item_name": item_name,
        "category": category,
        "available": available,
        "collected_at": ts,
    }


def record_promotion_observation(*, snapshot_id: int | None, platform: str, restaurant: str, country: str | None = None, city: str | None = None, location: str | None = None, promotion_text: str | None = None, promotion_type: str | None = None, discount_aed: float | None = None, collected_at: str | None = None) -> dict[str, Any]:
    ts = collected_at or _current_timestamp()
    country = country or ""
    city = city or ""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO promotions (
            snapshot_id, platform, country, city, restaurant, location,
            promotion_text, promotion_type, discount_aed, collected_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            platform,
            country,
            city,
            restaurant,
            location,
            promotion_text,
            promotion_type,
            discount_aed,
            ts,
            _current_timestamp(),
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": row_id,
        "snapshot_id": snapshot_id,
        "platform": platform,
        "country": country,
        "city": city,
        "restaurant": restaurant,
        "location": location,
        "promotion_text": promotion_text,
        "promotion_type": promotion_type,
        "discount_aed": discount_aed,
        "collected_at": ts,
    }


def sync_canonical_items_from_snapshots(*, restaurant: str, country: str | None = None, city: str | None = None, location: str | None = None) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    filters = ["LOWER(s.restaurant) = LOWER(?)"]
    values: list[Any] = [restaurant]

    if country:
        filters.append("LOWER(s.country) = LOWER(?)")
        values.append(country)
    if city:
        filters.append("LOWER(s.city) = LOWER(?)")
        values.append(city)
    if location:
        filters.append("LOWER(COALESCE(s.location, '')) = LOWER(?)")
        values.append(location)

    rows = conn.execute(
        f"""
        SELECT DISTINCT m.item_name, m.category, s.platform, s.location, s.country, s.city
        FROM menu_items m
        JOIN restaurant_snapshots s ON s.id = m.snapshot_id
        WHERE {' AND '.join(filters)}
        ORDER BY m.item_name
        """,
        values,
    ).fetchall()

    groupings: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for row in rows:
        normalized = normalize_item_name(row["item_name"])
        if not normalized:
            continue
        groupings.setdefault(normalized, {}).setdefault(row["platform"], set()).add(row["item_name"])

    canonical_items_created = 0
    mappings_created: list[dict[str, Any]] = []
    for normalized_name, platform_map in sorted(groupings.items()):
        canonical_name = next(iter(next(iter(platform_map.values()))))
        existing_canonical = conn.execute(
            "SELECT * FROM canonical_items WHERE restaurant = ? AND normalized_name = ?",
            (restaurant, normalized_name),
        ).fetchone()
        canonical = ensure_canonical_item(
            restaurant=restaurant,
            canonical_name=canonical_name,
            category=(next((row["category"] for row in rows if normalize_item_name(row["item_name"]) == normalized_name and row["category"]), None) if rows else None),
        )
        if existing_canonical is None:
            canonical_items_created += 1

        for platform, item_names in sorted(platform_map.items()):
            for item_name in sorted(item_names):
                existing_mapping = conn.execute(
                    """
                    SELECT id FROM item_mappings
                    WHERE canonical_item_id = ? AND platform = ? AND normalized_name = ?
                    """,
                    (canonical["id"], platform, normalized_name),
                ).fetchone()
                if existing_mapping is None:
                    mapping = record_item_mapping(
                        canonical_item_id=canonical["id"],
                        platform=platform,
                        platform_item_name=item_name,
                        platform_item_name_normalized=normalized_name,
                        match_method="exact_normalized",
                        confidence=1.0,
                        status="confirmed",
                    )
                    mappings_created.append(mapping)

    conn.close()
    return {
        "canonical_items_created": canonical_items_created,
        "mappings_created": mappings_created,
    }


def match_item_names(item_name: str, platform: str, restaurant: str) -> bool:
    normalized_name = normalize_item_name(item_name)
    if not normalized_name:
        return False
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT COUNT(*) as matches
        FROM item_mappings m
        JOIN canonical_items c ON c.id = m.canonical_item_id
        WHERE c.restaurant = ?
          AND LOWER(m.platform) = LOWER(?)
          AND m.normalized_name = ?
          AND m.status IN ('confirmed', 'review')
        """,
        (restaurant, platform, normalized_name),
    ).fetchone()
    conn.close()
    return (row["matches"] if row else 0) > 0


def evaluate_item_mapping_results(*, true_positives: int = 0, false_positives: int = 0, false_negatives: int = 0) -> dict[str, float]:
    precision = 0.0 if (true_positives + false_positives) == 0 else true_positives / (true_positives + false_positives)
    recall = 0.0 if (true_positives + false_negatives) == 0 else true_positives / (true_positives + false_negatives)
    f1 = 0.0 if (precision + recall) == 0 else (2 * precision * recall) / (precision + recall)
    return {
        "true_positives": float(true_positives),
        "false_positives": float(false_positives),
        "false_negatives": float(false_negatives),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def save_data(data: dict[str, Any], *, location: str | None = None) -> int:
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    restaurant_name = data["restaurant"]
    if restaurant_name.strip().lower() == "saravana bhavan":
        restaurant_name = "Saravanaa Bhavan"
    elif restaurant_name.strip().lower() == "nando's restaurant":
        restaurant_name = "Nando's"
    elif restaurant_name.strip().lower() == "zaatar w zeit, by robots":
        restaurant_name = "Zaatar w Zeit"
    elif restaurant_name.strip().lower() == "jazeel restaurant and cafe":
        restaurant_name = "Jazeel"

    insert_columns = (
        "platform, country, city, restaurant, location, rating, delivery_fee_aed, "
        "service_fee_aed, discount_aed, eta_minutes, collected_at, restaurant_status, "
        "busy_status, store_open, promotion_text, promotion_type, raw_status"
    )
    values = (
        data["platform"],
        data["country"],
        data["city"],
        restaurant_name,
        data["location"] if location is None else location,
        data["rating"],
        data["delivery_fee_aed"],
        data["service_fee_aed"],
        data["discount_aed"],
        data["eta_minutes"],
        data.get("collected_at") or data.get("collection_timestamp") or _current_timestamp(),
        data.get("restaurant_status") or data.get("store_status"),
        data.get("busy_status"),
        None if data.get("store_open") is None else int(bool(data.get("store_open"))),
        data.get("promotion_text") or data.get("promotion"),
        data.get("promotion_type"),
        data.get("raw_status"),
    )
    cursor.execute(
        f"INSERT INTO restaurant_snapshots ({insert_columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        values,
    )

    snapshot_id = cursor.lastrowid
    if snapshot_id is None:
        conn.rollback()
        conn.close()
        raise RuntimeError("SQLite did not return a snapshot ID")

    for item in data["items"]:
        cursor.execute("""
            INSERT INTO item_prices (
                snapshot_id,
                item_name,
                price_aed
            )
            VALUES (?, ?, ?)
        """, (
            snapshot_id,
            item["name"],
            item["price_aed"],
        ))

    for menu_item in data.get("menu_items", []):
        cursor.execute("""
            INSERT INTO menu_items (
                snapshot_id,
                item_name,
                price_aed,
                category,
                available,
                platform_item_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id,
            menu_item["name"],
            menu_item["price_aed"],
            menu_item.get("category"),
            None if menu_item.get("available") is None else int(menu_item["available"]),
            menu_item.get("platform_item_id"),
        ))

    observed_at = data.get("collected_at") or data.get("collection_timestamp") or _current_timestamp()
    cursor.execute(
        """
        INSERT INTO fee_observations (
            snapshot_id, platform, country, city, restaurant, location,
            delivery_fee_aed, service_fee_aed, discount_aed, collected_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            data["platform"],
            data["country"],
            data["city"],
            restaurant_name,
            data["location"] if location is None else location,
            data.get("delivery_fee_aed"),
            data.get("service_fee_aed"),
            data.get("discount_aed"),
            observed_at,
            _current_timestamp(),
        ),
    )

    for menu_item in data.get("menu_items", []):
        cursor.execute(
            """
            INSERT INTO availability_observations (
                snapshot_id, platform, country, city, restaurant, location,
                item_name, category, available, collected_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                data["platform"],
                data["country"],
                data["city"],
                restaurant_name,
                data["location"] if location is None else location,
                menu_item.get("name"),
                menu_item.get("category"),
                None if menu_item.get("available") is None else int(bool(menu_item.get("available"))),
                observed_at,
                _current_timestamp(),
            ),
        )

    if data.get("promotion_text") or data.get("promotion_type") or data.get("discount_aed") is not None:
        cursor.execute(
            """
            INSERT INTO promotions (
                snapshot_id, platform, country, city, restaurant, location,
                promotion_text, promotion_type, discount_aed, collected_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                data["platform"],
                data["country"],
                data["city"],
                restaurant_name,
                data["location"] if location is None else location,
                data.get("promotion_text") or data.get("promotion"),
                data.get("promotion_type"),
                data.get("discount_aed"),
                observed_at,
                _current_timestamp(),
            ),
        )

    conn.commit()
    conn.close()

    print(f"Saved snapshot to database. ID: {snapshot_id}")
    return int(snapshot_id)


def list_snapshots(
    *,
    platform: str | None = None,
    country: str | None = None,
    restaurant: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    filters = []
    values: list[Any] = []
    for column, value in (
        ("platform", platform),
        ("country", country),
        ("restaurant", restaurant),
    ):
        if value:
            filters.append(f"{column} = ?")
            values.append(value)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT id, platform, country, city, restaurant, location, rating,
               delivery_fee_aed, service_fee_aed, discount_aed, eta_minutes,
               collected_at
        FROM restaurant_snapshots
        {where_clause}
        ORDER BY collected_at DESC
        LIMIT ?
    """
    values.append(limit)
    rows = conn.execute(query, values).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_snapshot(snapshot_id: int) -> dict[str, Any] | None:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    snapshot = conn.execute(
        "SELECT * FROM restaurant_snapshots WHERE id = ?",
        (snapshot_id,),
    ).fetchone()
    if snapshot is None:
        conn.close()
        return None

    result = dict(snapshot)
    result["items"] = [
        dict(row)
        for row in conn.execute(
            """
            SELECT item_name AS name, price_aed
            FROM item_prices
            WHERE snapshot_id = ?
            ORDER BY id
            """,
            (snapshot_id,),
        ).fetchall()
    ]
    conn.close()
    return result


def compare_latest(
    *,
    restaurant: str,
    item: str,
    city: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    filters = [
        "CASE WHEN LOWER(s.restaurant) = 'saravana bhavan' "
        "THEN 'saravanaa bhavan' ELSE LOWER(s.restaurant) END = LOWER(?)",
        "LOWER(p.item_name) = LOWER(?)",
        "p.price_aed IS NOT NULL",
    ]
    values: list[Any] = [restaurant, item]
    if city:
        filters.append("LOWER(s.city) = LOWER(?)")
        values.append(city)
    if country:
        filters.append("LOWER(s.country) = LOWER(?)")
        values.append(country)

    query = f"""
        WITH ranked_prices AS (
            SELECT
                s.platform,
                p.price_aed AS price,
                s.rating,
                s.delivery_fee_aed AS delivery_fee,
                s.service_fee_aed AS service_fee,
                s.discount_aed AS discount,
                s.eta_minutes AS eta,
                s.collected_at,
                ROW_NUMBER() OVER (
                    PARTITION BY s.platform
                    ORDER BY s.collected_at DESC, p.id DESC
                ) AS row_number
            FROM restaurant_snapshots s
            JOIN item_prices p ON p.snapshot_id = s.id
            WHERE {' AND '.join(filters)}
        )
        SELECT platform, price, rating, delivery_fee, service_fee,
               discount, eta, collected_at
        FROM ranked_prices
        WHERE row_number = 1
        ORDER BY price, platform
    """
    rows = [dict(row) for row in conn.execute(query, values).fetchall()]
    conn.close()

    prices = [row["price"] for row in rows]
    cheapest_price = min(prices) if prices else None
    return {
        "results": rows,
        "cheapest_platform": rows[0]["platform"] if rows else None,
        "cheapest_price": cheapest_price,
        "price_difference": (max(prices) - cheapest_price) if prices else None,
        "number_of_platforms_with_data": len(rows),
    }


_ADDON_PATTERN = re.compile(
    r"\b(add[- ]?ons?|addons?|extras?|modifiers?)\b",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _canonical_restaurant(name: str) -> str:
    if _normalize_name(name) == "saravana bhavan":
        return "Saravanaa Bhavan"
    return name.strip()


def _canonical_location(value: str) -> str:
    text = _normalize_name(value)
    if text.startswith("al "):
        return text[3:]
    return text


def _location_matches(stored: str | None, requested: str) -> bool:
    requested_canonical = _canonical_location(requested)
    if not stored or not requested_canonical:
        return False
    stored_normalized = _normalize_name(stored)
    if _canonical_location(stored) == requested_canonical:
        return True
    return re.search(rf"\b{re.escape(requested_canonical)}\b", stored_normalized) is not None


def _is_modifier_or_addon(name: str, category: str | None) -> bool:
    haystack = f"{name} {category or ''}"
    if _ADDON_PATTERN.search(haystack):
        return True
    normalized = _normalize_name(name)
    return normalized.startswith("add ") or normalized.startswith("extra ")


def _comparable_menu_items(
    conn: sqlite3.Connection,
    snapshot_id: int,
) -> dict[str, tuple[str, float]]:
    rows = conn.execute(
        """
        SELECT item_name, price_aed, category
        FROM menu_items
        WHERE snapshot_id = ?
        ORDER BY id
        """,
        (snapshot_id,),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """
            SELECT item_name, price_aed, NULL AS category
            FROM item_prices
            WHERE snapshot_id = ?
            ORDER BY id
            """,
            (snapshot_id,),
        ).fetchall()

    items: dict[str, tuple[str, float]] = {}
    for row in rows:
        name = row["item_name"] or ""
        price = row["price_aed"]
        if not name or price is None or price <= 0:
            continue
        if _is_modifier_or_addon(name, row["category"]):
            continue
        key = _normalize_name(name)
        if key not in items:
            items[key] = (name, float(price))
    return items


def compare_menus(
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT s.id, s.platform, s.country, s.city, s.restaurant,
               s.location, s.collected_at
        FROM restaurant_snapshots s
        WHERE
            CASE WHEN LOWER(s.restaurant) = 'saravana bhavan'
                 THEN 'saravanaa bhavan' ELSE LOWER(s.restaurant) END
                = LOWER(?)
            AND LOWER(s.country) = LOWER(?)
            AND LOWER(s.city) = LOWER(?)
        ORDER BY s.platform, s.collected_at DESC, s.id DESC
    """
    candidates = conn.execute(
        query,
        (_canonical_restaurant(restaurant), country, city),
    ).fetchall()

    platform_rows: list[dict[str, Any]] = []
    menus: dict[str, dict[str, tuple[str, float]]] = {}
    selected_platforms: set[str] = set()
    for candidate in candidates:
        platform = candidate["platform"]
        if platform in selected_platforms:
            continue
        if not _location_matches(candidate["location"], location):
            continue
        selected_platforms.add(platform)
        menu = _comparable_menu_items(conn, candidate["id"])
        platform_rows.append({
            "platform": platform,
            "location": candidate["location"],
            "snapshot_id": candidate["id"],
            "collected_at": candidate["collected_at"],
            "item_count": len(menu),
        })
        menus[platform] = menu
    conn.close()

    matched_items: list[dict[str, Any]] = []
    if len(platform_rows) >= 2:
        shared_keys = set.intersection(*(set(menu) for menu in menus.values()))
        for key in sorted(shared_keys):
            display_name = next(iter(menus.values()))[key][0]
            prices = {
                platform: menus[platform][key][1]
                for platform in menus
            }
            cheapest_price = min(prices.values())
            cheapest_platforms = [
                platform
                for platform, price in prices.items()
                if price == cheapest_price
            ]
            matched_items.append({
                "name": display_name,
                "prices": prices,
                "cheapest_platform": cheapest_platforms[0],
                "cheapest_price": cheapest_price,
                "price_difference": max(prices.values()) - cheapest_price,
            })

    return {
        "restaurant": _canonical_restaurant(restaurant),
        "country": country,
        "city": city,
        "location": location,
        "platforms": platform_rows,
        "items": matched_items,
        "matched_item_count": len(matched_items),
        "number_of_platforms_with_data": len(platform_rows),
    }


def _basket_menu_items(
    conn: sqlite3.Connection,
    snapshot_id: int,
) -> dict[str, tuple[str, Decimal]]:
    rows = conn.execute(
        """
        SELECT item_name, price_aed, category, available
        FROM menu_items
        WHERE snapshot_id = ?
        ORDER BY id
        """,
        (snapshot_id,),
    ).fetchall()

    items: dict[str, tuple[str, Decimal]] = {}
    for row in rows:
        name = row["item_name"] or ""
        price = row["price_aed"]
        if not name or price is None or row["available"] == 0:
            continue
        try:
            numeric_price = float(price)
            decimal_price = Decimal(str(price))
        except (TypeError, ValueError, InvalidOperation):
            continue
        if not math.isfinite(numeric_price) or decimal_price <= 0:
            continue
        if _is_modifier_or_addon(name, row["category"]):
            continue
        key = _normalize_name(name)
        if key and key not in items:
            items[key] = (name, decimal_price)
    return items


def _known_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    if not math.isfinite(numeric_value) or amount < 0:
        return None
    return amount


FRESHNESS_THRESHOLDS_MINUTES = {
    "fresh": 15,
    "recent": 60,
    "aging": 24 * 60,
}
DEFAULT_REFRESH_THRESHOLD_MINUTES = 24 * 60


def _snapshot_age_seconds(
    collected_at: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if not collected_at:
        return None
    try:
        collected = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        if collected.tzinfo is None:
            collected = collected.astimezone()
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.astimezone()
        age = (current.astimezone(timezone.utc) - collected.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None
    return max(age, 0.0)


def _format_age(age_minutes: int) -> str:
    if age_minutes < 60:
        return f"{age_minutes} min ago"
    hours = age_minutes // 60
    if age_minutes < 24 * 60:
        return f"{hours} {'hr' if hours == 1 else 'hrs'} ago"
    days = age_minutes // (24 * 60)
    return f"{days} {'day' if days == 1 else 'days'} ago"


def get_snapshot_freshness(
    collected_at: str | None,
    *,
    now: datetime | None = None,
    refresh_threshold_minutes: int = DEFAULT_REFRESH_THRESHOLD_MINUTES,
) -> dict[str, Any]:
    """Return deterministic snapshot age, label, and refresh decision.

    Naive timestamps are interpreted in the host's local timezone, matching
    existing collector timestamps; offset-aware timestamps are normalized to UTC.
    """
    if refresh_threshold_minutes < 0:
        raise ValueError("refresh_threshold_minutes must be non-negative")
    age_seconds = _snapshot_age_seconds(collected_at, now=now)
    if age_seconds is None:
        return {
            "age_minutes": None,
            "freshness_status": "stale",
            "freshness_label": "Prices may be outdated — collection time unavailable",
            "should_refresh": True,
        }

    age_minutes = int(age_seconds // 60)
    if age_seconds < FRESHNESS_THRESHOLDS_MINUTES["fresh"] * 60:
        status = "fresh"
    elif age_seconds < FRESHNESS_THRESHOLDS_MINUTES["recent"] * 60:
        status = "recent"
    elif age_seconds <= FRESHNESS_THRESHOLDS_MINUTES["aging"] * 60:
        status = "aging"
    else:
        status = "stale"

    age_label = _format_age(age_minutes) if age_minutes else "just now"
    if status == "stale":
        label = f"Prices may be outdated — checked {age_label}"
    else:
        label = f"Prices checked {age_label}"
    return {
        "age_minutes": age_minutes,
        "freshness_status": status,
        "freshness_label": label,
        "should_refresh": should_refresh_snapshot(
            collected_at,
            refresh_after_minutes=refresh_threshold_minutes,
            now=now,
        ),
    }


def is_snapshot_fresh(
    collected_at: str | None,
    *,
    max_age_minutes: int = FRESHNESS_THRESHOLDS_MINUTES["fresh"],
    now: datetime | None = None,
) -> bool:
    """Return whether a snapshot is younger than a configurable age threshold."""
    if max_age_minutes < 0:
        raise ValueError("max_age_minutes must be non-negative")
    age_seconds = _snapshot_age_seconds(collected_at, now=now)
    return age_seconds is not None and age_seconds < max_age_minutes * 60


def should_refresh_snapshot(
    collected_at: str | None,
    *,
    refresh_after_minutes: int = DEFAULT_REFRESH_THRESHOLD_MINUTES,
    now: datetime | None = None,
) -> bool:
    """Return true when no timestamp exists or the refresh age is reached."""
    if refresh_after_minutes < 0:
        raise ValueError("refresh_after_minutes must be non-negative")
    age_seconds = _snapshot_age_seconds(collected_at, now=now)
    return age_seconds is None or age_seconds >= refresh_after_minutes * 60


def _platform_confidence(
    *,
    complete: bool,
    cost_values: dict[str, Decimal | None],
    freshness_status: str,
) -> str:
    if not complete or freshness_status == "stale":
        return "low"
    fee_fields_known = all(
        cost_values[field] is not None
        for field in ("delivery_fee", "service_fee", "discount")
    )
    if fee_fields_known and freshness_status == "fresh":
        return "high"
    if freshness_status in {"fresh", "recent", "aging"} and any(
        value is not None for value in cost_values.values()
    ):
        return "medium"
    return "low"


CARTLY_SCORE_WEIGHTS = {
    "price": 40,
    "completeness": 20,
    "freshness": 15,
    "rating": 10,
    "eta": 10,
    "fee_transparency": 5,
}
CARTLY_ETA_SCORE_CAP_MINUTES = 120
CARTLY_SCORE_BANDS = ((85, "excellent"), (70, "good"), (50, "fair"), (0, "low"))


def _parse_eta_minutes(value: str | None) -> float | None:
    if not value:
        return None
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    if not numbers:
        return None
    parsed = [float(number) for number in numbers]
    if not all(math.isfinite(number) for number in parsed):
        return None
    return sum(parsed) / len(parsed)


def calculate_cartly_scores(
    platforms: list[dict[str, Any]],
    *,
    comparison_basis: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Calculate deterministic platform scores from available snapshot signals.

    Missing component values stay null and do not earn their configured weight.
    Incomplete baskets receive no score and are ineligible for best-overall.
    """
    eligible = [platform for platform in platforms if platform.get("complete")]
    price_values: dict[str, Decimal] = {}
    if comparison_basis == "known_total":
        price_values = {
            platform["platform"]: platform["_known_total_decimal"]
            for platform in eligible
            if platform.get("_known_total_decimal") is not None
        }
    elif comparison_basis == "item_subtotal":
        price_values = {
            platform["platform"]: platform["_subtotal"]
            for platform in eligible
        }

    price_scores: dict[str, float] = {}
    if len(price_values) >= 2:
        lowest = min(price_values.values())
        highest = max(price_values.values())
        for platform, value in price_values.items():
            price_scores[platform] = (
                100.0 if highest == lowest else float((highest - value) / (highest - lowest) * 100)
            )

    freshness_scores = {"fresh": 100.0, "recent": 80.0, "aging": 50.0, "stale": 0.0}
    best_platform: dict[str, Any] | None = None
    for platform in platforms:
        complete = bool(platform.get("complete"))
        freshness_status = platform.get("freshness_status")
        rating = platform.get("_rating")
        if rating is not None:
            try:
                rating = float(rating)
                if not math.isfinite(rating) or not 0 <= rating <= 5:
                    rating = None
            except (TypeError, ValueError):
                rating = None
        eta_minutes = _parse_eta_minutes(platform.get("_eta_minutes"))
        known_fees = sum(
            platform.get(field) is not None
            for field in ("delivery_fee", "service_fee", "discount")
        )
        fee_transparency = known_fees / 3 * 100 if known_fees else None
        components: dict[str, float | None] = {
            "price": price_scores.get(platform["platform"]),
            "completeness": 100.0 if complete else 0.0,
            "freshness": freshness_scores.get(freshness_status),
            "rating": rating / 5 * 100 if rating is not None else None,
            "eta": max(0.0, 100 * (1 - eta_minutes / CARTLY_ETA_SCORE_CAP_MINUTES))
            if eta_minutes is not None else None,
            "fee_transparency": fee_transparency,
        }
        if complete:
            score = round(sum(
                CARTLY_SCORE_WEIGHTS[name] * value / 100
                for name, value in components.items()
                if value is not None
            ), 1)
            score_band = next(band for threshold, band in CARTLY_SCORE_BANDS if score >= threshold)
        else:
            score = None
            score_band = "ineligible" if platform.get("available") else "unavailable"

        reasons: list[str] = []
        if not platform.get("available"):
            reasons.append("No valid full-menu snapshot")
        elif not complete:
            reasons.append("Basket is incomplete")
        elif components["price"] is not None:
            best_price = min(price_values.values()) if price_values else None
            current_price = price_values.get(platform["platform"])
            if current_price == best_price:
                reasons.append("Lowest comparable basket cost")
        if complete and freshness_status == "fresh":
            reasons.append("Fresh pricing data")
        elif freshness_status == "stale":
            reasons.append("Pricing snapshot is stale")
        if rating is not None:
            reasons.append(f"Restaurant rating: {rating:.1f}/5")
        if eta_minutes is not None:
            reasons.append(f"Estimated delivery: {eta_minutes:g} min")
        if known_fees == 3:
            reasons.append("Delivery, service, and discount fields are known")
        elif known_fees:
            reasons.append("Some fee fields are unknown")

        coverage = sum(
            CARTLY_SCORE_WEIGHTS[name]
            for name, value in components.items()
            if value is not None
        )
        if not complete or freshness_status == "stale" or components["price"] is None:
            confidence = "low"
        elif (
            freshness_status == "fresh"
            and coverage == 100
            and known_fees == 3
            and rating is not None
            and eta_minutes is not None
        ):
            confidence = "high"
        elif freshness_status in {"fresh", "recent"} and coverage >= 60:
            confidence = "medium"
        else:
            confidence = "low"

        platform["cartly_score"] = score
        platform["score_band"] = score_band
        platform["component_scores"] = components
        platform["score_reasons"] = reasons
        platform["score_confidence"] = confidence
        if complete and score is not None and (
            best_platform is None
            or score > best_platform["cartly_score"]
            or (score == best_platform["cartly_score"] and platform["platform"] < best_platform["platform"])
        ):
            best_platform = platform

    return platforms, best_platform["platform"] if best_platform else None


def compare_basket(
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    from collectors.catalog import PLATFORM_CATALOG

    platforms = [platform.name for platform in PLATFORM_CATALOG if platform.implemented]
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        snapshots = conn.execute(
            """
            SELECT id, platform, country, city, restaurant, location, collected_at,
                     delivery_fee_aed, service_fee_aed, discount_aed, rating, eta_minutes
            FROM restaurant_snapshots
            WHERE
                CASE WHEN LOWER(restaurant) = 'saravana bhavan'
                     THEN 'saravanaa bhavan' ELSE LOWER(restaurant) END
                    = LOWER(?)
                AND LOWER(country) = LOWER(?)
                AND LOWER(city) = LOWER(?)
            ORDER BY platform, collected_at DESC, id DESC
            """,
            (_canonical_restaurant(restaurant), country, city),
        ).fetchall()

        platform_results: list[dict[str, Any]] = []
        complete_results: list[dict[str, Any]] = []
        available_platform_count = 0
        requested_items = [
            {"name": item["name"], "quantity": item["quantity"]}
            for item in items
        ]

        for platform in platforms:
            selected_snapshot = None
            menu: dict[str, tuple[str, Decimal]] = {}
            for snapshot in snapshots:
                if snapshot["platform"].strip().casefold() != platform.casefold():
                    continue
                if not _location_matches(snapshot["location"], location):
                    continue
                candidate_menu = _basket_menu_items(conn, snapshot["id"])
                if candidate_menu:
                    selected_snapshot = snapshot
                    menu = candidate_menu
                    break

            matched_items: list[dict[str, Any]] = []
            missing_items: list[dict[str, Any]] = []
            basket_items: list[dict[str, Any]] = []
            subtotal = Decimal("0")
            if selected_snapshot is not None and menu:
                available_platform_count += 1

            for requested in requested_items:
                match = menu.get(_normalize_name(requested["name"]))
                if match is None:
                    missing_item = {
                        "requested_name": requested["name"],
                        "matched_name": None,
                        "quantity": requested["quantity"],
                        "unit_price": None,
                        "line_total": None,
                        "available": False,
                    }
                    missing_items.append(missing_item)
                    basket_items.append(missing_item)
                    continue
                matched_name, unit_price = match
                line_total = unit_price * requested["quantity"]
                subtotal += line_total
                matched_item = {
                    "requested_name": requested["name"],
                    "matched_name": matched_name,
                    "quantity": requested["quantity"],
                    "unit_price": float(unit_price),
                    "line_total": float(line_total),
                    "available": True,
                }
                matched_items.append(matched_item)
                basket_items.append(matched_item)

            available = selected_snapshot is not None and bool(menu)
            complete = available and not missing_items
            delivery_fee = _known_amount(selected_snapshot["delivery_fee_aed"]) if available else None
            service_fee = _known_amount(selected_snapshot["service_fee_aed"]) if available else None
            discount = _known_amount(selected_snapshot["discount_aed"]) if available else None
            tax = None
            cost_values = {
                "delivery_fee": delivery_fee,
                "service_fee": service_fee,
                "discount": discount,
                "tax": tax,
            }
            has_cost_adjustments = any(value is not None for value in cost_values.values())
            known_total = None
            if available and matched_items:
                known_total = subtotal
                known_total += delivery_fee or Decimal("0")
                known_total += service_fee or Decimal("0")
                known_total += tax or Decimal("0")
                known_total -= discount or Decimal("0")

            if not available:
                total_status = None
            elif not complete:
                total_status = "partial"
            elif all(value is not None for value in cost_values.values()):
                total_status = "complete"
            elif has_cost_adjustments:
                total_status = "partial"
            else:
                total_status = "items_only"

            platform_status = "unavailable" if not available else "complete" if complete else "partial"
            collected_at = selected_snapshot["collected_at"] if available else None
            freshness = (
                get_snapshot_freshness(collected_at)
                if available
                else {
                    "age_minutes": None,
                    "freshness_status": None,
                    "freshness_label": None,
                    "should_refresh": True,
                }
            )
            confidence = _platform_confidence(
                complete=complete,
                cost_values=cost_values,
                freshness_status=freshness["freshness_status"] or "stale",
            )

            platform_result = {
                "platform": platform,
                "available": available,
                "status": platform_status,
                "snapshot_id": selected_snapshot["id"] if available else None,
                "snapshot_location": selected_snapshot["location"] if available else None,
                "collected_at": collected_at,
                **freshness,
                "items": basket_items,
                "matched_items": matched_items,
                "missing_items": missing_items,
                "item_subtotal": float(subtotal) if available else None,
                "delivery_fee": float(delivery_fee) if delivery_fee is not None else None,
                "service_fee": float(service_fee) if service_fee is not None else None,
                "discount": float(discount) if discount is not None else None,
                "tax": None,
                "known_total": float(known_total) if known_total is not None else None,
                "estimated_total": None,
                "total_status": total_status,
                "complete": complete,
                "confidence": confidence,
                "_rating": selected_snapshot["rating"] if available else None,
                "_eta_minutes": selected_snapshot["eta_minutes"] if available else None,
                "_cost_coverage": frozenset(name for name, value in cost_values.items() if value is not None),
                "_subtotal": subtotal,
                "_known_total_decimal": known_total,
            }
            platform_results.append(platform_result)
            if complete:
                complete_results.append(platform_result)

        comparison_basis: str | None = None
        winner_reason: str | None = None
        winner_confidence = "low"
        comparable_results: list[tuple[dict[str, Any], Decimal]] = []
        savings = None
        savings_percentage = None
        cheapest_platform = None
        comparison_coverage: frozenset[str] = frozenset()
        if complete_results:
            coverages = {result["_cost_coverage"] for result in complete_results}
            if len(complete_results) >= 2 and len(coverages) == 1:
                comparison_coverage = next(iter(coverages))
            if len(complete_results) >= 2 and comparison_coverage:
                comparison_basis = "known_total"
                comparable_results = [
                    (result, result["_known_total_decimal"])
                    for result in complete_results
                    if result["_known_total_decimal"] is not None
                ]
            else:
                comparison_basis = "item_subtotal"
                comparable_results = [(result, result["_subtotal"]) for result in complete_results]

            comparable_results.sort(key=lambda result: (result[1], result[0]["platform"]))
            cheapest_platform = comparable_results[0][0]["platform"]
            if len(complete_results) >= 2:
                savings = float(comparable_results[-1][1] - comparable_results[0][1])
                highest_comparable_cost = comparable_results[-1][1]
                savings_percentage = (
                    float((highest_comparable_cost - comparable_results[0][1]) / highest_comparable_cost * Decimal("100"))
                    if highest_comparable_cost > 0 else 0.0
                )
                if comparable_results[-1][1] == comparable_results[0][1]:
                    winner_reason = "Equal basket cost"
                elif comparison_basis == "item_subtotal":
                    winner_reason = "Lower item subtotal"
                elif comparison_coverage == frozenset({"delivery_fee"}):
                    winner_reason = "Lower cost after delivery fee"
                elif comparison_coverage == frozenset({"discount"}):
                    winner_reason = "Lower cost after discount"
                else:
                    winner_reason = "Lower known basket cost"
            elif len(complete_results) == 1:
                comparison_coverage = complete_results[0]["_cost_coverage"]
                comparison_basis = "known_total" if comparison_coverage else "item_subtotal"
                winner_reason = "Only complete basket available"

            statuses = [result["freshness_status"] for result in complete_results]
            confidences = [result["confidence"] for result in complete_results]
            if (
                len(complete_results) >= 2
                and comparison_basis == "known_total"
                and statuses
                and all(status == "fresh" for status in statuses)
                and all(confidence == "high" for confidence in confidences)
            ):
                winner_confidence = "high"
            elif (
                len(complete_results) >= 2
                and comparison_basis == "known_total"
                and all(status in {"fresh", "recent", "aging"} for status in statuses)
                and all(confidence in {"high", "medium"} for confidence in confidences)
            ):
                winner_confidence = "medium"
            else:
                winner_confidence = "low"

        comparison = {
            "cheapest_platform": cheapest_platform,
            "savings": savings,
            "savings_percentage": savings_percentage,
            "comparison_basis": comparison_basis,
            "winner_reason": winner_reason,
            "winner_confidence": winner_confidence,
        }

        platform_results, best_overall_platform = calculate_cartly_scores(
            platform_results,
            comparison_basis=comparison_basis,
        )
        deal_points: dict[str, int] = {}
        for platform_result in platform_results:
            if not platform_result["complete"]:
                continue
            points = 0
            for item in platform_result["matched_items"]:
                deal = get_deal_intelligence(
                    restaurant=restaurant,
                    platform=platform_result["platform"],
                    country=country,
                    city=city,
                    location=location,
                    item=item["requested_name"],
                )
                deal_weight = {"great_deal": 2, "good_deal": 1}.get(deal["deal_status"], 0)
                points += deal_weight * item["quantity"]
            if points > 0:
                deal_points[platform_result["platform"]] = points
        best_deal_platform = (
            min(deal_points, key=lambda platform: (-deal_points[platform], platform))
            if deal_points else None
        )
        comparison["best_overall_platform"] = best_overall_platform
        comparison["best_deal_platform"] = best_deal_platform

        public_platform_results = []
        for result in platform_results:
            public_platform_results.append({
                key: value
                for key, value in result.items()
                if not key.startswith("_")
            })

        return {
            "restaurant": _canonical_restaurant(restaurant),
            "country": country,
            "city": city,
            "location": location,
            "items": requested_items,
            "requested_items": requested_items,
            "platforms": public_platform_results,
            "comparison": comparison,
            "cheapest_platform": cheapest_platform,
            "savings": savings,
            "best_overall_platform": best_overall_platform,
            "best_deal_platform": best_deal_platform,
            "available_platform_count": available_platform_count,
        }
    finally:
        conn.close()


def _menu_parity_inventory(
    conn: sqlite3.Connection,
    snapshot_id: int,
) -> tuple[dict[str, str], dict[str, str]]:
    rows = conn.execute(
        """
        SELECT item_name, price_aed, category, available
        FROM menu_items
        WHERE snapshot_id = ?
        ORDER BY id
        """,
        (snapshot_id,),
    ).fetchall()
    listed: dict[str, str] = {}
    available: dict[str, str] = {}
    for row in rows:
        name = row["item_name"] or ""
        price = row["price_aed"]
        if not name or price is None or row["available"] == 0:
            if not name or price is None:
                continue
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_price) or numeric_price <= 0:
            continue
        if _is_modifier_or_addon(name, row["category"]):
            continue
        key = _normalize_name(name)
        if not key:
            continue
        listed.setdefault(key, name)
        if row["available"] != 0:
            available.setdefault(key, name)
    return listed, available


def compare_menu_parity(
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
    unmatched_limit: int = 50,
) -> dict[str, Any]:
    """Compare usable priced menus; parity is shared / union * 100.

    Usable items require a positive finite price and are not marked unavailable.
    Availability rate is usable unique items divided by positive-priced listed
    unique items. Parity is menu overlap, not user-basket completeness.
    """
    from collectors.catalog import PLATFORM_CATALOG

    platforms = [platform.name for platform in PLATFORM_CATALOG if platform.implemented]
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        candidates = conn.execute(
            """
            SELECT id, platform, country, city, restaurant, location, collected_at
            FROM restaurant_snapshots
            WHERE
                CASE WHEN LOWER(restaurant) = 'saravana bhavan'
                     THEN 'saravanaa bhavan' ELSE LOWER(restaurant) END
                    = LOWER(?)
                AND LOWER(country) = LOWER(?)
                AND LOWER(city) = LOWER(?)
            ORDER BY platform, collected_at DESC, id DESC
            """,
            (_canonical_restaurant(restaurant), country, city),
        ).fetchall()

        selected: dict[str, dict[str, Any]] = {}
        for platform in platforms:
            for snapshot in candidates:
                if snapshot["platform"].strip().casefold() != platform.casefold():
                    continue
                if not _location_matches(snapshot["location"], location):
                    continue
                listed, available = _menu_parity_inventory(conn, snapshot["id"])
                if not listed:
                    continue
                selected[platform] = {
                    "snapshot": snapshot,
                    "listed": listed,
                    "available": available,
                }
                break

        platform_results: list[dict[str, Any]] = []
        for platform in platforms:
            data = selected.get(platform)
            if data is None:
                platform_results.append({
                    "platform": platform,
                    "available": False,
                    "snapshot_id": None,
                    "location": None,
                    "collected_at": None,
                    "total_items": None,
                    "listed_items": None,
                    "availability_rate": None,
                })
                continue
            listed = data["listed"]
            usable = data["available"]
            platform_results.append({
                "platform": platform,
                "available": True,
                "snapshot_id": data["snapshot"]["id"],
                "location": data["snapshot"]["location"],
                "collected_at": data["snapshot"]["collected_at"],
                "total_items": len(usable),
                "listed_items": len(listed),
                "availability_rate": round(len(usable) / len(listed) * 100, 2),
            })

        valid_platform_count = len(selected)
        parity_result: dict[str, Any] = {
            "shared_items": None,
            "platform_a_only_count": None,
            "platform_b_only_count": None,
            "platform_a_only_items": [],
            "platform_b_only_items": [],
            "parity_score": None,
        }
        if valid_platform_count == 2:
            platform_a, platform_b = platforms[:2]
            items_a = selected[platform_a]["available"]
            items_b = selected[platform_b]["available"]
            keys_a = set(items_a)
            keys_b = set(items_b)
            shared = keys_a & keys_b
            only_a = sorted(keys_a - keys_b)
            only_b = sorted(keys_b - keys_a)
            union = keys_a | keys_b
            parity_result = {
                "shared_items": len(shared),
                "platform_a_only_count": len(only_a),
                "platform_b_only_count": len(only_b),
                "platform_a_only_items": [items_a[key] for key in only_a[:unmatched_limit]],
                "platform_b_only_items": [items_b[key] for key in only_b[:unmatched_limit]],
                "parity_score": round(len(shared) / len(union) * 100, 2) if union else None,
            }

        return {
            "restaurant": _canonical_restaurant(restaurant),
            "country": country,
            "city": city,
            "location": location,
            "status": "complete" if valid_platform_count == 2 else "partial",
            "platforms": platform_results,
            "platform_a": platforms[0] if platforms else None,
            "platform_b": platforms[1] if len(platforms) > 1 else None,
            "total_items_platform_a": platform_results[0]["total_items"] if platform_results else None,
            "total_items_platform_b": platform_results[1]["total_items"] if len(platform_results) > 1 else None,
            "availability_rate_a": platform_results[0]["availability_rate"] if platform_results else None,
            "availability_rate_b": platform_results[1]["availability_rate"] if len(platform_results) > 1 else None,
            **parity_result,
            "valid_platform_count": valid_platform_count,
        }
    finally:
        conn.close()


def _parse_snapshot_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def get_menu_price_history(
    *,
    restaurant: str,
    platform: str,
    country: str,
    city: str,
    location: str,
    item: str,
    days: int = 30,
    limit: int = 200,
) -> dict[str, Any] | None:
    """Calculate exact-item statistics from valid full-menu snapshots only.

    Change and percentage compare the newest price with the arithmetic mean
    over the requested window. The history list is capped, while statistics use
    every qualifying snapshot in the window.
    """
    if days <= 0 or limit <= 0:
        raise ValueError("days and limit must be positive")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    target = _normalize_name(item)
    if not target:
        return None

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        snapshots = conn.execute(
            """
            SELECT id, platform, country, city, restaurant, location, collected_at
            FROM restaurant_snapshots
            WHERE LOWER(platform) = LOWER(?)
                AND CASE WHEN LOWER(restaurant) = 'saravana bhavan'
                         THEN 'saravanaa bhavan' ELSE LOWER(restaurant) END
                    = LOWER(?)
                AND LOWER(country) = LOWER(?)
                AND LOWER(city) = LOWER(?)
            ORDER BY collected_at DESC, id DESC
            """,
            (platform, _canonical_restaurant(restaurant), country, city),
        ).fetchall()

        observations: list[dict[str, Any]] = []
        display_name = item.strip()
        for snapshot in snapshots:
            if not _location_matches(snapshot["location"], location):
                continue
            collected = _parse_snapshot_time(snapshot["collected_at"])
            if collected is None or collected < cutoff:
                continue
            menu = _basket_menu_items(conn, snapshot["id"])
            match = menu.get(target)
            if match is None:
                continue
            matched_name, price = match
            display_name = matched_name
            observations.append({
                "snapshot_id": snapshot["id"],
                "collected_at": snapshot["collected_at"],
                "price": price,
            })

        if not observations:
            return None
        observations.sort(key=lambda observation: (_parse_snapshot_time(observation["collected_at"]), observation["snapshot_id"]))
        prices = [observation["price"] for observation in observations]
        current = prices[-1]
        average = sum(prices, Decimal("0")) / len(prices)
        price_change = current - average
        percentage = price_change / average * Decimal("100") if average else None
        selected_history = observations[-limit:]
        return {
            "item": display_name,
            "platform": platform,
            "location": location,
            "days": days,
            "current_price": float(current),
            "average_price": float(average),
            "minimum_price": float(min(prices)),
            "maximum_price": float(max(prices)),
            "observation_count": len(observations),
            "price_change": float(price_change),
            "price_change_percentage": float(percentage) if percentage is not None else None,
            "history": [
                {
                    "snapshot_id": observation["snapshot_id"],
                    "collected_at": observation["collected_at"],
                    "price": float(observation["price"]),
                }
                for observation in selected_history
            ],
        }
    finally:
        conn.close()


DEAL_THRESHOLDS = {
    "minimum_observations": 3,
    "great_deal_below_average_pct": -10.0,
    "good_deal_below_average_pct": -5.0,
    "above_average_pct": 5.0,
    "high_confidence_observations": 10,
}

COMPETITIVE_PRICE_POSITION_THRESHOLD_PCT = 10.0


def get_deal_intelligence(
    *,
    restaurant: str,
    platform: str,
    country: str,
    city: str,
    location: str,
    item: str,
    days: int = 30,
) -> dict[str, Any]:
    """Classify a current price against real full-menu history only.

    Deal claims require at least the configured minimum observation count.
    Promotional discounts are not used in this historical-price classification.
    """
    history = get_menu_price_history(
        restaurant=restaurant,
        platform=platform,
        country=country,
        city=city,
        location=location,
        item=item,
        days=days,
        limit=1,
    )
    if history is None:
        return {
            "restaurant": _canonical_restaurant(restaurant),
            "item": item,
            "platform": platform,
            "location": location,
            "days": days,
            "current_price": None,
            "historical_average": None,
            "historical_minimum": None,
            "historical_maximum": None,
            "observation_count": 0,
            "difference_from_average": None,
            "difference_from_average_pct": None,
            "deal_status": "insufficient_history",
            "confidence": "low",
            "freshness_status": None,
        }

    freshness = get_snapshot_freshness(history["history"][-1]["collected_at"])
    difference = history["price_change"]
    difference_pct = history["price_change_percentage"]
    count = history["observation_count"]
    if count < DEAL_THRESHOLDS["minimum_observations"]:
        status = "insufficient_history"
        confidence = "low"
    else:
        if difference_pct <= DEAL_THRESHOLDS["great_deal_below_average_pct"]:
            status = "great_deal"
        elif difference_pct <= DEAL_THRESHOLDS["good_deal_below_average_pct"]:
            status = "good_deal"
        elif difference_pct >= DEAL_THRESHOLDS["above_average_pct"]:
            status = "above_average"
        else:
            status = "normal"
        if freshness["freshness_status"] == "stale":
            confidence = "low"
        elif (
            count >= DEAL_THRESHOLDS["high_confidence_observations"]
            and freshness["freshness_status"] == "fresh"
        ):
            confidence = "high"
        else:
            confidence = "medium"
    return {
        "restaurant": _canonical_restaurant(restaurant),
        "item": history["item"],
        "platform": platform,
        "location": location,
        "days": days,
        "current_price": history["current_price"],
        "historical_average": history["average_price"],
        "historical_minimum": history["minimum_price"],
        "historical_maximum": history["maximum_price"],
        "observation_count": count,
        "difference_from_average": difference,
        "difference_from_average_pct": difference_pct,
        "deal_status": status,
        "confidence": confidence,
        "freshness_status": freshness["freshness_status"],
        "freshness_label": freshness["freshness_label"],
    }


def _latest_location_menus(
    conn: sqlite3.Connection,
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
) -> dict[str, dict[str, Any]]:
    from collectors.catalog import PLATFORM_CATALOG

    platforms = [platform.name for platform in PLATFORM_CATALOG if platform.implemented]
    snapshots = conn.execute(
        """
        SELECT id, platform, country, city, restaurant, location, collected_at,
               rating, eta_minutes, delivery_fee_aed, service_fee_aed, discount_aed
        FROM restaurant_snapshots
        WHERE
            CASE WHEN LOWER(restaurant) = 'saravana bhavan'
                 THEN 'saravanaa bhavan' ELSE LOWER(restaurant) END
                = LOWER(?)
            AND LOWER(country) = LOWER(?)
            AND LOWER(city) = LOWER(?)
        ORDER BY platform, collected_at DESC, id DESC
        """,
        (_canonical_restaurant(restaurant), country, city),
    ).fetchall()
    selected: dict[str, dict[str, Any]] = {}
    for platform in platforms:
        for snapshot in snapshots:
            if snapshot["platform"].strip().casefold() != platform.casefold():
                continue
            if not _location_matches(snapshot["location"], location):
                continue
            menu = _basket_menu_items(conn, snapshot["id"])
            if menu:
                selected[platform] = {"snapshot": snapshot, "menu": menu}
                break
    return selected


def get_menu_intelligence(
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
    limit: int = 50,
    significant_gap_pct: float = COMPETITIVE_PRICE_POSITION_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Summarize observed menu overlap, availability, category, and price gaps."""
    if limit <= 0 or significant_gap_pct < 0:
        raise ValueError("limit must be positive and significant_gap_pct non-negative")
    parity = compare_menu_parity(
        restaurant=restaurant,
        country=country,
        city=city,
        location=location,
        unmatched_limit=limit,
    )

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        selected = _latest_location_menus(
            conn,
            restaurant=restaurant,
            country=country,
            city=city,
            location=location,
        )
        platforms = list(selected)
        inventories: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
        categories: dict[str, dict[str, int]] = {}
        for platform, data in selected.items():
            snapshot_id = data["snapshot"]["id"]
            inventories[platform] = _menu_parity_inventory(conn, snapshot_id)
            counts: dict[str, int] = {}
            counted_items: set[str] = set()
            rows = conn.execute(
                "SELECT item_name, category FROM menu_items WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchall()
            for row in rows:
                key = _normalize_name(row["item_name"] or "")
                if key not in data["menu"] or key in counted_items:
                    continue
                category = (row["category"] or "Uncategorized").strip() or "Uncategorized"
                counts[category] = counts.get(category, 0) + 1
                counted_items.add(key)
            categories[platform] = counts

        price_gaps: list[dict[str, Any]] = []
        exclusive: list[dict[str, Any]] = []
        opportunities: list[dict[str, Any]] = []
        category_comparison: list[dict[str, Any]] = []
        if len(platforms) == 2:
            platform_a, platform_b = platforms
            menu_a = selected[platform_a]["menu"]
            menu_b = selected[platform_b]["menu"]
            keys_a, keys_b = set(menu_a), set(menu_b)
            for key in sorted(keys_a & keys_b):
                name_a, price_a = menu_a[key]
                name_b, price_b = menu_b[key]
                low = min(price_a, price_b)
                high = max(price_a, price_b)
                difference = high - low
                difference_pct = float(difference / low * Decimal("100")) if low else 0.0
                lower_platform = platform_a if price_a <= price_b else platform_b
                if difference_pct < 5:
                    position_a = position_b = "similar"
                elif price_a == price_b:
                    position_a = position_b = "equal_lowest"
                elif price_a < price_b:
                    position_a = "significantly_cheaper" if difference_pct >= significant_gap_pct else "cheaper"
                    position_b = "significantly_more_expensive" if difference_pct >= significant_gap_pct else "more_expensive"
                else:
                    position_a = "significantly_more_expensive" if difference_pct >= significant_gap_pct else "more_expensive"
                    position_b = "significantly_cheaper" if difference_pct >= significant_gap_pct else "cheaper"
                price_gaps.append({
                    "item_name": name_a,
                    "platform_a": platform_a,
                    "price_a": float(price_a),
                    "platform_b": platform_b,
                    "price_b": float(price_b),
                    "lower_price_platform": lower_platform,
                    "difference": float(difference),
                    "difference_percentage": round(difference_pct, 2),
                    "position": "similar" if difference_pct < 5 else "significant_gap" if difference_pct >= significant_gap_pct else "moderate_gap",
                    "platform_a_position": position_a,
                    "platform_b_position": position_b,
                })
                if difference_pct >= significant_gap_pct:
                    opportunities.append({
                        "type": "large_cross_platform_price_gap",
                        "item_name": name_a,
                        "lower_price_platform": lower_platform,
                        "difference": float(difference),
                        "difference_percentage": round(difference_pct, 2),
                    })

            for key in sorted(keys_a - keys_b):
                reason = "unavailable_on_other_platform" if key in inventories[platform_b][0] else "not_listed_on_other_platform"
                name = menu_a[key]
                exclusive.append({
                    "item_name": name[0],
                    "available_on": platform_a,
                    "missing_from": platform_b,
                    "reason": reason,
                })
                opportunities.append({
                    "type": "platform_menu_coverage_gap",
                    "item_name": name[0],
                    "available_on": platform_a,
                    "missing_from": platform_b,
                    "reason": reason,
                })
            for key in sorted(keys_b - keys_a):
                reason = "unavailable_on_other_platform" if key in inventories[platform_a][0] else "not_listed_on_other_platform"
                name = menu_b[key]
                exclusive.append({
                    "item_name": name[0],
                    "available_on": platform_b,
                    "missing_from": platform_a,
                    "reason": reason,
                })
                opportunities.append({
                    "type": "platform_menu_coverage_gap",
                    "item_name": name[0],
                    "available_on": platform_b,
                    "missing_from": platform_a,
                    "reason": reason,
                })

            category_names = sorted(set(categories.get(platform_a, {})) | set(categories.get(platform_b, {})))
            category_comparison = [
                {
                    "category": category,
                    platform_a: categories.get(platform_a, {}).get(category, 0),
                    platform_b: categories.get(platform_b, {}).get(category, 0),
                }
                for category in category_names
            ]
            for category_row in category_comparison:
                count_a = category_row[platform_a]
                count_b = category_row[platform_b]
                largest = max(count_a, count_b)
                if largest >= 4 and abs(count_a - count_b) / largest >= 0.5:
                    opportunities.append({
                        "type": "category_coverage_difference",
                        "category": category_row["category"],
                        platform_a: count_a,
                        platform_b: count_b,
                    })

        freshness_statuses = [
            get_snapshot_freshness(data["snapshot"]["collected_at"])["freshness_status"]
            for data in selected.values()
        ]
        if len(selected) < 2 or any(status == "stale" for status in freshness_statuses):
            confidence = "low"
        elif all(status == "fresh" for status in freshness_statuses):
            confidence = "high"
        else:
            confidence = "medium"

        return {
            "restaurant": _canonical_restaurant(restaurant),
            "country": country,
            "city": city,
            "location": location,
            "platforms": parity["platforms"],
            "menu_parity": {
                "shared_items": parity["shared_items"],
                "platform_a_only_count": parity["platform_a_only_count"],
                "platform_b_only_count": parity["platform_b_only_count"],
                "parity_score": parity["parity_score"],
            },
            "price_gaps": sorted(price_gaps, key=lambda gap: (-gap["difference_percentage"], gap["item_name"]))[:limit],
            "platform_exclusive_items": exclusive[:limit],
            "category_comparison": category_comparison,
            "opportunities": opportunities[:limit],
            "confidence": confidence,
        }
    finally:
        conn.close()


def get_competitive_price(
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
    item: str,
) -> dict[str, Any]:
    """Position an exact normalized item price across comparable platforms."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        selected = _latest_location_menus(
            conn,
            restaurant=restaurant,
            country=country,
            city=city,
            location=location,
        )
    finally:
        conn.close()

    target = _normalize_name(item)
    platform_prices: list[dict[str, Any]] = []
    for platform, data in selected.items():
        snapshot = data["snapshot"]
        match = data["menu"].get(target)
        freshness = get_snapshot_freshness(snapshot["collected_at"])
        platform_prices.append({
            "platform": platform,
            "snapshot_id": snapshot["id"],
            "location": snapshot["location"],
            "collected_at": snapshot["collected_at"],
            **freshness,
            "available": match is not None,
            "item_name": match[0] if match else None,
            "item_price": float(match[1]) if match else None,
        })

    comparable = [platform for platform in platform_prices if platform["available"]]
    prices = [platform["item_price"] for platform in comparable]
    has_alternatives = len(prices) >= 2
    lowest = min(prices) if has_alternatives else None
    average = sum(prices) / len(prices) if has_alternatives else None
    all_prices_equal = bool(prices) and all(price == prices[0] for price in prices)
    for platform in comparable:
        price = platform["item_price"]
        difference = price - lowest if lowest is not None else None
        difference_pct = difference / lowest * 100 if difference is not None and lowest else None
        if not has_alternatives:
            position = "uncompared"
        elif all_prices_equal:
            position = "equal_lowest"
        elif difference == 0:
            position = "lowest"
        elif average is not None and abs(price - average) / average * 100 <= 1:
            position = "at_average"
        elif average is not None and price < average:
            position = "below_average"
        else:
            position = "above_average"
        platform["difference_from_cheapest"] = difference
        platform["difference_from_cheapest_pct"] = difference_pct
        platform["relative_price_position"] = position

    winner = min(comparable, key=lambda platform: (platform["item_price"], platform["platform"])) if has_alternatives else None
    return {
        "restaurant": _canonical_restaurant(restaurant),
        "country": country,
        "city": city,
        "location": location,
        "item": item,
        "platforms": platform_prices,
        "comparable_platform_count": len(comparable),
        "cheapest_platform": winner["platform"] if winner else None,
        "market_average_price": average,
        "price_difference": max(prices) - lowest if has_alternatives and lowest is not None else None,
        "price_difference_percentage": (max(prices) - lowest) / max(prices) * 100 if has_alternatives and max(prices) else None,
        "comparison_basis": "item_price" if has_alternatives else None,
        "confidence": "high" if has_alternatives and all(p["freshness_status"] == "fresh" for p in comparable) else "medium" if has_alternatives else "low",
    }


def get_price_history(
    *,
    restaurant: str,
    item: str,
    platform: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    filters = [
        "LOWER(s.restaurant) = LOWER(?)",
        "LOWER(p.item_name) = LOWER(?)",
        "p.price_aed IS NOT NULL",
        "s.collected_at >= ?",
    ]
    values: list[Any] = [restaurant, item, cutoff]
    if platform:
        filters.append("LOWER(s.platform) = LOWER(?)")
        values.append(platform)

    rows = conn.execute(
        f"""
        SELECT s.platform, p.item_name AS item, p.price_aed AS price,
               s.collected_at
        FROM restaurant_snapshots s
        JOIN item_prices p ON p.snapshot_id = s.id
        WHERE {' AND '.join(filters)}
        ORDER BY s.collected_at ASC, p.id ASC
        """,
        values,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_analytics() -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    totals = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM restaurant_snapshots) AS total_snapshots,
            (SELECT COUNT(DISTINCT platform) FROM restaurant_snapshots)
                AS total_platforms,
            (SELECT COUNT(DISTINCT restaurant) FROM restaurant_snapshots)
                AS total_restaurants,
            (SELECT COUNT(DISTINCT item_name) FROM item_prices
                WHERE price_aed IS NOT NULL) AS total_tracked_items,
            (SELECT COUNT(*) FROM item_prices WHERE price_aed IS NOT NULL)
                AS number_of_price_observations
        """
    ).fetchone()

    average_prices = [
        dict(row)
        for row in conn.execute(
            """
            SELECT s.platform, AVG(p.price_aed) AS average_price,
                   COUNT(*) AS observation_count
            FROM restaurant_snapshots s
            JOIN item_prices p ON p.snapshot_id = s.id
            WHERE p.price_aed IS NOT NULL
            GROUP BY s.platform
            ORDER BY s.platform
            """
        ).fetchall()
    ]

    cheapest_by_item = [
        dict(row)
        for row in conn.execute(
            """
            WITH platform_prices AS (
                SELECT p.item_name AS item, s.platform,
                       AVG(p.price_aed) AS average_price,
                       COUNT(*) AS observation_count
                FROM restaurant_snapshots s
                JOIN item_prices p ON p.snapshot_id = s.id
                WHERE p.price_aed IS NOT NULL
                GROUP BY p.item_name, s.platform
            ), ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY item ORDER BY average_price, platform
                ) AS row_number
                FROM platform_prices
            )
            SELECT item, platform, average_price, observation_count
            FROM ranked
            WHERE row_number = 1
            ORDER BY item
            """
        ).fetchall()
    ]

    price_changes = [
        dict(row)
        for row in conn.execute(
            """
            WITH observations AS (
                SELECT s.platform, p.item_name AS item, p.price_aed AS price,
                       s.collected_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.platform, p.item_name
                           ORDER BY s.collected_at ASC, p.id ASC
                       ) AS first_row,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.platform, p.item_name
                           ORDER BY s.collected_at DESC, p.id DESC
                       ) AS last_row
                FROM restaurant_snapshots s
                JOIN item_prices p ON p.snapshot_id = s.id
                WHERE p.price_aed IS NOT NULL
            )
            SELECT first_obs.platform, first_obs.item,
                   first_obs.price AS earliest_price,
                   last_obs.price AS latest_price,
                   last_obs.price - first_obs.price AS price_change,
                   first_obs.collected_at AS earliest_collected_at,
                   last_obs.collected_at AS latest_collected_at
            FROM observations first_obs
            JOIN observations last_obs
              ON last_obs.platform = first_obs.platform
             AND last_obs.item = first_obs.item
            WHERE first_obs.first_row = 1 AND last_obs.last_row = 1
            ORDER BY first_obs.item, first_obs.platform
            """
        ).fetchall()
    ]
    conn.close()

    return {
        **dict(totals),
        "average_item_price_by_platform": average_prices,
        "cheapest_platform_by_item": cheapest_by_item,
        "price_changes": price_changes,
    }


def get_market_analysis(
    *,
    restaurant: str | None = None,
    platform: str | None = None,
    country: str | None = None,
    city: str | None = None,
    location: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    if days <= 0:
        raise ValueError("days must be positive")

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        where = []
        values: list[Any] = []
        if restaurant:
            where.append("CASE WHEN LOWER(restaurant) = 'saravana bhavan' THEN 'saravanaa bhavan' ELSE LOWER(restaurant) END = LOWER(?)")
            values.append(restaurant)
        if platform:
            where.append("LOWER(platform) = LOWER(?)")
            values.append(platform)
        if country:
            where.append("LOWER(country) = LOWER(?)")
            values.append(country)
        if city:
            where.append("LOWER(city) = LOWER(?)")
            values.append(city)
        if location:
            where.append("LOWER(location) = LOWER(?)")
            values.append(location)
        where_clause = " AND ".join(where)
        query = "SELECT * FROM restaurant_snapshots"
        if where_clause:
            query += f" WHERE {where_clause}"
        if where_clause:
            query += " AND collected_at >= ?"
        else:
            query += " WHERE collected_at >= ?"
        query += " ORDER BY collected_at DESC, id DESC"
        snapshots = conn.execute(query, values + [cutoff]).fetchall()

        if not snapshots:
            return {
                "status": "insufficient_data",
                "data_scope": {
                    "restaurant": restaurant,
                    "platform": platform,
                    "country": country,
                    "city": city,
                    "location": location,
                    "days": days,
                    "observation_count": 0,
                    "comparable_item_count": 0,
                    "date_range": None,
                    "platforms_included": [],
                    "locations_included": [],
                },
                "price_difference": {"comparison_count": 0, "median_pct": None, "mean_pct": None, "p75": None, "p90": None, "items_gt_5_pct": None, "items_gt_10_pct": None, "items_gt_20_pct": None},
                "fee_difference": {"delivery_fee_diff": None, "service_fee_diff": None, "total_known_cost_diff": None, "basis": "insufficient_data"},
                "winner_frequency": {},
                "winner_stability": {"observations": 0, "winner_changes": 0, "stability_percentage": None},
                "limitations": ["No qualifying historical snapshots were available within the requested window."],
            }

        by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for snapshot in snapshots:
            by_platform[snapshot["platform"]].append(dict(snapshot))

        comparable_values: list[float] = []
        comparisons: list[dict[str, Any]] = []
        for snapshot in snapshots:
            menu = _basket_menu_items(conn, snapshot["id"])
            if not menu:
                continue
            for other in snapshots:
                if other["id"] <= snapshot["id"]:
                    continue
                if snapshot["platform"] == other["platform"]:
                    continue
                if snapshot["location"] != other["location"] and not _location_matches(snapshot["location"], other["location"] or ""):
                    continue
                menu_other = _basket_menu_items(conn, other["id"])
                for item_key, (_, price_a) in menu.items():
                    price_b = menu_other.get(item_key)
                    if price_b is None:
                        continue
                    _, other_price = price_b
                    if price_a is None or other_price is None:
                        continue
                    denom = max(float(price_a), float(other_price))
                    if denom <= 0:
                        continue
                    percent = abs(float(price_a) - float(other_price)) / denom * 100.0
                    comparable_values.append(percent)
                    comparisons.append({
                        "snapshot_a": snapshot["id"],
                        "snapshot_b": other["id"],
                        "platform_a": snapshot["platform"],
                        "platform_b": other["platform"],
                        "price_a": float(price_a),
                        "price_b": float(other_price),
                        "difference_pct": percent,
                        "location": snapshot["location"],
                    })

        if not comparisons:
            return {
                "status": "insufficient_data",
                "data_scope": {
                    "restaurant": restaurant,
                    "platform": platform,
                    "country": country,
                    "city": city,
                    "location": location,
                    "days": days,
                    "observation_count": len(snapshots),
                    "comparable_item_count": 0,
                    "date_range": [snapshots[-1]["collected_at"], snapshots[0]["collected_at"]] if snapshots else None,
                    "platforms_included": sorted({row["platform"] for row in snapshots}),
                    "locations_included": sorted({row["location"] for row in snapshots if row["location"]}),
                },
                "price_difference": {"comparison_count": 0, "median_pct": None, "mean_pct": None, "p75": None, "p90": None, "items_gt_5_pct": None, "items_gt_10_pct": None, "items_gt_20_pct": None},
                "fee_difference": {"delivery_fee_diff": None, "service_fee_diff": None, "total_known_cost_diff": None, "basis": "insufficient_data"},
                "winner_frequency": {},
                "winner_stability": {"observations": 0, "winner_changes": 0, "stability_percentage": None},
                "limitations": ["No exact cross-platform item comparisons were available within the requested window."],
            }

        values_sorted = sorted(comparable_values)
        def _pct(value: float) -> float | None:
            if not values_sorted:
                return None
            index = (len(values_sorted) - 1) * value / 100.0
            lo = math.floor(index)
            hi = min(len(values_sorted) - 1, math.ceil(index))
            if lo == hi:
                return values_sorted[lo]
            ratio = index - lo
            return values_sorted[lo] + (values_sorted[hi] - values_sorted[lo]) * ratio
        price_difference = {
            "comparison_count": len(comparisons),
            "median_pct": median(values_sorted),
            "mean_pct": sum(values_sorted) / len(values_sorted),
            "p75": _pct(75),
            "p90": _pct(90),
            "items_gt_5_pct": sum(1 for value in values_sorted if value > 5.0) / len(values_sorted),
            "items_gt_10_pct": sum(1 for value in values_sorted if value > 10.0) / len(values_sorted),
            "items_gt_20_pct": sum(1 for value in values_sorted if value > 20.0) / len(values_sorted),
        }

        fee_rows = [
            {
                "platform": row["platform"],
                "delivery_fee": row["delivery_fee_aed"],
                "service_fee": row["service_fee_aed"],
                "discount": row["discount_aed"],
                "known_total": (row["delivery_fee_aed"] or 0) + (row["service_fee_aed"] or 0) - (row["discount_aed"] or 0),
            }
            for row in snapshots
        ]
        fees_by_platform: defaultdict[str, list[float]] = defaultdict(list)
        for row in fee_rows:
            if row["delivery_fee"] is not None:
                fees_by_platform[row["platform"] + ":delivery"].append(float(row["delivery_fee"]))
            if row["service_fee"] is not None:
                fees_by_platform[row["platform"] + ":service"].append(float(row["service_fee"]))
            if row["discount"] is not None:
                fees_by_platform[row["platform"] + ":discount"].append(float(row["discount"]))

        fee_difference = {
            "delivery_fee_diff": None,
            "service_fee_diff": None,
            "total_known_cost_diff": None,
            "basis": "observed_fee_difference",
        }
        delivery = sorted({value for key, values in fees_by_platform.items() if key.endswith(":delivery") for value in values})
        if len(delivery) >= 2:
            fee_difference["delivery_fee_diff"] = max(delivery) - min(delivery)
        service = sorted({value for key, values in fees_by_platform.items() if key.endswith(":service") for value in values})
        if len(service) >= 2:
            fee_difference["service_fee_diff"] = max(service) - min(service)
        totals = sorted({value for row in fee_rows for value in [row["known_total"]] if value is not None})
        if len(totals) >= 2:
            fee_difference["total_known_cost_diff"] = max(totals) - min(totals)

        winner_counts: defaultdict[str, int] = defaultdict(int)
        winner_stability_observations = 0
        winner_sequence: list[str] = []
        if comparisons:
            by_key = defaultdict(list)
            for comparison in comparisons:
                key = (comparison["snapshot_a"], comparison["snapshot_b"])
                by_key[key].append(comparison)
            for group in by_key.values():
                winner_platform = min(
                    ((group[0]["platform_a"], group[0]["price_a"]), (group[0]["platform_b"], group[0]["price_b"])),
                    key=lambda item: (item[1], item[0]),
                )[0]
                winner_counts[winner_platform] += 1
                winner_sequence.append(winner_platform)
                winner_stability_observations += 1

        winner_stability = {
            "observations": winner_stability_observations,
            "winner_changes": sum(1 for index in range(1, len(winner_sequence)) if winner_sequence[index] != winner_sequence[index - 1]),
            "stability_percentage": (1.0 - (sum(1 for index in range(1, len(winner_sequence)) if winner_sequence[index] != winner_sequence[index - 1]) / max(len(winner_sequence) - 1, 1))) if winner_sequence else None,
        }

        result = {
            "status": "ok" if comparable_values else "insufficient_data",
            "data_scope": {
                "restaurant": restaurant,
                "platform": platform,
                "country": country,
                "city": city,
                "location": location,
                "days": days,
                "observation_count": len(snapshots),
                "comparable_item_count": len(comparisons),
                "date_range": [snapshots[-1]["collected_at"], snapshots[0]["collected_at"]] if snapshots else None,
                "platforms_included": sorted({row["platform"] for row in snapshots}),
                "locations_included": sorted({row["location"] for row in snapshots if row["location"]}),
            },
            "price_difference": price_difference,
            "fee_difference": fee_difference,
            "winner_frequency": {platform: count / max(sum(winner_counts.values()) or 1, 1) for platform, count in sorted(winner_counts.items())},
            "winner_stability": winner_stability,
            "limitations": [
                "This analysis uses exact comparable menu-item observations only within the selected date window.",
                "No causal statement is made about whether price differences are driven by item pricing or fees; only observed differences are reported.",
                "Unmatched items are excluded from the price-difference analysis.",
            ],
        }
        if not comparable_values:
            result["status"] = "insufficient_data"
        return result
    finally:
        conn.close()


def get_restaurant_parity(
    *,
    restaurant: str,
    country: str,
    city: str,
    location: str,
) -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        snapshots = conn.execute(
            """
            SELECT id, platform, country, city, restaurant, location, collected_at
            FROM restaurant_snapshots
            WHERE CASE WHEN LOWER(restaurant) = 'saravana bhavan' THEN 'saravanaa bhavan' ELSE LOWER(restaurant) END = LOWER(?)
              AND LOWER(country) = LOWER(?)
              AND LOWER(city) = LOWER(?)
            ORDER BY platform, collected_at DESC, id DESC
            """,
            (_canonical_restaurant(restaurant), country, city),
        ).fetchall()
        latest_by_platform: dict[str, dict[str, Any]] = {}
        for snapshot in snapshots:
            if not _location_matches(snapshot["location"], location):
                continue
            platform_key = snapshot["platform"].strip().casefold()
            if platform_key not in latest_by_platform:
                latest_by_platform[platform_key] = dict(snapshot)

        if not latest_by_platform:
            return {
                "status": "insufficient_data",
                "restaurant": _canonical_restaurant(restaurant),
                "country": country,
                "city": city,
                "location": location,
                "platforms": [],
                "price_mismatches": [],
                "missing_items": [],
                "price_changes": [],
                "availability_differences": [],
                "summary": {"platform_count": 0, "price_mismatch_count": 0, "missing_item_count": 0, "price_change_count": 0},
                "limitations": ["No qualifying snapshots were found for the requested restaurant and location."],
            }

        platform_data: dict[str, dict[str, dict[str, Any]]] = {}
        for platform_key, snapshot in latest_by_platform.items():
            rows = conn.execute(
                "SELECT item_name, price_aed, available FROM menu_items WHERE snapshot_id = ? ORDER BY id",
                (snapshot["id"],),
            ).fetchall()
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                normalized = _normalize_name(row["item_name"])
                if not normalized:
                    continue
                grouped[normalized] = {
                    "name": row["item_name"],
                    "price": _safe_float(row["price_aed"]),
                    "available": None if row["available"] is None else bool(int(row["available"])),
                }
            platform_data[platform_key] = {"snapshot": snapshot, "items": grouped}

        price_mismatches: list[dict[str, Any]] = []
        missing_items: list[dict[str, Any]] = []
        availability_differences: list[dict[str, Any]] = []
        price_changes: list[dict[str, Any]] = []
        platform_names = [data["snapshot"]["platform"] for data in platform_data.values()]
        all_keys = set().union(*(set(data["items"]) for data in platform_data.values()))

        for item_key in sorted(all_keys):
            item_entries = {platform: data["items"].get(item_key) for platform, data in platform_data.items() if item_key in data["items"]}
            platforms_with_item = list(item_entries)
            if len(platforms_with_item) >= 2:
                prices = [(platform, entry["price"]) for platform, entry in item_entries.items() if entry and entry["price"] is not None]
                if len(prices) >= 2:
                    by_price = sorted(prices, key=lambda pair: (pair[1], pair[0]))
                    reference_platform, reference_price = by_price[0]
                    for platform, price in by_price[1:]:
                        if price is None or reference_price is None:
                            continue
                        delta = price - reference_price
                        pct = ((delta / reference_price) * 100.0) if reference_price else None
                        if abs(delta) > 0:
                            price_mismatches.append({
                                "item": item_key,
                                "reference_platform": reference_platform,
                                "reference_price": reference_price,
                                "other_platform": platform,
                                "other_price": price,
                                "absolute_change": float(delta),
                                "percentage_change": pct,
                            })
            if len(platforms_with_item) == 1:
                platform, entry = next(iter(item_entries.items()))
                missing_items.append({
                    "item": item_key,
                    "available_on": platform,
                    "missing_from": [name for name in platform_names if name != platform],
                    "platform_price": entry["price"],
                })
            for platform, item in item_entries.items():
                for other_platform, other_item in item_entries.items():
                    if platform == other_platform:
                        continue
                    if item and other_item and item.get("available") is not None and other_item.get("available") is not None and item["available"] != other_item["available"]:
                        availability_differences.append({
                            "item": item_key,
                            "platform_a": platform,
                            "platform_b": other_platform,
                            "platform_a_available": item["available"],
                            "platform_b_available": other_item["available"],
                        })

        for platform_key, data in platform_data.items():
            snapshot = data["snapshot"]
            history_rows = conn.execute(
                """
                SELECT m.item_name, m.price_aed, m.available, s.collected_at
                FROM menu_items m
                JOIN restaurant_snapshots s ON s.id = m.snapshot_id
                WHERE LOWER(s.platform) = LOWER(?)
                  AND CASE WHEN LOWER(s.restaurant) = 'saravana bhavan' THEN 'saravanaa bhavan' ELSE LOWER(s.restaurant) END = LOWER(?)
                  AND LOWER(s.country) = LOWER(?)
                  AND LOWER(s.city) = LOWER(?)
                  AND LOWER(COALESCE(s.location, '')) = LOWER(?)
                ORDER BY s.collected_at DESC, s.id DESC
                """,
                (snapshot["platform"], _canonical_restaurant(restaurant), country, city, location),
            ).fetchall()
            history_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in history_rows:
                normalized = _normalize_name(row["item_name"])
                if not normalized:
                    continue
                history_by_item[normalized].append({
                    "item_name": row["item_name"],
                    "price": _safe_float(row["price_aed"]),
                    "available": row["available"],
                    "collected_at": row["collected_at"],
                })
            for item_key, values in history_by_item.items():
                if len(values) < 2:
                    continue
                values_sorted = sorted(values, key=lambda entry: (entry["collected_at"] or "", entry["item_name"]))
                previous = values_sorted[-2]
                current = values_sorted[-1]
                if previous["price"] is None or current["price"] is None:
                    continue
                delta = current["price"] - previous["price"]
                pct = ((delta / previous["price"]) * 100.0) if previous["price"] else None
                price_changes.append({
                    "platform": snapshot["platform"],
                    "item": item_key,
                    "previous_price": previous["price"],
                    "current_price": current["price"],
                    "absolute_change": float(delta),
                    "percentage_change": pct,
                    "observed_at": current["collected_at"],
                })

        summary = {
            "platform_count": len(platform_data),
            "price_mismatch_count": len(price_mismatches),
            "missing_item_count": len(missing_items),
            "price_change_count": len(price_changes),
        }
        limitations = [
            "Price differences are observed among exact normalized menu items only and do not imply consumer demand or profitability.",
            "Availability differences are reported only when the platform explicitly provided availability information.",
            "Price-change checks compare the newest observation to the immediately previous observation for that item and platform.",
        ]
        if len(platform_data) < 2:
            limitations.append("Fewer than two valid platforms were available for comparison at this restaurant and location.")
        return {
            "status": "ok" if summary["platform_count"] >= 2 else "insufficient_data",
            "restaurant": _canonical_restaurant(restaurant),
            "country": country,
            "city": city,
            "location": location,
            "platforms": platform_names,
            "price_mismatches": price_mismatches,
            "missing_items": missing_items,
            "price_changes": price_changes,
            "availability_differences": availability_differences,
            "summary": summary,
            "limitations": limitations,
        }
    finally:
        conn.close()


def get_data_quality_report() -> dict[str, Any]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    issues: list[dict[str, Any]] = []
    try:
        duplicate_rows = conn.execute(
            """
            SELECT platform, country, city, restaurant, location, collected_at, COUNT(*) AS count
            FROM restaurant_snapshots
            GROUP BY platform, country, city, restaurant, location, collected_at
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_rows:
            issues.append({
                "type": "duplicate_snapshot",
                "platform": row["platform"],
                "restaurant": row["restaurant"],
                "location": row["location"],
                "collected_at": row["collected_at"],
                "message": "Duplicate snapshot time detected for the same restaurant and location.",
            })

        empty_menu_rows = conn.execute(
            "SELECT snapshot_id, COUNT(*) AS item_count FROM menu_items GROUP BY snapshot_id HAVING COUNT(*) = 0"
        ).fetchall()
        for row in empty_menu_rows:
            issues.append({
                "type": "empty_menu",
                "snapshot_id": row["snapshot_id"],
                "message": "Snapshot contains no menu items.",
            })

        invalid_price_rows = conn.execute(
            "SELECT snapshot_id, item_name, price_aed FROM menu_items WHERE price_aed IS NOT NULL AND price_aed <= 0"
        ).fetchall()
        for row in invalid_price_rows:
            issues.append({
                "type": "invalid_price",
                "snapshot_id": row["snapshot_id"],
                "item_name": row["item_name"],
                "value": row["price_aed"],
                "message": "Zero or negative prices were detected in menu items.",
            })

        missing_timestamp_rows = conn.execute(
            "SELECT id, platform, restaurant FROM restaurant_snapshots WHERE collected_at IS NULL OR collected_at = ''"
        ).fetchall()
        for row in missing_timestamp_rows:
            issues.append({
                "type": "missing_collection_timestamp",
                "id": row["id"],
                "platform": row["platform"],
                "restaurant": row["restaurant"],
                "message": "Snapshot is missing a valid collection timestamp.",
            })

        failed_runs = conn.execute(
            "SELECT platform, restaurant, location, error_message FROM collection_runs WHERE status = 'failed'"
        ).fetchall()
        for row in failed_runs:
            issues.append({
                "type": "failed_collection_run",
                "platform": row["platform"],
                "restaurant": row["restaurant"],
                "location": row["location"],
                "message": row["error_message"] or "Collection failed without a detail.",
            })

        low_count_rows = conn.execute(
            "SELECT snapshot_id, COUNT(*) AS item_count FROM menu_items GROUP BY snapshot_id HAVING COUNT(*) < 3"
        ).fetchall()
        for row in low_count_rows:
            issues.append({
                "type": "unusually_low_item_count",
                "snapshot_id": row["snapshot_id"],
                "item_count": row["item_count"],
                "message": "Snapshot has unusually low menu coverage.",
            })

        unmatched_rows = conn.execute(
            "SELECT m.snapshot_id, m.item_name FROM menu_items m LEFT JOIN item_mappings im ON LOWER(im.platform_item_name) = LOWER(m.item_name) WHERE im.id IS NULL LIMIT 50"
        ).fetchall()
        for row in unmatched_rows:
            issues.append({
                "type": "unmatched_menu_item",
                "snapshot_id": row["snapshot_id"],
                "item_name": row["item_name"],
                "message": "Menu item has not been mapped to a canonical item yet.",
            })

        stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        stale_rows = conn.execute(
            "SELECT id, platform, restaurant, location, collected_at FROM restaurant_snapshots WHERE collected_at < ?",
            (stale_cutoff,),
        ).fetchall()
        for row in stale_rows:
            issues.append({
                "type": "stale_snapshot",
                "id": row["id"],
                "platform": row["platform"],
                "restaurant": row["restaurant"],
                "location": row["location"],
                "collected_at": row["collected_at"],
                "message": "Snapshot is older than 30 days.",
            })

        return {
            "status": "warning" if issues else "ok",
            "issue_count": len(issues),
            "issues": issues,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    create_database()
    print("Database created successfully.")