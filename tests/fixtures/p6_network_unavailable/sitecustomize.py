"""Isolated P6 acceptance fixture: fail external connections without modifying providers."""
import socket


def unavailable(*args, **kwargs):
    raise OSError("P6_ISOLATED_NETWORK_UNAVAILABLE")


socket.socket.connect = unavailable
socket.socket.connect_ex = unavailable
socket.create_connection = unavailable
