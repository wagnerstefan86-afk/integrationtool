"""Assessment and harmonization models.

The assessment model captures the evaluation of a stream or subprocess
across multiple alignment dimensions, applies hard constraints, and
produces a deterministic harmonization classification.

Classification levels (ordered from most to least harmonizable):
1. fully_centralizable - Can be run identically across DE/AT
2. central_method_local_execution - Central methodology, local execution
3. partially_harmonizable - Some parts can be unified, others remain local
4. minimum_standard_only - Only central minimum standards are feasible
5. currently_not_harmonizable - Must remain fully local for now

Prioritization levels for harmonization initiatives:
- high_priority
- medium_priority
- low_priority
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class HarmonizationClassification(str, Enum):
    FULLY_CENTRALIZABLE = "fully_centralizable"
    CENTRAL_METHOD_LOCAL_EXECUTION = "central_method_local_execution"
    PARTIALLY_HARMONIZABLE = "partially_harmonizable"
    MINIMUM_STANDARD_ONLY = "minimum_standard_only"
    CURRENTLY_NOT_HARMONIZABLE = "currently_not_harmonizable"


class HarmonizationPriority(str, Enum):
    HIGH = "high_priority"
    MEDIUM = "medium_priority"
    LOW = "low_priority"


class AssessedObjectType(str, Enum):
    STREAM = "stream"
    SUBPROCESS = "subprocess"


class AlignmentDimension(str, Enum):
    """Dimensions scored during harmonization assessment."""
    REGULATORY_ALIGNMENT = "regulatory_alignment"
    OPERATIONAL_ALIGNMENT = "operational_alignment"
    TOOLING_ALIGNMENT = "tooling_alignment"
    GOVERNANCE_ALIGNMENT = "governance_alignment"
    MATURITY = "maturity"
    LOCAL_NECESSITY = "local_necessity"


class HardConstraint(str, Enum):
    """Conditions that force a lower harmonization classification regardless of score."""
    LEGAL_LOCAL_DIFFERENCE = "legal_local_difference"
    TENANT_SEPARATION_BLOCKS_OPERATION = "tenant_separation_blocks_operation"
    SEPARATE_CONTROL_OWNERSHIP = "separate_control_ownership"
    INSUFFICIENT_DOCUMENTATION = "insufficient_documentation"


class AssessmentAnswer(BaseModel):
    """A single dimension rating within an assessment.

    Score range: 1 (no alignment / high local necessity) to 5 (full alignment).
    For local_necessity the scale is inverted conceptually:
      1 = high local necessity (bad for harmonization)
      5 = no local necessity (good for harmonization)
    """
    dimension: AlignmentDimension
    score: int = Field(ge=1, le=5)
    rationale: str


class PrioritizationInput(BaseModel):
    """Input factors for harmonization initiative prioritization.

    Each factor scored 1 (low) to 5 (high).
    """
    harmonization_potential: int = Field(ge=1, le=5)
    operational_relevance: int = Field(ge=1, le=5)
    governance_compliance_benefit: int = Field(ge=1, le=5)
    implementation_effort: int = Field(ge=1, le=5)
    dependencies: int = Field(ge=1, le=5)


class PrioritizationResult(BaseModel):
    """Computed prioritization for a harmonization initiative."""
    priority: HarmonizationPriority
    priority_score: float = Field(ge=0.0, le=1.0)
    rationale: str


class HarmonizationResult(BaseModel):
    """Computed harmonization outcome for a single assessed object."""
    harmonization_score: float = Field(ge=0.0, le=1.0)
    classification: HarmonizationClassification
    rationale: str
    harmonizable_parts: list[str] = Field(default_factory=list)
    local_only_parts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    recommendation: str


class Assessment(BaseModel):
    """Full assessment record for a stream or subprocess."""
    assessed_object_type: AssessedObjectType
    assessed_object_id: str
    answers: list[AssessmentAnswer] = Field(default_factory=list)
    hard_constraints: list[HardConstraint] = Field(default_factory=list)
    prioritization: Optional[PrioritizationInput] = None
    result: Optional[HarmonizationResult] = None
    prioritization_result: Optional[PrioritizationResult] = None
