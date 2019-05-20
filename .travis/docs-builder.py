#!/usr/bin/env python

import argparse
import subprocess
import os
import sys
from shutil import rmtree
import tempfile
import yaml

WORKING_DIR = os.environ['TRAVIS_BUILD_DIR']

VERSION_REGEX = r"(\s*)(version)(\s*)(=)(\s*)(['\"])(.*)(['\"])(.*)"
RELEASE_REGEX = r"(\s*)(release)(\s*)(=)(\s*)(['\"])(.*)(['\"])(.*)"

LATEST = '2.16'

USERNAME = 'doc_builder'
HOSTNAME = '8.43.85.236'

SITE_ROOT = '/var/www/docs.pulpproject.org/'


def make_directory_with_rsync(remote_paths_list):
    """
    Ensure the remote directory path exists

    :param remote_paths_list: The list of parameters. e.g. ['en', 'latest'] to be en/latest on the
        remote.
    :type remote_paths_list: a list of strings, with each string representing a directory.
    """
    try:
        tempdir_path = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tempdir_path)
        os.makedirs(os.sep.join(remote_paths_list))
        remote_path_arg = '%s@%s:%s%s' % (USERNAME, HOSTNAME, SITE_ROOT, remote_paths_list[0])
        local_path_arg = tempdir_path + os.sep + remote_paths_list[0] + os.sep
        rsync_command = ['rsync', '-avzh', local_path_arg, remote_path_arg]
        exit_code = subprocess.call(rsync_command)
        if exit_code != 0:
            raise RuntimeError('An error occurred while creating remote directories.')
    finally:
        rmtree(tempdir_path)
        os.chdir(cwd)


def load_config(config_name):
    # Get the config
    config_file = os.path.join(os.path.dirname(__file__), '%s.yaml' % config_name)
    if not os.path.exists(config_file):
        print("Error: %s not found. " % config_file)
        sys.exit(1)
    with open(config_file, 'r') as config_handle:
        config = yaml.safe_load(config_handle)
    return config


def components(configuration):
    return configuration['repositories']


def ensure_dir(target_dir, clean=True):
    """
    Ensure that the directory specified exists and is empty.  By default this will delete
    the directory if it already exists

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
    # Parse the args
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-type", required=True, help="Build type: nightly or beta.")
    opts = parser.parse_args()
    if opts.build_type not in ['nightly', 'beta', 'rc']:
        raise RuntimeError("Build type must be either 'nightly' or 'beta' or 'rc'.")

    build_type = opts.build_type

    x_y_version = '3.0'

    # build the docs via the Pulp project itself
    print("Building the docs")
    docs_directory = os.sep.join([WORKING_DIR, 'docs'])

    make_command = ['make', 'diagrams', 'html']
    exit_code = subprocess.call(make_command, cwd=docs_directory)
    if exit_code != 0:
        raise RuntimeError('An error occurred while building the docs.')

    # rsync the docs
    local_path_arg = os.sep.join([docs_directory, '_build', 'html']) + os.sep
    remote_path_arg = '%s@%s:%sen/%s/' % (USERNAME, HOSTNAME, SITE_ROOT, x_y_version)
    if build_type != 'ga':
        remote_path_arg += build_type + '/'

        make_directory_with_rsync(['en', x_y_version, build_type])
        rsync_command = ['rsync', '-avzh', '--delete', local_path_arg, remote_path_arg]
    else:
        make_directory_with_rsync(['en', x_y_version])
        rsync_command = ['rsync', '-avzh', '--delete', '--exclude', 'nightly', '--exclude',
                         'testing', local_path_arg, remote_path_arg]
    exit_code = subprocess.call(rsync_command, cwd=docs_directory)
    if exit_code != 0:
        raise RuntimeError('An error occurred while pushing docs.')


if __name__ == "__main__":
    main()
