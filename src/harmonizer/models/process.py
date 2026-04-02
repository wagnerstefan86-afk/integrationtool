"""Process domain models.

Represents the core process hierarchy:
- MainProcess (Stream): Top-level InfoSec process domain
- SubProcess: A process step belonging to exactly one MainProcess
- ProcessInterface: A directed dependency/handoff between two processes

Assumption: country_scope and tenant_scope are critical for harmonization
analysis. A process scoped to "BOTH" countries is a candidate for
harmonization; one scoped to a single country may indicate local necessity.
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
    SEPARATE = "SEPARATE"  # Explicitly modeled as separate tenants


class InterfaceType(str, Enum):
    """Type of relationship between two processes."""
    DATA_FLOW = "data_flow"
    TRIGGER = "trigger"
    ESCALATION = "escalation"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    HANDOVER = "handover"


class MainProcess(BaseModel):
    """A top-level InfoSec process domain (Stream).

    Example: Incident Management, Vulnerability Management, Access Management.
    """
    id: str
    name: str
    description: str
    owner_role: str
    country_scope: CountryScope
    regulatory_context: list[str] = Field(default_factory=list)
    tenant_scope: TenantScope
    notes: Optional[str] = None


class SubProcess(BaseModel):
    """A process step belonging to exactly one MainProcess.

    Interfaces to other processes are modeled separately via ProcessInterface,
    not via the parent relationship. A SubProcess with main_process_id='X'
    belongs to Stream X -- an interface to Stream Y does NOT make it part of Y.
    """
    id: str
    main_process_id: str
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
    """A directed interface between two processes.

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
