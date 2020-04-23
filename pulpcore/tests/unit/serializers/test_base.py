from unittest import TestCase

from rest_framework import serializers

from pulpcore.app.serializers import validate_unknown_fields


class TestValidateUnknownFields(TestCase):
    def test_unknown_field(self):
        """
        Test disjoint sets of `initial_data` with a single field and `defined_fields`.
        """
        initial_data = {"unknown1": "unknown"}
        defined_fields = {"field1": 1, "field2": 2}

        self.assertRaises(
            serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
        )

    def test_unknown_fields(self):
        """
        Test disjoint sets of `initial_data` with multiple fields and `defined_fields`.
        """
        initial_data = {"unknown1": "unknown", "unknown2": "unknown", "unknown3": "unknown"}
        defined_fields = {"field1": 1, "field2": 2}

        self.assertRaises(
            serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
        )

    def test_mixed_initial_data(self):
        """
        Test where `defined_fields` is a proper subset of the `initial_data`.
        """
        initial_data = {
            "field1": 1,
            "field2": 2,
            "unknown1": "unknown",
            "unknown2": "unknown",
            "unknown3": "unknown",
        }
        defined_fields = {"field1": 1, "field2": 2}
        self.assertRaises(
            serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
        )

    def test_mixed_incomplete_initial_data(self):
        """
        Test where `initial_data` and `defined_fields` are intersecting sets.
        """
        initial_data = {
            "field2": 2,
            "unknown1": "unknown",
            "unknown2": "unknown",
            "unknown3": "unknown",
        }
        defined_fields = {"field1": 1, "field2": 2}
        self.assertRaises(
            serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
        )

    def test_empty_defined_fields(self):
        """
        Test an empty `defined_fields`.
        """
        initial_data = {
            "field2": 2,
            "unknown1": "unknown",
            "unknown2": "unknown",
            "unknown3": "unknown",
        }
        defined_fields = {}
        self.assertRaises(
            serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
        )

    def test_validate_no_unknown_fields(self):
        """
        Test where the `initial_data` is equal to `defined_fields`.
        """
        initial_data = {"field1": 1, "field2": 2}
        defined_fields = {"field1": 1, "field2": 2}
        try:
            validate_unknown_fields(initial_data, defined_fields)
        except serializers.ValidationError:
            self.fail("validate_unknown_fields() failed improperly.")

    def test_validate_no_unknown_fields_no_side_effects(self):
        """
        Test validation success where the `initial_data` is equal to `defined_fields`
        and that `initial_data` and `defined_fields` are not mutated.
        """
        initial_data = {"field1": 1, "field2": 2}
        defined_fields = {"field1": 1, "field2": 2}
        try:
            validate_unknown_fields(initial_data, defined_fields)
        except serializers.ValidationError:
            self.fail("validate_unknown_fields() failed improperly.")

        self.assertEqual(initial_data, {"field1": 1, "field2": 2})
        self.assertEqual(defined_fields, {"field1": 1, "field2": 2})

    def test_ignored_fields_no_side_effects(self):
        """
        Test ignored fields in initial data don't cause side effects
        """
        # there's just the `csrfmiddlewaretoken` in the ignored_fields
        initial_data = {"field1": 1, "csrfmiddlewaretoken": 2}
        defined_fields = {"field1": 1}
        try:
            validate_unknown_fields(initial_data, defined_fields)
        except serializers.ValidationError:
            self.fail("validate_unknown_fields() failed improperly.")
