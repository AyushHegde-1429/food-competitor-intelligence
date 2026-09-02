import sqlite3
import json


DB_NAME = "food_competitor.db"


def create_database():
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

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

    conn.commit()
    conn.close()


def save_data(data):
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

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
        data["restaurant"],
        data["location"],
        data["rating"],
        data["delivery_fee_aed"],
        data["service_fee_aed"],
        data["discount_aed"],
        data["eta_minutes"],
        data["collected_at"],
    ))

    snapshot_id = cursor.lastrowid

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

    conn.commit()
    conn.close()

    print(f"Saved snapshot to database. ID: {snapshot_id}")


if __name__ == "__main__":
    create_database()
    print("Database created successfully.")