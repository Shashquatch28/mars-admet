"""A 2D drawing of a molecule for the serving layer (frontend ADR-039).

A drawing says what a molecule looks like and nothing about it. It is therefore deliberately plain: black strokes on a
transparent background, RDKit's black-and-white atom palette (no element colours, so no atom is coloured by what it is,
let alone by any property), no highlighted atoms or bonds, no atom indices, no stereo or CIP annotations beyond the
wedges the structure itself implies. Atom attribution belongs to the explainability feature, not here.

* `canonical_smiles` parses and re-writes the SMILES. The route keys its cache on it, and `draw_svg` draws from it, so
  every way of writing one molecule gives the same drawing (RDKit's 2D layout depends on atom order).
* `draw_svg` returns the SVG text. The only colour in it is `#000000`; a client that wants the ink in another colour
  replaces that one literal (the tests pin that there is no other).

Both raise `ValueError` with a reason a person can read; neither returns a drawing it could not make.
"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

DEPICTION_SOURCE = "rdkit"
# Part of the cache key: change it whenever the drawing options below change, so an older drawing is never served as the new one.
DEPICTION_VERSION = "d1"
INK = "#000000"  # the one colour RDKit's black-and-white palette writes

WIDTH = 320
HEIGHT = 220
MAX_SMILES_LENGTH = 1000
MAX_HEAVY_ATOMS = 250  # past this a 320 x 220 drawing is a smudge, and layout time grows with size


def canonical_smiles(smiles: str) -> str:
    """The RDKit canonical (isomeric) SMILES of `smiles`, or `ValueError` if it cannot be drawn."""
    text = (smiles or "").strip()
    if not text:
        raise ValueError("smiles must be a non-empty string")
    if len(text) > MAX_SMILES_LENGTH:
        raise ValueError(f"smiles is longer than {MAX_SMILES_LENGTH} characters")
    mol = Chem.MolFromSmiles(text)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("could not parse the SMILES")
    if mol.GetNumHeavyAtoms() > MAX_HEAVY_ATOMS:
        raise ValueError(f"the molecule has more than {MAX_HEAVY_ATOMS} heavy atoms, too many to draw legibly")
    return Chem.MolToSmiles(mol)


def draw_svg(canonical: str) -> str:
    """An SVG drawing of a SMILES, as plain black line art."""
    mol = Chem.MolFromSmiles(canonical)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("could not parse the SMILES")
    drawer = rdMolDraw2D.MolDraw2DSVG(WIDTH, HEIGHT)
    opts = drawer.drawOptions()
    opts.useBWAtomPalette()  # every atom and bond black: no element colours
    opts.clearBackground = False  # transparent: the page, not the drawing, supplies the ground
    opts.padding = 0.08
    opts.bondLineWidth = 1.6
    opts.addAtomIndices = False
    opts.addBondIndices = False
    opts.addStereoAnnotation = False
    drawer.DrawMolecule(mol)  # no highlight arguments: nothing is marked
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    # RDKit writes an XML declaration that claims iso-8859-1; the response is served as UTF-8 and the text is ASCII.
    return svg[svg.index("<svg") :]
