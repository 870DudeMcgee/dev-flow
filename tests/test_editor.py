import unittest
from devflow.editor import apply_xml_edits

class TestEditor(unittest.TestCase):
    def test_apply_single_xml_edit(self):
        original = "def foo():\n    return 'bar'\n"
        xml_changes = """<search>
def foo():
    return 'bar'
</search>
<replace>
def foo():
    return 'baz'
</replace>"""
        modified, err = apply_xml_edits(original, xml_changes)
        self.assertIsNone(err)
        self.assertEqual(modified, "def foo():\n    return 'baz'\n")

    def test_apply_multiple_xml_edits(self):
        original = "first_line\nsecond_line\nthird_line\n"
        xml_changes = """<search>
first_line
</search>
<replace>
1st
</replace>
<search>
third_line
</search>
<replace>
3rd
</replace>"""
        modified, err = apply_xml_edits(original, xml_changes)
        self.assertIsNone(err)
        self.assertEqual(modified, "1st\nsecond_line\n3rd\n")

    def test_apply_xml_edit_missing_search_block(self):
        original = "def foo():\n    return 'bar'\n"
        xml_changes = """<search>
def missing_function():
    return 'bar'
</search>
<replace>
def missing_function():
    return 'baz'
</replace>"""
        modified, err = apply_xml_edits(original, xml_changes)
        self.assertIsNotNone(err)
        self.assertIn("Search block not found", err)
        self.assertEqual(modified, original)

if __name__ == "__main__":
    unittest.main()
