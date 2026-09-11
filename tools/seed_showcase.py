#!/usr/bin/env python3
"""Seed a coherent, development-only Smart Match showcase dataset."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from seed_pilot import acquire_seed_lock, require_development_fixture_settings
from smartmatch_api.config import Settings
from smartmatch_domain.events import normalize_title
from smartmatch_persistence import schema
from smartmatch_persistence.engine import create_db_engine

NS = uuid.UUID("e5348172-b20d-4db0-9fa7-b9175855a14d")


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


def add(connection: sa.Connection, table: sa.Table, **values: object) -> None:
    connection.execute(insert(table).values(**values).on_conflict_do_nothing())


def account_for_role(connection: sa.Connection, tenant_id: uuid.UUID, role: str) -> uuid.UUID:
    preferred = f"pilot-login-{role}"
    row = connection.execute(
        sa.select(schema.user_account.c.id)
        .join(
            schema.membership,
            sa.and_(
                schema.membership.c.tenant_id == schema.user_account.c.tenant_id,
                schema.membership.c.user_id == schema.user_account.c.id,
            ),
        )
        .where(
            schema.user_account.c.tenant_id == tenant_id,
            schema.membership.c.role == role,
        )
        .order_by((schema.user_account.c.external_subject == preferred).desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"no {role} pilot principal exists; seed principals/logins first")
    return row


def seed(anchor: date) -> None:
    settings = require_development_fixture_settings(Settings())
    engine = create_db_engine(settings.database_url)
    with engine.begin() as connection:
        acquire_seed_lock(connection)
        tenant = connection.execute(
            sa.select(schema.tenant.c.id).where(schema.tenant.c.slug == "pilot")
        ).scalar_one()
        unit = connection.execute(
            sa.select(schema.org_unit.c.id).where(
                schema.org_unit.c.tenant_id == tenant,
                sa.cast(schema.org_unit.c.path, sa.Text) == "pilot",
            )
        ).scalar_one()
        connector = account_for_role(connection, tenant, "admin")
        host = account_for_role(connection, tenant, "coordinator")
        student = account_for_role(connection, tenant, "student")
        speaker_account = account_for_role(connection, tenant, "volunteer")

        speaker_specs = (
            (speaker_account, "Jordan Lee", "Director of Analytics", "Bronco Insights", ["data analytics", "career pathways"], "Pomona", ["Pomona", "Inland Empire"]),
            (uid("speaker-2"), "Maya Patel", "Product Manager", "Citrus Labs", ["product management", "entrepreneurship"], "Los Angeles", ["Los Angeles", "Pomona"]),
            (uid("speaker-3"), "Carlos Ramirez", "Finance Manager", "Foothill Credit Union", ["finance", "financial literacy"], "Inland Empire", ["Inland Empire", "Pomona"]),
            (uid("speaker-4"), "Avery Chen", "People Operations Lead", "Evergreen Works", ["human resources", "leadership"], "Orange County", ["Orange County", "Los Angeles"]),
            (uid("speaker-5"), "Nia Thompson", "Founder", "Bridge & Bloom", ["entrepreneurship", "marketing"], "Pomona", ["Pomona", "Los Angeles"]),
            (uid("speaker-6"), "Sam Kim", "Supply Chain Analyst", "Pacific Logistics", ["operations", "supply chain"], "Inland Empire", ["Inland Empire", "Pomona"]),
        )
        for index, (speaker_id, name, title, company, topics, home, regions) in enumerate(speaker_specs):
            add(
                connection,
                schema.speaker,
                id=speaker_id,
                tenant_id=tenant,
                owning_unit_id=unit,
                created_by=connector,
                account_id=speaker_account if index == 0 else None,
                name=name,
                title=title,
                company=company,
                board_role=None,
                expertise_topics=topics,
                home_region=home,
                service_regions=regions,
                contact_email=f"showcase-speaker-{index + 1}@example.invalid",
                contact_phone=None,
                available=True,
                active=True,
                version=1,
            )
        add(connection, schema.speaker_roster, tenant_id=tenant, owning_unit_id=unit, version=1, published_by=connector, published_at=datetime.now(timezone.utc))
        for speaker_id, name, title, company, topics, home, regions in speaker_specs:
            add(connection, schema.speaker_roster_entry, tenant_id=tenant, owning_unit_id=unit, speaker_id=speaker_id, roster_version=1, name=name, title=title, company=company, board_role=None, expertise_topics=topics, home_region=home, service_regions=regions)

        exact_start = datetime.combine(anchor + timedelta(days=14), time(18), tzinfo=timezone(timedelta(hours=-7)))
        past_start = datetime.combine(anchor - timedelta(days=4), time(17), tzinfo=timezone(timedelta(hours=-7)))
        event_specs = (
            ("analytics-night", "Analytics Career Night", "published", exact_start, exact_start + timedelta(hours=2), None, "Collins College of Hospitality Management", 2, ["data analytics", "career pathways"], "Pomona"),
            ("founder-workshop", "Student Founder Workshop", "published", None, None, anchor + timedelta(days=28), "Innovation Orchard", 1, ["entrepreneurship", "marketing"], "Pomona"),
            ("career-panel", "Career Paths in Business", "published", past_start, past_start + timedelta(hours=2), None, "Bronco Student Center", 1, ["career pathways", "leadership"], "Pomona"),
            ("spring-roundtable", "Spring Industry Roundtable", "draft", None, None, None, None, None, [], None),
            ("cancelled-roundtable", "Supply Chain Roundtable", "cancelled", exact_start + timedelta(days=7), exact_start + timedelta(days=7, hours=2), None, "College of Business Administration", 1, ["operations", "supply chain"], "Pomona"),
        )
        for key, title, status_value, starts, ends, on_date, location, needed, topics, region in event_specs:
            event_id = uid(f"event-{key}")
            catalog_id = uid(f"catalog-{key}") if status_value == "published" else None
            precision = "exact" if starts else "date_only" if on_date else "unresolved"
            if catalog_id:
                resolved = starts.astimezone(timezone(timedelta(hours=-7))).date() if starts else on_date
                add(connection, schema.event, id=catalog_id, tenant_id=tenant, host_org_unit_id=unit, title=title, normalized_title=normalize_title(title), description="A synthetic showcase event created for portal previews.", starts_at=starts, ends_at=ends, on_date=on_date, time_zone="America/Los_Angeles", time_precision=precision, resolved_date=resolved, publication_status="published", review_status="approved", quarantined_tag_count=0, origin="coordinator_entry", source_url=None, fetched_at=None, extractor_version=None, is_virtual=False, location_city="Pomona", location_postal_code="91768", filed_by_user_id=host)
            add(connection, schema.managed_event, id=event_id, tenant_id=tenant, owning_unit_id=unit, created_by=host, idempotency_key=f"showcase-{key}", request_fingerprint=f"showcase-{key}-v1", title=title, normalized_title=normalize_title(title), description="A synthetic showcase event created for portal previews." if status_value != "draft" else None, category="guest lecturer event" if status_value != "draft" else None, time_precision=precision, starts_at=starts, ends_at=ends, on_date=on_date, time_zone="America/Los_Angeles" if precision != "unresolved" else None, location=location, capacity=80 if status_value != "draft" else None, volunteer_openings=needed, volunteer_needs="Share practical experience and leave time for student questions." if status_value != "draft" else None, audience="Cal Poly Pomona students" if status_value != "draft" else None, contact_name="Showcase Event Host" if status_value != "draft" else None, contact_email="showcase-host@example.invalid" if status_value != "draft" else None, speaker_topics=topics, region=region, status=status_value, source_kind="synthetic", version=1, cancelled_at=datetime.now(timezone.utc) if status_value == "cancelled" else None, cancelled_by=host if status_value == "cancelled" else None, cancellation_reason="Synthetic cancelled event for the showcase." if status_value == "cancelled" else None, catalog_event_id=catalog_id)

        analytics = uid("event-analytics-night")
        past = uid("event-career-panel")
        run_id = uid("match-run-analytics")
        add(connection, schema.speaker_match_run, id=run_id, tenant_id=tenant, owning_unit_id=unit, event_id=analytics, requested_by=host, idempotency_key="showcase-match", request_fingerprint="showcase-match-v1", roster_version=1)
        for position, spec in enumerate(speaker_specs[:3], start=1):
            speaker_id, name, title, company, topics, home, regions = spec
            add(connection, schema.speaker_match_result, tenant_id=tenant, owning_unit_id=unit, match_run_id=run_id, speaker_id=speaker_id, position=position, speaker_name=name, speaker_title=title, speaker_company=company, speaker_board_role=None, expertise_topics=topics, home_region=home, service_regions=regions, topic_score=Decimal("1.0") if position == 1 else Decimal("0.5"), proximity_score=Decimal("1.0"), total_score=Decimal("1.0") if position == 1 else Decimal("0.65"), explanations=["Experience overlaps with the event topics", "Serves the event region"])
        add(connection, schema.speaker_shortlist_submission, id=uid("shortlist-analytics"), tenant_id=tenant, owning_unit_id=unit, match_run_id=run_id, idempotency_key="showcase-shortlist", request_fingerprint="showcase-shortlist-v1")

        invitation_specs = (
            ("analytics-jordan", analytics, speaker_account, "handed_off"),
            ("analytics-maya", analytics, uid("speaker-2"), "awaiting_response"),
            ("analytics-avery", analytics, uid("speaker-4"), "not_emailed_yet"),
            ("founder-nia", uid("event-founder-workshop"), uid("speaker-5"), "ready_for_handoff"),
            ("founder-maya", uid("event-founder-workshop"), uid("speaker-2"), "confirmed"),
            ("founder-carlos", uid("event-founder-workshop"), uid("speaker-3"), "awaiting_final_confirmation"),
            ("past-jordan", past, speaker_account, "attended"),
            ("past-carlos", past, uid("speaker-3"), "did_not_attend"),
            ("past-avery", past, uid("speaker-4"), "withdrawn"),
            ("cancelled-sam", uid("event-cancelled-roundtable"), uid("speaker-6"), "event_cancelled"),
        )
        for key, event_id, speaker_id, state in invitation_specs:
            record_id = uid(f"speaker-event-{key}")
            add(connection, schema.speaker_event, id=record_id, tenant_id=tenant, owning_unit_id=unit, event_id=event_id, speaker_id=speaker_id, assigned_host_id=host, status=state, version=1)
            add(connection, schema.speaker_event_history, id=uid(f"history-{key}"), tenant_id=tenant, owning_unit_id=unit, speaker_event_id=record_id, from_status=None, to_status=state, action_kind="showcase_seed", actor_id=connector if state in {"awaiting_response", "ready_for_handoff", "handed_off"} else host, note="Synthetic status history for the showcase.", correction_reason=None, idempotency_key=f"showcase-history-{key}")
            add(connection, schema.speaker_event_note, id=uid(f"note-{key}"), tenant_id=tenant, owning_unit_id=unit, speaker_event_id=record_id, actor_id=connector, body="Synthetic coordination note for the panel preview.")

        catalog_upcoming = uid("catalog-analytics-night")
        catalog_past = uid("catalog-career-panel")
        add(connection, schema.event_registration, id=uid("registration-student-analytics"), tenant_id=tenant, owning_unit_id=unit, event_id=catalog_upcoming, subject_id=student, status="registered")
        extra_students = []
        for index in range(2):
            account = uid(f"feedback-student-{index}")
            add(connection, schema.user_account, id=account, tenant_id=tenant, external_subject=f"showcase-feedback-student-{index}", email=f"showcase-feedback-student-{index}@example.invalid", suspended=False, version=1)
            extra_students.append(account)
        for index, student_id in enumerate([student, *extra_students]):
            attendance_id = uid(f"attendance-{index}")
            add(connection, schema.attendance_record, id=attendance_id, tenant_id=tenant, owning_unit_id=unit, subject_id=student_id, event_id=catalog_past, method="coordinator_entry")
        add(connection, schema.speaker_profile, tenant_id=tenant, professional_id=speaker_account, owning_unit_id=unit, full_name="Jordan Lee", company="Bronco Insights", title="Director of Analytics", primary_industry_code="54", industry_taxonomy_version="cba-naics-2026-09-04", primary_role_code="information_systems_analytics", role_taxonomy_version="cba-roles-2026-09-04", topic_text="Data analytics and career pathways", prior_talk=None, location_city="Pomona", location_postal_code="91768", industry_classification_source="human", industry_classified_by_user_id=connector, industry_classified_at=datetime.now(timezone.utc), role_classification_source="human", role_classified_by_user_id=connector, role_classified_at=datetime.now(timezone.utc))
        for index, student_id in enumerate([student, *extra_students]):
            add(connection, schema.student_speaker_feedback, id=uid(f"feedback-{index}"), tenant_id=tenant, owning_unit_id=unit, event_id=catalog_past, student_id=student_id, speaker_professional_id=speaker_account, status="submitted", rating=5 - index, comment="Helpful examples and clear advice." if index == 0 else None)

        qr_id = uid("feedback-qr-analytics")
        add(connection, schema.event_feedback_qr, id=qr_id, tenant_id=tenant, owning_unit_id=unit, event_id=analytics, public_token="showcase-feedback-analytics-2026", destination_url="https://example.com/showcase-feedback", created_by=connector)
        for index in range(3):
            add(connection, schema.event_feedback_qr_open, id=uid(f"qr-open-{index}"), tenant_id=tenant, qr_id=qr_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    try:
        seed(args.anchor_date)
    except Exception as exc:
        print(f"seed-showcase: {exc}", file=sys.stderr)
        return 2
    print("seed-showcase: synthetic four-portal dataset is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
