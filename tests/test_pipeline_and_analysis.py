import os
import tempfile
import unittest

import database


class PipelineAndAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_food_competitor.db")
        database.DB_NAME = self.db_path
        database.create_database()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_collection_run_records_success_and_failure(self):
        database.record_collection_run(
            platform="Talabat",
            country="UAE",
            city="Dubai",
            restaurant="McDonald's",
            location="Dubai Silicon Oasis",
            started_at="2025-01-01T00:00:00+00:00",
            completed_at="2025-01-01T00:05:00+00:00",
            duration_seconds=300,
            status="success",
            snapshot_id=42,
            items_collected=8,
            error_message=None,
        )
        database.record_collection_run(
            platform="Noon Food",
            country="UAE",
            city="Dubai",
            restaurant="McDonald's",
            location="Dubai Silicon Oasis",
            started_at="2025-01-01T00:10:00+00:00",
            completed_at="2025-01-01T00:11:00+00:00",
            duration_seconds=60,
            status="failed",
            snapshot_id=None,
            items_collected=0,
            error_message="timeout",
        )

        runs = database.get_collection_runs(limit=10)
        self.assertEqual(len(runs), 2)
        assert runs[0]["status"] in {"success", "failed"}

    def test_normalization_and_matching(self):
        self.assertEqual(
            database.normalize_item_name("9 Pcs Chicken McNuggets Medium Meal"),
            "9 pcs chicken mcnuggets medium meal",
        )
        self.assertEqual(
            database.normalize_item_name("Chicken Burger Meal"),
            "chicken burger meal",
        )
        self.assertNotEqual(
            database.normalize_item_name("Chicken Burger"),
            database.normalize_item_name("Chicken Burger Meal"),
        )

        canonical = database.ensure_canonical_item(
            restaurant="McDonald's",
            canonical_name="Chicken Burger",
            category="Burgers",
        )
        database.record_item_mapping(
            canonical_item_id=canonical["id"],
            platform="Talabat",
            platform_item_name="Chicken Burger",
            platform_item_name_normalized=database.normalize_item_name("Chicken Burger"),
            match_method="exact_normalized",
            confidence=1.0,
            status="confirmed",
        )

        self.assertTrue(database.match_item_names("Chicken Burger", "Talabat", "McDonald's"))

    def test_market_analysis_insufficient_data(self):
        report = database.get_market_analysis(days=30)
        self.assertEqual(report["status"], "insufficient_data")

    def test_data_quality_report_detects_problems(self):
        database.conn_execute(
            "INSERT INTO restaurant_snapshots(platform, country, city, restaurant, location, collected_at, delivery_fee_aed, service_fee_aed, discount_aed, eta_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Talabat", "UAE", "Dubai", "McDonald's", "Dubai Silicon Oasis", "", -5, 2, 0, "20 mins"),
        )
        database.conn_execute(
            "INSERT INTO menu_items(snapshot_id, item_name, price_aed, category, available) VALUES (?, ?, ?, ?, ?)",
            (1, "Bad Item", 0, "Meals", 1),
        )

        report = database.get_data_quality_report()
        self.assertTrue(any(issue["type"] == "missing_collection_timestamp" for issue in report["issues"]))
        self.assertTrue(any(issue["type"] == "invalid_price" for issue in report["issues"]))

    def test_evaluation_metrics(self):
        metrics = database.evaluate_item_mapping_results(
            true_positives=10,
            false_positives=2,
            false_negatives=3,
        )
        self.assertAlmostEqual(metrics["precision"], 0.8333333333333334)
        self.assertAlmostEqual(metrics["recall"], 0.7692307692307693)
        self.assertAlmostEqual(metrics["f1"], 0.8)

    def test_checkout_feedback_and_saved_basket_foundation(self):
        feedback = database.record_checkout_feedback(
            platform="Talabat",
            restaurant="McDonald's",
            location="Dubai Silicon Oasis",
            cartly_known_total=26.50,
            actual_checkout_total=26.50,
            difference=0.0,
            difference_percentage=0.0,
            reason="matched",
        )
        self.assertEqual(feedback["classification"], "matched")

        summary = database.get_checkout_feedback_summary()
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["sample_count"], 1)

        basket_id = database.save_basket(
            basket_name="Lunch",
            restaurant="McDonald's",
            country="UAE",
            city="Dubai",
            location="Dubai Silicon Oasis",
            items=[{"name": "Big Mac Meal", "quantity": 1}],
        )
        self.assertIsInstance(basket_id, int)

        updated = database.update_basket(
            basket_id=basket_id,
            items=[{"name": "Big Mac Meal", "quantity": 2}],
            alert_threshold_pct=10,
            alert_direction="lower",
        )
        self.assertEqual(updated["alert_threshold_pct"], 10)

        deleted = database.delete_basket(basket_id=basket_id)
        self.assertTrue(deleted["deleted"])

    def test_restaurant_parity_summary(self):
        database.conn_execute(
            "INSERT INTO restaurant_snapshots(platform, country, city, restaurant, location, collected_at, delivery_fee_aed, service_fee_aed, eta_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Talabat", "UAE", "Dubai", "McDonald's", "Dubai Silicon Oasis", "2025-01-01T12:00:00+00:00", 5.0, 0.0, "20 mins"),
        )
        database.conn_execute(
            "INSERT INTO restaurant_snapshots(platform, country, city, restaurant, location, collected_at, delivery_fee_aed, service_fee_aed, eta_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Noon Food", "UAE", "Dubai", "McDonald's", "Dubai Silicon Oasis", "2025-01-01T12:05:00+00:00", 6.0, 0.0, "25 mins"),
        )
        database.conn_execute(
            "INSERT INTO menu_items(snapshot_id, item_name, price_aed, available) VALUES (?, ?, ?, ?)",
            (1, "Big Mac Meal", 28.0, 1),
        )
        database.conn_execute(
            "INSERT INTO menu_items(snapshot_id, item_name, price_aed, available) VALUES (?, ?, ?, ?)",
            (1, "Fries", 9.0, 1),
        )
        database.conn_execute(
            "INSERT INTO menu_items(snapshot_id, item_name, price_aed, available) VALUES (?, ?, ?, ?)",
            (2, "Big Mac Meal", 32.0, 1),
        )
        database.conn_execute(
            "INSERT INTO menu_items(snapshot_id, item_name, price_aed, available) VALUES (?, ?, ?, ?)",
            (2, "Fries", 10.0, 1),
        )
        database.conn_execute(
            "INSERT INTO menu_items(snapshot_id, item_name, price_aed, available) VALUES (?, ?, ?, ?)",
            (2, "Cheese Burger", 14.0, 1),
        )

        report = database.get_restaurant_parity(
            restaurant="McDonald's",
            country="UAE",
            city="Dubai",
            location="Dubai Silicon Oasis",
        )
        self.assertIn("summary", report)
        self.assertIn("price_mismatches", report)
        self.assertIn("limitations", report)

    def test_observation_tables_and_canonical_sync(self):
        database.save_data({
            "platform": "Talabat",
            "country": "UAE",
            "city": "Dubai",
            "restaurant": "McDonald's",
            "location": "Dubai Silicon Oasis",
            "rating": 4.5,
            "delivery_fee_aed": 7.0,
            "service_fee_aed": 1.0,
            "discount_aed": 0.0,
            "eta_minutes": "20 mins",
            "restaurant_status": "open",
            "busy_status": "normal",
            "store_open": True,
            "promotion_text": "2 for 1",
            "promotion_type": "deal",
            "raw_status": "open",
            "items": [{"name": "Big Mac Meal", "price_aed": 28.5}],
            "menu_items": [{
                "name": "Big Mac Meal",
                "price_aed": 28.5,
                "category": "Meals",
                "available": True,
                "platform_item_id": "talabat-1",
            }],
        }, location="Dubai Silicon Oasis")

        snapshot_id = 1
        fee = database.record_fee_observation(
            snapshot_id=snapshot_id,
            platform="Talabat",
            restaurant="McDonald's",
            country="UAE",
            city="Dubai",
            location="Dubai Silicon Oasis",
            delivery_fee_aed=7.0,
            service_fee_aed=1.0,
            discount_aed=0.0,
            collected_at="2025-01-02T10:05:00+00:00",
        )
        availability = database.record_availability_observation(
            snapshot_id=snapshot_id,
            platform="Talabat",
            restaurant="McDonald's",
            item_name="Big Mac Meal",
            available=True,
            category="Meals",
            collected_at="2025-01-02T10:05:00+00:00",
        )
        promotion = database.record_promotion_observation(
            snapshot_id=snapshot_id,
            platform="Talabat",
            restaurant="McDonald's",
            location="Dubai Silicon Oasis",
            promotion_text="2 for 1",
            promotion_type="deal",
            discount_aed=2.0,
            collected_at="2025-01-02T10:05:00+00:00",
        )

        self.assertIsNotNone(fee["id"])
        self.assertIsNotNone(availability["id"])
        self.assertIsNotNone(promotion["id"])

        result = database.sync_canonical_items_from_snapshots(
            restaurant="McDonald's",
            country="UAE",
            city="Dubai",
            location="Dubai Silicon Oasis",
        )
        self.assertGreaterEqual(result["canonical_items_created"], 1)
        self.assertGreaterEqual(len(result["mappings_created"]), 1)


if __name__ == "__main__":
    unittest.main()
