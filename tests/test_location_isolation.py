import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import database
import main


class LocationIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_NAME = os.path.join(self.temp_dir.name, "locations.db")
        database.create_database()
        self.restaurant = "Location Isolation Test"
        self.locations = (
            "Dubai Silicon Oasis",
            "Deira",
            "Al Karama",
        )
        collected_at = datetime.now(timezone.utc).isoformat()
        self.snapshot_ids = {}
        for location_index, location in enumerate(self.locations):
            for platform_index, platform in enumerate(("Talabat", "Noon Food")):
                snapshot_id = database.save_data({
                    "platform": platform,
                    "country": "UAE",
                    "city": "Dubai",
                    "restaurant": self.restaurant,
                    "location": location,
                    "rating": 4.0,
                    "delivery_fee_aed": None,
                    "service_fee_aed": None,
                    "discount_aed": None,
                    "eta_minutes": None,
                    "collected_at": collected_at,
                    "items": [{"name": "Test Burger", "price_aed": 10 + location_index * 10 + platform_index}],
                    "menu_items": [{
                        "name": "Test Burger",
                        "price_aed": 10 + location_index * 10 + platform_index,
                        "category": "Burgers",
                        "available": True,
                        "platform_item_id": None,
                    }],
                }, location=location)
                self.snapshot_ids[(location, platform)] = snapshot_id

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_analysis_paths_are_location_isolated(self):
        requested_location = "Dubai Silicon Oasis"

        menu = database.compare_menus(
            restaurant=self.restaurant,
            country="UAE",
            city="Dubai",
            location=requested_location,
        )
        self.assertEqual({row["location"] for row in menu["platforms"]}, {requested_location})
        self.assertEqual(menu["items"][0]["prices"], {"Noon Food": 11.0, "Talabat": 10.0})

        basket = database.compare_basket(
            restaurant=self.restaurant,
            country="UAE",
            city="Dubai",
            location=requested_location,
            items=[{"name": "Test Burger", "quantity": 1}],
        )
        available_basket_rows = [row for row in basket["platforms"] if row["available"]]
        self.assertEqual({row["snapshot_location"] for row in available_basket_rows}, {requested_location})
        self.assertEqual({row["item_subtotal"] for row in available_basket_rows}, {10.0, 11.0})

        history = database.get_menu_price_history(
            restaurant=self.restaurant,
            platform="Talabat",
            country="UAE",
            city="Dubai",
            location=requested_location,
            item="Test Burger",
        )
        self.assertEqual(history["location"], requested_location)
        self.assertEqual(history["history"][0]["price"], 10.0)
        self.assertEqual(history["observation_count"], 1)

        market = database.get_market_analysis(
            restaurant=self.restaurant,
            country="UAE",
            city="Dubai",
            location=requested_location,
        )
        self.assertEqual(market["data_scope"]["locations_included"], [requested_location])
        self.assertEqual(market["data_scope"]["comparable_item_count"], 1)

        parity = database.get_restaurant_parity(
            restaurant=self.restaurant,
            country="UAE",
            city="Dubai",
            location=requested_location,
        )
        self.assertEqual(parity["summary"]["platform_count"], 2)
        self.assertEqual(len(parity["price_mismatches"]), 1)
        self.assertEqual(
            {parity["price_mismatches"][0]["reference_price"], parity["price_mismatches"][0]["other_price"]},
            {10.0, 11.0},
        )

    def test_size_and_quantity_tokens_do_not_merge(self):
        self.assertNotEqual(
            database.normalize_item_name("Chicken Burger Small"),
            database.normalize_item_name("Chicken Burger Large"),
        )
        self.assertNotEqual(
            database.normalize_item_name("Chicken Wings 2 pcs"),
            database.normalize_item_name("Chicken Wings 4 pcs"),
        )

    def test_main_all_triggers_canonical_sync(self):
        result = {
            "status": "success",
            "configuration": {
                "platform": "Talabat",
                "restaurant": self.restaurant,
                "country": "UAE",
                "city": "Dubai",
                "location": "Dubai Silicon Oasis",
            },
        }
        with patch("sys.argv", ["main.py", "--all"]), \
                patch.object(main, "create_database"), \
                patch.object(main, "collect_all_configurations", return_value=[result]), \
                patch.object(main, "sync_canonical_items_from_snapshots", create=True) as sync:
            self.assertEqual(main.main(), 0)
        sync.assert_called_once_with(
            restaurant=self.restaurant,
            country="UAE",
            city="Dubai",
            location="Dubai Silicon Oasis",
        )


if __name__ == "__main__":
    unittest.main()
