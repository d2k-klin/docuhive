# Mount a WD My Cloud EX2 Ultra vault

Use the NAS for document files; keep PostgreSQL and staging on the host SSD. Back up the
NAS before changing firmware, RAID or shares. Confirm drive health and RAID status in its
admin console. RAID 1 is availability, not a backup.

## Find the NAS and write the mount

`deploy/scripts/nas.py` does the network part for you. It runs on the host with plain
Python 3, changes nothing on the host, and never asks for a password:

```sh
python3 deploy/scripts/nas.py find                       # file servers on this network
python3 deploy/scripts/nas.py check 192.168.1.50         # NFS, SMB or both; NFS exports
python3 deploy/scripts/nas.py units 192.168.1.50 --share docuhive --out /tmp/units
```

`find` scans your home network (the /24 this machine is on) for devices that offer NFS or
SMB and shows their names, so a My Cloud appears as `mycloudex2ultra…`. `units` writes the
systemd mount and automount files described below, using NFS when the NAS offers it and
SMB otherwise, and prints the commands that install them. It works for any NAS: for one
whose NFS export is not `/nfs/<share>` (Synology uses `/volume1/<share>`), add
`--export /volume1/docuhive`.

With SMB the password goes into `/etc/docuhive/nas-credentials` (root only), never into a
unit or a command, and the [library view](#the-library-view) is unavailable because SMB
shares do not support hardlinks. Prefer NFS when you can switch it on.

## Prepare the NAS

1. Install firmware supported for this device after reading WD's release notes. Confirm the
   device's current support status with WD; this guide does not assume an end-of-support date.
2. Disable cloud access, UPnP, router port forwards and unused FTP/media services. Set a
   unique admin password and keep the NAS on the trusted LAN.
3. Create a `docuhive` share and a dedicated account. Give only the host write access.
4. Enable NFS for the share restricted to the host IP, mapping writes to UID/GID 1000 where
   supported. Use synchronous writes. If NFS is unreliable, use SMB3 with a private
   credentials file and explicit UID/GID mapping; never put a password in a mount command.
5. Create `/srv/docuhive/vault` as an empty host mount point. Install a systemd mount and
   automount unit using the NAS's actual exported share path. Example:

```ini
# /etc/systemd/system/srv-docuhive-vault.mount
[Unit]
Description=DocuHive NAS vault
After=network-online.target
Wants=network-online.target
[Mount]
What=wdnas.local:/nfs/docuhive
Where=/srv/docuhive/vault
Type=nfs
Options=vers=3,hard,timeo=600,retrans=2,_netdev,noatime
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/srv-docuhive-vault.automount
[Unit]
Description=Automount DocuHive NAS vault
[Automount]
Where=/srv/docuhive/vault
TimeoutIdleSec=0
[Install]
WantedBy=multi-user.target
```

Enable the automount, access the share and verify the mounted filesystem with `findmnt`.
Do not initialise the empty directory underneath a missing mount. The `hard` option can
block filesystem I/O during an outage; recovery time must be measured on the actual NAS.

## Register the mounted vault

Either mount the share under the storage folder and choose it on **Storage health → Change storage**, or run `docuhive vault init` once against the mounted share (in production, through
`docker compose ... run --rm api vault init`; see the [installation guide](installation.md#5-create-the-first-administrator-and-register-the-vault)). It creates `_system/VAULT_ID` and registers that ID in the
database. Capture polling, library sync and backups refuse a missing or different marker.
Keep the host mount point empty and unwritable to the application when the NAS is absent.
Production bind mounts use `create_host_path: false`; they never manufacture missing paths.

## The library view

`docuhive vault library-sync` creates hardlinks in `library/<category>/<year>/…pdf` and
retries a previously unsupported hardlink filesystem. A periodic job refreshes hourly.
Names are normalised and sanitised, and collisions get numbered suffixes. Only tracked
links are removed when metadata or sharing changes; vault originals never move.
Unsupported hardlinks disable the feature instead of copying every PDF.

Private documents appear under `library/_private/<username>/`, behind a mode-700 parent.
The host/NAS administrator must enforce equivalent share ACLs; SMB mode bits may not enforce
these permissions. Do not expose `library/` to other NAS accounts until those ACLs have been
verified. All hardlinks share the original's inode: give library readers read-only access.

Test a NAS outage with the [drill](../../deploy/drills/nas-down.md) before using real files.
