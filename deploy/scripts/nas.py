"""Find a NAS on the home network, check it, and write the host mount for the vault.

Runs on the host with any Python 3 and nothing else installed:

    python3 deploy/scripts/nas.py find
    python3 deploy/scripts/nas.py check 192.168.1.50
    python3 deploy/scripts/nas.py units 192.168.1.50 --share docuhive --out /tmp/units

DocuHive needs the share as a folder on the host (atomic writes, and the nightly backup
reads the vault from the host), so this writes systemd mount units instead of talking to the
NAS from inside the app. It never asks for, stores or prints a password, and it changes
nothing on the host: `units` writes two files and prints the commands that install them.
"""

import argparse
import ipaddress
import re
import shutil
import socket
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

NFS, SMB, WEB = 2049, 445, 80
CREDENTIALS = "/etc/docuhive/nas-credentials"


def is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def local_network() -> ipaddress.IPv4Network:
    """The /24 this machine is on. No packet is sent: connecting a UDP socket only picks
    the outgoing interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    return ipaddress.ip_network(f"{address}/24", strict=False)


def page_title(host: str) -> str:
    """The NAS admin page's title names the device (for example "WD My Cloud EX2 Ultra")."""
    try:
        with urllib.request.urlopen(f"http://{host}/", timeout=2) as response:  # noqa: S310
            html = response.read(20_000).decode("utf-8", "replace")
    except (OSError, ValueError):
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return " ".join(match.group(1).split())[:80] if match else ""


def name_of(host: str) -> str:
    try:
        return socket.gethostbyaddr(host)[0]
    except OSError:
        return ""


def describe(host: str) -> dict | None:
    nfs, smb = is_open(host, NFS), is_open(host, SMB)
    if not (nfs or smb):
        return None
    title = page_title(host) if is_open(host, WEB) else ""
    return {"host": host, "name": name_of(host), "nfs": nfs, "smb": smb, "title": title}


def find(network: ipaddress.IPv4Network) -> list[dict]:
    """Every address on the network that offers file sharing over NFS or SMB."""
    if network.num_addresses > 1024:
        raise ValueError("Scan one home network at a time (at most a /22)")
    with ThreadPoolExecutor(max_workers=64) as pool:
        return [d for d in pool.map(describe, map(str, network.hosts())) if d]


def exports(host: str) -> list[str]:
    """NFS exports, when the host has `showmount`; otherwise nothing."""
    if not shutil.which("showmount"):
        return []
    try:
        run = subprocess.run(  # noqa: S603
            ["showmount", "-e", "--no-headers", host],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.split()[0] for line in run.stdout.splitlines() if line.startswith("/")]


def unit_name(where: str) -> str:
    """systemd's name for a mount point: `/srv/docuhive/vault` -> `srv-docuhive-vault`."""
    path = "/" + where.strip("/")
    if path == "/" or not re.fullmatch(r"(/[A-Za-z0-9_.-]+)+", path):
        raise ValueError("Use an absolute mount point made of letters, digits, '.', '_' or '-'")
    return "-".join(part.replace("-", "\\x2d") for part in path.strip("/").split("/"))


def units(
    host: str, share: str, protocol: str, where: str, export: str | None = None
) -> dict[str, str]:
    """The .mount and .automount unit files, by file name."""
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", host) or not re.fullmatch(r"[A-Za-z0-9_.-]+", share):
        raise ValueError("Host and share names may hold letters, digits, '.', '_' and '-' only")
    if export and not re.fullmatch(r"(/[A-Za-z0-9_.-]+)+", export):
        raise ValueError("The export is an absolute path on the NAS, such as /nfs/docuhive")
    name = unit_name(where)
    if protocol == "nfs":
        # WD My Cloud exports a share named X as /nfs/X.
        what = f"{host}:{export or '/nfs/' + share}"
        kind, options = "nfs", "vers=3,hard,timeo=600,retrans=2,_netdev,noatime"
    else:
        what, kind = f"//{host}/{share}", "cifs"
        # The password lives in a root-only file on the host, never in a unit or a command.
        options = (
            f"credentials={CREDENTIALS},vers=3.0,uid=1000,gid=1000,"
            "file_mode=0640,dir_mode=0750,_netdev,noatime"
        )
    mount = f"""[Unit]
Description=DocuHive NAS vault ({host})
After=network-online.target
Wants=network-online.target

[Mount]
What={what}
Where=/{where.strip("/")}
Type={kind}
Options={options}

[Install]
WantedBy=multi-user.target
"""
    automount = f"""[Unit]
Description=Automount DocuHive NAS vault ({host})

[Automount]
Where=/{where.strip("/")}
TimeoutIdleSec=0

[Install]
WantedBy=multi-user.target
"""
    return {f"{name}.mount": mount, f"{name}.automount": automount}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    finder = commands.add_parser("find", help="List file servers on this network")
    finder.add_argument("--network", help="For example 192.168.1.0/24 (default: this one)")
    checker = commands.add_parser("check", help="Say what one NAS offers")
    checker.add_argument("host")
    writer = commands.add_parser("units", help="Write the systemd units that mount the share")
    writer.add_argument("host")
    writer.add_argument("--share", required=True)
    writer.add_argument("--protocol", choices=["nfs", "smb"], help="Default: NFS if offered")
    writer.add_argument("--export", help="NFS export path, if it is not /nfs/<share>")
    writer.add_argument("--where", default="/srv/docuhive/vault")
    writer.add_argument("--out", default=".", help="Folder to write the two unit files into")
    args = parser.parse_args()

    if args.command == "find":
        network = ipaddress.ip_network(args.network) if args.network else local_network()
        print(f"Looking for file servers on {network} …")
        found = find(network)
        for d in found:
            offers = " + ".join(p for p, on in (("NFS", d["nfs"]), ("SMB", d["smb"])) if on)
            print(f"  {d['host']:<15} {offers:<9} {d['title'] or d['name'] or ''}")
        if not found:
            print("  None found. Check that the NAS is on and on the same network (not a guest")
            print("  Wi-Fi), and that NFS or SMB is switched on in its settings.")
        return

    if args.command == "check":
        found = describe(args.host)
        if found is None:
            raise SystemExit(
                f"{args.host} offers neither NFS (port {NFS}) nor SMB (port {SMB}). "
                "Switch one on in the NAS settings."
            )
        print(f"{args.host}: {found['title'] or found['name'] or 'file server'}")
        print(f"  NFS: {'yes' if found['nfs'] else 'no'}    SMB: {'yes' if found['smb'] else 'no'}")
        for path in exports(args.host) if found["nfs"] else []:
            print(f"  NFS export: {path}")
        print(f"  Recommended: {'NFS' if found['nfs'] else 'SMB'}")
        return

    protocol = args.protocol or ("nfs" if is_open(args.host, NFS) else "smb")
    files = units(args.host, args.share, protocol, args.where, args.export)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (out / name).write_text(content)
    mount, automount = files
    print(f"Wrote {mount} and {automount} to {out.resolve()} ({protocol.upper()}).")
    print("Install them on the DocuHive host:")
    if protocol == "smb":
        print("  sudo apt install cifs-utils     # or your distribution's package for SMB mounts")
        print(f"  sudo install -D -m 600 /dev/null {CREDENTIALS}")
        print(f"  sudoedit {CREDENTIALS}     # two lines: username=…  and  password=…")
    print(f"  sudo install -d -m 700 {args.where}")
    print(f"  sudo cp '{out / mount}' '{out / automount}' /etc/systemd/system/")
    print(f"  sudo systemctl daemon-reload && sudo systemctl enable --now '{automount}'")
    print(f"  findmnt {args.where}")


if __name__ == "__main__":
    main()
