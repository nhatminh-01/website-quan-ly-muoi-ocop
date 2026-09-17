import unittest

import ocop_manual


class OcopManualDeleteButtonTests(unittest.TestCase):
    def test_remove_recognition_button_is_visually_dangerous(self):
        markup = ocop_manual.recognition_fields(0, {})
        self.assertIn('manual-remove-recognition', markup)
        self.assertIn('background:#dc2626', ocop_manual.MANUAL_PAGE_STYLE)
        self.assertIn('background:#b91c1c', ocop_manual.MANUAL_PAGE_STYLE)
        self.assertIn('data-remove-recognition', markup)


if __name__ == '__main__':
    unittest.main()
