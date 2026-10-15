import unittest

from greet import greeting


class GreetingTests(unittest.TestCase):
    def test_named_and_default(self):
        self.assertEqual(greeting("Ada"), "Hello, Ada.")
        self.assertEqual(greeting(), "Hello, world.")

    def test_empty_refused(self):
        with self.assertRaises(ValueError):
            greeting("  ")
