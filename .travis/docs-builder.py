#!/usr/bin/env python

import argparse
import subprocess
import os
import re
from shutil import rmtree
import tempfile

WORKING_DIR = os.environ["TRAVIS_BUILD_DIR"]

VERSION_REGEX = r"(\s*)(version)(\s*)(=)(\s*)(['\"])(.*)(['\"])(.*)"
RELEASE_REGEX = r"(\s*)(release)(\s*)(=)(\s*)(['\"])(.*)(['\"])(.*)"

USERNAME = "doc_builder_pulpcore"
HOSTNAME = "8.43.85.236"

SITE_ROOT = "/var/www/docs.pulpproject.org/pulpcore/"


def make_directory_with_rsync(remote_paths_list):
    """
    Ensure the remote directory path exists.

    :param remote_paths_list: The list of parameters. e.g. ['en', 'latest'] to be en/latest on the
        remote.
    :type remote_paths_list: a list of strings, with each string representing a directory.
    """
    try:
        tempdir_path = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tempdir_path)
        os.makedirs(os.sep.join(remote_paths_list))
        remote_path_arg = "%s@%s:%s%s" % (USERNAME, HOSTNAME, SITE_ROOT, remote_paths_list[0])
        local_path_arg = tempdir_path + os.sep + remote_paths_list[0] + os.sep
        rsync_command = ["rsync", "-avzh", local_path_arg, remote_path_arg]
        exit_code = subprocess.call(rsync_command)
        if exit_code != 0:
            raise RuntimeError("An error occurred while creating remote directories.")
    finally:
        rmtree(tempdir_path)
        os.chdir(cwd)


def ensure_dir(target_dir, clean=True):
    """
    Ensure that the directory specified exists and is empty.

    By default this will delete the directory if it already exists

    :param target_dir: The directory to process
    :type target_dir: str
    :param clean: Whether or not the directory should be removed and recreated
    :type clean: bool
    """
    if clean:
        rmtree(target_dir, ignore_errors=True)
    try:
        os.makedirs(target_dir)
    except OSError:
        pass


def main():
    """
    Builds documentation using the 'make html' command and rsyncs to docs.pulpproject.org.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-type", required=True, help="Build type: nightly or beta.")
    parser.add_argument("--branch", required=True, help="Branch or tag name.")
    opts = parser.parse_args()
    if opts.build_type not in ["nightly", "tag"]:
        raise RuntimeError("Build type must be either 'nightly' or 'tag'.")

    build_type = opts.build_type

    branch = opts.branch

    ga_build = False

    if not re.search("[a-zA-Z]", branch) and len(branch.split(".")) > 2:
        ga_build = True

    # build the docs via the Pulp project itself
    print("Building the docs")
    docs_directory = os.sep.join([WORKING_DIR, "docs"])

    make_command = ["make", "PULP_URL=http://pulp", "diagrams", "html"]
    exit_code = subprocess.call(make_command, cwd=docs_directory)
    if exit_code != 0:
        raise RuntimeError("An error occurred while building the docs.")
    # rsync the docs
    local_path_arg = os.sep.join([docs_directory, "_build", "html"]) + os.sep
    if build_type != "tag":
        # This is a nightly build
        remote_path_arg = "%s@%s:%sen/%s/%s/" % (USERNAME, HOSTNAME, SITE_ROOT, branch, build_type)
        make_directory_with_rsync(["en", branch, build_type])
        rsync_command = ["rsync", "-avzh", "--delete", local_path_arg, remote_path_arg]
        exit_code = subprocess.call(rsync_command, cwd=docs_directory)
        if exit_code != 0:
            raise RuntimeError("An error occurred while pushing docs.")
    elif ga_build:
        # This is a GA build.
        # publish to the root of docs.pulpproject.org
        version_components = branch.split(".")
        x_y_version = "{}.{}".format(version_components[0], version_components[1])
        remote_path_arg = "%s@%s:%s" % (USERNAME, HOSTNAME, SITE_ROOT)
        rsync_command = [
            "rsync",
            "-avzh",
            "--delete",
            "--exclude",
            "en",
            "--omit-dir-times",
            local_path_arg,
            remote_path_arg,
        ]
        exit_code = subprocess.call(rsync_command, cwd=docs_directory)
        if exit_code != 0:
            raise RuntimeError("An error occurred while pushing docs.")
        # publish to docs.pulpproject.org/en/3.y/
        make_directory_with_rsync(["en", x_y_version])
        remote_path_arg = "%s@%s:%sen/%s/" % (USERNAME, HOSTNAME, SITE_ROOT, x_y_version)
        rsync_command = [
            "rsync",
            "-avzh",
            "--delete",
            "--omit-dir-times",
            local_path_arg,
            remote_path_arg,
        ]
        exit_code = subprocess.call(rsync_command, cwd=docs_directory)
        if exit_code != 0:
            raise RuntimeError("An error occurred while pushing docs.")
        # publish to docs.pulpproject.org/en/3.y.z/
        make_directory_with_rsync(["en", branch])
        remote_path_arg = "%s@%s:%sen/%s/" % (USERNAME, HOSTNAME, SITE_ROOT, branch)
        rsync_command = [
            "rsync",
            "-avzh",
            "--delete",
            "--omit-dir-times",
            local_path_arg,
            remote_path_arg,
        ]
        exit_code = subprocess.call(rsync_command, cwd=docs_directory)
        if exit_code != 0:
            raise RuntimeError("An error occurred while pushing docs.")
    else:
        # This is a pre-release
        make_directory_with_rsync(["en", branch])
        remote_path_arg = "%s@%s:%sen/%s/%s/" % (USERNAME, HOSTNAME, SITE_ROOT, branch, build_type)
        rsync_command = [
            "rsync",
            "-avzh",
            "--delete",
            "--exclude",
            "nightly",
            "--exclude",
            "testing",
            local_path_arg,
            remote_path_arg,
        ]
        exit_code = subprocess.call(rsync_command, cwd=docs_directory)
        if exit_code != 0:
            raise RuntimeError("An error occurred while pushing docs.")


if __name__ == "__main__":
    main()
