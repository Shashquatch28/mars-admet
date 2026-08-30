"""
3D conformer data, consumed by frontend's 3Dmol.js viewer (Module 7).
Generated lazily by ML/featurization (ETKDG + MMFF94, Module 3 stage 5), served via
GET /molecule/{id}/3d (Module 8), cached in Redis with the same molecule_id key.
"""

from pydantic import BaseModel, Field


class Atom(BaseModel):
    element: str
    x: float
    y: float
    z: float
    partial_charge: float | None = Field(default=None, description="Gasteiger charge, used by electrostatic surface view")


class Bond(BaseModel):
    atom_index_1: int
    atom_index_2: int
    order: float  # 1, 1.5 (aromatic), 2, 3


class ConformerResponse(BaseModel):
    molecule_id: str
    atoms: list[Atom]
    bonds: list[Bond]
    energy_kcal_mol: float = Field(..., description="MMFF94 optimized energy of the returned (lowest-energy) conformer")
    sdf_block: str = Field(..., description="Full SDF block, for direct 3Dmol.js consumption without client-side reconstruction")
