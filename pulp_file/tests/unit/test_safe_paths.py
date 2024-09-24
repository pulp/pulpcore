import pytest
from unittest import mock
from pulp_file.app.tasks.synchronizing import _get_safe_path


@pytest.mark.parametrize(
    "relative_path, scheme, expected_path",
    [
        # 1. Empty path
        ("", "file", "/root/directory/"),
        ("", "http", "/root/directory/"),
        # 2. Leading/trailing slashes
        ("/leading/slash.txt", "file", "/root/directory/leading/slash.txt"),
        ("/leading/slash.txt", "http", "/root/directory/leading/slash.txt"),
        ("trailing/slash.txt/", "file", "/root/directory/trailing/slash.txt/"),
        ("trailing/slash.txt/", "http", "/root/directory/trailing/slash.txt/"),
        # Special ASCII characters
        ("file#name.txt", "file", "/root/directory/file#name.txt"),
        ("file#name.txt", "http", "/root/directory/file%23name.txt"),
        ("file?name.txt", "file", "/root/directory/file?name.txt"),
        ("file?name.txt", "http", "/root/directory/file%3Fname.txt"),
        ("file@name.txt", "file", "/root/directory/file@name.txt"),
        ("file@name.txt", "http", "/root/directory/file%40name.txt"),
        ("file$name.txt", "file", "/root/directory/file$name.txt"),
        ("file$name.txt", "http", "/root/directory/file%24name.txt"),
        ("file%name.txt", "file", "/root/directory/file%name.txt"),
        ("file%name.txt", "http", "/root/directory/file%25name.txt"),
        # Spaces
        ("file  with  spaces.txt", "file", "/root/directory/file  with  spaces.txt"),
        ("file  with  spaces.txt", "http", "/root/directory/file%20%20with%20%20spaces.txt"),
        ("file.txt  ", "file", "/root/directory/file.txt  "),
        ("file.txt  ", "http", "/root/directory/file.txt%20%20"),
        # Unusual ASCII characters
        ("file!name.txt", "file", "/root/directory/file!name.txt"),
        ("file!name.txt", "http", "/root/directory/file%21name.txt"),
        ("file'name.txt", "file", "/root/directory/file'name.txt"),
        ("file'name.txt", "http", "/root/directory/file%27name.txt"),
        ("file(name).txt", "file", "/root/directory/file(name).txt"),
        ("file(name).txt", "http", "/root/directory/file%28name%29.txt"),
        ("file[name].txt", "file", "/root/directory/file[name].txt"),
        ("file[name].txt", "http", "/root/directory/file%5Bname%5D.txt"),
        ("file;name.txt", "file", "/root/directory/file;name.txt"),
        ("file;name.txt", "http", "/root/directory/file%3Bname.txt"),
        ("file&name.txt", "file", "/root/directory/file&name.txt"),
        ("file&name.txt", "http", "/root/directory/file%26name.txt"),
        # Dots
        (".", "file", "/root/directory/."),
        (".", "http", "/root/directory/."),
        ("..", "file", "/root/directory/.."),
        ("..", "http", "/root/directory/.."),
        # Mixed slashes
        ("dir\\file.txt", "file", "/root/directory/dir\\file.txt"),
        ("dir\\file.txt", "http", "/root/directory/dir%5Cfile.txt"),
        ("///path//to///file.txt", "file", "/root/directory/path//to///file.txt"),
        ("///path//to///file.txt", "http", "/root/directory/path//to///file.txt"),
        # Only special characters
        ("!@#$%^&*()", "file", "/root/directory/!@#$%^&*()"),
        ("!@#$%^&*()", "http", "/root/directory/%21%40%23%24%25%5E%26%2A%28%29"),
        # Encoded characters
        ("file%3a.txt", "file", "/root/directory/file%3a.txt"),
        ("file%3a.txt", "http", "/root/directory/file%253a.txt"),
        ("file%3A.txt", "file", "/root/directory/file%3A.txt"),
        ("file%3A.txt", "http", "/root/directory/file%253A.txt"),
    ],
)
def test_get_safe_path(relative_path, scheme, expected_path):
    entry = mock.Mock(relative_path=relative_path)
    root_dir = "/root/directory"
    result = _get_safe_path(root_dir, entry, scheme)
    assert result == expected_path
