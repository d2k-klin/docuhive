"""The NAS helper finds file servers and writes mount units without touching the host."""

import importlib.util
import ipaddress
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("nas_script", ROOT / "deploy/scripts/nas.py")
nas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nas)


@pytest.mark.enable_socket  # loopback only: a listening socket stands in for the NAS
def test_find_lists_only_hosts_that_share_files(monkeypatch):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        monkeypatch.setattr(nas, "NFS", port)
        monkeypatch.setattr(nas, "SMB", 1)  # nothing listens there
        monkeypatch.setattr(nas, "WEB", 1)
        found = nas.find(ipaddress.ip_network("127.0.0.0/30"))
    assert [(d["host"], d["nfs"], d["smb"]) for d in found] == [("127.0.0.1", True, False)]
    with pytest.raises(ValueError):
        nas.find(ipaddress.ip_network("10.0.0.0/16"))


def test_units_for_nfs_and_smb():
    files = nas.units("192.168.1.50", "docuhive", "nfs", "/srv/docuhive/vault")
    assert list(files) == ["srv-docuhive-vault.mount", "srv-docuhive-vault.automount"]
    mount = files["srv-docuhive-vault.mount"]
    assert "What=192.168.1.50:/nfs/docuhive\n" in mount and "Type=nfs\n" in mount
    assert "Where=/srv/docuhive/vault\n" in files["srv-docuhive-vault.automount"]

    smb = nas.units("wdnas.local", "docs", "smb", "/mnt/my-vault")["mnt-my\\x2dvault.mount"]
    assert "What=//wdnas.local/docs\n" in smb and "Type=cifs\n" in smb
    # The password is only ever a path to a root-only file.
    assert "credentials=/etc/docuhive/nas-credentials" in smb and "password" not in smb

    custom = nas.units("nas", "docs", "nfs", "/srv/v", export="/volume1/docs")
    assert "What=nas:/volume1/docs\n" in custom["srv-v.mount"]


@pytest.mark.parametrize(
    "host,share,where",
    [
        ("nas; rm -rf /", "docs", "/srv/v"),
        ("nas", "docs\nOptions=exec", "/srv/v"),
        ("nas", "docs", "relative path"),
        ("nas", "docs", "/"),
    ],
)
def test_units_refuse_names_that_could_alter_the_unit(host, share, where):
    with pytest.raises(ValueError):
        nas.units(host, share, "nfs", where)


def test_units_command_writes_files_and_changes_nothing_else(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(nas, "is_open", lambda host, port: False)  # no NFS: falls back to SMB
    monkeypatch.setattr(
        sys, "argv", ["nas.py", "units", "192.168.1.50", "--share", "docs", "--out", str(tmp_path)]
    )
    nas.main()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "srv-docuhive-vault.automount",
        "srv-docuhive-vault.mount",
    ]
    out = capsys.readouterr().out
    assert "(SMB)" in out and "sudoedit /etc/docuhive/nas-credentials" in out
