"""Figure Definition schema — Scientific Figure Catalog ontology."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CapabilityLevel(str, Enum):
    CORE = "core"
    ADVANCED = "advanced"
    EXPERIMENTAL = "experimental"


class ImplementationStatus(str, Enum):
    CATALOG_ONLY = "catalog_only"
    SCHEMA_READY = "schema_ready"
    REQUIREMENT_READY = "requirement_ready"
    CODE_GENERATION_READY = "code_generation_ready"
    EXECUTION_VERIFIED = "execution_verified"
    QC_VERIFIED = "qc_verified"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NEEDS_VERIFICATION = "needs_verification"


class FieldRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    type: str
    description: str = ""


class ParameterDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    default: Any = None


class PrivacyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_allowed: list[str] = Field(default_factory=list)
    local_only: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_raw_data_local(self) -> "PrivacyPolicy":
        local = {item.lower() for item in self.local_only}
        required_tokens = ("raw_rows", "patient_level_values", "sample_level_values")
        if not any(token in local for token in required_tokens):
            raise ValueError(
                "privacy.local_only must include raw_rows / patient_level_values / sample_level_values"
            )
        return self


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    url: str = ""
    doi: str = ""
    verification_status: VerificationStatus = VerificationStatus.NEEDS_VERIFICATION
    source_status: Optional[str] = None


class FigureDefinition(BaseModel):
    """Canonical metadata for one scientific figure family."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    scientific_questions: list[str] = Field(default_factory=list)
    typical_data_contexts: list[str] = Field(default_factory=list)
    data_schema_id: str
    required_fields: list[FieldRole] = Field(default_factory=list)
    optional_fields: list[FieldRole] = Field(default_factory=list)
    accepted_data_shapes: list[str] = Field(default_factory=lambda: ["tidy_table"])
    recommended_r_packages: list[str] = Field(default_factory=list)
    statistical_parameters: list[ParameterDef] = Field(default_factory=list)
    visual_parameters: list[ParameterDef] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    compatible_panels: list[str] = Field(default_factory=list)
    privacy: PrivacyPolicy
    sources: list[SourceRef] = Field(default_factory=list)
    retrieval_keywords: list[str] = Field(default_factory=list)
    user_intent_examples: list[str] = Field(default_factory=list)
    negative_intents: list[str] = Field(default_factory=list)
    capability_level: CapabilityLevel = CapabilityLevel.CORE
    implementation_status: ImplementationStatus = ImplementationStatus.CATALOG_ONLY
    notes: str = ""

    @field_validator("id")
    @classmethod
    def _id_dotted(cls, value: str) -> str:
        if "." not in value or value.startswith(".") or value.endswith("."):
            raise ValueError("id must look like 'category.figure_family'")
        return value

    @model_validator(mode="after")
    def _params_disjoint(self) -> "FigureDefinition":
        stats = {item.name for item in self.statistical_parameters}
        visuals = {item.name for item in self.visual_parameters}
        overlap = stats & visuals
        if overlap:
            raise ValueError(f"statistical/visual parameter overlap: {sorted(overlap)}")
        return self

    @model_validator(mode="after")
    def _id_category_prefix(self) -> "FigureDefinition":
        prefix = self.id.split(".", 1)[0]
        if prefix != self.category:
            raise ValueError(f"id prefix '{prefix}' must match category '{self.category}'")
        return self


DEFAULT_PRIVACY = PrivacyPolicy(
    llm_allowed=["column_schema", "field_roles", "figure_spec", "desensitized_prompt"],
    local_only=["raw_rows", "patient_level_values", "sample_level_values", "dataframe_values"],
)
