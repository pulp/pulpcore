"""
Custom Django fields provided by pulpcore
"""
import json

from django.db import models


class JSONField(models.TextField):
    """
    A custom Django field to serialize data into a text field and vice versa

    """

    def from_db_value(self, value, *args, **kwargs):
        """
        Converts a value as returned by the database to a Python object

        Args:
            value: DB value to convert to Python
            args: unused positional arguments
            kwargs: unused keyword arguments

        Returns:
            Python representation of ``value``
        """
        if isinstance(value, str):
            return self.to_python(value)
        return value

    def to_python(self, value):
        """
        Converts the value into the correct Python object

        Args:
            value: The JSON-serializeable value to convert to Python

        Returns:
            Python representation of value
        """
        return json.loads(value)

    def get_db_prep_value(self, value, *args, **kwargs):
        """
        Converts value to a backend-specific value

        Args:
            value: value to convert
            args: unused positional arguments
            kwargs: unused keyword arguments

        Returns:
            JSON string representation of ``value``
        """
        if value is None:
            return None
        return json.dumps(value)

    def value_to_string(self, obj):
        """
        Converts obj to a string. Used to serialize the value of the field

        Args:
            obj: The JSON-serializable object to be converted
        Returns:
            str: JSON Serialized value
        """
        value = self.value_from_object(obj)
        return self.get_db_prep_value(value, None)
