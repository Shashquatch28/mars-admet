"""2D depiction (ml/serve/depiction.py, frontend ADR-039).

What matters is what the drawing must not do: no colour but black, no highlight, no text that could carry a value, the same
drawing for every way of writing one molecule, and an error, never a made-up drawing, for something that cannot be drawn.
"""

from __future__ import annotations

import re

import pytest
from serve.depiction import (
    DEPICTION_SOURCE,
    DEPICTION_VERSION,
    HEIGHT,
    INK,
    MAX_HEAVY_ATOMS,
    MAX_SMILES_LENGTH,
    WIDTH,
    canonical_smiles,
    draw_svg,
)

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_OTHER = "OC(=O)c1ccccc1OC(C)=O"  # the same molecule, written from the other end
RHODANINE = "S=C1SC(=Cc2ccc(O)cc2)C(=O)N1"
ALANINE_L = "C[C@H](N)C(=O)O"
ALANINE_D = "C[C@@H](N)C(=O)O"
SALT = "[Na+].[Cl-]"


def test_source_and_version_are_named():
    assert DEPICTION_SOURCE == "rdkit"
    assert DEPICTION_VERSION  # part of the cache key


@pytest.mark.parametrize("smiles", [ASPIRIN, RHODANINE, ALANINE_L, SALT, "c1ccccc1", "CCO"])
def test_the_drawing_is_black_line_art_and_nothing_else(smiles):
    svg = draw_svg(canonical_smiles(smiles))
    assert svg.startswith("<svg")
    assert f"viewBox='0 0 {WIDTH} {HEIGHT}'" in svg
    # one ink only: no element colours, no highlight colour, whatever the atoms are
    assert set(re.findall(r"#[0-9A-Fa-f]{3,8}", svg)) == {INK}
    assert not re.search(r"\b(rgb|rgba|hsl)\(", svg)
    # a transparent ground: no background rectangle
    assert "<rect" not in svg
    # nothing that could carry a number, a label of a property, or active content
    for banned in ("<text", "<script", "<image", "<foreignObject", "onload", "href="):
        assert banned not in svg


def test_a_rhodanine_is_drawn_without_marking_its_alert():
    # the PAINS match is a different feature's to show; the drawing of a flagged molecule is as plain as any other
    svg = draw_svg(canonical_smiles(RHODANINE))
    assert set(re.findall(r"#[0-9A-Fa-f]{3,8}", svg)) == {INK}


def test_every_way_of_writing_a_molecule_gives_the_same_drawing():
    assert canonical_smiles(ASPIRIN) == canonical_smiles(ASPIRIN_OTHER)
    assert draw_svg(canonical_smiles(ASPIRIN)) == draw_svg(canonical_smiles(ASPIRIN_OTHER))


def test_the_drawing_is_deterministic():
    c = canonical_smiles(RHODANINE)
    assert draw_svg(c) == draw_svg(c)


def test_stereochemistry_is_kept_in_the_canonical_form_and_changes_the_drawing():
    assert canonical_smiles(ALANINE_L) != canonical_smiles(ALANINE_D)
    assert draw_svg(canonical_smiles(ALANINE_L)) != draw_svg(canonical_smiles(ALANINE_D))


def test_a_salt_draws_both_components():
    assert canonical_smiles(SALT).count(".") == 1
    assert draw_svg(canonical_smiles(SALT)).startswith("<svg")


@pytest.mark.parametrize("bad", ["", "   ", "not a smiles ((", "C1CC", "[Xx]"])
def test_something_that_cannot_be_parsed_is_an_error_not_a_drawing(bad):
    with pytest.raises(ValueError):
        canonical_smiles(bad)


def test_an_overlong_smiles_is_refused_before_it_is_parsed():
    with pytest.raises(ValueError, match="longer than"):
        canonical_smiles("C" * (MAX_SMILES_LENGTH + 1))


def test_a_molecule_too_large_to_draw_legibly_is_refused():
    with pytest.raises(ValueError, match="heavy atoms"):
        canonical_smiles("C" * (MAX_HEAVY_ATOMS + 1))


def test_the_drawing_is_not_a_function_of_any_property():
    # a small polar molecule and a large greasy one: both are drawn with the identical option set, so the only
    # colours in either are black. (There is nothing to compare a value with: the drawer is never given one.)
    for smiles in ("OCC(O)CO", "CCCCCCCCCCCCCCCCCC"):
        assert set(re.findall(r"#[0-9A-Fa-f]{3,8}", draw_svg(canonical_smiles(smiles)))) == {INK}
