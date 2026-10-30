"""Maltego transform for alias search through Sherlock and Maigret."""

from __future__ import annotations

import json
from typing import List, Union

from maltego.entities import Alias, Phrase, URL
from maltego.server import MaltegoContext, register_transform

from .alias_core import (
    Profile,
    combined_raw_result,
    format_profile_note,
    format_summary_note,
    limit_profiles,
    merge_profiles,
    normalize_alias,
    run_alias_search,
)

AliasSearchEntity = Union[Phrase, URL]


def _short_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 20].rstrip() + "\n... [truncated]"


def _profile_properties(profile: Profile, alias: str) -> dict[str, object]:
    properties: dict[str, object] = {
        "alias": alias,
        "sources": ", ".join(sorted(profile.sources)),
    }
    if profile.http_status is not None:
        properties["http_status"] = profile.http_status

    for key in (
        "fullname",
        "location",
        "company",
        "bio",
        "created_at",
        "follower_count",
        "following_count",
        "public_repos_count",
        "tags",
    ):
        value = profile.metadata.get(key)
        if value:
            properties[key] = value

    if profile.metadata:
        properties["profile_metadata"] = json.dumps(
            profile.metadata,
            ensure_ascii=False,
            sort_keys=True,
        )
    return properties


def _build_alias_entities(alias: str, outcomes) -> List[AliasSearchEntity]:
    all_profiles = merge_profiles(outcomes)
    profiles, truncated = limit_profiles(all_profiles)

    engines = " + ".join(outcome.engine for outcome in outcomes)
    if profiles:
        summary_text = f"{alias}: {len(profiles)} profile(s) via {engines}"
    else:
        summary_text = f"{alias}: no profiles ({engines})"

    note = format_summary_note(alias, outcomes, profiles, truncated)
    summary = Phrase(
        summary_text,
        note=_short_text(note, 60_000),
        link_label="alias search",
    )
    summary.set_property("alias", alias, "Alias")
    summary.set_property("engines", engines, "Engines")
    summary.set_property("profile_count", len(profiles), "Unique profiles")
    summary.set_property(
        "truncated",
        "yes" if truncated else "no",
        "Result list truncated",
    )
    summary.set_property(
        "duration_seconds",
        round(sum(outcome.duration_seconds for outcome in outcomes), 2),
        "Total engine duration (s)",
    )

    for outcome in outcomes:
        prefix = outcome.engine.lower()
        summary.set_property(
            f"{prefix}_profiles",
            len(outcome.profiles),
            f"{outcome.engine} profiles",
        )
        summary.set_property(
            f"{prefix}_scope",
            outcome.scope,
            f"{outcome.engine} scope",
        )
        if outcome.error:
            summary.set_property(
                f"{prefix}_error",
                outcome.error,
                f"{outcome.engine} error",
            )

    raw_results = combined_raw_result(outcomes)
    if raw_results:
        summary.set_property(
            "raw_results",
            _short_text(raw_results, 60_000),
            "Raw Sherlock/Maigret output",
        )

    entities: List[AliasSearchEntity] = [summary]
    for profile in profiles:
        url_entity = URL(
            profile.url,
            note=_short_text(format_profile_note(profile), 4_000),
            link_label=profile.site,
        )
        url_entity.set_property("title", profile.site, "Title")
        url_entity.set_property("short-title", profile.site, "Short title")
        for key, value in _profile_properties(profile, alias).items():
            url_entity.set_property(key, value, key.replace("_", " ").title())
        entities.append(url_entity)

    return entities


@register_transform(
    display_name="Search alias (Sherlock + Maigret) [OSINT]",
    description=(
        "Ищет профили по нику через Sherlock и Maigret, объединяет результаты "
        "и возвращает URL профилей. Движки можно включать/выключать через "
        "ALIAS_ENGINES (например, ALIAS_ENGINES=sherlock)."
    ),
    transform_set="OSINT Toolkit",
)
async def alias_search(
    entity: Alias,
    context: MaltegoContext,
) -> List[AliasSearchEntity]:
    alias = normalize_alias(entity.value)
    outcomes = await run_alias_search(alias)
    return _build_alias_entities(alias, outcomes)
