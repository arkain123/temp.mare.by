import ipaddress
import os

from config import ESCALATED_IP_FILE, BLOCKED_IP_FILE


def parse_ip_or_cidr(token):
    token = token.strip()
    if not token:
        return None
    try:
        if '/' in token:
            return ipaddress.ip_network(token, strict=False)
        return ipaddress.ip_network(f"{token}/32", strict=False)
    except ValueError:
        return None


def load_ip_list(file_path):
    networks = []
    if not os.path.exists(file_path):
        return networks

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if '#' in line:
                line = line.split('#', 1)[0].strip()
            parts = line.split()
            if not parts:
                continue
            net = parse_ip_or_cidr(parts[0])
            if net is not None:
                networks.append(net)

    return networks


def load_escalated_ips():
    return load_ip_list(ESCALATED_IP_FILE)


def load_banned_ips():
    return load_ip_list(BLOCKED_IP_FILE)


def is_ip_in_list(ip_str, networks):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def append_ip_to_file(file_path, token, comment=""):
    net = parse_ip_or_cidr(token)
    if net is None:
        return False, "Invalid IP/CIDR"

    if net in load_ip_list(file_path):
        return False, f"Already in list: {token}"

    line = token.strip()
    if comment:
        line += "  # " + comment.strip()

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        return False, f"Writing error: {e}"

    return True, f"Added: {token}"


def remove_ip_from_file(file_path, token):
    target = parse_ip_or_cidr(token)
    if target is None:
        return False, "Invalid IP/CIDR"

    if not os.path.exists(file_path):
        return False, "File not found"

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    removed = False

    for line in lines:
        raw = line.split("#", 1)[0].strip()
        parts = raw.split()
        if not parts:
            new_lines.append(line)
            continue

        net = parse_ip_or_cidr(parts[0])
        if net is not None and net == target:
            removed = True
            continue

        new_lines.append(line)

    if not removed:
        return False, f"Not found: {token}"

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return True, f"Deleted: {token}"


def read_ip_file(file_path):
    if not os.path.exists(file_path):
        return "(file not found)"
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.read().strip()
    return data if data else "(list empty)"
