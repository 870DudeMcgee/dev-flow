import unittest
import os

class TestMarketingAssets(unittest.TestCase):

    def test_styles_css_exists(self):
        self.assertTrue(os.path.exists('public/styles.css'))

    def test_styles_css_variables(self):
        with open('public/styles.css', 'r') as file:
            content = file.read()
            self.assertIn('--accent-purple', content)
            self.assertIn('--accent-indigo-glow', content)

    def test_index_html_font_family(self):
        with open('public/index.html', 'r') as file:
            content = file.read()
            self.assertTrue('family=Outfit' in content or 'Outfit' in content)

if __name__ == '__main__':
    unittest.main()
