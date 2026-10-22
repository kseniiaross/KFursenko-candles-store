"""Load the reviewed scent tags and Lumière notes onto the candles.

Reads the two tables in docs/CANDLE_TAGS_DRAFT.md — the file the owner
reviews is the file that loads, so an edit there is what gets written.

    python manage.py load_candle_tags            # dry run: prints, writes nothing
    python manage.py load_candle_tags --apply    # writes

The dry run prints, per candle, each field it would set and each non-empty
value it would overwrite. --apply refuses to run:

- unless every value has a label in all four languages in
  frontend/src/locales/candle-tags.json, and frontend/src/i18n.ts imports
  that file — the product page shows these values as stored, so until the
  frontend reads the labels it would show lower-case English keys in every
  language;
- if it would overwrite a non-empty value, unless --allow-overwrite is
  given as well.

The labels file is shaped
    {"en": {"notes": {"tonka bean": "Tonka bean", ...}, "mood": {...}, ...},
     "ru": {...}, "es": {...}, "fr": {...}}
with one group per kind of value (see LABEL_GROUPS).

A "—" cell leaves that field as it is: "the description says nothing" is
not a reason to clear what is there. burn_time is never touched. A row is
matched by id and must still carry the scent's name, so a table drafted
against one database can't write onto different candles in another.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from candles.models import Candle

REPO_ROOT = Path(settings.BASE_DIR).parent
DEFAULT_SOURCE = REPO_ROOT / "docs" / "CANDLE_TAGS_DRAFT.md"
DEFAULT_LABELS = REPO_ROOT / "frontend" / "src" / "locales" / "candle-tags.json"
DEFAULT_I18N = REPO_ROOT / "frontend" / "src" / "i18n.ts"

LANGUAGES = ("en", "ru", "es", "fr")

# Table column -> label group in the labels file. List fields hold several
# comma-separated values; the rest hold one.
LABEL_GROUPS = {
    "fragrance_family": "family",
    "intensity": "intensity",
    "top_notes": "notes",
    "heart_notes": "notes",
    "base_notes": "notes",
    "mood_tags": "mood",
    "use_case_tags": "use_case",
    "ideal_spaces": "spaces",
    "season_tags": "season",
}
LIST_FIELDS = {
    "top_notes",
    "heart_notes",
    "base_notes",
    "mood_tags",
    "use_case_tags",
    "ideal_spaces",
    "season_tags",
}

TAGS_HEADER = ["Scent", "Rows", *LABEL_GROUPS]
NOTES_HEADER = ["Scent", "Write on row", "assistant_notes"]

EMPTY = "—"
# Review marks in the draft, not part of any value.
MARKERS = str.maketrans("", "", "†‡◊")


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table(lines, header):
    """The rows of the table whose header is exactly `header`, as dicts."""
    for i, line in enumerate(lines):
        if line.startswith("|") and _cells(line) == header:
            break
    else:
        raise CommandError(f"No table with the columns {' | '.join(header)}.")

    rows = []

    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break

        cells = _cells(line)

        if len(cells) != len(header):
            raise CommandError(f"Wrong number of cells: {line}")

        rows.append(dict(zip(header, cells)))

    return rows


def _value(field, cell):
    """The cell as the field stores it, or None for "leave as it is"."""
    cell = cell.translate(MARKERS).strip()

    if cell.startswith(EMPTY):
        return None

    if field in LIST_FIELDS:
        return [part.strip() for part in cell.split(",") if part.strip()]

    return cell


def read_draft(path):
    """{candle id: (scent name, {field: value})} from the draft's tables."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise CommandError(f"Can't read {path}: {error}") from error

    plan = {}
    rows_of = {}

    for row in _table(lines, TAGS_HEADER):
        name = row["Scent"]
        values = {
            field: value
            for field in LABEL_GROUPS
            if (value := _value(field, row[field])) is not None
        }

        try:
            ids = [int(part) for part in row["Rows"].split(",")]
        except ValueError as error:
            raise CommandError(f"{name}: Rows must be ids, got {row['Rows']!r}.") from error

        rows_of[name] = ids

        for candle_id in ids:
            if candle_id in plan:
                raise CommandError(f"Row {candle_id} is listed twice.")
            plan[candle_id] = (name, dict(values))

    for row in _table(lines, NOTES_HEADER):
        name = row["Scent"]
        notes = _value("assistant_notes", row["assistant_notes"])

        if notes is None:
            continue

        if name not in rows_of:
            raise CommandError(f"{name}: has notes but no row in the tags table.")

        try:
            candle_id = int(row["Write on row"])
        except ValueError as error:
            raise CommandError(f"{name}: Write on row must be an id.") from error

        if candle_id not in rows_of[name]:
            raise CommandError(
                f"{name}: notes go on row {candle_id}, which isn't one of its "
                f"rows {rows_of[name]}."
            )

        max_length = Candle._meta.get_field("assistant_notes").max_length
        if len(notes) > max_length:
            raise CommandError(f"{name}: notes are {len(notes)} characters, over {max_length}.")

        plan[candle_id][1]["assistant_notes"] = notes

    return plan


def missing_labels(plan, path):
    """Every value without a label, as "lang: group 'value'" — all of them
    when the labels file is missing or unreadable."""
    wanted = sorted(
        {
            (LABEL_GROUPS[field], value)
            for _, values in plan.values()
            for field, stored in values.items()
            if field in LABEL_GROUPS
            for value in (stored if field in LIST_FIELDS else [stored])
        }
    )

    try:
        labels = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        labels = {}

    if not isinstance(labels, dict):
        labels = {}

    missing = []

    for lang in LANGUAGES:
        groups = labels.get(lang)
        groups = groups if isinstance(groups, dict) else {}

        for group, value in wanted:
            names = groups.get(group)
            label = names.get(value) if isinstance(names, dict) else None

            if not isinstance(label, str) or not label.strip():
                missing.append(f"{lang}: {group} {value!r}")

    return missing, len(wanted)


def labels_imported(labels_path, i18n_path):
    """Whether the frontend's i18n setup imports the labels file. A complete
    file nothing reads labels nothing on the page."""
    try:
        source = Path(i18n_path).read_text(encoding="utf-8")
    except OSError:
        return False

    return Path(labels_path).name in source


def _show(value):
    if isinstance(value, list):
        return ", ".join(value) if value else "(empty)"
    return value if value else "(empty)"


class Command(BaseCommand):
    help = "Load scent tags and Lumière notes from docs/CANDLE_TAGS_DRAFT.md."

    def add_arguments(self, parser):
        parser.add_argument("--source", default=str(DEFAULT_SOURCE))
        parser.add_argument("--labels", default=str(DEFAULT_LABELS))
        parser.add_argument("--i18n", default=str(DEFAULT_I18N))
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without it, nothing is written.",
        )
        parser.add_argument(
            "--allow-overwrite",
            action="store_true",
            help="With --apply: also replace values that aren't empty.",
        )

    def handle(self, *args, **options):
        plan = read_draft(options["source"])
        candles = Candle.objects.in_bulk(plan.keys())

        problems = [
            f"Row {candle_id} ({name}) doesn't exist."
            for candle_id, (name, _) in plan.items()
            if candle_id not in candles
        ] + [
            f"Row {candle_id} is {candles[candle_id].name!r}, the draft says {name!r}."
            for candle_id, (name, _) in plan.items()
            if candle_id in candles and candles[candle_id].name != name
        ] + [
            f"{name}: intensity {values['intensity']!r} isn't one of "
            f"{', '.join(Candle.Intensity.values)}."
            for name, values in plan.values()
            if values.get("intensity") not in (None, *Candle.Intensity.values)
        ]

        if problems:
            raise CommandError("Nothing written:\n  " + "\n  ".join(problems))

        changes = {}
        counts = {"set": 0, "overwrite": 0, "unchanged": 0, "left": 0}

        for candle_id in sorted(plan):
            name, values = plan[candle_id]
            candle = candles[candle_id]
            label = f"#{candle_id} {candle.name} {candle.size}".strip()
            self.stdout.write(f"\n{label}")

            changed = {}

            for field in (*LABEL_GROUPS, "assistant_notes"):
                current = getattr(candle, field)

                if field not in values:
                    counts["left"] += 1
                    continue

                new = values[field]

                if new == current:
                    counts["unchanged"] += 1
                    continue

                kind = "overwrite" if current else "set"
                counts[kind] += 1
                changed[field] = new

                if kind == "set":
                    self.stdout.write(f"  {field:<17} set        {_show(new)}")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {field:<17} OVERWRITE  {_show(current)}\n"
                            f"  {'':<17}       with  {_show(new)}"
                        )
                    )

            if not changed:
                self.stdout.write("  nothing to change")

            changes[candle_id] = changed

        unplanned = Candle.objects.exclude(id__in=plan.keys()).order_by("id")
        if unplanned.exists():
            self.stdout.write(self.style.WARNING("\nNot in the draft, left as they are:"))
            for candle in unplanned:
                self.stdout.write(f"  #{candle.id} {candle.name} {candle.size}".rstrip())

        self.stdout.write(
            f"\n{len(plan)} candles: {counts['set']} fields to set, "
            f"{counts['overwrite']} to overwrite, {counts['unchanged']} already "
            f"equal, {counts['left']} left as they are (— in the draft). "
            "burn_time is not touched."
        )

        missing, distinct = missing_labels(plan, options["labels"])

        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"Labels: {len(missing)} of {distinct * len(LANGUAGES)} missing "
                    f"({distinct} values × {len(LANGUAGES)} languages) in "
                    f"{options['labels']}."
                )
            )
            for line in missing[:10]:
                self.stdout.write(f"  {line}")
            if len(missing) > 10:
                self.stdout.write(f"  … and {len(missing) - 10} more")
        else:
            self.stdout.write(self.style.SUCCESS(f"Labels: all {distinct} values labelled."))

        imported = labels_imported(options["labels"], options["i18n"])

        if imported:
            self.stdout.write(self.style.SUCCESS(f"Labels: imported by {options['i18n']}."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Labels: not imported by {options['i18n']} — the product page "
                    "doesn't read them yet."
                )
            )

        if not options["apply"]:
            self.stdout.write(self.style.NOTICE("\nDry run — nothing written."))
            return

        if missing or not imported:
            raise CommandError(
                "Not applied: the product page would show unlabelled values. "
                + (
                    "Add the missing labels first."
                    if missing
                    else "Import the labels file in i18n.ts first."
                )
            )

        if counts["overwrite"] and not options["allow_overwrite"]:
            raise CommandError(
                f"Not applied: {counts['overwrite']} non-empty values would be "
                "overwritten. Check them above, then add --allow-overwrite."
            )

        with transaction.atomic():
            for candle_id, changed in changes.items():
                if changed:
                    Candle.objects.filter(pk=candle_id).update(**changed)

        written = sum(len(changed) for changed in changes.values())
        self.stdout.write(self.style.SUCCESS(f"\nWritten: {written} fields."))
