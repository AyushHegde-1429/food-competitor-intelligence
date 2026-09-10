import sqlite3
from datetime import datetime, timedelta
from typing import Any


DB_NAME = "food_competitor.db"


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
            collected_at TEXT NOT NULL
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

    conn.commit()
    conn.close()


def save_data(data: dict[str, Any]) -> int:
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    restaurant_name = data["restaurant"]
    if restaurant_name.strip().lower() == "saravana bhavan":
        restaurant_name = "Saravanaa Bhavan"

    cursor.execute("""
        INSERT INTO restaurant_snapshots (
            platform,
            country,
            city,
            restaurant,
            location,
            rating,
            delivery_fee_aed,
            service_fee_aed,
            discount_aed,
            eta_minutes,
            collected_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["platform"],
        data["country"],
        data["city"],
        restaurant_name,
        data["location"],
        data["rating"],
        data["delivery_fee_aed"],
        data["service_fee_aed"],
        data["discount_aed"],
        data["eta_minutes"],
        data["collected_at"],
    ))

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


if __name__ == "__main__":
    create_database()
    print("Database created successfully.")