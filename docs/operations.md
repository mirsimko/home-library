# Running the app

How the capture and review app ([app.md](app.md)) runs at home: on battlebox, in WSL, reached over Tailscale. Why battlebox is in the [implementation plan](plans/home-library-app-plan-20261013.html), decision D2. What was checked on the machine itself is in [app-spikes.md](research/app-spikes.md).

## The pieces

| Piece | Where | What |
|---|---|---|
| `hl serve` | WSL on battlebox, user `ai`, systemd user service `hl-web` | The web app, on `127.0.0.1:8765` only. |
| `hl worker` | the same, service `hl-worker` | Reads uploaded photos with the pipeline, one at a time. Needs `codex` and `pi` logged in, and `yaz-client` for Czech look-ups. |
| `hl backup` | the same, `hl-backup.timer`, nightly at 03:30 | A consistent copy of the data root in `~/home-library-backup/`, with 14 days of catalog snapshots and of deleted photos. |
| Tailscale Serve | Windows on battlebox | Puts `127.0.0.1:8765` on the tailnet at `https://battlebox.<tailnet>.ts.net/`, with HTTPS and the `Tailscale-User-Login` header. |
| Backup pull | Battlebook | Copies `~/home-library-backup/` from battlebox whenever the laptop is on. |

The data root is `~/home-library/` in WSL (`catalog.db`, `captures/`, `work/`). The checkout is `~/dev/home-library/`. The data root must not be inside the checkout.

## Setting it up on battlebox

In WSL, as `ai`:

```sh
sudo apt install yaz rsync
git clone https://github.com/mirsimko/home-library ~/dev/home-library
cd ~/dev/home-library && uv sync --frozen
mkdir -p ~/.config/home-library ~/.config/systemd/user
cp deploy/systemd/env.example ~/.config/home-library/env   # then fill in HL_USERS
cp deploy/systemd/hl-*.service deploy/systemd/hl-backup.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hl-web hl-worker hl-backup.timer
curl -s http://127.0.0.1:8765/health
```

`HL_USERS` holds the two Tailscale logins, exactly as `tailscale status` or the admin console shows them. Nobody else is let in.

Lingering is already on for `ai` (`loginctl enable-linger ai`), so the user services start with WSL, without a login.

### Tailscale Serve

Tailscale on battlebox runs on Windows and belongs to the Windows account `ps`. From that account, in a terminal:

```powershell
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

Windows reaches the app in WSL through WSL's localhost forwarding. Check it once from Windows with `curl http://127.0.0.1:8765/health`.

In the Tailscale admin console, the access rules should let only the two family logins reach battlebox on port 443.

**Accepted risk.** The app trusts the `Tailscale-User-Login` header, and it can only tell that a request came from `127.0.0.1`, not who sent it. Any process on battlebox, in Windows or in WSL, that can reach `127.0.0.1:8765` can send that header with a family login and be let in as that person. That is accepted for a family machine whose only users are the family; it would not be acceptable on a shared one.

### Starting WSL at boot

The two scheduled tasks that keep WSL alive today (`WSLKeeper`, `WSLKeepalive`) run only while `ai` is logged in. For the app to come back after a Windows update with nobody logged in, add a task that starts at boot whether or not anyone is logged on. As an administrator:

```powershell
schtasks /create /tn HomeLibraryWSL /sc onstart /ru ai /rp * /tr "wsl.exe -d Ubuntu26 --exec /usr/bin/sleep infinity"
```

`/rp *` asks for the password of `ai`; a task that runs without a logged-in user needs it stored. Then reboot without logging in and check from a phone (the Pixel 8 or the Galaxy A55) that `/health` answers. This is the phase 0 host test; until it passes, the app is only up while someone is logged in on battlebox.

### The subscriptions

The worker runs `codex` and `pi` as `ai`, headless. When a login expires, jobs fail with the tool's own message, which the Status page shows. Log in again in WSL (`codex login`, and pi's own login), then press Retry on the failed jobs. After a failed attempt the whole queue pauses: the job is tried again by itself after 5 minutes, and the next time after 15 more, and no other photo is read meanwhile. A short outage or rate limit may clear without help, and a cause that hits every photo (an expired login, a usage limit) costs one try, not one per photo. The Status page says why reading is paused; "Retry now" ends the pause at once. Only a job that failed all 3 attempts waits for Retry.

## Agents

`hl token` on battlebox prints a new bearer token for agents and revokes the old one. How agents use it is in [harness.md](harness.md).

## Backups

Every night `hl backup ~/home-library-backup` writes the catalog through `VACUUM INTO`, so the copy is consistent while the app runs, and copies `captures/` and `work/` with `rsync`. The directory holds:

- `catalog.db`: the latest catalog copy.
- `snapshots/catalog-YYYYMMDD.db`: one catalog copy per day, the 14 most recent kept. A second backup on the same day replaces that day's snapshot.
- `captures/` and `work/`: a mirror of the data root.
- `deleted/YYYYMMDD/captures/` and `deleted/YYYYMMDD/work/`: the files that the mirror deleted or replaced on that day, kept for 14 days.

So a bad night (a bulk edit through the API, deleted photos) can be undone from an older snapshot and from `deleted/`.

`hl backup` refuses to run, and says why, when the data root has no `catalog.db` (a wrong `HL_DATA`; it does not create an empty one), or when the catalog has fewer than half the books of the latest snapshot. If you really removed that many books, run `uv run hl backup --force ~/home-library-backup` in the checkout. Until then the nightly run fails, which shows in `systemctl --user status hl-backup`.

Battlebook pulls that directory whenever it is on. As a user crontab line or a systemd user timer there:

```sh
rsync -a battlebox-wsl:home-library-backup/ ~/home-library-backup/
```

There is no `--delete` on purpose: if the backup on battlebox is wiped or emptied, the laptop copy stays. Old snapshots and `deleted/` directories that battlebox has pruned stay on the laptop until you remove them; do that by hand now and then.

`battlebox-wsl` is an SSH host entry that reaches WSL on battlebox. The photos stay inside the house: no cloud copy unless the family decides otherwise (plan, question 2).

### Restoring

1. Stop the services: `systemctl --user stop hl-web hl-worker`.
2. Remove the old write-ahead files, so that SQLite does not replay them over the restored database: `rm -f ~/home-library/catalog.db-wal ~/home-library/catalog.db-shm`.
3. Copy the backup into place, but not `snapshots/` and `deleted/`: `rsync -a ~/home-library-backup/{catalog.db,captures,work} ~/home-library/`.
4. Start them again. Jobs that were `running` when the backup was taken are taken over once their heartbeat is stale, after at most 20 minutes.

To go back to an older day, do step 3 and then replace the catalog with that day's snapshot: `cp ~/home-library-backup/snapshots/catalog-YYYYMMDD.db ~/home-library/catalog.db`. Photos that were deleted since are in `deleted/` under the day they were removed; copy them back, for example `cp ~/home-library-backup/deleted/YYYYMMDD/captures/<file> ~/home-library/captures/`.

Try a restore once on Battlebook, into an empty directory with `HL_DATA` pointing at it and `HL_DEV_USER` set (and `HL_USERS` unset; `hl serve` refuses both), and check that the books and photos are there.

## Updating

```sh
cd ~/dev/home-library && git pull && uv sync --frozen
systemctl --user restart hl-web hl-worker
```

A worker restart kills a running read; its job is picked up again once the heartbeat is stale.

## When something is wrong

- **The Status page** shows the queue, the worker's last heartbeat, why reading is paused if it is, and every failed job with its error. Retry from there.
- **Logs:** `journalctl --user -u hl-web -u hl-worker`. They name captures and jobs by id, never a title.
- **`/health`** answers without a login and gives no titles, so it can be checked from anywhere on the tailnet.
