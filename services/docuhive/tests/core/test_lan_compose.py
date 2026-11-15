"""The home-network add-on publishes ports to the LAN, so its container stays locked down."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]


def test_lan_proxy_is_pinned_unprivileged_and_only_proxies():
    lan = yaml.safe_load((ROOT / "deploy/compose.lan.yml").read_text())["services"]["lan"]
    assert "@sha256:" in lan["image"]
    assert lan["user"] == "1000:1000" and lan["read_only"] is True
    assert lan["cap_drop"] == ["ALL"] and lan["security_opt"] == ["no-new-privileges:true"]
    assert lan["networks"] == ["entry"]  # never on the network of the database and the API
    assert {p.rsplit(":", 2)[-2] for p in lan["ports"]} == {"80", "443"}
    caddyfile = (ROOT / "deploy/lan/Caddyfile").read_text()
    assert "admin off" in caddyfile and caddyfile.count("reverse_proxy") == 1
    assert "reverse_proxy web:3000" in caddyfile
