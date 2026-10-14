# App phase 0: the checks the plan rests on

The [implementation plan](../plans/home-library-app-plan-20261013.html) starts with five checks, each with a go or no-go. This note records what was checked, how, and what came out. A check that is still open says so.

Provenance: the host facts below were read on battlebox over SSH by Claude Code (Opus 5.5) on 2026-10-13. Everything marked *open* needs the family, the phones or a reboot.

## 1. Host: can battlebox run the app unattended?

**Observed on 2026-10-13**, read-only:

| Fact | Found |
|---|---|
| WSL distribution | `Ubuntu26` (Ubuntu 26.04 LTS), WSL 2, running |
| systemd in WSL | on (`/etc/wsl.conf`: `[boot] systemd=true`); state `degraded`, which a failing unrelated unit causes |
| Lingering for `ai` | on, so user services start with WSL |
| `uv`, `codex`, `pi`, `rsync` | installed; `codex login status` says logged in with ChatGPT |
| `yaz-client` | **missing**: Czech look-ups would be skipped until `sudo apt install yaz` |
| Sleep on mains power | never (`STANDBYIDLE` AC index 0) |
| Tailscale | installed on Windows, owned by the Windows account `ps`; the `ai` account cannot run `tailscale serve`; no Tailscale inside WSL |
| WSL kept alive by | two scheduled tasks, `WSLKeeper` and `WSLKeepalive`, both *Interactive only*: they run only while `ai` is logged in |
| Memory, cores | 94 GB, 24 |

**Open:**

- That the user services run `codex` and `pi` headless: one `hl run` on a test photo from a systemd service.
- That WSL starts at boot with nobody logged in, with the boot task in [operations.md](../operations.md), and the app answers `/health` from a phone afterwards. **Kill criterion:** if it does not, choose another host (plan, question 1).
- That Tailscale Serve on Windows reaches the app on WSL's `127.0.0.1:8765`.

## 2. Capture: do the phones upload full-size photos from the browser?

**Open.** Method, once the app is up:

1. On each phone (the Pixel 8 and the Galaxy A55), open `/capture`, choose a location and *Shelf*.
2. Take one shelf photo with the camera button, then pick the same shelf's photo from the gallery with the gallery button.
3. After each upload the page shows the size the server received, and warns when the longer side of a shelf photo is under 3000 pixels (a cover or barcode photo can be any size). The Status page lists it too, with the EXIF orientation.
4. Compare with the original in the camera roll: 4080x3072 on the phone used for the 2026-10-05 test, JPEG, sharp.
5. Install the app to the home screen on both phones (browser menu, *Install* or *Add to home screen*), and open it on the iPad (9th generation, 10.2 in, 810 x 1080 CSS px) in Safari.

**Kill criterion:** if both ways in deliver a smaller photo than the original, the Expo Android capture app (plan, phase 4) comes next.

## 3. Cover and barcode photos

**Open.** Take 10 cover photos and 10 barcode photos, across the three languages, and upload them in *One book* mode. Record per photo: whether the cover's title and author were read right, whether the barcode decoded, and whether the ISBN found a record. This settles whether covers need two reads and whether the cover prompt needs changes.

## 4. Store: is Grist good enough to replace the review pages?

**Open, one evening at most.** Put 20 rows of an existing `records.csv` into Grist and into Google Sheets, correct them on the iPad (9th generation, 10.2 in) with the keyboard, and note what was awkward. The app's own pages are built already, so Grist now has to be clearly better to win.

## 5. Answer key

**Open.** Miro confirms the provisional answer key of the four test shelves (spec section 3, step 2), so accuracy numbers mean something.
