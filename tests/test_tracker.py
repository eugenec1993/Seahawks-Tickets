import json
import unittest
from pathlib import Path

from tracker import EventPrice, alerts_to_send, extract_json_ld_prices


class TrackerTests(unittest.TestCase):
    def test_extracts_low_price_from_json_ld(self):
        page = '<script type="application/ld+json">{"offers":{"lowPrice":"83.50"}}</script>'
        self.assertEqual(extract_json_ld_prices(page), [83.5])

    def test_alerts_only_for_new_low_under_threshold(self):
        prices = [EventPrice("Rams", "SeatGeek", 120, "https://example.test")]
        previous = {"Rams|SeatGeek": {"last_alerted_price": 125}}
        self.assertEqual(alerts_to_send(prices, previous, 130), prices)
        previous["Rams|SeatGeek"] = {"last_alerted_price": 110}
        self.assertEqual(alerts_to_send(prices, previous, 130), [])


if __name__ == "__main__":
    unittest.main()
