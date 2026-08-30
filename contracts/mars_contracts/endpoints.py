"""
Canonical list of the 14 MARS ADMET endpoints.
This is the single source of truth for endpoint keys used across
ml/, api/, and frontend/ — never hardcode endpoint names elsewhere.
"""

from enum import Enum


class TaskType(str, Enum):
    REGRESSION = "regression"
    CLASSIFICATION = "classification"
    RULE_BASED = "rule_based"


class EndpointCategory(str, Enum):
    ABSORPTION = "absorption"
    DISTRIBUTION = "distribution"
    METABOLISM = "metabolism"
    EXCRETION = "excretion"
    TOXICITY = "toxicity"


class Endpoint(str, Enum):
    SOLUBILITY = "solubility_logs"
    LIPOPHILICITY = "lipophilicity_logp"
    CACO2 = "caco2_permeability"
    HIA = "hia_absorption"
    PGP = "pgp_inhibition"
    BBB = "bbb_permeability"
    PPB = "ppb_binding"
    CYP3A4 = "cyp3a4_inhibition"
    CYP2D6 = "cyp2d6_inhibition"
    CYP2C9 = "cyp2c9_inhibition"
    CLEARANCE = "clearance_microsomal"
    HERG = "herg_cardiotoxicity"
    AMES = "ames_mutagenicity"
    DILI = "dili_liver_injury"
    SA_SCORE = "synthetic_accessibility"  # rule-based, no ML model


# endpoint -> (task_type, category, cluster)
# cluster groups endpoints served by one multi-task forward pass (Module 4 / Module 8 routing table)
ENDPOINT_METADATA: dict[Endpoint, dict] = {
    Endpoint.SOLUBILITY: {"task_type": TaskType.REGRESSION, "category": EndpointCategory.ABSORPTION, "cluster": "absorption_distribution"},
    Endpoint.LIPOPHILICITY: {"task_type": TaskType.REGRESSION, "category": EndpointCategory.ABSORPTION, "cluster": "absorption_distribution"},
    Endpoint.CACO2: {"task_type": TaskType.REGRESSION, "category": EndpointCategory.ABSORPTION, "cluster": "absorption_distribution"},
    Endpoint.HIA: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.ABSORPTION, "cluster": "absorption_distribution"},
    Endpoint.PGP: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.ABSORPTION, "cluster": "absorption_distribution"},
    Endpoint.BBB: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.DISTRIBUTION, "cluster": "absorption_distribution"},
    Endpoint.PPB: {"task_type": TaskType.REGRESSION, "category": EndpointCategory.DISTRIBUTION, "cluster": "absorption_distribution"},
    Endpoint.CYP3A4: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.METABOLISM, "cluster": "metabolism"},
    Endpoint.CYP2D6: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.METABOLISM, "cluster": "metabolism"},
    Endpoint.CYP2C9: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.METABOLISM, "cluster": "metabolism"},
    Endpoint.CLEARANCE: {"task_type": TaskType.REGRESSION, "category": EndpointCategory.EXCRETION, "cluster": "metabolism"},
    Endpoint.HERG: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.TOXICITY, "cluster": "toxicity"},
    Endpoint.AMES: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.TOXICITY, "cluster": "toxicity"},
    Endpoint.DILI: {"task_type": TaskType.CLASSIFICATION, "category": EndpointCategory.TOXICITY, "cluster": "dili_standalone"},
    Endpoint.SA_SCORE: {"task_type": TaskType.RULE_BASED, "category": EndpointCategory.ABSORPTION, "cluster": None},
}

ALL_ENDPOINTS: list[Endpoint] = list(Endpoint)
ML_ENDPOINTS: list[Endpoint] = [e for e in Endpoint if e != Endpoint.SA_SCORE]
