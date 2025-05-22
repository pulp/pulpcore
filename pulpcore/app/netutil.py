"""
network utility functions
"""

import socket


def has_ipv6():
    """
    check if host can use IPv6
    """
    # if python has IPv6 support we need to check if we can bind an IPv6 socket
    if socket.has_ipv6:
        try:
            with socket.socket(socket.AF_INET6) as sock:
                sock.bind(("::1", 0))
                return True
        except OSError:
            pass
    return False
