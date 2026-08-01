import unittest

from tracker import EventPrice, alerts_to_send, extract_json_ld_prices


class TrackerTests(unittest.TestCase):
    def test_extracts_low_price_from_json_ld(self):
        page = '<script type="application/ld+json">{"offers":{"lowPrice":"83.50"}}</script>'
        self.assertEqual(extract_json_ld_prices(page), [83.5])

    def test_alerts_use_the_matching_category_limit(self):
        limits = {"charter_club": 300, "sideline": 250, "everything_else": 150}
        prices = [
            EventPrice("Rams", "SeatGeek", 299, "https://example.test", category="charter_club"),
            EventPrice("Rams", "SeatGeek", 251, "https://example.test", category="sideline"),
            EventPrice("Rams", "SeatGeek", 150, "https://example.test", category="everything_else"),
        ]
        alerts = alerts_to_send(prices, {}, limits)
        self.assertEqual([item.category for item in alerts], ["charter_club", "everything_else"])

    def test_alerts_only_for_new_lower_price(self):
        price = EventPrice("Rams", "SeatGeek", 120, "https://example.test")
        previous = {price.key: {"last_alerted_price": 125}}
        self.assertEqual(alerts_to_send([price], previous, 130), [price])
        previous[price.key] = {"last_alerted_price": 110}
        self.assertEqual(alerts_to_send([price], previous, 130), [])


if __name__ == "__main__":
    unittest.main()
