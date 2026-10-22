"""load_candle_tags writes only what was reviewed, and only when it's safe.

A dry run writes nothing. --apply refuses while any value lacks a label in
one of the four languages, and refuses to replace a non-empty value without
--allow-overwrite. A "—" cell leaves the field as it is; burn_time is never
touched.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from candles.management.commands.load_candle_tags import (DEFAULT_SOURCE,
                                                          LANGUAGES,
                                                          read_draft)
from candles.models import Candle

TAGS_HEADER = (
    "| Scent | Rows | fragrance_family | intensity | top_notes | heart_notes | "
    "base_notes | mood_tags | use_case_tags | ideal_spaces | season_tags |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)
NOTES_HEADER = "| Scent | Write on row | assistant_notes |\n|---|---|---|\n"


@pytest.fixture
def matcha(db, category):
    small = Candle.objects.create(
        category=category, name="Matcha Chill", size="8 oz", burn_time="50+ hours"
    )
    large = Candle.objects.create(
        category=category, name="Matcha Chill", size="11.3 oz", mood_tags=["serene"]
    )
    return small, large


def _draft(tmp_path, small, large, *, notes_row=None, name="Matcha Chill"):
    path = tmp_path / "draft.md"
    path.write_text(
        "# Draft\n\n"
        + TAGS_HEADER
        + f"| {name} | {small.id}, {large.id} | — | soft | bergamot, lemon† | "
        "green tea, mint◊ | sandalwood | calm, clean | evenings | bedroom | — |\n"
        "\nSome text.\n\n"
        + NOTES_HEADER
        + f"| {name} | {notes_row or small.id} | A calm green-tea scent. |\n",
        encoding="utf-8",
    )
    return str(path)


LABELLED = {
    "intensity": ["soft"],
    "notes": ["bergamot", "lemon", "green tea", "mint", "sandalwood"],
    "mood": ["calm", "clean"],
    "use_case": ["evenings"],
    "spaces": ["bedroom"],
}


def _labels(tmp_path, *, drop=None):
    labels = {
        lang: {
            group: {value: f"{value} ({lang})" for value in values}
            for group, values in LABELLED.items()
        }
        for lang in LANGUAGES
    }
    if drop:
        lang, group, value = drop
        del labels[lang][group][value]

    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels), encoding="utf-8")
    return str(path)


@pytest.fixture
def i18n(tmp_path):
    """An i18n.ts that imports the labels file."""
    path = tmp_path / "i18n.ts"
    path.write_text('import candleTags from "./locales/labels.json";\n', encoding="utf-8")
    return str(path)


def _run(*args, **kwargs):
    out = StringIO()
    call_command("load_candle_tags", *args, stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
class TestDryRun:
    def test_writes_nothing_and_says_what_it_would(self, tmp_path, matcha):
        small, large = matcha

        out = _run(source=_draft(tmp_path, small, large), labels=_labels(tmp_path))

        small.refresh_from_db()
        assert small.top_notes == []
        assert "top_notes         set        bergamot, lemon" in out
        assert "OVERWRITE  serene" in out
        assert "Dry run — nothing written." in out

    def test_reports_missing_labels(self, tmp_path, matcha):
        out = _run(source=_draft(tmp_path, *matcha), labels=str(tmp_path / "none.json"))

        assert "Labels: 40 of 40 missing (10 values × 4 languages)" in out


@pytest.mark.django_db
class TestApply:
    def test_refused_without_labels(self, tmp_path, matcha):
        small, large = matcha

        with pytest.raises(CommandError, match="unlabelled values"):
            _run(
                source=_draft(tmp_path, small, large),
                labels=str(tmp_path / "none.json"),
                apply=True,
                allow_overwrite=True,
            )

        small.refresh_from_db()
        assert small.top_notes == []

    def test_one_missing_label_in_one_language_is_enough_to_refuse(
        self, tmp_path, matcha, i18n
    ):
        with pytest.raises(CommandError, match="unlabelled values"):
            _run(
                source=_draft(tmp_path, *matcha),
                labels=_labels(tmp_path, drop=("fr", "notes", "mint")),
                i18n=i18n,
                apply=True,
                allow_overwrite=True,
            )

    def test_refused_while_i18n_doesnt_import_the_labels(self, tmp_path, matcha):
        small, large = matcha
        unwired = tmp_path / "i18n.ts"
        unwired.write_text('import i18n from "i18next";\n', encoding="utf-8")

        with pytest.raises(CommandError, match="Import the labels file in i18n.ts first"):
            _run(
                source=_draft(tmp_path, small, large),
                labels=_labels(tmp_path),
                i18n=str(unwired),
                apply=True,
                allow_overwrite=True,
            )

        small.refresh_from_db()
        assert small.top_notes == []

    def test_refused_when_it_would_overwrite(self, tmp_path, matcha, i18n):
        small, large = matcha

        with pytest.raises(CommandError, match="1 non-empty values would be overwritten"):
            _run(
                source=_draft(tmp_path, small, large),
                labels=_labels(tmp_path),
                i18n=i18n,
                apply=True,
            )

        large.refresh_from_db()
        assert large.mood_tags == ["serene"]
        assert large.top_notes == []

    def test_writes_the_reviewed_values(self, tmp_path, matcha, i18n):
        small, large = matcha

        _run(
            source=_draft(tmp_path, small, large),
            labels=_labels(tmp_path),
            i18n=i18n,
            apply=True,
            allow_overwrite=True,
        )

        small.refresh_from_db()
        large.refresh_from_db()
        for candle in (small, large):
            assert candle.intensity == "soft"
            # Review marks are stripped.
            assert candle.top_notes == ["bergamot", "lemon"]
            assert candle.heart_notes == ["green tea", "mint"]
            assert candle.mood_tags == ["calm", "clean"]
            # "—" leaves the field alone.
            assert candle.fragrance_family == ""
            assert candle.season_tags == []
        assert small.assistant_notes == "A calm green-tea scent."
        assert large.assistant_notes == ""
        assert small.burn_time == "50+ hours"
        assert large.burn_time == ""

    def test_a_second_run_has_nothing_to_do(self, tmp_path, matcha, i18n):
        source, labels = _draft(tmp_path, *matcha), _labels(tmp_path)
        _run(source=source, labels=labels, i18n=i18n, apply=True, allow_overwrite=True)

        out = _run(source=source, labels=labels)

        assert "0 fields to set, 0 to overwrite" in out


@pytest.mark.django_db
class TestRefusesAMismatchedDraft:
    def test_a_row_with_a_different_name(self, tmp_path, matcha):
        small, large = matcha

        with pytest.raises(CommandError, match="is 'Matcha Chill', the draft says 'Matcha Latte'"):
            _run(source=_draft(tmp_path, small, large, name="Matcha Latte"))

    def test_a_row_that_doesnt_exist(self, tmp_path, matcha):
        small, large = matcha
        source = _draft(tmp_path, small, large)
        large_id = large.id
        large.delete()

        with pytest.raises(CommandError, match=f"Row {large_id} .* doesn't exist"):
            _run(source=source)

    def test_notes_on_another_scents_row(self, tmp_path, matcha, category):
        other = Candle.objects.create(category=category, name="Tidal Bore", size="8 oz")

        with pytest.raises(CommandError, match="isn't one of its rows"):
            _run(source=_draft(tmp_path, *matcha, notes_row=other.id))


def test_the_review_draft_parses():
    """docs/CANDLE_TAGS_DRAFT.md is the loader's input: a reformatted table
    should fail here, not on the production run."""
    plan = read_draft(DEFAULT_SOURCE)

    assert sorted(plan) == list(range(5, 20))
    assert plan[7][1]["heart_notes"] == ["honey", "cake", "mint"]
    assert plan[8][1]["top_notes"] == ["ozone", "citrus"]
    assert plan[14] == ("Woman Body", {})
    assert "assistant_notes" in plan[5][1]
    assert "assistant_notes" not in plan[16][1]


def test_the_labels_file_covers_the_review_draft():
    """Every value the draft would load has a label in all four languages."""
    from candles.management.commands.load_candle_tags import (DEFAULT_LABELS,
                                                              missing_labels)

    missing, distinct = missing_labels(read_draft(DEFAULT_SOURCE), DEFAULT_LABELS)

    assert missing == []
    assert distinct == 82
