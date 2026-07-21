"""Tests for extensions/memory_wiki/apply.py.

Phase 4.3f-mr2: ports the OpenClaw
``apply.ts`` helpers. The tests focus on:

- ``normalize_memory_wiki_mutation_input``
  validates the raw input + maps the
  ``synthesis`` / ``metadata`` shortcut
  aliases.
- ``apply_memory_wiki_mutation`` for
  ``create_synthesis`` writes a new
  synthesis page under ``syntheses/`` +
  triggers a compile.
- ``apply_memory_wiki_mutation`` for
  ``update_metadata`` patches the frontmatter
  of an existing page (body preserved).
- The ``## Summary`` managed block is
  replaced; the ``## Notes`` human-notes
  block is preserved (the OpenClaw
  "human wins" behavior).
- Invalid inputs raise ``ValueError``.
- The ``confidence`` field is clamped to
  ``[0, 1]`` + the ``null`` sentinel clears
  the field (when ``allow_null=True``).
"""

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.apply import (  # noqa: E402
    GENERATED_END_MARKER,
    GENERATED_START_MARKER,
    HUMAN_END_MARKER,
    HUMAN_START_MARKER,
    CreateSynthesisMutation,
    UpdateMetadataMutation,
    apply_memory_wiki_mutation,
    normalize_memory_wiki_mutation_input,
)
from extensions.memory_wiki.markdown_pages import (  # noqa: E402
    render_wiki_markdown,
)


def _config(vault_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        vaultMode="single",
        vault=SimpleNamespace(path=str(vault_path), scope="global", renderMode="native"),
        search=SimpleNamespace(corpus="wiki"),
    )


def _existing_entity_page(*, id_: str = "entity.alpha", title: str = "Alpha") -> str:
    return render_wiki_markdown(
        frontmatter={"pageType": "entity", "id": id_},
        body=f"# {title}\n\nFirst line.\n",
    )


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    for sub in ("entities", "concepts", "sources", "syntheses", "reports"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "entities" / "alpha.md").write_text(_existing_entity_page(), encoding="utf-8")
    return tmp_path


class TestNormalizeInput:
    def test_create_synthesis_canonical(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {
                "op": "create_synthesis",
                "title": "Hello",
                "body": "Body.",
                "sourceIds": ["s1"],
            }
        )
        assert isinstance(m, CreateSynthesisMutation)
        assert m.title == "Hello"
        assert m.body == "Body."
        assert m.source_ids == ["s1"]
        assert m.op == "create_synthesis"

    def test_create_synthesis_alias_synthesis(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {
                "op": "synthesis",
                "title": "Hello",
                "body": "Body.",
                "sourceIds": ["s1"],
            }
        )
        assert m.op == "create_synthesis"

    def test_create_synthesis_missing_title_raises(self) -> None:
        with pytest.raises(ValueError, match="title"):
            normalize_memory_wiki_mutation_input(
                {
                    "op": "create_synthesis",
                    "body": "b",
                    "sourceIds": ["s1"],
                }
            )

    def test_create_synthesis_missing_body_raises(self) -> None:
        with pytest.raises(ValueError, match="body"):
            normalize_memory_wiki_mutation_input(
                {
                    "op": "create_synthesis",
                    "title": "T",
                    "sourceIds": ["s1"],
                }
            )

    def test_create_synthesis_missing_source_ids_raises(self) -> None:
        with pytest.raises(ValueError, match="sourceId"):
            normalize_memory_wiki_mutation_input(
                {
                    "op": "create_synthesis",
                    "title": "T",
                    "body": "b",
                }
            )

    def test_update_metadata_canonical(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {
                "op": "update_metadata",
                "lookup": "entities/alpha",
                "status": "draft",
            }
        )
        assert isinstance(m, UpdateMetadataMutation)
        assert m.op == "update_metadata"
        assert m.lookup == "entities/alpha"
        assert m.status == "draft"

    def test_update_metadata_alias_metadata(self) -> None:
        m = normalize_memory_wiki_mutation_input({"op": "metadata", "lookup": "entities/alpha"})
        assert m.op == "update_metadata"

    def test_update_metadata_missing_lookup_raises(self) -> None:
        with pytest.raises(ValueError, match="lookup"):
            normalize_memory_wiki_mutation_input({"op": "update_metadata", "status": "draft"})

    def test_update_metadata_confidence_null_clears(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {
                "op": "update_metadata",
                "lookup": "entities/alpha",
                "confidence": None,
            }
        )
        assert isinstance(m, UpdateMetadataMutation)
        assert m.confidence is None

    def test_update_metadata_confidence_omitted_keeps_existing(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {"op": "update_metadata", "lookup": "entities/alpha"}
        )
        assert m.confidence == "__unset__"

    def test_update_metadata_confidence_in_range_accepted(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {
                "op": "update_metadata",
                "lookup": "entities/alpha",
                "confidence": 0.5,
            }
        )
        assert isinstance(m, UpdateMetadataMutation)
        assert m.confidence == 0.5

    def test_update_metadata_confidence_out_of_range_dropped(self) -> None:
        m = normalize_memory_wiki_mutation_input(
            {
                "op": "update_metadata",
                "lookup": "entities/alpha",
                "confidence": 1.5,
            }
        )
        # Out-of-range → ignored (None).
        assert m.confidence is None

    def test_unknown_op_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            normalize_memory_wiki_mutation_input(
                {"op": "bogus", "title": "t", "body": "b", "sourceIds": ["s"]}
            )

    def test_non_object_input_raises(self) -> None:
        with pytest.raises(ValueError, match="object input"):
            normalize_memory_wiki_mutation_input("not a dict")


class TestCreateSynthesis:
    def test_creates_new_synthesis_page(self, vault: Path) -> None:
        result = apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=CreateSynthesisMutation(
                title="My synthesis",
                body="Summary body.",
                source_ids=["s1", "s2"],
                status="active",
                confidence=0.9,
            ),
        )
        assert result.changed is True
        assert result.operation == "create_synthesis"
        assert result.page_path.startswith("syntheses/")
        assert result.page_path.endswith(".md")
        assert result.page_id is not None
        assert result.page_id.startswith("synthesis.")

        # The file is on disk with the right
        # managed blocks.
        page = (vault / result.page_path).read_text(encoding="utf-8")
        assert GENERATED_START_MARKER in page
        assert GENERATED_END_MARKER in page
        assert HUMAN_START_MARKER in page
        assert HUMAN_END_MARKER in page
        assert "Summary body." in page
        assert "id: synthesis." in page
        assert "pageType: synthesis" in page
        # ``status: active`` (the default).
        assert "status: active" in page

    def test_preserves_existing_notes_block(self, vault: Path) -> None:
        # Pre-create a synthesis page with
        # operator notes inside the
        # ``HUMAN_START``/``HUMAN_END`` markers.
        (vault / "syntheses" / "preexisting.md").write_text(
            render_wiki_markdown(
                frontmatter={"pageType": "synthesis", "id": "synthesis.preexisting"},
                body=(
                    "# Preexisting\n\n"
                    "## Notes\n"
                    f"{HUMAN_START_MARKER}\n"
                    "operator note 1\n"
                    "operator note 2\n"
                    f"{HUMAN_END_MARKER}\n"
                ),
            ),
            encoding="utf-8",
        )
        result = apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=CreateSynthesisMutation(
                title="Preexisting",
                body="new summary",
                source_ids=["s1"],
            ),
        )
        assert result.changed is True
        page = (vault / result.page_path).read_text(encoding="utf-8")
        # The operator notes are preserved.
        assert "operator note 1" in page
        assert "operator note 2" in page
        # The summary is rewritten.
        assert "new summary" in page


class TestUpdateMetadata:
    def test_updates_status_field(self, vault: Path) -> None:
        result = apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=UpdateMetadataMutation(
                lookup="entities/alpha",
                status="draft",
            ),
        )
        assert result.changed is True
        assert result.operation == "update_metadata"
        assert result.page_path == "entities/alpha.md"
        assert result.page_id == "entity.alpha"
        page = (vault / "entities" / "alpha.md").read_text(encoding="utf-8")
        assert "status: draft" in page
        # The body is preserved (the
        # ``# Alpha`` H1 is still there).
        assert "# Alpha" in page

    def test_clears_confidence_with_null(self, vault: Path) -> None:
        # Pre-set the confidence via a
        # create_synthesis.
        apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=CreateSynthesisMutation(
                title="tmp",
                body="b",
                source_ids=["s1"],
                confidence=0.5,
            ),
        )
        # Now patch entities/alpha to add a
        # confidence, then clear it.
        apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=UpdateMetadataMutation(
                lookup="entities/alpha",
                confidence=0.7,
            ),
        )
        # Read the file content to confirm
        # the confidence is present.
        page = (vault / "entities" / "alpha.md").read_text(encoding="utf-8")
        assert "confidence: 0.7" in page
        # Clear the confidence.
        apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=UpdateMetadataMutation(
                lookup="entities/alpha",
                confidence=None,
            ),
        )
        page = (vault / "entities" / "alpha.md").read_text(encoding="utf-8")
        assert "confidence:" not in page

    def test_missing_page_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            apply_memory_wiki_mutation(
                config=_config(vault),
                mutation=UpdateMetadataMutation(
                    lookup="entities/missing",
                    status="draft",
                ),
            )

    def test_lookup_by_id_works(self, vault: Path) -> None:
        # The ``resolve_queryable_wiki_page_by_lookup``
        # helper accepts an id; the apply
        # path passes the lookup string
        # through unchanged.
        result = apply_memory_wiki_mutation(
            config=_config(vault),
            mutation=UpdateMetadataMutation(
                lookup="entity.alpha",
                status="archived",
            ),
        )
        assert result.changed is True
        assert result.page_path == "entities/alpha.md"
        page = (vault / "entities" / "alpha.md").read_text(encoding="utf-8")
        assert "status: archived" in page
