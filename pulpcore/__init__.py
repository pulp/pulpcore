import pkg_resources

__version__ = pkg_resources.get_distribution("pulpcore").version


from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
