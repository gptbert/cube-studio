import unittest

from myapp_run_config import resolve_run_options, to_bool


class RunConfigTestCase(unittest.TestCase):
    def test_to_bool_true_values(self):
        for value in ["1", "true", "TRUE", " yes ", "on"]:
            self.assertTrue(to_bool(value))

    def test_to_bool_false_values(self):
        for value in ["", "0", "false", "off", "no"]:
            self.assertFalse(to_bool(value))

    def test_resolve_run_options_defaults(self):
        debug, port = resolve_run_options({})
        self.assertFalse(debug)
        self.assertEqual(port, 80)

    def test_resolve_run_options_custom_values(self):
        debug, port = resolve_run_options({"FLASK_DEBUG": "true", "PORT": "8080"})
        self.assertTrue(debug)
        self.assertEqual(port, 8080)


if __name__ == "__main__":
    unittest.main()
