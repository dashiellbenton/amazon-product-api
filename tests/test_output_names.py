import unittest

from amazon_buddy import safe_output_stem


class OutputNameTests(unittest.TestCase):
    def test_safe_output_stem_avoids_parentheses_and_spaces(self):
        self.assertEqual(safe_output_stem("reviews", "B01GW3H3U8", 1589470878252), "reviews-B01GW3H3U8-1589470878252")
        products = safe_output_stem("products", "vacuum cleaner", 1)
        self.assertNotIn("(", products)
        self.assertNotIn(")", products)
        self.assertEqual(products, "products-vacuum-cleaner-1")
