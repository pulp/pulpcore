import json
from unittest.mock import patch

from django.test import TestCase

from pulpcore.app.fields import JSONField


class TestJSONField(TestCase):
    def setUp(self):
        self.json_field = JSONField()
        self.obj = {"test": 12}
        self.obj_json = json.dumps(self.obj)

    def test_to_python(self):
        """Assert the value returned by to_python is the same as the initial value"""
        new_obj = self.json_field.to_python(self.obj_json)
        self.assertDictEqual(self.obj, new_obj)

    def test_from_db_value(self):
        """Assert the value returned by from_db_value is the same as the initial value"""
        new_obj = self.json_field.from_db_value(self.obj_json)
        self.assertDictEqual(self.obj, new_obj)

    def test_get_db_prep_value(self):
        """Assert the value returned by get_db_prep_value matches a serialized version of obj"""
        new_obj = self.json_field.get_db_prep_value(self.obj)
        self.assertEquals(self.obj_json, new_obj)

    def test_value_to_string(self):
        """Assert the value returned by value_to_string matches a json-serialized version of obj"""
        with patch("pulpcore.app.fields.JSONField.value_from_object", return_value=self.obj):
            new_obj = self.json_field.value_to_string(object())
            self.assertEquals(self.obj_json, new_obj)
