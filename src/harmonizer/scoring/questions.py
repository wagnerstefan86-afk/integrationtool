"""Stream-type-specific supplementary question definitions.

Each stream type has a set of supplementary questions that go beyond
the six base alignment dimensions. These capture type-specific concerns
that influence harmonization feasibility.

Questions are defined as a catalog. Each question has:
- id: unique identifier within its stream type
- text: the question posed to the assessor
- focus: what this question evaluates (for documentation)

The base 6 alignment dimensions remain mandatory for ALL types.
Type-specific questions are supplementary and contribute to
completeness scoring and the type-specific score modifier.
"""

from dataclasses import dataclass

from harmonizer.models.process import StreamType


@dataclass(frozen=True)
class TypeQuestion:
    id: str
    text: str
    focus: str


# --- Question catalogs per stream type ---

STREAM_TYPE_QUESTIONS: dict[StreamType, list[TypeQuestion]] = {
    StreamType.PROCESS: [
        TypeQuestion(
            id="proc_trigger_uniform",
            text="Are process triggers and entry criteria identical across DE/AT?",
            focus="Trigger and entry point alignment",
        ),
        TypeQuestion(
            id="proc_workflow_steps",
            text="Can the core workflow steps be executed identically?",
            focus="Operational step-level alignment",
        ),
        TypeQuestion(
            id="proc_roles_mapped",
            text="Are roles and responsibilities mapped consistently across locations?",
            focus="Role alignment",
        ),
        TypeQuestion(
            id="proc_handover_points",
            text="Are handover points to other processes standardized?",
            focus="Interface standardization",
        ),
        TypeQuestion(
            id="proc_evidence_uniform",
            text="Can the same evidence and audit trail be produced in both locations?",
            focus="Evidence and documentation alignment",
        ),
    ],
    StreamType.GOVERNANCE_FUNCTION: [
        TypeQuestion(
            id="gov_mandate_shared",
            text="Is the governance mandate (charter, scope) identically defined?",
            focus="Mandate alignment",
        ),
        TypeQuestion(
            id="gov_policy_model",
            text="Can the policy/standard model be unified across both ISMS tenants?",
            focus="Policy framework alignment",
        ),
        TypeQuestion(
            id="gov_control_objectives",
            text="Are control objectives and control sets aligned?",
            focus="Control model alignment",
        ),
        TypeQuestion(
            id="gov_evidence_logic",
            text="Can evidence and compliance reporting follow a unified logic?",
            focus="Evidence and reporting alignment",
        ),
        TypeQuestion(
            id="gov_committee_structure",
            text="Can governance committees and decision bodies be consolidated?",
            focus="Committee/body alignment",
        ),
    ],
    StreamType.SERVICE_DOMAIN: [
        TypeQuestion(
            id="svc_service_catalog",
            text="Can the service catalog be defined identically for both countries?",
            focus="Service definition alignment",
        ),
        TypeQuestion(
            id="svc_customer_interface",
            text="Is the customer/requester interface harmonizable?",
            focus="Customer interface alignment",
        ),
        TypeQuestion(
            id="svc_delivery_model",
            text="Can the service delivery model be standardized?",
            focus="Delivery model alignment",
        ),
        TypeQuestion(
            id="svc_sla_framework",
            text="Can SLAs and quality criteria be unified?",
            focus="SLA alignment",
        ),
        TypeQuestion(
            id="svc_local_delivery_need",
            text="Is local delivery capacity required, or can it be centralized?",
            focus="Local delivery necessity",
        ),
    ],
    StreamType.SUPPORT_FUNCTION: [
        TypeQuestion(
            id="sup_process_standard",
            text="Can the administrative process be fully standardized?",
            focus="Process standardization",
        ),
        TypeQuestion(
            id="sup_tooling_shared",
            text="Are the support tools shared or easily consolidatable?",
            focus="Tooling consolidation",
        ),
        TypeQuestion(
            id="sup_templates_reuse",
            text="Can templates and artifacts be reused across locations?",
            focus="Template reusability",
        ),
        TypeQuestion(
            id="sup_dependency_local",
            text="Are there local dependencies (HR systems, legal, etc.) that block unification?",
            focus="Local dependency assessment",
        ),
    ],
    StreamType.CAPABILITY_DOMAIN: [
        TypeQuestion(
            id="cap_method_shared",
            text="Are methodologies and frameworks shared across DE/AT?",
            focus="Methodology alignment",
        ),
        TypeQuestion(
            id="cap_platform_unified",
            text="Are platforms and tools unified or easily consolidatable?",
            focus="Platform alignment",
        ),
        TypeQuestion(
            id="cap_knowhow_pooled",
            text="Can specialist know-how be pooled across locations?",
            focus="Knowledge pooling feasibility",
        ),
        TypeQuestion(
            id="cap_enablement_shared",
            text="Can enablement and training be delivered centrally?",
            focus="Enablement delivery alignment",
        ),
    ],
    StreamType.PROGRAM_DOMAIN: [
        TypeQuestion(
            id="prg_steering_unified",
            text="Can program steering and governance be unified?",
            focus="Steering alignment",
        ),
        TypeQuestion(
            id="prg_initiative_shared",
            text="Are transformation initiatives applicable to both locations?",
            focus="Initiative alignment",
        ),
        TypeQuestion(
            id="prg_coordination_central",
            text="Can coordination be centralized without losing local effectiveness?",
            focus="Coordination centralization feasibility",
        ),
        TypeQuestion(
            id="prg_local_participation",
            text="Is local participation ensured in a centralized model?",
            focus="Local stakeholder inclusion",
        ),
        TypeQuestion(
            id="prg_reporting_unified",
            text="Can program reporting and KPIs be unified?",
            focus="Reporting alignment",
        ),
    ],
}


def get_required_questions(stream_type: StreamType) -> list[TypeQuestion]:
    """Return the supplementary questions required for a given stream type."""
    return STREAM_TYPE_QUESTIONS.get(stream_type, [])


def get_required_question_ids(stream_type: StreamType) -> set[str]:
    """Return the set of question IDs required for a given stream type."""
    return {q.id for q in get_required_questions(stream_type)}
