# Cohort — HTB writeup & exploit chain

Machine **Cohort** (HackTheBox). Full kill chain:

1. **SSRF** in the Flask API (`/api/validate`) → internal vhost discovery
2. **Pre-auth RCE** in Marimo 0.20.4 WebSocket terminal (CVE-2026-39987) → shell as `marimo`
3. **Privilege escalation** via PackageKit 1.2.8 D-Bus TOCTOU (CVE-2026-41651) → SUID bash → root

> Flags are intentionally not included (HTB rules).

---

## 1. Recon & enumeration

```
10.129.93.8        cohort.htb
```

- **8080** — nginx serving a Flask app (`/api/...` endpoints)
- **8888** — internal Marimo notebook server (vhost: `nb-1be3782a8afd3ad5.cohort.htb`), not exposed externally

## 2. SSRF → internal vhost discovery

The app exposed a **URL validation** endpoint that fetched remote content and reflected it.
The URL filter could be bypassed by encoding the loopback address:

```http
POST /api/validate HTTP/1.1
Host: cohort.htb

{"url": "http://127.1:80/status"}
```

This hit the internal nginx and revealed the configured **upstreams**, including the
internal Marimo vhost `nb-1be3782a8afd3ad5.cohort.htb` → `127.0.0.1:8888`.

## 3. Pre-auth RCE — Marimo 0.20.4 (CVE-2026-39987)

Marimo's notebook WebSocket terminal handler **did not validate authentication**.
Connecting to `/terminal/ws` spawns a bash shell via `pty.fork()`.

The internal vhost was reachable through the external nginx by sending the internal
`Host` header:

```bash
./scripts/marimo_shell.py 10.129.93.8
```

```text
[+] connected to wss://10.129.93.8/terminal/ws host=nb-1be3782a8afd3ad5.cohort.htb
marimo@cohort:~$
```

Result: **shell as `marimo`** (uid 1000).

### Enumeration as `marimo`

- `dpkg -l | grep -i packagekit` → **PackageKit 1.2.8-2ubuntu1.1**
- `pkcon` / polkit versions match the vulnerable TOCTOU pattern
- Flag `user.txt` at `/home/marimo/user.txt`

## 4. Privilege escalation — PackageKit TOCTOU (CVE-2026-41651)

### Vulnerability

PackageKit 1.2.8 has a **time-of-check / time-of-use** flaw: the transaction role and
flags read by the GLib idle callback can be **raced** by issuing two async D-Bus calls
on the same transaction, so the privileged backend runs the second call (role `NONE`,
no auth check) even though the first one (`SIMULATE`) already passed the authorization
check.

Two calls are issued back-to-back on the same transaction:

1. `InstallFiles(SIMULATE=4)` — passes the polkit authorization check
2. `InstallFiles(NONE=0)` — carries the malicious `.deb`, read as part of the same
   message batch

The malicious `.deb` runs a `postinst` script as **root** which drops a SUID `bash`:

```bash
cp /bin/bash /tmp/.suid_bash && chmod u+s /tmp/.suid_bash
```

### Working exploit

Key detail: the two calls must be flushed **together** so the backend reads both
messages in one batch. Use GIO async `call()` + `flush_sync()`:

```bash
./scripts/cve-2026-41651_gio.py
```

```text
[*] CVE-2026-41651 GIO exploit
[+] TxID: /org/freedesktop/PackageKit/Transaction/22/_c3e63a1a
[*] Racing: SIMULATE=4 -> NONE=0 ...
[*] Polling for SUID bash (60s)...
........................[+] SUCCESS: SUID bash at /tmp/.suid_bash
```

### Why the first attempt failed

The initial exploit used `python-dbus`:

```bash
./scripts/cve-2026-41651_pydbus.py   # ❌ race lost
```

`python-dbus` serializes the two `InstallFiles` calls into **separate writes**, so the
backend's idle callback processed them as separate events and the race never hit.
GIO's `flush_sync` sends both D-Bus messages in a single write batch → race won.

### Root

```bash
/tmp/.suid_bash -p -c 'id'
# uid=1000(marimo) euid=0(root) ...
```

`/root/root.txt` readable.

---

## Files

```
scripts/
├── marimo_shell.py           # CVE-2026-39987 — WebSocket shell as marimo
├── cve-2026-41651_gio.py     # CVE-2026-41651 — PackageKit TOCTOU (working, GIO)
└── cve-2026-41651_pydbus.py  # CVE-2026-41651 — first attempt (python-dbus, race lost)
```
