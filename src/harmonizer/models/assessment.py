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


class DecisionType(str, Enum):
    """Classification of a decision by organizational scope."""
    STRATEGIC = "strategic"
    TACTICAL = "tactical"
    OPERATIONAL = "operational"


class DurationCategory(str, Enum):
    """Rough implementation duration buckets."""
    SHORT = "short"     # < 3 months
    MEDIUM = "medium"   # 3-9 months
    LONG = "long"       # > 9 months


class AlternativeOption(BaseModel):
    """One option within a decision context.

    Each decision presents 2-3 alternatives so that management
    can evaluate trade-offs rather than receiving a single verdict.
    """
    label: str
    description: str
    is_recommended: bool = False
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class NoActionImpact(BaseModel):
    """Consequences of NOT implementing the recommended decision.

    Makes explicit what happens if the organization does nothing.
    Each factor is rated low/medium/high.
    """
    regulatory_risk: ValueLevel
    operational_risk: ValueLevel
    inefficiency_cost: ValueLevel
    audit_exposure: ValueLevel
    rationale: str


class ImplementationImpact(BaseModel):
    """Impact assessment for implementing the recommended decision."""
    implementation_complexity: ValueLevel
    process_changes: list[str] = Field(default_factory=list)
    role_changes: list[str] = Field(default_factory=list)
    tool_changes: list[str] = Field(default_factory=list)
    governance_changes: list[str] = Field(default_factory=list)
    affected_roles: list[str] = Field(default_factory=list)
    change_magnitude: ValueLevel


class EffortEstimate(BaseModel):
    """Rough effort estimate — no false precision, only buckets.

    person_months_bucket: rough order of magnitude (e.g. "1-3", "3-6", "6-12", "12+")
    """
    person_months_bucket: str
    implementation_duration: DurationCategory
    cost_category: ValueLevel
    rationale: str


class GovernanceMapping(BaseModel):
    """Maps a decision to organizational governance structures."""
    decision_owner: str
    involved_stakeholders: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    decision_type: DecisionType


class DecisionTrace(BaseModel):
    """Full audit trail for a decision — makes the reasoning reproducible.

    Every decision must be fully traceable: which inputs were used,
    which rules fired, which constraints applied, and what the
    confidence basis was.
    """
    input_factors: list[str] = Field(default_factory=list)
    rules_triggered: list[str] = Field(default_factory=list)
    constraints_applied: list[str] = Field(default_factory=list)
    confidence_basis: str


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
    # Phase 5: Decision context, impact, governance, audit
    alternative_options: list[AlternativeOption] = Field(default_factory=list)
    no_action_impact: Optional[NoActionImpact] = None
    implementation_impact: Optional[ImplementationImpact] = None
    effort_estimate: Optional[EffortEstimate] = None
    governance: Optional[GovernanceMapping] = None
    decision_trace: Optional[DecisionTrace] = None


# --- Phase 6: Decision Outcome Tracking & Calibration ---

class OutcomeStatus(str, Enum):
    """What happened with the recommendation."""
    IMPLEMENTED = "implemented"
    REJECTED = "rejected"
    MODIFIED = "modified"
    DEFERRED = "deferred"


class DeviationLevel(str, Enum):
    """How much the actual outcome deviated from the recommendation."""
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    COMPLETE_OVERRIDE = "complete_override"


class DeviationReason(str, Enum):
    """Root cause of why the actual outcome deviated from the recommendation.

    Critical distinction: not every deviation is a model error.
    Political decisions and strategic overrides are legitimate governance
    actions that must NOT pollute model calibration.
    """
    MODEL_ERROR = "model_error"
    INCOMPLETE_DATA = "incomplete_data"
    CHANGED_CONTEXT = "changed_context"
    POLITICAL_DECISION = "political_decision"
    RESOURCE_CONSTRAINT = "resource_constraint"
    STRATEGIC_OVERRIDE = "strategic_override"


class LearningRelevance(str, Enum):
    """How relevant an outcome is for model calibration.

    Maps from DeviationReason:
    - model_error → high (the model was genuinely wrong)
    - incomplete_data → medium (data gap, partially the model's fault)
    - changed_context → medium (environment shifted after prediction)
    - political_decision → none (not a model issue)
    - strategic_override → none (not a model issue)
    - resource_constraint → low (external limitation, not model quality)
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ModelMaturityLevel(str, Enum):
    """Maturity of the decision model based on calibration data.

    initial: no outcome data yet — all predictions are uncalibrated
    learning: 1-4 outcomes recorded — patterns emerging but insufficient
    calibrated: 5-9 outcomes — systematic biases identified and adjusted
    stable: 10+ outcomes — model is well-calibrated with historical data
    """
    INITIAL = "initial"
    LEARNING = "learning"
    CALIBRATED = "calibrated"
    STABLE = "stable"


class ActualImplementation(BaseModel):
    """What actually happened during implementation."""
    actual_effort_bucket: str  # same format as EffortEstimate: "1-3", "3-6", etc.
    actual_duration: DurationCategory
    actual_complexity: ValueLevel


class ActualImpact(BaseModel):
    """What impact was actually realized."""
    business_value_realized: ValueLevel
    operational_improvement: ValueLevel
    issues_encountered: list[str] = Field(default_factory=list)


class DecisionOutcome(BaseModel):
    """Recorded outcome of a decision for calibration purposes.

    Populated after a decision has been executed (or rejected).
    Links back to the stream via assessed_object_id.

    deviation_reason and learning_relevance control whether this
    outcome influences model calibration. Political decisions and
    strategic overrides (learning_relevance=none) are excluded
    from bias detection to prevent false learning.
    """
    assessed_object_id: str
    outcome_status: OutcomeStatus
    actual_implementation: Optional[ActualImplementation] = None
    actual_impact: Optional[ActualImpact] = None
    deviation: DeviationLevel
    deviation_reason: Optional[DeviationReason] = None
    learning_relevance: Optional[LearningRelevance] = None
    deviation_rationale: str = ""
    lessons_learned: list[str] = Field(default_factory=list)


class CalibrationDeviation(BaseModel):
    """A single predicted-vs-actual comparison for one dimension."""
    dimension: str
    predicted: str
    actual: str
    direction: str  # "overestimated", "underestimated", "accurate"


class CalibrationSuggestion(BaseModel):
    """A concrete suggestion for adjusting the decision engine."""
    area: str  # e.g. "effort_estimate", "interface_complexity", "decision_aggressiveness"
    suggestion: str
    evidence: str
    priority: ValueLevel


class TrustScoreResult(BaseModel):
    """Model trust score based on validated high-relevance outcomes.

    Score 0.0-1.0 reflecting how much the model's predictions can be trusted.
    Only computed from outcomes with learning_relevance high or medium.
    """
    trust_score: float = Field(ge=0.0, le=1.0)
    validated_outcomes: int
    high_relevance_correct: int
    high_relevance_total: int
    rationale: str


class ProtectedRule(BaseModel):
    """A decision engine rule that must not be weakened by calibration.

    Certain rules (regulatory constraints, hard constraint handling,
    minimum confidence logic) are governance-mandated and must remain
    stable regardless of outcome data.
    """
    rule_id: str
    description: str
    reason: str  # why this rule is protected


class FilteredCalibrationStats(BaseModel):
    """Comparison of filtered vs unfiltered calibration results."""
    total_outcomes: int
    learning_relevant_outcomes: int
    excluded_outcomes: int
    excluded_reasons: list[str] = Field(default_factory=list)
    unfiltered_accuracy: float = Field(ge=0.0, le=1.0)
    filtered_accuracy: float = Field(ge=0.0, le=1.0)
    rationale: str


class CalibrationResult(BaseModel):
    """Result of comparing predictions against actual outcomes."""
    outcomes_analyzed: int
    accuracy_rate: float = Field(ge=0.0, le=1.0)
    deviations: list[CalibrationDeviation] = Field(default_factory=list)
    systematic_biases: list[str] = Field(default_factory=list)
    suggestions: list[CalibrationSuggestion] = Field(default_factory=list)
    model_maturity: ModelMaturityLevel
    confidence_adjustment: float = Field(ge=-0.5, le=0.5)
    rationale: str
    # Phase 7: Controlled learning
    trust_score: Optional[TrustScoreResult] = None
    protected_rules: list[ProtectedRule] = Field(default_factory=list)
    filtered_stats: Optional[FilteredCalibrationStats] = None
    deviation_reasons_summary: list[str] = Field(default_factory=list)


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
