"""Process domain models.

Represents the three-tier organizational hierarchy:
- Area: Organizational grouping of streams (e.g., "Definition & Design")
- Stream: A functional domain within an area (e.g., "IT-Risk")
- SubProcess: A process step belonging to exactly one stream

Each stream has a StreamType that characterizes its nature, which
influences how harmonization is assessed.

ProcessInterface models directed dependencies between any two processes
(streams or subprocesses) without implying parent-child relationships.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CountryScope(str, Enum):
    DE = "DE"
    AT = "AT"
    BOTH = "BOTH"


class TenantScope(str, Enum):
    DE = "DE"
    AT = "AT"
    BOTH = "BOTH"
    SEPARATE = "SEPARATE"


class StreamType(str, Enum):
    """Characterizes the nature of a stream.

    Not every stream is a classical linear process. The stream type
    determines which alignment dimensions are weighted more heavily
    during harmonization assessment.
    """
    PROCESS = "process"
    GOVERNANCE_FUNCTION = "governance_function"
    SERVICE_DOMAIN = "service_domain"
    SUPPORT_FUNCTION = "support_function"
    CAPABILITY_DOMAIN = "capability_domain"
    PROGRAM_DOMAIN = "program_domain"


class InterfaceType(str, Enum):
    """Type of relationship between two processes."""
    DATA_FLOW = "data_flow"
    TRIGGER = "trigger"
    ESCALATION = "escalation"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    HANDOVER = "handover"


class GapLevel(str, Enum):
    """Three-tier gap/difference level for delta assessment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TargetOption(str, Enum):
    """Harmonization target option — which standard to adopt."""
    DE_STANDARD = "de_standard"
    AT_STANDARD = "at_standard"
    CENTRAL = "central"


class AsIsProcess(BaseModel):
    """AS-IS process description for one country variant."""
    description: str = ""
    steps: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)


class DeltaAssessment(BaseModel):
    """Gap analysis between DE and AT AS-IS processes."""
    structural_diff: GapLevel = GapLevel.LOW
    tooling_gap: GapLevel = GapLevel.LOW
    regulatory_gap: GapLevel = GapLevel.LOW
    role_model_diff: GapLevel = GapLevel.LOW


class Area(BaseModel):
    """An organizational grouping of streams.

    Example: "Definition & Design", "Check & Execute".
    """
    id: str
    name: str
    description: str = ""
    notes: Optional[str] = None


class Stream(BaseModel):
    """A functional domain within an area.

    Replaces the former MainProcess model. Each stream has a type that
    reflects its organizational nature (process, governance function, etc.).
    """
    id: str
    area_id: str
    name: str
    stream_type: StreamType
    description: str
    owner_role: str
    country_scope: CountryScope
    tenant_scope: TenantScope
    regulatory_context: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SubProcess(BaseModel):
    """A process step belonging to exactly one stream.

    Interfaces to other streams or subprocesses are modeled separately
    via ProcessInterface. A SubProcess with stream_id='X' belongs to
    Stream X -- an interface to Stream Y does NOT make it part of Y.
    """
    id: str
    stream_id: str
    name: str
    description: str
    purpose: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    country_scope: CountryScope
    tenant_scope: TenantScope
    regulatory_context: list[str] = Field(default_factory=list)
    interfaces_with: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ProcessInterface(BaseModel):
    """A directed interface between two processes (streams or subprocesses).

    This is NOT a parent-child relationship. It models data flows, triggers,
    escalations, or other handoffs between independently owned processes.
    """
    id: str
    source_process_id: str
    target_process_id: str
    interface_type: InterfaceType
    description: str
    trigger: Optional[str] = None
    exchanged_artifacts: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
