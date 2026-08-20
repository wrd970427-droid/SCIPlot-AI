"""Validate Scientific Figure Catalog integrity."""

from __future__ import annotations

from knowledge.scientific_figures.loader import (
    load_catalog,
    load_composition_rules,
    load_data_schemas,
    load_package_registry,
    load_source_registry,
    load_taxonomy,
)
from schemas.figure_definition import ImplementationStatus


def test_catalog_loads_and_unique_ids() -> None:
    figures = load_catalog()
    assert len(figures) >= 50
    ids = [item.id for item in figures]
    assert len(ids) == len(set(ids))


def test_categories_exist_in_taxonomy() -> None:
    taxonomy = load_taxonomy()
    categories = set(taxonomy["categories"])
    for figure in load_catalog():
        assert figure.category in categories
        families = taxonomy["categories"][figure.category]["families"]
        family = figure.id.split(".", 1)[1]
        assert family in families


def test_data_schema_references_exist() -> None:
    schemas = set(load_data_schemas()["schemas"])
    for figure in load_catalog():
        assert figure.data_schema_id in schemas


def test_packages_exist_in_registry() -> None:
    packages = {item["package"] for item in load_package_registry()["packages"]}
    for figure in load_catalog():
        for pkg in figure.recommended_r_packages:
            assert pkg in packages, f"{figure.id} references missing package {pkg}"


def test_statistical_and_visual_params_disjoint() -> None:
    for figure in load_catalog():
        stats = {p.name for p in figure.statistical_parameters}
        visuals = {p.name for p in figure.visual_parameters}
        assert not (stats & visuals)


def test_implementation_status_legal() -> None:
    allowed = {item.value for item in ImplementationStatus}
    for figure in load_catalog():
        assert figure.implementation_status.value in allowed


def test_privacy_local_only_covers_raw_data() -> None:
    for figure in load_catalog():
        local = {item.lower() for item in figure.privacy.local_only}
        assert "raw_rows" in local or "patient_level_values" in local or "sample_level_values" in local
        assert "raw_rows" in local
        assert "patient_level_values" in local
        assert "sample_level_values" in local


def test_sources_have_verification_status() -> None:
    for figure in load_catalog():
        assert figure.sources
        for source in figure.sources:
            assert source.verification_status.value in {"verified", "unverified", "needs_verification"}


def test_volcano_maps_to_existing_capability() -> None:
    volcano = next(item for item in load_catalog() if item.id == "transcriptomics.volcano")
    assert volcano.implementation_status is ImplementationStatus.QC_VERIFIED
    assert "ggplot2" in volcano.recommended_r_packages
    assert "ggrepel" in volcano.recommended_r_packages
    stats = {p.name for p in volcano.statistical_parameters}
    visuals = {p.name for p in volcano.visual_parameters}
    assert "log2FC_threshold" in stats
    assert "significance_threshold" in stats
    assert "point_size" in visuals
    assert "threshold_line_width" in visuals
    assert "point_size" not in stats


def test_composition_and_source_registry_load() -> None:
    compositions = load_composition_rules()
    assert len(compositions["compositions"]) >= 5
    catalog_ids = {item.id for item in load_catalog()}
    for rule in compositions["compositions"]:
        for panel in rule["recommended_panels"]:
            assert panel in catalog_ids
    source = load_source_registry()
    assert source["figureya"]["modules_mapped_here"] >= 30
    for mapping in source["figureya"]["mappings"]:
        assert mapping["mapped_figure_family"] in catalog_ids
        assert mapping["verification_status"] in {"verified", "unverified"}
