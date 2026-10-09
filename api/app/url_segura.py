import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse


class SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener_sem_redirect = urllib.request.build_opener(SemRedirect)


def is_safe_url(url: str) -> bool:
    try:
        partes = urlparse(url)
    except ValueError:
        return False

    if partes.scheme not in ("http", "https"):
        return False

    host = partes.hostname
    if not host:
        return False

    try:
        porta = partes.port or (443 if partes.scheme == "https" else 80)
        infos = socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, ValueError, UnicodeError):
        return False

    if not infos:
        return False

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False

    return True
