import ipaddress
import threading
import time

import requests

# rdap.org will redirect to needed RIR (RIPE/ARIN/APNIC/...)
# rdap.db.ripe.net fallback
RDAP_ENDPOINTS = (
    "https://rdap.org/ip/{ip}",
    "https://rdap.db.ripe.net/ip/{ip}",
)

_CACHE_TTL = 3600
_cache = {}
_cache_lock = threading.Lock()


def _is_private(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _extract_fn_from_vcard(vcard_array):
    if not vcard_array or len(vcard_array) < 2:
        return None
    for item in vcard_array[1]:
        if not item or item[0] != "fn" or len(item) < 4:
            continue
        value = item[3]
        if isinstance(value, list):
            value = " ".join(str(v) for v in value if v)
        if value:
            return str(value).strip()
    return None


def _extract_operator(data):
    for ent in data.get("entities", []) or []:
        roles = ent.get("roles") or []
        if "registrant" in roles or "administrative" in roles:
            name = _extract_fn_from_vcard(ent.get("vcardArray"))
            if name:
                return name
    return None


def _query_rdap(ip_str, timeout=5):
    for tpl in RDAP_ENDPOINTS:
        url = tpl.format(ip=ip_str)
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={"Accept": "application/rdap+json"},
                allow_redirects=True,
            )
        except requests.RequestException as e:
            print(f"[RDAP] {url} -> {e}")
            continue

        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except ValueError:
            continue

        country = (data.get("country") or "").upper() or None
        operator = _extract_operator(data) or data.get("name") or data.get("handle")
        if not country and not operator:
            continue

        return {
            "country": country or "??",
            "operator": operator or "Unknown",
            "handle": data.get("handle"),
            "source": url,
        }

    return None


def lookup_ip(ip_str):
    if not ip_str:
        return None

    ip_str = ip_str.strip()
    if "," in ip_str:
        ip_str = ip_str.split(",", 1)[0].strip()

    if _is_private(ip_str):
        return {"country": "LAN", "operator": "Private / Local", "handle": None}

    now = time.time()
    with _cache_lock:
        cached = _cache.get(ip_str)
        if cached and now - cached[1] < _CACHE_TTL:
            return cached[0]

    result = _query_rdap(ip_str)

    with _cache_lock:
        _cache[ip_str] = (result, now)

    return result


def format_ip_origin(ip_str):
    info = lookup_ip(ip_str)
    if not info:
        return None
    country = info.get("country") or "??"
    operator = info.get("operator") or "Unknown"
    if len(operator) > 48:
        operator = operator[:45] + "..."
    return f"{country} / {operator}"
