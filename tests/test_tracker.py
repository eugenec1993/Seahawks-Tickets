import unittest
from datetime import datetime, timezone

from tracker import EventPrice, alerts_to_send, should_check_now


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.config = {"alert_rules": {"everything_else": {"max_price": 150, "drop_percent": 10, "repeat_drop_percent": 5, "cooldown_hours": 0}}, "alert_on_first_match": True}
        self.now = datetime(2026, 8, 3, tzinfo=timezone.utc)

    def test_alerts_when_price_falls_by_configured_percentage(self):
        price = EventPrice("Rams", "SeatGeek", 135, "https://example.test")
        state = {price.key: {"history": [{"price": 150, "observed_at": "2026-08-02T00:00:00+00:00"}]}}
        self.assertEqual(len(alerts_to_send([price], state, self.config, self.now)), 1)

    def test_does_not_repeat_without_another_meaningful_fall(self):
        price = EventPrice("Rams", "SeatGeek", 135, "https://example.test")
        state = {price.key: {"history": [{"price": 160, "observed_at": "2026-08-02T00:00:00+00:00"}], "last_alerted_price": 138}}
        self.assertEqual(alerts_to_send([price], state, self.config, self.now), [])

    def test_schedule_is_quarter_hour_only_in_final_week(self):
        config = {"games": [{"kickoff": "2026-08-05T20:00:00Z"}]}
        self.assertTrue(should_check_now(config, datetime(2026, 8, 3, 12, 15, tzinfo=timezone.utc)))
        self.assertFalse(should_check_now({"games": []}, datetime(2026, 8, 3, 12, 15, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
