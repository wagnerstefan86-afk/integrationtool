"""Assessment and harmonization models.

The assessment model captures the evaluation of a stream or subprocess
across multiple alignment dimensions, applies hard constraints, and
produces a deterministic harmonization classification.

This module also defines:
- Stream-type-specific supplementary questions
- Completeness and confidence scoring
- Aggregation metadata for stream-level roll-ups from subprocesses
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


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssessedObjectType(str, Enum):
    STREAM = "stream"
    SUBPROCESS = "subprocess"


class AlignmentDimension(str, Enum):
    """Base dimensions scored during harmonization assessment."""
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


class TypeSpecificAnswer(BaseModel):
    """Answer to a stream-type-specific supplementary question.

    These questions are defined per StreamType and provide additional
    depth beyond the six base alignment dimensions.
    Score range: 1 (low/negative) to 5 (high/positive for harmonization).
    """
    question_id: str
    score: int = Field(ge=1, le=5)
    rationale: str


class PrioritizationInput(BaseModel):
    """Input factors for harmonization initiative prioritization."""
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


class CompletenessResult(BaseModel):
    """Assessment completeness and confidence evaluation."""
    completeness_score: int = Field(ge=0, le=100)
    confidence_level: ConfidenceLevel
    missing_items: list[str] = Field(default_factory=list)
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


class Decision(str, Enum):
    """Concrete management decision derived from assessment data."""
    CENTRALIZE_NOW = "centralize_now"
    CENTRALIZE_LATER = "centralize_later"
    HARMONIZE_ONLY = "harmonize_only"
    STANDARDIZE_ONLY = "standardize_only"
    KEEP_LOCAL = "keep_local"
    REASSESS_AFTER_DATA_COMPLETION = "reassess_after_data_completion"


class TargetOperatingModel(str, Enum):
    """Target operating model for a stream after harmonization."""
    CENTRALIZED_EXECUTION = "centralized_execution"
    CENTRAL_METHOD_LOCAL_EXECUTION = "central_method_local_execution"
    FEDERATED_STANDARDIZED = "federated_standardized"
    LOCAL_INDEPENDENT = "local_independent"


class ValueLevel(str, Enum):
    """Three-tier value/impact indicator."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InterfaceComplexityResult(BaseModel):
    """Computed interface complexity for a stream."""
    complexity_score: float = Field(ge=0.0, le=1.0)
    interface_count: int = Field(ge=0)
    distinct_types: int = Field(ge=0)
    distinct_artifacts: int = Field(ge=0)
    cross_area_connections: int = Field(ge=0)
    rationale: str


class HarmonizationDegree(BaseModel):
    """Separate assessment of harmonizability, standardizability, centralizability.

    These three dimensions can diverge: a process may be standardizable
    (common templates/methods) but not centralizable (must run locally).
    """
    harmonizable: bool
    harmonization_degree: float = Field(ge=0.0, le=1.0)
    standardizable: bool
    standardization_degree: float = Field(ge=0.0, le=1.0)
    centralizable: bool
    centralization_degree: float = Field(ge=0.0, le=1.0)
    rationale: str


class ValueIndicators(BaseModel):
    """Economic and strategic value indicators for a stream."""
    expected_business_value: ValueLevel
    regulatory_pressure: ValueLevel
    operational_impact: ValueLevel
    rationale: str


class DecisionResult(BaseModel):
    """Complete decision output from the decision engine."""
    decision: Decision
    decision_rationale: str
    blocking_factors: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    expected_benefit: str
    implementation_risk: str
    target_operating_model: TargetOperatingModel
    interface_complexity: InterfaceComplexityResult
    harmonization_degree: HarmonizationDegree
    value_indicators: ValueIndicators


class Assessment(BaseModel):
    """Full assessment record for a stream or subprocess."""
    assessed_object_type: AssessedObjectType
    assessed_object_id: str
    answers: list[AssessmentAnswer] = Field(default_factory=list)
    type_specific_answers: list[TypeSpecificAnswer] = Field(default_factory=list)
    hard_constraints: list[HardConstraint] = Field(default_factory=list)
    prioritization: Optional[PrioritizationInput] = None
    result: Optional[HarmonizationResult] = None
    prioritization_result: Optional[PrioritizationResult] = None
    completeness: Optional[CompletenessResult] = None
    decision_result: Optional[DecisionResult] = None
