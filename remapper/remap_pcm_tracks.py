import argparse
import csv
import os
import re
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remap PCM track numbers using a CSV mapping file."
    )
    parser.add_argument(
        "--csv",
        "-c",
        required=True,
        help="CSV file with source track number in the first column and destination track number in the second column.",
    )
    parser.add_argument(
        "--folder",
        "-f",
        default=".",
        help="Folder containing PCM files. Defaults to current directory.",
    )
    parser.add_argument(
        "--source-prefix",
        "-p",
        default=None,
        help="Optional input filename prefix to limit remapping to files that start with this prefix.",
    )
    parser.add_argument(
        "--dest-prefix",
        "-P",
        default=None,
        help="Optional output filename prefix to use for remapped files.",
    )
    parser.add_argument(
        "--delimiter",
        "-d",
        default="-",
        help="Delimiter between game name and track number in the filename. Default is '-'.",
    )
    parser.add_argument(
        "--suffix",
        "-s",
        default=".pcm",
        help="File suffix to match. Default is '.pcm'.",
    )
    parser.add_argument(
        "--output-folder",
        "-o",
        default=None,
        help="Optional output folder to write remapped copies. If omitted, files are renamed in place.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the remapping plan without renaming or copying files.",
    )
    return parser.parse_args()


def load_mapping(csv_path: Path) -> dict[int, int]:
    mapping: dict[int, int] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        for row_num, row in enumerate(reader, start=1):
            if not row or len(row) < 2:
                continue
            try:
                source = int(row[0].strip())
                dest = int(row[1].strip())
            except ValueError:
                continue
            mapping[source] = dest
    return mapping


def gather_pcm_files(folder: Path, prefix: str | None, delimiter: str, suffix: str) -> list[tuple[Path, str, int]]:
    escaped = re.escape(delimiter) + r"(\d+)" + re.escape(suffix) + r"$"
    if prefix is not None:
        pattern = re.compile(rf"^{re.escape(prefix)}{escaped}", re.IGNORECASE)
    else:
        pattern = re.compile(rf"^(.+?){escaped}", re.IGNORECASE)

    files: list[tuple[Path, str, int]] = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file():
            continue
        name = entry.name
        match = pattern.match(name)
        if not match:
            continue
        if prefix is None:
            base = match.group(1)
            track_num = int(match.group(2))
        else:
            base = prefix
            track_num = int(match.group(1))
        files.append((entry, base, track_num))
    return files


def build_plan(
    files: list[tuple[Path, str, int]],
    mapping: dict[int, int],
    delimiter: str,
    suffix: str,
    dest_prefix: str | None = None,
    output_folder: Path | None = None,
) -> list[tuple[Path, Path, int, int]]:
    plan: list[tuple[Path, Path, int, int]] = []
    for source_path, base, track_num in files:
        if track_num not in mapping:
            continue
        dest = mapping[track_num]
        output_base = dest_prefix if dest_prefix is not None else base
        dest_name = f"{output_base}{delimiter}{dest}{suffix}"
        target_path = (output_folder / dest_name) if output_folder is not None else source_path.with_name(dest_name)
        plan.append((source_path, target_path, track_num, dest))
    return plan


def find_missing_destinations(
    files: list[tuple[Path, str, int]], mapping: dict[int, int]
) -> list[int]:
    found_track_numbers = {track_num for _, _, track_num in files}
    return [dest for source, dest in mapping.items() if source not in found_track_numbers]


def ensure_no_conflicts(plan: list[tuple[Path, Path, int, int]]) -> list[str]:
    problems: list[str] = []
    target_counts: dict[Path, int] = {}
    for _, target, source_num, dest_num in plan:
        target_counts[target] = target_counts.get(target, 0) + 1
        if target.exists():
            problems.append(f"Target already exists: {target} (would map to {dest_num})")
    for target, count in target_counts.items():
        if count > 1:
            problems.append(f"Duplicate target path in plan: {target}")
    return problems


def execute_plan(
    plan: list[tuple[Path, Path, int, int]],
    dry_run: bool,
    output_folder: Path | None,
    missing_destinations: list[int],
) -> None:
    if not plan:
        print("No files to remap.")
        if missing_destinations:
            print_missing_destinations(missing_destinations)
        return

    print(f"Remap plan ({len(plan)} files):")
    for src, tgt, source_num, dest_num in plan:
        print(f"  {src.name} -> {tgt.name}")

    if dry_run:
        print("Dry run enabled; no files were changed.")
        if missing_destinations:
            print_missing_destinations(missing_destinations)
        return

    if output_folder is not None:
        output_folder.mkdir(parents=True, exist_ok=True)
        for src, tgt, _, _ in plan:
            if tgt.exists():
                raise FileExistsError(f"Output file already exists: {tgt}")
            shutil.copy2(src, tgt)
        print(f"Copied {len(plan)} remapped files to {output_folder}")
        if missing_destinations:
            print_missing_destinations(missing_destinations)
        return

    # In-place rename with temporary names to avoid collisions.
    temp_paths: list[tuple[Path, Path]] = []
    for src, tgt, _, _ in plan:
        temp = src.with_name(f"{src.name}.remap.tmp")
        if temp.exists():
            temp.unlink()
        src.rename(temp)
        temp_paths.append((temp, tgt))

    for temp, tgt in temp_paths:
        if tgt.exists():
            raise FileExistsError(f"Cannot rename {temp} to {tgt}; target already exists")
        temp.rename(tgt)

    print(f"Renamed {len(plan)} files.")


def print_missing_destinations(missing_destinations: list[int]) -> None:
    unique_destinations = sorted(set(missing_destinations))
    print("Note: the following destination track numbers were not remapped because source tracks were not found:")
    print("  " + ", ".join(str(dest) for dest in unique_destinations))


def main() -> int:
    args = parse_args()
    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        print(f"Error: folder not found: {folder}", file=sys.stderr)
        return 1

    csv_path = Path(args.csv)
    if not csv_path.exists() or not csv_path.is_file():
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        return 1

    mapping = load_mapping(csv_path)
    if not mapping:
        print(f"Error: no valid mappings found in {csv_path}", file=sys.stderr)
        return 1

    files = gather_pcm_files(folder, args.source_prefix, args.delimiter, args.suffix)
    if not files:
        print("No matching PCM files found.")
        return 0

    output_folder = Path(args.output_folder) if args.output_folder else None
    missing_destinations = find_missing_destinations(files, mapping)
    plan = build_plan(
        files,
        mapping,
        args.delimiter,
        args.suffix,
        dest_prefix=args.dest_prefix,
        output_folder=output_folder,
    )
    problems = ensure_no_conflicts(plan)
    if problems:
        print("Conflicts detected:")
        for problem in problems:
            print(f"  - {problem}")
        print("Fix conflicts before running the script.")
        return 1

    execute_plan(plan, args.dry_run, output_folder, missing_destinations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
