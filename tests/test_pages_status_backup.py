"""The status page says when the last backup ran and warns when it is old or was refused."""
import json
from datetime import datetime, timedelta, timezone

from web_helpers import anonymous as anonymous
from web_helpers import client as client


def record(client, success=None, failed=None, error=None):
    def stamp(ago):
        return (datetime.now(timezone.utc) - ago).isoformat(timespec="seconds").replace("+00:00", "Z") if ago else None

    (client.app.state.data_root / "backup.json").write_text(
        json.dumps({"last_success": stamp(success), "failed_at": stamp(failed), "error": error}))


def test_a_recent_backup_shows_how_long_ago_without_a_warning(client):
    record(client, success=timedelta(hours=3))
    for page in (client.get("/status").text, client.get("/status/panel").text):
        assert "Last backup: 3 hours ago" in page
        assert 'data-backup="ok"' in page and "older than 2 days" not in page and "attempt failed" not in page


def test_a_backup_older_than_two_days_gets_a_warning(client):
    record(client, success=timedelta(days=3))
    page = client.get("/status").text
    assert "Last backup: 3 days ago" in page and 'data-backup="old"' in page
    assert 'class="badge warn"' in page and "older than 2 days" in page
    record(client, success=timedelta(days=1, hours=20))
    assert 'data-backup="ok"' in client.get("/status").text


def test_a_refused_backup_shows_its_message_and_when_the_last_one_worked(client):
    record(client, success=timedelta(hours=27), failed=timedelta(hours=1), error="the catalog has 1 of the 4 books <b>x</b>; use --force")
    page = client.get("/status").text
    assert 'data-backup="failed"' in page and 'class="badge bad"' in page
    assert "Last backup: 1 day ago" in page and "1 hour ago" in page
    assert "the catalog has 1 of the 4 books &lt;b&gt;x&lt;/b&gt;; use --force" in page


def test_no_backup_record_says_none_was_made_and_warns(client):
    page = client.get("/status").text
    assert 'data-backup="none"' in page and "No backup has been recorded" in page and 'class="badge warn"' in page
    (client.app.state.data_root / "backup.json").write_text("{damaged")
    assert 'data-backup="none"' in client.get("/status").text
