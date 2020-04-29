# coding=utf-8
"""Utilities for pulpcore API tests."""
import string
from datetime import datetime
from random import choice


def gen_username(length=10, valid_characters=True):
    """Generate username given a certain length or punctuation to be used."""
    valid_punctuation = "@.+-_"
    if valid_characters:
        return "".join(
            choice(string.ascii_letters + string.digits + valid_punctuation) for _ in range(length)
        )
    invalid_puntuation = "".join(
        value for value in string.punctuation if value not in valid_punctuation
    )
    return "".join(choice(invalid_puntuation) for _ in range(length))


def parse_date_from_string(s, parse_format="%Y-%m-%dT%H:%M:%S.%fZ"):
    """Parse string to datetime object.

    :param s: str like '2018-11-18T21:03:32.493697Z'
    :param parse_format: str defaults to %Y-%m-%dT%H:%M:%S.%fZ
    :return: datetime.datetime
    """
    return datetime.strptime(s, parse_format)
