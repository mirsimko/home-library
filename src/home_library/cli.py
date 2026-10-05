"""The hl command (see docs/pipeline.md). Every stage can be run by itself, or all of them with `hl run`."""
import argparse
import json
import sys
from pathlib import Path

from home_library import pipeline
from home_library.pick import run_pick
from home_library.reader import BACKENDS, run_read
from home_library.tiles import cut_tiles
from home_library.workspace import DEFAULT_WORK_ROOT, photo_dir

SECOND_READ_ID = {"pi": "b-spark", "codex-exec": "b-sol"}


def _parser():
    parser = argparse.ArgumentParser(prog="hl", description="Shelf photos in, review-ready book records out.")
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT,
                        help="where the private work directories live (default: %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)

    def command(name, text):
        sub = commands.add_parser(name, help=text, description=text)
        # also accepted after the command, where it is easier to type
        sub.add_argument("--work-root", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sub

    run = command("run", "Run every stage for each photo, one photo at a time.")
    run.add_argument("photos", nargs="+", type=Path)
    run.add_argument("--location", default="", help="the shelf or box the photo shows, for example 'Box 3'")
    run.add_argument("--second-reader", choices=sorted(SECOND_READ_ID), default="pi",
                     help="backend of the second, checking read (default: %(default)s)")
    run.add_argument("--force", action="store_true", help="start from nothing even if reads are stored")

    command("tiles", "Cut a photo into tiles.").add_argument("photo", type=Path)
    read = command("read", "Run one read of a photo's tiles.")
    read.add_argument("photo", type=Path)
    read.add_argument("--read-id", required=True)
    read.add_argument("--backend", choices=sorted(BACKENDS), required=True)
    merge = command("merge", "Compare two stored reads of a photo.")
    merge.add_argument("photo", type=Path)
    merge.add_argument("--reads", nargs=2, default=[read_id for read_id, _ in pipeline.READERS],
                       metavar="READ_ID")
    command("lookup", "Fetch catalogue candidates for a photo's titles.").add_argument("photo", type=Path)
    command("pick", "Let the model pick among a photo's candidates.").add_argument("photo", type=Path)
    export = command("export", "Write a photo's records.json and records.csv.")
    export.add_argument("photo", type=Path)
    export.add_argument("--location", default="")
    command("gather", "Print one read's answers for all photos, in the shape the scoring tools take."
            ).add_argument("read_id")
    return parser


def _report(result):
    if "error" in result:
        print(f"{result['photo']}: {result['error']}", file=sys.stderr, flush=True)
        return
    seconds = ", ".join(f"{read_id} {value:.0f} s" for read_id, value in result["seconds"].items())
    print(f"{result['photo']}: {result['accepted']} accepted, {result['review']} to review, "
          f"{result['unreadable']} unreadable ({seconds}) -> {result['directory']}/records.csv", flush=True)


def _run(args):
    readers = (pipeline.READERS[0], (SECOND_READ_ID[args.second_reader], args.second_reader))
    results = pipeline.run_photos(args.photos, args.work_root, readers=readers, location=args.location,
                                  force=args.force, report=_report)
    return 1 if any("error" in result for result in results) else 0


def _stage(args):
    directory = photo_dir(args.work_root, args.photo)
    if args.command == "tiles":
        manifest = cut_tiles(args.photo, directory)
        print(f"{manifest['photo']}: {len(manifest['tiles'])} images, "
              f"{manifest['total_bytes'] / 1e6:.1f} MB -> {directory}/tiles")
    elif args.command == "read":
        read = run_read(directory, args.read_id, args.backend)
        print(f"{read['file']}: {len(read['books'])} entries, {len(read['errors'])} unreadable pieces")
    elif args.command == "merge":
        merged = pipeline.merge_photo(directory, args.reads)
        statuses = [item["status"] for item in merged["items"]]
        print(f"{merged['file']}: {statuses.count('accepted')} accepted, {statuses.count('review')} to review")
    elif args.command == "lookup":
        found = pipeline.lookup_photo(directory)
        print(f"{found['file']}: candidates for {sum(1 for book in found['books'] if book['candidates'])} "
              f"of {len(found['books'])} titles")
    elif args.command == "pick":
        picks = run_pick(directory)
        print(f"{picks['file']}: {sum(1 for pick in picks['picks'] if pick['verdict'] == 'match')} matched")
    elif args.command == "export":
        records = pipeline.export_photo(directory, location=args.location)
        print(f"{len(records)} records -> {directory}/records.csv")
    return 0


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "gather":
        json.dump(pipeline.gather_read(args.work_root, args.read_id), sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    try:
        return _stage(args)
    except Exception as failure:
        print(f"{args.photo}: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
