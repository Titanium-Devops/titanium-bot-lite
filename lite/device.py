"""Find the Tiiny, instead of shipping a hostname that resolves on one Mac.

The default model address used to be `http://openai.api.tiiny/v1`. That name is
written into /etc/resolver by the TiinyOS desktop app and points at a proxy on the
machine running it, so it worked there and nowhere else. On Linux, which this bot
also runs on, it did not resolve at all. Worse, the voice lifecycle path sends its
requests with `Host: p8800.api.tiiny`, and that name plus that header reaches the
proxy, which answers 502.

So the address is found. In order:

    TIINY_BASE                  what the farm CLI exports
    ~/.tiinyapps/device.json    what `farm device` writes: {"base", "key"}
    a search                    every attached USB /30 peer, then this host's /24

The search reads the unauthenticated http://<addr>:39218/device.json, which
carries the serial number, so it identifies a box rather than merely finding an
open port. A box answering on both Wi-Fi and USB is one box, and the USB address
wins, because a /30 handed out by the cable cannot move and a DHCP lease can.

Then the port. Firmware 1.0 binds the model gateway to the container bridge only,
so 8800 is refused from another machine and every service arrives on port 80.
Older firmware still serves it on 8800. We ask rather than assume.

NO SUBPROCESS. `lite` is checked for that by tests/test_server.py and by the
farm's own scanner, so the local addresses are found with sockets rather than by
reading the output of `ifconfig`:

  * A UDP socket that "connects" sends no packet. The kernel picks the route and
    binds a local address, and reading it back gives the address a Tiiny on the
    LAN would see this host as.
  * bind() on an address succeeds only if that address belongs to this host. A
    USB link is a fixed /30 inside 172.17/16, so bind-testing the host side of
    every /30 in that range finds the attached cables. All 16384 of them cost
    about a quarter of a second, and only happen when nothing else has said
    where the device is.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

DISCO_PORT = 39218
FARM_DEVICE = os.path.join(os.path.expanduser("~"), ".tiinyapps", "device.json")

# A USB-attached Tiiny is a point-to-point /30 inside this range.
USB_PREFIX = (172, 17)


def farm_device() -> dict:
    """What `farm device` wrote, or an empty dict."""
    try:
        with open(FARM_DEVICE, "rb") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def split_base(base) -> tuple:
    """A base URL or bare address as (host, explicit port or None)."""
    base = (base or "").strip()
    if not base:
        return None, None
    if "//" not in base:
        base = "http://" + base
    try:
        parts = urllib.parse.urlsplit(base)
        return (parts.hostname or None), parts.port
    except ValueError:
        return None, None


def gateway_port(host: str, timeout: float = 2.0) -> int:
    """Which port serves the model API on this box.

    Port 80 answers on every firmware, so a plain TCP probe cannot tell the two
    apart. Asking for a model route can: firmware that does not serve it answers
    404, and a 401 still means the gateway is here and wants a key.
    """
    env = os.environ.get("TIINY_PORT")
    if env and env.isdigit():
        return int(env)
    for port in (80, 8800):
        try:
            request = urllib.request.Request(
                "http://%s:%d/v1/models" % (host, port),
                headers={"Authorization": "Bearer probe"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 404:
                    return port
        except urllib.error.HTTPError as error:
            if error.code != 404:
                return port
        except Exception:
            continue
    return 80


def device_json(addr: str, timeout: float = 0.6):
    """What the box at this address says about itself, or None."""
    try:
        with urllib.request.urlopen(
                "http://%s:%d/device.json" % (addr, DISCO_PORT),
                timeout=timeout) as response:
            value = json.load(response)
    except Exception:
        return None
    if not isinstance(value, dict) or not value.get("serial_number"):
        return None
    return value


# --------------------------------------------------------------------------
# this host's own addresses, without spawning anything
# --------------------------------------------------------------------------

def own_lan_address() -> str:
    """The address a Tiiny on the LAN would see this host as, or "".

    The UDP connect sends nothing; 192.0.2.1 is a documentation address that is
    never routed anywhere, so this is a routing-table lookup and not traffic.
    """
    for probe in ("192.0.2.1", "198.51.100.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe, 9))
            addr = sock.getsockname()[0]
            if addr and not addr.startswith("127."):
                return addr
        except OSError:
            continue
        finally:
            sock.close()
    return ""


def is_local(addr: str) -> bool:
    """Does this address belong to this host? bind() is the only one who knows."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((addr, 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def usb_peers() -> list:
    """The device end of every attached USB link.

    The link is a point-to-point /30: four addresses, of which the box takes the
    first usable one and this host the second. So finding our own side tells us
    the box's side by arithmetic, and somebody with several boxes plugged in has
    one of these per cable.
    """
    peers = []
    for third in range(256):
        for block in range(64):
            ours = "%d.%d.%d.%d" % (USB_PREFIX[0], USB_PREFIX[1], third, block * 4 + 2)
            if is_local(ours):
                peers.append("%d.%d.%d.%d" % (
                    USB_PREFIX[0], USB_PREFIX[1], third, block * 4 + 1))
    return peers


def lan_candidates() -> list:
    """Every other address in the /24 this host sits in.

    Only that /24. Sweeping anything larger to find one box is not a thing an
    assistant should do to somebody's network.
    """
    mine = own_lan_address()
    if not mine:
        return []
    head = mine.rsplit(".", 1)[0]
    return [addr for addr in ("%s.%d" % (head, i) for i in range(1, 255))
            if addr != mine]


def search(timeout: float = 0.35, workers: int = 128) -> list:
    """Every Tiiny this host can see, deduped by serial, USB first.

    Sized to finish in about a second, because this runs while somebody is
    waiting for the bot to start. A box on the local wire answers :39218 in a
    few milliseconds; anything slower than a third of a second here is a box
    that is not there.
    """
    found, lock = {}, threading.Lock()

    def probe(addr, plane):
        value = device_json(addr, timeout)
        if not value:
            return
        record = {"addr": addr, "plane": plane,
                  "serial": value.get("serial_number"),
                  "name": value.get("device_name")}
        with lock:
            current = found.get(record["serial"])
            if current is None or (current["plane"] == "lan" and plane == "usb"):
                found[record["serial"]] = record

    for plane, addrs in (("usb", usb_peers()), ("lan", lan_candidates())):
        for i in range(0, len(addrs), workers):
            threads = [threading.Thread(target=probe, args=(addr, plane))
                       for addr in addrs[i:i + workers]]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
    return sorted(found.values(),
                  key=lambda record: (record["plane"] != "usb", record["addr"]))


# --------------------------------------------------------------------------
# the answer
# --------------------------------------------------------------------------

def base_for(host: str, port=None) -> str:
    """The model API base for a host.

    Port 80 is left off deliberately, so the rest of the code can tell the 1.0
    shape from "the gateway has a port of its own" by looking at the URL. The
    voice lifecycle path relies on exactly that.
    """
    port = port or gateway_port(host)
    return ("http://%s/v1" % host) if port == 80 else ("http://%s:%d/v1" % (host, port))


def find() -> dict:
    """{"base", "key", "source", "plane", "serial"} for the box we should use.

    Never raises. A machine with no Tiiny on it still has to start and show
    somebody the settings page, and an empty base is the honest answer to "no
    Tiiny anywhere". It reads better than a hostname that cannot resolve.
    """
    key = (os.environ.get("TIINY_KEY") or farm_device().get("key") or "").strip()
    for value, source in ((os.environ.get("TIINY_BASE"), "TIINY_BASE"),
                          (farm_device().get("base"), FARM_DEVICE)):
        host, port = split_base(value)
        if host:
            return {"base": base_for(host, port), "key": key,
                    "source": source, "plane": "given", "serial": ""}
    boxes = search()
    if boxes:
        box = boxes[0]
        return {"base": base_for(box["addr"]), "key": key,
                "source": "a search", "plane": box["plane"],
                "serial": box["serial"] or ""}
    return {"base": "", "key": key, "source": "nothing found",
            "plane": "", "serial": ""}


def find_base() -> str:
    """Just the base URL, for the callers that only want that."""
    return find()["base"]


if __name__ == "__main__":
    got = find()
    print("  base    %s" % (got["base"] or "not found"))
    print("  found   %s" % got["source"])
    if got["plane"]:
        print("  plane   %s" % got["plane"])
    if got["serial"]:
        print("  serial  %s" % got["serial"])
