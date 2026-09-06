"""Every CHECK constraint is exercised by the write it exists to refuse.

`test_schema_matches_migration.py::test_check_constraints_match` compares CHECK
constraints between the schema mirror and the database **by name only**.
PostgreSQL rewrites the expression on the way in, so the definitions are not
comparable as text, and reflection does not report the columns. That test
therefore catches a constraint added, dropped, or renamed on one side — and
nothing about what the constraint actually says.

The gap that leaves is concrete: a constraint re-added under the same name with
an **inverted** expression keeps its name and stays green. This file closes it,
for all eight, by attempting the forbidden write and asserting the database
refuses it — and, just as importantly, by attempting the *permitted* write and
asserting it succeeds. The second half is what catches inversion: an inverted
`ck_budget_non_negative` reading `spent < 0` would still refuse `spent = -1` for
the wrong reason, and would refuse `spent = 0`, which is where it fails.

**The `NOT VALID` half of the gap needs a different instrument, and this is the
correction to the record.** `docs/plans/remaining-foundation-r1-work.md` (F10)
and the docstring of `test_check_constraint_names_match` both say a constraint
re-added as `NOT VALID` "stays green". That is true of the name-only test and it
is *equally true of a write test*: verified against PostgreSQL 16.15, a
`NOT VALID` CHECK rejects new inserts and updates exactly as a validated one
does. What `NOT VALID` skips is the initial scan of rows already present — so
the constraint is enforced from that point on, and has simply never been checked
against the existing data. No attempted write can distinguish the two. So
`test_every_check_constraint_is_validated` below reads
`pg_constraint.convalidated` directly, which is the only thing that can. Both
documents are corrected in the same commit as this file.

**The expression itself is pinned too**, for the class of weakening no write can
reach: a vocabulary quietly widened, or a threshold moved. See
`CHECK_CONSTRAINT_DEFINITIONS`.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Every CHECK constraint in the schema, keyed by ``(table, name)`` and mapped to
#: the exact expression PostgreSQL renders for it.
#:
#: **Keyed by table as well as name, because a name is not an identity.**
#: PostgreSQL permits the same constraint name on two different tables —
#: verified by adding a second ``ck_outbox_status`` to ``job``, which both
#: meta-tests below missed entirely while they compared bare names. A ninth
#: constraint reusing an existing name was invisible.
#:
#: **The expression is pinned, and that is what closes the weakening class.**
#: Attempted writes prove a constraint refuses the values a test happens to try.
#: They cannot prove it refuses the ones it does not: adding ``'audit'`` to
#: ``ck_resource_grant_effect``, or ``'cancelled'`` to ``ck_outbox_status``, or
#: relaxing either numeric clause to ``>= -0.5``, passes every behavioural test
#: in this file. Comparing the rendered definition catches all of them at once.
#:
#: The rendering is PostgreSQL's, not ours — ``status IN (...)`` comes back as
#: ``status = ANY (ARRAY[...])``. That makes this a poor tool for comparing the
#: schema mirror against the database, which is why
#: ``test_schema_matches_migration.py`` deliberately does not do it. Here both
#: sides are the *database*, so the rendering is stable and the comparison is
#: exact. It is pinned against PostgreSQL 16; a major-version upgrade that
#: changed the normalisation would fail this test, and reviewing that diff on
#: purpose is the intended behaviour rather than a cost.
CHECK_CONSTRAINT_DEFINITIONS = {
    # --- Outreach (migration 0021) -------------------------------------
    #
    # Every one of these is a claim about a real person that the application
    # layer also enforces, which is why the expressions are pinned here as
    # well as attempted in `test_outreach_persistence.py`: a vocabulary that
    # quietly widened would pass every behavioural test, because the values
    # it newly admits are exactly the ones nothing tries to write.
    ("contact_channel", "ck_contact_channel_address_present"): (
        "CHECK (((length(btrim(address)) > 0) AND (POSITION(('@'::text) IN (address)) > 1)))"
    ),
    ("contact_channel", "ck_contact_channel_consent_dated"): (
        "CHECK (((consent_source IS NULL) = (consent_recorded_at IS NULL)))"
    ),
    ("contact_channel", "ck_contact_channel_consent_source"): (
        "CHECK (((consent_source IS NULL) OR (consent_source = ANY "
        "(ARRAY['self_service'::text, 'authenticated'::text, 'in_person'::text, "
        "'institutional_relationship'::text, 'scraped'::text, 'purchased'::text, "
        "'inferred'::text]))))"
    ),
    ("contact_channel", "ck_contact_channel_kind"): ("CHECK ((channel_kind = 'email'::text))"),
    ("contact_channel", "ck_contact_channel_sendable_consent"): (
        "CHECK (((contact_state <> 'active_candidate'::text) OR ((consent_source IS NOT NULL) "
        "AND (consent_source = ANY (ARRAY['self_service'::text, 'authenticated'::text, "
        "'in_person'::text, 'institutional_relationship'::text])))))"
    ),
    ("contact_channel", "ck_contact_channel_state"): (
        "CHECK ((contact_state = ANY (ARRAY['discovered'::text, 'corroborated'::text, "
        "'reviewed'::text, 'relationship_recorded'::text, 'rejected'::text, "
        "'consented'::text, 'active_candidate'::text, 'stale'::text])))"
    ),
    # --- The consent audit trail (migration 0022) ----------------------
    ("contact_channel_transition", "ck_contact_channel_transition_consent_source"): (
        "CHECK (((consent_source IS NULL) OR (consent_source = ANY "
        "(ARRAY['self_service'::text, 'authenticated'::text, 'in_person'::text, "
        "'institutional_relationship'::text, "
        "'scraped'::text, 'purchased'::text, 'inferred'::text]))))"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_consented_source"): (
        "CHECK (((to_state <> ALL (ARRAY['consented'::text, 'active_candidate'::text])) "
        "OR ((consent_source IS NOT NULL) AND (consent_source = ANY "
        "(ARRAY['self_service'::text, 'authenticated'::text, 'in_person'::text, "
        "'institutional_relationship'::text])))))"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_from_state"): (
        "CHECK (((from_state IS NULL) OR (from_state = ANY "
        "(ARRAY['discovered'::text, 'corroborated'::text, "
        "'reviewed'::text, 'relationship_recorded'::text, 'rejected'::text, "
        "'consented'::text, 'active_candidate'::text, 'stale'::text]))))"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_moves"): (
        "CHECK (((from_state IS NULL) OR (from_state <> to_state)))"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_text_present"): (
        "CHECK ((((reason IS NULL) OR (length(btrim(reason)) > 0)) AND "
        "((consent_evidence IS NULL) OR (length(btrim(consent_evidence)) > 0))))"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_to_state"): (
        "CHECK ((to_state = ANY (ARRAY['discovered'::text, 'corroborated'::text, "
        "'reviewed'::text, 'relationship_recorded'::text, 'rejected'::text, "
        "'consented'::text, 'active_candidate'::text, 'stale'::text])))"
    ),
    ("delivery_event", "ck_delivery_event_detail_object"): (
        "CHECK (((detail IS NULL) OR (jsonb_typeof(detail) = 'object'::text)))"
    ),
    ("delivery_event", "ck_delivery_event_type"): (
        "CHECK ((event_type = ANY (ARRAY['queued'::text, 'blocked'::text, 'accepted'::text, "
        "'delivered'::text, 'bounced'::text, 'complained'::text, 'unsubscribed'::text, "
        "'failed'::text])))"
    ),
    ("outreach_draft", "ck_outreach_draft_approval_dated"): (
        "CHECK (((approved_by IS NULL) = (approved_at IS NULL)))"
    ),
    ("outreach_draft", "ck_outreach_draft_approved_has_approver"): (
        "CHECK (((status <> 'approved'::text) OR (approved_by IS NOT NULL)))"
    ),
    ("outreach_draft", "ck_outreach_draft_content_status"): (
        "CHECK ((content_status = ANY (ARRAY['synthetic'::text, 'reviewed'::text])))"
    ),
    ("outreach_draft", "ck_outreach_draft_status"): (
        "CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text, 'superseded'::text])))"
    ),
    ("outreach_draft", "ck_outreach_draft_supersession"): (
        "CHECK (((superseded_by_draft_id IS NULL) OR ((status = 'superseded'::text) AND "
        "(superseded_by_draft_id <> id))))"
    ),
    ("outreach_draft", "ck_outreach_draft_text_present"): (
        "CHECK (((length(btrim(template_id)) > 0) AND (length(btrim(subject)) > 0) AND "
        "(length(btrim(body)) > 0)))"
    ),
    ("outreach_draft", "ck_outreach_draft_version"): ("CHECK ((version >= 1))"),
    ("outreach_send", "ck_outreach_send_accepted_has_provider"): (
        "CHECK (((disposition <> 'accepted'::text) OR ((provider IS NOT NULL) AND "
        "(provider_message_id IS NOT NULL))))"
    ),
    ("outreach_send", "ck_outreach_send_concluded"): (
        "CHECK (((disposition IS NULL) = (concluded_at IS NULL)))"
    ),
    ("outreach_send", "ck_outreach_send_disposition"): (
        "CHECK (((disposition IS NULL) OR (disposition = ANY (ARRAY['accepted'::text, "
        "'blocked'::text, 'failed'::text]))))"
    ),
    ("outreach_send", "ck_outreach_send_failure_reason"): (
        "CHECK (((disposition IS NULL) OR ((disposition = ANY (ARRAY['blocked'::text, "
        "'failed'::text])) = (failure_reason IS NOT NULL))))"
    ),
    ("outreach_send", "ck_outreach_send_fields_present"): (
        "CHECK (((length(btrim(idempotency_key)) > 0) AND (length(btrim(recipient_address)) > "
        "0) AND (length(btrim(from_address)) > 0) AND (length(btrim(unsubscribe_token_hash)) "
        "> 0)))"
    ),
    ("outreach_send", "ck_outreach_send_message_id_means_accepted"): (
        "CHECK (((provider_message_id IS NULL) OR (disposition = 'accepted'::text)))"
    ),
    ("suppression_record", "ck_suppression_record_address_present"): (
        "CHECK ((length(btrim(address)) > 0))"
    ),
    ("suppression_record", "ck_suppression_record_source"): (
        "CHECK ((source = ANY (ARRAY['unsubscribe_link'::text, 'one_click'::text, "
        "'coordinator'::text, 'bounce'::text, 'complaint'::text])))"
    ),
    ("attendance_record", "ck_attendance_record_method"): (
        "CHECK ((method = ANY (ARRAY['qr_scan'::text, 'coordinator_entry'::text, 'import'::text])))"
    ),
    ("job", "ck_job_status"): (
        "CHECK ((status = ANY (ARRAY['queued'::text, 'dispatched'::text, "
        "'running'::text, 'succeeded'::text, 'partial'::text, "
        "'failed_provider'::text, 'failed_budget'::text, 'failed_policy'::text, "
        "'cancelled'::text, 'timed_out'::text, 'redrive_pending'::text, "
        "'abandoned'::text])))"
    ),
    ("membership", "ck_membership_valid_window"): (
        "CHECK (((valid_until IS NULL) OR (valid_from IS NULL) OR (valid_until > valid_from)))"
    ),
    ("outbox_record", "ck_outbox_status"): (
        "CHECK ((status = ANY (ARRAY['pending'::text, 'leased'::text, "
        "'dispatched'::text, 'failed'::text])))"
    ),
    ("point_ledger_entry", "ck_point_ledger_entry_amount_nonzero"): "CHECK ((amount <> 0))",
    ("pipeline_record", "ck_pipeline_record_attendance_evidence"): (
        "CHECK (((attended_at IS NULL) = (attended_attendance_id IS NULL)))"
    ),
    ("pipeline_record", "ck_pipeline_record_matched_provenance"): (
        "CHECK ((matched_provenance = ANY (ARRAY['synthetic / coordinator-accepted'::text, "
        "'match-engine'::text])))"
    ),
    ("pipeline_record", "ck_pipeline_record_stage_order"): (
        "CHECK ((((contacted_at IS NULL) OR (contacted_at >= matched_at)) AND "
        "((confirmed_at IS NULL) OR (confirmed_at >= contacted_at)) AND "
        "((attended_at IS NULL) OR (attended_at >= confirmed_at)) AND "
        "((member_inquiry_at IS NULL) OR (member_inquiry_at >= attended_at))))"
    ),
    ("pipeline_record", "ck_pipeline_record_stage_prefix"): (
        "CHECK ((((contacted_at IS NULL) OR (matched_at IS NOT NULL)) AND "
        "((confirmed_at IS NULL) OR (contacted_at IS NOT NULL)) AND "
        "((attended_at IS NULL) OR (confirmed_at IS NOT NULL)) AND "
        "((member_inquiry_at IS NULL) OR (attended_at IS NOT NULL))))"
    ),
    ("rate_limit_counter", "ck_rate_limit_count_non_negative"): "CHECK ((count >= 0))",
    ("redrive_record", "ck_redrive_authorship_complete"): (
        "CHECK (((redriven_at IS NULL) = (redriven_by IS NULL)))"
    ),
    ("resource_grant", "ck_resource_grant_effect"): (
        "CHECK ((effect = ANY (ARRAY['allow'::text, 'deny'::text])))"
    ),
    ("review_item", "ck_review_item_status"): (
        "CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'rejected'::text])))"
    ),
    ("review_item", "ck_review_item_decision_evidence"): (
        "CHECK ((((status = 'pending'::text) = (decided_at IS NULL)) AND "
        "((decided_at IS NULL) = (decided_by IS NULL))))"
    ),
    ("reward_item", "ck_reward_item_points_cost_positive"): "CHECK ((points_cost > 0))",
    ("reward_item", "ck_reward_item_fulfilment_cost_non_negative"): (
        "CHECK ((fulfilment_cost >= (0)::numeric))"
    ),
    ("tenant_budget", "ck_budget_ceiling_non_negative"): "CHECK ((ceiling >= (0)::numeric))",
    ("tenant_budget", "ck_budget_non_negative"): (
        "CHECK (((spent >= (0)::numeric) AND (reserved >= (0)::numeric)))"
    ),
    ("spend_ceiling_bucket", "ck_spend_ceiling_bucket_type"): (
        "CHECK ((bucket_type = ANY (ARRAY['job'::text, 'tenant_day'::text, 'tenant_month'::text])))"
    ),
    ("spend_ceiling_bucket", "ck_spend_ceiling_bucket_non_negative"): (
        "CHECK (((reserved >= (0)::numeric) AND (spent >= (0)::numeric)))"
    ),
    ("spend_ceiling_bucket", "ck_spend_ceiling_bucket_ceiling_non_negative"): (
        "CHECK ((ceiling >= (0)::numeric))"
    ),
    ("spend_reservation", "ck_spend_reservation_estimate_non_negative"): (
        "CHECK ((estimate >= (0)::numeric))"
    ),
    ("spend_reservation", "ck_spend_reservation_actual_non_negative"): (
        "CHECK (((actual_cost IS NULL) OR (actual_cost >= (0)::numeric)))"
    ),
    ("spend_reservation", "ck_spend_reservation_state"): (
        "CHECK ((state = ANY (ARRAY['reserved'::text, 'reconciled'::text, "
        "'expired_spent'::text, 'released'::text])))"
    ),
    ("spend_reservation", "ck_spend_reservation_lease_token_iff_reserved"): (
        "CHECK (((state = 'reserved'::text) = (lease_token IS NOT NULL)))"
    ),
    # Migration 0017 — the P6 event model (cards S3-S5f).
    ("event", "ck_event_time_precision"): (
        "CHECK ((time_precision = ANY (ARRAY['exact'::text, 'date_only'::text, "
        "'unresolved'::text])))"
    ),
    ("event", "ck_event_temporal_shape"): (
        "CHECK ((((time_precision = 'exact'::text) AND (starts_at IS NOT NULL) AND "
        "(on_date IS NULL) AND (time_zone IS NOT NULL)) OR ((time_precision = "
        "'date_only'::text) AND (starts_at IS NULL) AND (on_date IS NOT NULL) AND "
        "(time_zone IS NOT NULL)) OR ((time_precision = 'unresolved'::text) AND "
        "(starts_at IS NULL) AND (on_date IS NULL) AND (time_zone IS NULL))))"
    ),
    ("event", "ck_event_identity_iff_resolved"): (
        "CHECK (((time_precision = 'unresolved'::text) = (resolved_date IS NULL)))"
    ),
    ("event", "ck_event_publication_status"): (
        "CHECK ((publication_status = ANY (ARRAY['unpublished'::text, 'published'::text])))"
    ),
    ("event", "ck_event_review_status"): (
        "CHECK ((review_status = ANY (ARRAY['pending'::text, 'approved'::text, 'rejected'::text])))"
    ),
    ("event", "ck_event_quarantined_tag_count_non_negative"): (
        "CHECK ((quarantined_tag_count >= 0))"
    ),
    ("event", "ck_event_publishable"): (
        "CHECK (((publication_status = 'unpublished'::text) OR ((time_precision <> "
        "'unresolved'::text) AND (quarantined_tag_count = 0))))"
    ),
    ("event", "ck_event_origin"): (
        "CHECK ((origin = ANY (ARRAY['coordinator_entry'::text, 'extraction'::text])))"
    ),
    ("event", "ck_event_provenance_evidence"): (
        "CHECK ((((origin = 'extraction'::text) = (source_url IS NOT NULL)) AND "
        "((source_url IS NULL) = (fetched_at IS NULL)) AND ((fetched_at IS NULL) = "
        "(extractor_version IS NULL))))"
    ),
    # Migration 0022 — the end instant an .ics document needs and cannot invent.
    # The `time_precision = 'exact'` clause is load-bearing rather than
    # decorative: without it a row could hold an end and no start, because
    # `ends_at > NULL` is unknown rather than false and an unknown CHECK passes.
    # The `>` is pinned for the same reason the numeric thresholds above are —
    # relaxing it to `>=` admits the zero-length event an adapter writes when it
    # copies `starts_at` across, which no behavioural test that only tries a
    # reversed pair would notice.
    ("event", "ck_event_end_after_start"): (
        "CHECK (((ends_at IS NULL) OR ((time_precision = 'exact'::text) AND "
        "(ends_at > starts_at))))"
    ),
    ("event_tag", "ck_event_tag_resolution"): (
        "CHECK ((resolution = ANY (ARRAY['mapped'::text, 'quarantined'::text])))"
    ),
    ("event_tag", "ck_event_tag_resolution_shape"): (
        "CHECK ((((resolution = 'mapped'::text) = (term IS NOT NULL)) AND "
        "((resolution = 'quarantined'::text) = (raw_value IS NOT NULL))))"
    ),
    ("discovery_review_item", "ck_discovery_review_item_kind"): (
        "CHECK ((kind = ANY (ARRAY['unmapped_tag'::text, 'unresolved_time'::text, "
        "'first_seen_event'::text])))"
    ),
    ("discovery_review_item", "ck_discovery_review_item_status"): (
        "CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'rejected'::text])))"
    ),
    ("discovery_review_item", "ck_discovery_review_item_decision_evidence"): (
        "CHECK ((((status = 'pending'::text) = (decided_at IS NULL)) AND "
        "((decided_at IS NULL) = (decided_by IS NULL))))"
    ),
    ("discovery_review_item", "ck_discovery_review_item_tag_evidence"): (
        "CHECK ((((kind = 'unmapped_tag'::text) = (raw_value IS NOT NULL)) AND "
        "((raw_value IS NULL) = (vocabulary_version IS NULL))))"
    ),
    # Migration 0018, the immutable match_run snapshot. The table's other
    # guarantee — that no UPDATE succeeds at all — is a trigger rather than a
    # CHECK, because a CHECK sees only the new row and cannot know one existed
    # before. It is exercised in test_match_run_snapshot.py and has no entry
    # here, because this file is about CHECK constraints.
    ("match_run", "ck_match_run_supersedes_is_not_self"): (
        "CHECK (((supersedes_run_id IS NULL) OR (supersedes_run_id <> id)))"
    ),
    ("match_run", "ck_match_run_pins_present"): (
        "CHECK (((length(btrim(event_need_id)) > 0) AND (length(btrim(inputs_hash)) > 0) "
        "AND (length(btrim(registry_version)) > 0) AND (length(btrim(registry_hash)) > 0) "
        "AND (length(btrim(optimizer_model_version)) > 0) AND (length(btrim(solver_name)) "
        "> 0) AND (length(btrim(solver_version)) > 0) AND "
        "(length(btrim(route_estimate_version)) > 0)))"
    ),
    ("match_run", "ck_match_run_weights_object"): (
        "CHECK (((jsonb_typeof(weights) = 'object'::text) AND (weights <> '{}'::jsonb)))"
    ),
    ("match_run", "ck_match_run_portfolio_size"): "CHECK ((portfolio_size >= 1))",
    ("match_run", "ck_match_run_random_seed"): "CHECK ((random_seed >= 0))",
    ("match_run", "ck_match_run_route_estimate_source"): (
        "CHECK ((route_estimate_source = ANY (ARRAY['straight_line'::text, 'route_matrix'::text])))"
    ),
    ("match_run", "ck_match_run_portfolio_status"): (
        "CHECK ((portfolio_status = ANY (ARRAY['optimal'::text, 'feasible'::text, "
        "'infeasible'::text, 'unknown'::text])))"
    ),
    # Migration 0019, the durable redemption and the representable debit. The
    # ledger's other new guarantee — that no UPDATE succeeds — is a trigger, as
    # match_run's is, and so has no entry here; the two partial unique indexes
    # are indexes and likewise not CHECK constraints. All three are exercised in
    # test_redemption_durability.py.
    #
    # ck_point_ledger_entry_kind is the one that earns the most from being
    # pinned as text. It is what keeps source_attendance_id's new nullability
    # from being a hole, and the ways to weaken it — dropping one conjunct from
    # a disjunct, admitting a fourth kind, relaxing a sign — all keep the name
    # and most of the behaviour.
    ("point_ledger_entry", "ck_point_ledger_entry_kind"): (
        "CHECK ((((kind = 'attendance_credit'::text) AND (source_attendance_id IS NOT NULL) "
        "AND (source_redemption_id IS NULL) AND (amount > 0)) OR ((kind = 'reversal'::text) "
        "AND (source_attendance_id IS NOT NULL) AND (source_redemption_id IS NULL) AND "
        "(amount < 0)) OR ((kind = 'redemption_debit'::text) AND (source_attendance_id IS "
        "NULL) AND (source_redemption_id IS NOT NULL) AND (amount < 0))))"
    ),
    ("redemption", "ck_redemption_state"): (
        "CHECK ((state = ANY (ARRAY['requested'::text, 'approved'::text, 'fulfilled'::text, "
        "'denied'::text, 'expired'::text])))"
    ),
    ("redemption", "ck_redemption_approval_evidence"): (
        "CHECK ((((approved_at IS NULL) = (approved_by IS NULL)) AND ((state <> "
        "'fulfilled'::text) OR (approved_at IS NOT NULL)) AND ((state <> 'requested'::text) "
        "OR (approved_at IS NULL))))"
    ),
    ("redemption", "ck_redemption_closure_evidence"): (
        "CHECK ((((state = ANY (ARRAY['fulfilled'::text, 'denied'::text, 'expired'::text])) "
        "= (closed_at IS NOT NULL)) AND ((closed_by IS NULL) OR (closed_at IS NOT NULL))))"
    ),
    ("redemption", "ck_redemption_snapshot_present"): (
        "CHECK (((points_cost_snapshot > 0) AND (length(btrim(item_name_snapshot)) > 0)))"
    ),
    # Migration 0020, pilot login credentials and sessions.
    ("pilot_credential", "ck_pilot_credential_algorithm"): (
        "CHECK ((algorithm = 'pbkdf2_hmac_sha256'::text))"
    ),
    ("pilot_credential", "ck_pilot_credential_material"): (
        "CHECK (((octet_length(salt) >= 16) AND (octet_length(password_hash) = 32) "
        "AND (iterations >= 100000)))"
    ),
    ("pilot_session", "ck_pilot_session_window"): (
        "CHECK (((expires_at > issued_at) AND ((revoked_at IS NULL) OR (revoked_at >= issued_at))))"
    ),
    ("pilot_session", "ck_pilot_session_token_hash"): "CHECK ((octet_length(token_hash) = 32))",
    ("pilot_login_attempt", "ck_pilot_login_attempt_count"): "CHECK ((count >= 0))",
    # --- CBA classification storage (migration 0024) --------------------
    #
    # The two vocabulary constraints below are the only place in the running
    # database where customer §§7-8's closed taxonomies appear, and pinning
    # their rendered text is what this file's "quietly widened vocabulary" case
    # is *for*: a twenty-first sector code added to a CHECK and to nothing else
    # passes every behavioural test, because no attempted write knows to try
    # it. The complementary direction — a code released in
    # `smartmatch_domain` that never reached a migration — is caught in
    # test_cba_classification_schema.py, which parametrizes over the domain's
    # own tuples. Neither test catches what the other does.
    ("event", "ck_event_location_present"): (
        "CHECK ((((location_city IS NULL) OR (length(btrim(location_city)) > 0)) "
        "AND ((location_postal_code IS NULL) "
        "OR (length(btrim(location_postal_code)) > 0))))"
    ),
    ("event", "ck_event_virtual_has_no_location"): (
        "CHECK (((NOT is_virtual) OR ((location_city IS NULL) AND (location_postal_code IS NULL))))"
    ),
    ("speaker_profile", "ck_speaker_profile_industry_code"): (
        "CHECK (((primary_industry_code IS NULL) OR (primary_industry_code = ANY "
        "(ARRAY['11'::text, '21'::text, '22'::text, '23'::text, '31-33'::text, '42'::text, "
        "'44-45'::text, '48-49'::text, '51'::text, '52'::text, '53'::text, '54'::text, "
        "'55'::text, '56'::text, '61'::text, '62'::text, '71'::text, '72'::text, "
        "'81'::text, '92'::text]))))"
    ),
    ("speaker_profile", "ck_speaker_profile_industry_versioned"): (
        "CHECK (((primary_industry_code IS NULL) = (industry_taxonomy_version IS NULL)))"
    ),
    ("speaker_profile", "ck_speaker_profile_role_code"): (
        "CHECK (((primary_role_code IS NULL) OR (primary_role_code = ANY "
        "(ARRAY['accounting'::text, 'finance'::text, 'marketing'::text, "
        "'management_strategy'::text, 'human_resources'::text, "
        "'operations_supply_chain'::text, 'information_systems_analytics'::text, "
        "'international_business'::text, 'entrepreneurship_founder'::text, "
        "'sales_business_development'::text]))))"
    ),
    ("speaker_profile", "ck_speaker_profile_role_versioned"): (
        "CHECK (((primary_role_code IS NULL) = (role_taxonomy_version IS NULL)))"
    ),
    # Widened by migration 0025: `full_name` leads (NOT NULL, so no NULL arm —
    # the clause exists to refuse '   ') and `company`/`title` join the tail.
    ("speaker_profile", "ck_speaker_profile_text_present"): (
        "CHECK (((length(btrim(full_name)) > 0) "
        "AND ((topic_text IS NULL) OR (length(btrim(topic_text)) > 0)) "
        "AND ((prior_talk IS NULL) OR (length(btrim(prior_talk)) > 0)) "
        "AND ((location_city IS NULL) OR (length(btrim(location_city)) > 0)) "
        "AND ((location_postal_code IS NULL) "
        "OR (length(btrim(location_postal_code)) > 0)) "
        "AND ((company IS NULL) OR (length(btrim(company)) > 0)) "
        "AND ((title IS NULL) OR (length(btrim(title)) > 0))))"
    ),
    ("speaker_request_classification", "ck_speaker_request_classification_code"): (
        "CHECK ((((kind = 'industry'::text) AND (code = ANY "
        "(ARRAY['11'::text, '21'::text, '22'::text, '23'::text, '31-33'::text, '42'::text, "
        "'44-45'::text, '48-49'::text, '51'::text, '52'::text, '53'::text, '54'::text, "
        "'55'::text, '56'::text, '61'::text, '62'::text, '71'::text, '72'::text, "
        "'81'::text, '92'::text]))) OR ((kind = 'role'::text) AND (code = ANY "
        "(ARRAY['accounting'::text, 'finance'::text, 'marketing'::text, "
        "'management_strategy'::text, 'human_resources'::text, "
        "'operations_supply_chain'::text, 'information_systems_analytics'::text, "
        "'international_business'::text, 'entrepreneurship_founder'::text, "
        "'sales_business_development'::text])))))"
    ),
    ("speaker_request_classification", "ck_speaker_request_classification_kind"): (
        "CHECK ((kind = ANY (ARRAY['industry'::text, 'role'::text])))"
    ),
    # Migration 0026. Two values, and the *absence* of a third is the part worth
    # pinning: `waitlisted` is not here because no capacity exists anywhere in
    # this schema for it to overflow from (OQ-CBA-029), and a value no writer
    # could produce would be a vocabulary invented by DDL. Recording the
    # definition literally means adding one has to pass through this file.
    ("event_registration", "ck_event_registration_status"): (
        "CHECK ((status = ANY (ARRAY['registered'::text, 'cancelled'::text])))"
    ),
    # Migration 0027. Both tables get the same pair, and the *weakness* of the
    # first is the thing worth pinning: it requires a JSON object and says
    # nothing about which keys or values are acceptable. That is deliberate — a
    # CHECK cannot see the factor registry, and encoding the factor vocabulary
    # here would make DDL one more place a factor key is written down, which is
    # the duplication `CBA-MATCH-WEIGHTS` exists to prevent. The admissible keys,
    # the refusal of negatives and non-finite values, and the zero-total rule all
    # live in `smartmatch_domain.weight_settings`. Recording the definition
    # literally means strengthening it here has to be a deliberate edit.
    ("match_weight_setting", "ck_match_weight_setting_overrides_object"): (
        "CHECK ((jsonb_typeof(overrides) = 'object'::text))"
    ),
    ("match_weight_setting", "ck_match_weight_setting_version"): "CHECK ((version >= 1))",
    ("match_weight_setting_revision", "ck_match_weight_setting_revision_overrides_object"): (
        "CHECK ((jsonb_typeof(overrides) = 'object'::text))"
    ),
    ("match_weight_setting_revision", "ck_match_weight_setting_revision_version"): (
        "CHECK ((version >= 1))"
    ),
}

#: Where each constraint's forbidden and permitted writes are attempted. Six are
#: in this file. The other two are covered, thoroughly, by modules that predate
#: it, and are recorded here rather than duplicated — a reader asking "is
#: ``ck_job_status`` exercised?" gets an answer without grepping.
BEHAVIOURAL_COVERAGE = {
    # --- Outreach (migration 0021) -------------------------------------
    ("contact_channel", "ck_contact_channel_address_present"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_contact_channel_refuses"
    ),
    ("contact_channel", "ck_contact_channel_consent_dated"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_contact_channel_refuses"
    ),
    ("contact_channel", "ck_contact_channel_consent_source"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_contact_channel_refuses"
    ),
    ("contact_channel", "ck_contact_channel_kind"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_contact_channel_refuses"
    ),
    ("contact_channel", "ck_contact_channel_sendable_consent"): (
        "test_outreach_persistence.py::TestContactConstraints — attempts each refusable "
        "consent source and the absent one"
    ),
    ("contact_channel", "ck_contact_channel_state"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_contact_channel_refuses"
    ),
    # --- The consent audit trail (migration 0022) ----------------------
    ("contact_channel_transition", "ck_contact_channel_transition_consent_source"): (
        "test_contact_channel_lifecycle.py::TestVocabularyAndShapeConstraints::test_a_transition_refuses_a_value_outside_its_vocabulary"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_consented_source"): (
        "test_contact_channel_lifecycle.py::TestTheDatabaseRefusesWhatTheDomainRefuses — a "
        "scraped source and an absent one, the second being the three-valued-logic case"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_from_state"): (
        "test_contact_channel_lifecycle.py::TestVocabularyAndShapeConstraints::test_a_transition_refuses_a_value_outside_its_vocabulary"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_moves"): (
        "test_contact_channel_lifecycle.py::TestTheDatabaseRefusesWhatTheDomainRefuses"
        "::test_a_transition_to_the_state_it_came_from_is_not_a_transition"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_text_present"): (
        "test_contact_channel_lifecycle.py::TestVocabularyAndShapeConstraints::test_a_transition_refuses_a_value_outside_its_vocabulary"
    ),
    ("contact_channel_transition", "ck_contact_channel_transition_to_state"): (
        "test_contact_channel_lifecycle.py::TestVocabularyAndShapeConstraints::test_a_transition_refuses_a_value_outside_its_vocabulary"
    ),
    ("delivery_event", "ck_delivery_event_detail_object"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_delivery_event_refuses "
        "— a JSON array and a JSON scalar"
    ),
    ("delivery_event", "ck_delivery_event_type"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_delivery_event_refuses"
    ),
    ("outreach_draft", "ck_outreach_draft_approval_dated"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses"
    ),
    ("outreach_draft", "ck_outreach_draft_approved_has_approver"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses"
    ),
    ("outreach_draft", "ck_outreach_draft_content_status"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses"
    ),
    ("outreach_draft", "ck_outreach_draft_status"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses"
    ),
    ("outreach_draft", "ck_outreach_draft_supersession"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses "
        "— both halves: a non-superseded draft naming a successor, and a draft naming itself"
    ),
    ("outreach_draft", "ck_outreach_draft_text_present"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses"
    ),
    ("outreach_draft", "ck_outreach_draft_version"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_draft_refuses"
    ),
    ("outreach_send", "ck_outreach_send_accepted_has_provider"): (
        "test_outreach_persistence.py::TestConcludeSend::test_an_acceptance_without_a_provider_is_refused"
    ),
    ("outreach_send", "ck_outreach_send_concluded"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_send_refuses "
        "— both directions"
    ),
    ("outreach_send", "ck_outreach_send_disposition"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_send_refuses"
    ),
    ("outreach_send", "ck_outreach_send_failure_reason"): (
        "test_outreach_persistence.py::TestConcludeSend::test_a_refusal_must_say_why"
    ),
    ("outreach_send", "ck_outreach_send_fields_present"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_an_outreach_send_refuses "
        "— one case per field"
    ),
    ("outreach_send", "ck_outreach_send_message_id_means_accepted"): (
        "test_outreach_persistence.py::TestConcludeSend::test_a_blocked_send_cannot_carry_a_provider_message_id"
    ),
    ("suppression_record", "ck_suppression_record_address_present"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_suppression_record_refuses"
    ),
    ("suppression_record", "ck_suppression_record_source"): (
        "test_outreach_persistence.py::TestVocabularyConstraints::test_a_suppression_record_refuses"
    ),
    ("job", "ck_job_status"): (
        "test_job_states_match_domain.py — reads the admitted set out of the "
        "catalogue and compares it to JobState both directions, and inserts one "
        "job per legal state; test_tenant_isolation.py::"
        "test_job_status_check_rejects_an_unknown_state for the refusal"
    ),
    ("attendance_record", "ck_attendance_record_method"): "test_engagement_schema_constraints.py",
    ("point_ledger_entry", "ck_point_ledger_entry_amount_nonzero"): (
        "test_engagement_schema_constraints.py"
    ),
    ("pipeline_record", "ck_pipeline_record_stage_prefix"): ("test_pipeline_record_constraints.py"),
    ("pipeline_record", "ck_pipeline_record_stage_order"): "test_pipeline_record_constraints.py",
    ("pipeline_record", "ck_pipeline_record_attendance_evidence"): (
        "test_pipeline_record_constraints.py"
    ),
    ("pipeline_record", "ck_pipeline_record_matched_provenance"): (
        "test_pipeline_provenance_migration.py"
    ),
    ("reward_item", "ck_reward_item_points_cost_positive"): "test_engagement_schema_constraints.py",
    ("reward_item", "ck_reward_item_fulfilment_cost_non_negative"): (
        "test_engagement_schema_constraints.py"
    ),
    ("tenant_budget", "ck_budget_ceiling_non_negative"): "this file",
    ("membership", "ck_membership_valid_window"): "this file",
    ("outbox_record", "ck_outbox_status"): "this file",
    ("rate_limit_counter", "ck_rate_limit_count_non_negative"): "this file",
    ("redrive_record", "ck_redrive_authorship_complete"): "this file",
    ("resource_grant", "ck_resource_grant_effect"): "this file",
    ("review_item", "ck_review_item_status"): "test_import_review_constraints.py",
    ("review_item", "ck_review_item_decision_evidence"): "test_import_review_constraints.py",
    ("tenant_budget", "ck_budget_non_negative"): "this file",
    ("spend_ceiling_bucket", "ck_spend_ceiling_bucket_type"): "this file",
    ("spend_ceiling_bucket", "ck_spend_ceiling_bucket_non_negative"): "this file",
    ("spend_ceiling_bucket", "ck_spend_ceiling_bucket_ceiling_non_negative"): "this file",
    ("spend_reservation", "ck_spend_reservation_estimate_non_negative"): "this file",
    ("spend_reservation", "ck_spend_reservation_actual_non_negative"): "this file",
    ("spend_reservation", "ck_spend_reservation_state"): "this file",
    ("spend_reservation", "ck_spend_reservation_lease_token_iff_reserved"): "this file",
    # Migration 0017. Every one of these attempts the forbidden write against a
    # real database in the file named; none of them is covered by existence alone.
    ("event", "ck_event_time_precision"): "test_event_schema_constraints.py",
    ("event", "ck_event_temporal_shape"): "test_event_schema_constraints.py",
    ("event", "ck_event_identity_iff_resolved"): "test_event_schema_constraints.py",
    ("event", "ck_event_publication_status"): "test_event_schema_constraints.py",
    ("event", "ck_event_review_status"): "test_event_schema_constraints.py",
    ("event", "ck_event_quarantined_tag_count_non_negative"): ("test_event_schema_constraints.py"),
    ("event", "ck_event_publishable"): (
        "test_event_schema_constraints.py — refused on INSERT and on UPDATE, for both "
        "reasons an event is unpublishable; test_event_identity_upsert.py covers the "
        "same rule through EventRepository.publish"
    ),
    ("event", "ck_event_origin"): "test_event_schema_constraints.py",
    ("event", "ck_event_provenance_evidence"): "test_event_schema_constraints.py",
    # Migration 0022. Both halves, in the file the other event constraints use:
    # the forbidden writes are a reversed pair, an equal pair, and an end at a
    # precision that carries no start; the permitted ones are a ninety-minute
    # exact event and a NULL end at all three precisions. The permitted half is
    # what an inverted expression fails, and the NULL half is what a migration
    # that backfilled nothing depends on. Refused on UPDATE as well as INSERT.
    ("event", "ck_event_end_after_start"): "test_event_schema_constraints.py",
    ("event_tag", "ck_event_tag_resolution"): "test_event_schema_constraints.py",
    ("event_tag", "ck_event_tag_resolution_shape"): "test_event_schema_constraints.py",
    ("discovery_review_item", "ck_discovery_review_item_kind"): (
        "test_event_schema_constraints.py"
    ),
    ("discovery_review_item", "ck_discovery_review_item_status"): (
        "test_event_schema_constraints.py"
    ),
    ("discovery_review_item", "ck_discovery_review_item_decision_evidence"): (
        "test_event_schema_constraints.py"
    ),
    ("discovery_review_item", "ck_discovery_review_item_tag_evidence"): (
        "test_event_schema_constraints.py"
    ),
    # Migration 0018. Every one attempts the forbidden write against a real
    # database in the file named, alongside the permitted write that catches an
    # inverted expression.
    ("match_run", "ck_match_run_supersedes_is_not_self"): "test_match_run_snapshot.py",
    ("match_run", "ck_match_run_pins_present"): (
        "test_match_run_snapshot.py — one case per pin, so a constraint narrowed "
        "to fewer columns than it names fails rather than passing on the one "
        "column a single case happened to blank"
    ),
    ("match_run", "ck_match_run_weights_object"): "test_match_run_snapshot.py",
    ("match_run", "ck_match_run_portfolio_size"): "test_match_run_snapshot.py",
    ("match_run", "ck_match_run_random_seed"): "test_match_run_snapshot.py",
    ("match_run", "ck_match_run_route_estimate_source"): "test_match_run_snapshot.py",
    ("match_run", "ck_match_run_portfolio_status"): "test_match_run_snapshot.py",
    # Migration 0019.
    ("point_ledger_entry", "ck_point_ledger_entry_kind"): (
        "test_redemption_durability.py — one refused case per kind for each of "
        "the three fields that kind constrains (the wrong source, both sources, "
        "neither source, the wrong sign), and one accepted row per kind, so a "
        "disjunct quietly widened to fewer conjuncts fails rather than passing "
        "on the one column a single case happened to vary"
    ),
    ("redemption", "ck_redemption_state"): "test_redemption_durability.py",
    ("redemption", "ck_redemption_approval_evidence"): (
        "test_redemption_durability.py — including the UPDATE case, which is "
        "the one that matters: this constraint is what makes 'fulfilled is "
        "reachable only from approved' true of a hand-written statement and "
        "not only of the domain state machine"
    ),
    ("redemption", "ck_redemption_closure_evidence"): "test_redemption_durability.py",
    ("redemption", "ck_redemption_snapshot_present"): "test_redemption_durability.py",
    # Migration 0020.
    ("pilot_credential", "ck_pilot_credential_algorithm"): "this file",
    ("pilot_credential", "ck_pilot_credential_material"): "this file",
    ("pilot_session", "ck_pilot_session_window"): "this file",
    ("pilot_session", "ck_pilot_session_token_hash"): "this file",
    ("pilot_login_attempt", "ck_pilot_login_attempt_count"): "this file",
    # Migration 0024. Every one of these is exercised in both directions —
    # forbidden write and permitted write — by the module written alongside the
    # migration, which is where the taxonomy fixtures and row builders already
    # live. Recorded here rather than duplicated, exactly as the outreach
    # entries above are.
    ("event", "ck_event_location_present"): (
        "test_event_schema_constraints.py"
        "::test_a_blank_location_value_is_refused_rather_than_stored, with the permitted "
        "half in ::test_a_physical_event_stores_its_city_and_zip"
    ),
    ("event", "ck_event_virtual_has_no_location"): (
        "test_event_schema_constraints.py::test_a_virtual_event_cannot_carry_a_location "
        "and ::test_an_event_cannot_be_made_virtual_while_it_still_holds_a_location, with "
        "the permitted half in ::test_a_virtual_event_stores"
    ),
    ("speaker_profile", "ck_speaker_profile_industry_code"): (
        "test_cba_classification_schema.py"
        "::test_an_industry_value_outside_the_taxonomy_is_refused, with the permitted half "
        "in ::test_every_released_sector_code_is_storable — parametrized over the domain's "
        "own SECTOR_CODES rather than a list repeated here"
    ),
    ("speaker_profile", "ck_speaker_profile_industry_versioned"): (
        "test_cba_classification_schema.py"
        "::test_a_stored_classification_must_name_the_taxonomy_it_was_resolved_against — "
        "both directions, a code with no version and a version with no code"
    ),
    ("speaker_profile", "ck_speaker_profile_role_code"): (
        "test_cba_classification_schema.py::test_a_role_value_outside_the_taxonomy_is_refused "
        "and ::test_an_adr_0012_event_tag_cannot_be_stored_as_a_cba_role, with the permitted "
        "half in ::test_every_released_role_category_code_is_storable"
    ),
    ("speaker_profile", "ck_speaker_profile_role_versioned"): (
        "test_cba_classification_schema.py"
        "::test_a_stored_classification_must_name_the_taxonomy_it_was_resolved_against"
    ),
    ("speaker_profile", "ck_speaker_profile_text_present"): (
        "test_cba_classification_schema.py"
        "::test_a_blank_speaker_field_is_refused_rather_than_stored — every one of the four "
        "columns 0024 added — with the permitted half in "
        "::test_a_speaker_stores_topic_prior_talk_and_location; and, for the three columns "
        "0025 added, test_cba_contact_schema.py::test_a_blank_name_is_refused and "
        "::test_a_blank_company_or_title_is_refused, with the permitted half in "
        "::test_a_contact_stores_name_company_and_title and "
        "::test_an_absent_company_or_title_is_a_real_state"
    ),
    ("speaker_request_classification", "ck_speaker_request_classification_code"): (
        "test_cba_classification_schema.py"
        "::test_the_two_vocabularies_cannot_be_stored_under_each_others_kind and "
        "::test_an_adr_0012_event_tag_is_not_a_speaker_request_classification, with the "
        "permitted half in ::test_every_released_sector_code_is_targetable and "
        "::test_every_released_role_category_code_is_targetable"
    ),
    ("speaker_request_classification", "ck_speaker_request_classification_kind"): (
        "test_cba_classification_schema.py::test_the_classification_kind_vocabulary_is_closed, "
        "with the permitted half in "
        "::test_a_speaker_request_targets_many_industries_and_many_roles, which writes both "
        "kinds"
    ),
    ("event_registration", "ck_event_registration_status"): (
        "0026 added, test_event_registration.py"
        "::TestRegistrationIsScopedToItsTenantAndItsStudent"
        "::test_an_unknown_status_is_refused_by_the_database, which attempts the "
        "`waitlisted` value this constraint deliberately omits (OQ-CBA-029), plus "
        "::TestTheTableHasTheShapeTheBlockedCardSpecified"
        "::test_the_status_vocabulary_is_exactly_two_values reading the definition "
        "back. The permitted half is every write in TestRegisteringIsIdempotent and "
        "TestCancellingIsATransitionAndNotADelete, which store both admitted values"
    ),
    ("match_weight_setting", "ck_match_weight_setting_overrides_object"): (
        "0027 added, test_cba_weight_settings_persistence.py"
        "::test_the_database_refuses_a_non_object_override_payload, which inserts a JSON "
        "array. The permitted half is every write in that file, including "
        "::test_a_reset_stores_an_empty_map_rather_than_the_registry_values — `{}` is an "
        "object and is admitted deliberately, because a unit that reset its weights is a "
        "different history from one that never configured any"
    ),
    ("match_weight_setting", "ck_match_weight_setting_version"): (
        "0027 added, test_cba_weight_settings_persistence.py"
        "::test_the_database_refuses_a_version_below_one, with the permitted half in "
        "::test_a_written_setting_is_in_the_table_not_only_in_the_response (version 1) and "
        "::test_the_current_version_is_accepted_as_expected_version (version 2)"
    ),
    ("match_weight_setting_revision", "ck_match_weight_setting_revision_overrides_object"): (
        "0027 added, test_cba_weight_settings_persistence.py"
        "::test_the_revision_log_refuses_a_non_object_payload, which inserts a JSON string. "
        "The permitted half is ::test_each_accepted_change_appends_one_revision"
    ),
    ("match_weight_setting_revision", "ck_match_weight_setting_revision_version"): (
        "0027 added, test_cba_weight_settings_persistence.py"
        "::test_the_revision_log_refuses_a_version_below_one, with the permitted half in "
        "::test_each_accepted_change_appends_one_revision, which stores versions 1 and 2"
    ),
}


# ---------------------------------------------------------------------------
# Row builders. Each returns the id of a row the constraint under test can hang
# off, so the test body contains only the value that is actually in question.
# ---------------------------------------------------------------------------


def _make_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"ck-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _make_job(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
            "VALUES (:id, :tenant_id, 'noop', 'queued', :unit_id)"
        ),
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(conn, tenant_id),
        },
    )
    return job_id


def _insert_membership(conn, tenant_id, user_id, valid_from, valid_until) -> None:
    conn.execute(
        text(
            "INSERT INTO membership "
            "(id, tenant_id, user_id, granted_path, role, valid_from, valid_until) "
            "VALUES (:id, :tenant_id, :user_id, 'root'::ltree, 'coordinator', "
            ":valid_from, :valid_until)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "valid_from": valid_from,
            "valid_until": valid_until,
        },
    )


def _insert_grant(conn, tenant_id, user_id, effect: str) -> None:
    conn.execute(
        text(
            "INSERT INTO resource_grant "
            "(id, tenant_id, user_id, resource_type, resource_id, effect) "
            "VALUES (:id, :tenant_id, :user_id, 'job', :resource_id, :effect)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "resource_id": uuid.uuid4(),
            "effect": effect,
        },
    )


def _insert_outbox(conn, tenant_id, job_id, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO outbox_record (id, tenant_id, job_id, task_name, status) "
            "VALUES (:id, :tenant_id, :job_id, :task_name, :status)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "job_id": job_id,
            "task_name": f"task-{uuid.uuid4().hex[:12]}",
            "status": status,
        },
    )


def _insert_redrive(conn, tenant_id, job_id, redriven_at, redriven_by) -> None:
    conn.execute(
        text(
            "INSERT INTO redrive_record "
            "(id, tenant_id, job_id, attempt_history, redriven_at, redriven_by) "
            "VALUES (:id, :tenant_id, :job_id, '[]'::jsonb, :redriven_at, :redriven_by)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "job_id": job_id,
            "redriven_at": redriven_at,
            "redriven_by": redriven_by,
        },
    )


# ---------------------------------------------------------------------------
# ck_membership_valid_window — (until IS NULL) OR (from IS NULL) OR (until > from)
# ---------------------------------------------------------------------------

_EARLY = "2026-01-01T00:00:00+00:00"
_LATE = "2026-06-01T00:00:00+00:00"


def test_membership_window_rejects_an_end_before_its_start(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError, match="ck_membership_valid_window"), engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_membership(conn, tenant_id, user, _LATE, _EARLY)


def test_membership_window_rejects_a_zero_length_window(engine: Engine, tenant_id) -> None:
    """The constraint is `>`, not `>=`.

    A membership valid from an instant until that same instant grants nothing,
    and a constraint written `>=` would let it through. Nothing else in this
    file distinguishes the two operators.
    """
    with pytest.raises(IntegrityError, match="ck_membership_valid_window"), engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_membership(conn, tenant_id, user, _EARLY, _EARLY)


@pytest.mark.parametrize(
    ("valid_from", "valid_until", "description"),
    [
        (_EARLY, _LATE, "an ordinary bounded window"),
        (None, _LATE, "open at the start"),
        (_EARLY, None, "open at the end"),
        (None, None, "unbounded"),
    ],
)
def test_membership_window_accepts_every_legitimate_shape(
    engine: Engine, tenant_id, valid_from, valid_until, description: str
) -> None:
    """The inversion check: an inverted constraint refuses these.

    The two `NULL` escapes are part of the expression, so a constraint rewritten
    without them would pass the rejection tests above and fail here.
    """
    with engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_membership(conn, tenant_id, user, valid_from, valid_until)


# ---------------------------------------------------------------------------
# ck_resource_grant_effect — effect IN ('allow', 'deny')
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("effect", ["maybe", "ALLOW", "Deny", "", "allow "])
def test_resource_grant_rejects_an_effect_outside_the_vocabulary(
    engine: Engine, tenant_id, effect: str
) -> None:
    """Authorization reads this column; a value it does not know is not safe.

    The case variants and the trailing space are deliberate. A constraint
    relaxed to `lower(trim(effect)) IN (...)` would accept them, and the
    authorization code compares the literal, so it would then read a grant it
    does not recognise as neither allow nor deny.
    """
    with pytest.raises(IntegrityError, match="ck_resource_grant_effect"), engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_grant(conn, tenant_id, user, effect)


@pytest.mark.parametrize("effect", ["allow", "deny"])
def test_resource_grant_accepts_both_effects(engine: Engine, tenant_id, effect: str) -> None:
    """Both halves of the vocabulary, so a narrowed list fails here.

    `deny` in particular: a constraint reduced to `effect = 'allow'` would pass
    every rejection test above.
    """
    with engine.begin() as conn:
        user = _make_user(conn, tenant_id)
        _insert_grant(conn, tenant_id, user, effect)


# ---------------------------------------------------------------------------
# ck_outbox_status — status IN ('pending', 'leased', 'dispatched', 'failed')
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["claimed", "PENDING", "", "done"])
def test_outbox_rejects_a_status_outside_the_lifecycle(
    engine: Engine, tenant_id, status: str
) -> None:
    """`claimed` is the interesting one — it is the word the code does not use.

    The dispatcher's claim sets `leased`. A status the claim query never selects
    for is a row no dispatcher will ever pick up, and the constraint is what
    stops one being written.
    """
    with pytest.raises(IntegrityError, match="ck_outbox_status"), engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_outbox(conn, tenant_id, job, status)


@pytest.mark.parametrize("status", ["pending", "leased", "dispatched", "failed"])
def test_outbox_accepts_every_lifecycle_status(engine: Engine, tenant_id, status: str) -> None:
    """All four, because the dispatcher writes all four.

    ADR-0005 makes `pending → leased → dispatched | failed` the outbox's whole
    lifecycle. A constraint that lost one of them would break the dispatcher at
    the transition that writes it, and pass every rejection test above.
    """
    with engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_outbox(conn, tenant_id, job, status)


# ---------------------------------------------------------------------------
# ck_redrive_authorship_complete — (redriven_at IS NULL) = (redriven_by IS NULL)
# ---------------------------------------------------------------------------

_ACTOR = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def test_redrive_rejects_a_time_with_no_author(engine: Engine, tenant_id) -> None:
    """A re-drive that happened, with nobody accountable for it."""
    with (
        pytest.raises(IntegrityError, match="ck_redrive_authorship_complete"),
        engine.begin() as conn,
    ):
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, _LATE, None)


def test_redrive_rejects_an_author_with_no_time(engine: Engine, tenant_id) -> None:
    """The other half. A constraint written as a one-way implication —
    `redriven_at IS NULL OR redriven_by IS NOT NULL` — passes the test above and
    fails here, which is the whole reason both directions are written out."""
    with (
        pytest.raises(IntegrityError, match="ck_redrive_authorship_complete"),
        engine.begin() as conn,
    ):
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, None, _ACTOR)


def test_redrive_accepts_a_parked_row_that_has_not_been_redriven(engine: Engine, tenant_id) -> None:
    """Both `NULL` — the state every redrive_record is written in first."""
    with engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, None, None)


def test_redrive_accepts_a_complete_authorship_pair(engine: Engine, tenant_id) -> None:
    """Both set — the state a re-drive moves it to."""
    with engine.begin() as conn:
        job = _make_job(conn, tenant_id)
        _insert_redrive(conn, tenant_id, job, _LATE, _ACTOR)


# ---------------------------------------------------------------------------
# ck_budget_non_negative — spent >= 0 AND reserved >= 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("column", ["spent", "reserved"])
@pytest.mark.parametrize("amount", ["-1", "-0.0001"])
def test_budget_rejects_a_negative_amount(
    engine: Engine, tenant_id, column: str, amount: str
) -> None:
    """Both columns, because the constraint is a conjunction of two clauses.

    A constraint that lost the `reserved >= 0` half would still refuse a
    negative `spent`. Parametrising over the column is what makes each clause
    independently load-bearing.

    `-0.0001` is the smallest negative `numeric(12,4)` can hold. Sampling only
    `-1` would leave a clause relaxed to `>= -0.5` passing.
    """
    with pytest.raises(IntegrityError, match="ck_budget_non_negative"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, "
                f"{column}) VALUES (:tenant_id, 'email', 100, -1)"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_accepts_zero_and_positive_amounts(engine: Engine, tenant_id) -> None:
    """Zero is the boundary, and an inverted constraint refuses it."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, spent, reserved) "
                "VALUES (:tenant_id, 'email', 100, 0, 0)"
            ),
            {"tenant_id": tenant_id},
        )
        conn.execute(
            text(
                "UPDATE tenant_budget SET spent = 10, reserved = 5 "
                "WHERE tenant_id = :tenant_id AND provider = 'email'"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_rejects_a_negative_amount_on_update(engine: Engine, tenant_id) -> None:
    """A refund that overshoots is the realistic way this goes negative.

    Every other test here inserts. The reservation path *updates* — `spent =
    spent - x` on release — and a CHECK declared on a column is enforced on both,
    so this pins that the release path cannot drive the row below zero either.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling, spent) "
                "VALUES (:tenant_id, 'email', 100, 5)"
            ),
            {"tenant_id": tenant_id},
        )

    with pytest.raises(IntegrityError, match="ck_budget_non_negative"), engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE tenant_budget SET spent = spent - 10 "
                "WHERE tenant_id = :tenant_id AND provider = 'email'"
            ),
            {"tenant_id": tenant_id},
        )


# ---------------------------------------------------------------------------
# ck_budget_ceiling_non_negative — ceiling >= 0
# ---------------------------------------------------------------------------
#
# `test_tenant_isolation.py::test_budget_ceiling_cannot_go_negative` already
# refuses a ceiling of -5. That is a rejection test and nothing else: it leaves
# the permitted side unproven, so an inverted constraint passes it, and it
# samples one value a long way from the boundary, so a constraint relaxed to
# `ceiling >= -1` passes it too. These close both gaps.


@pytest.mark.parametrize("ceiling", ["-5", "-1", "-0.0001"])
def test_budget_ceiling_rejects_any_negative_value(engine: Engine, tenant_id, ceiling: str) -> None:
    """Including the value just below the boundary.

    `-0.0001` is the smallest negative the column's `numeric(12,4)` scale can
    represent. Sampling only `-5` leaves every relaxation between the boundary
    and that value undetected.
    """
    with (
        pytest.raises(IntegrityError, match="ck_budget_ceiling_non_negative"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                f"VALUES (:tenant_id, 'email', {ceiling})"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_ceiling_accepts_zero(engine: Engine, tenant_id) -> None:
    """Zero is the boundary, and an inverted constraint refuses it.

    A ceiling of zero is also meaningful rather than degenerate: it is how a
    provider is switched off without deleting the row.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                "VALUES (:tenant_id, 'email', 0)"
            ),
            {"tenant_id": tenant_id},
        )


def test_budget_ceiling_rejects_going_negative_on_update(engine: Engine, tenant_id) -> None:
    """Lowering a ceiling is an UPDATE, which is how this would really happen."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenant_budget (tenant_id, provider, ceiling) "
                "VALUES (:tenant_id, 'email', 10)"
            ),
            {"tenant_id": tenant_id},
        )

    with (
        pytest.raises(IntegrityError, match="ck_budget_ceiling_non_negative"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "UPDATE tenant_budget SET ceiling = ceiling - 20 "
                "WHERE tenant_id = :tenant_id AND provider = 'email'"
            ),
            {"tenant_id": tenant_id},
        )


# ---------------------------------------------------------------------------
# ck_rate_limit_count_non_negative — count >= 0
# ---------------------------------------------------------------------------


def _insert_counter(conn, tenant_id, count: int) -> None:
    conn.execute(
        text(
            "INSERT INTO rate_limit_counter "
            "(tenant_id, subject, operation, window_start, count) "
            "VALUES (:tenant_id, :subject, 'redrive', :window_start, :count)"
        ),
        {
            "tenant_id": tenant_id,
            "subject": unique_subject(f"ck-{uuid.uuid4().hex[:8]}"),
            "window_start": _EARLY,
            "count": count,
        },
    )


def test_rate_limit_count_rejects_a_negative_count(engine: Engine, tenant_id) -> None:
    """A negative counter is quota the caller has not spent — S-008's shape.

    The limiter increments; nothing decrements. A count below zero would mean
    the window grants more requests than the limit allows, which is the failure
    the limiter exists to prevent.
    """
    with (
        pytest.raises(IntegrityError, match="ck_rate_limit_count_non_negative"),
        engine.begin() as conn,
    ):
        _insert_counter(conn, tenant_id, -1)


def test_rate_limit_count_accepts_zero_and_above(engine: Engine, tenant_id) -> None:
    """Zero is the value every window starts at, so an inverted check breaks the
    limiter on its first write rather than on some edge case."""
    with engine.begin() as conn:
        _insert_counter(conn, tenant_id, 0)
        _insert_counter(conn, tenant_id, 1)


def test_rate_limit_count_rejects_going_negative_on_update(engine: Engine, tenant_id) -> None:
    """The decrement no code performs today, refused by the database anyway."""
    with engine.begin() as conn:
        _insert_counter(conn, tenant_id, 1)

    with (
        pytest.raises(IntegrityError, match="ck_rate_limit_count_non_negative"),
        engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE rate_limit_counter SET count = count - 5 WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


# ---------------------------------------------------------------------------
# Migration 0010 spend constraints
# ---------------------------------------------------------------------------


def _insert_spend_bucket(
    conn, tenant_id, *, bucket_type: str = "job", ceiling="100", reserved="0", spent="0"
) -> None:
    conn.execute(
        text(
            "INSERT INTO spend_ceiling_bucket "
            "(tenant_id, bucket_type, bucket_key, ceiling, reserved, spent) "
            "VALUES (:tenant_id, :bucket_type, :bucket_key, :ceiling, :reserved, :spent)"
        ),
        {
            "tenant_id": tenant_id,
            "bucket_type": bucket_type,
            "bucket_key": f"test:{uuid.uuid4()}",
            "ceiling": ceiling,
            "reserved": reserved,
            "spent": spent,
        },
    )


def _insert_spend_reservation(
    conn,
    tenant_id,
    *,
    estimate="1",
    actual_cost=None,
    state: str = "reserved",
    lease_token: uuid.UUID | None = _ACTOR,
) -> None:
    row_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO spend_reservation "
            "(id, tenant_id, work_key, job_bucket_key, tenant_day_bucket_key, "
            "tenant_month_bucket_key, estimate, actual_cost, state, lease_token, "
            "lease_expires_at) VALUES "
            "(:id, :tenant_id, :work_key, :job_key, :day_key, :month_key, "
            ":estimate, :actual_cost, :state, :lease_token, now())"
        ),
        {
            "id": row_id,
            "tenant_id": tenant_id,
            "work_key": f"test:{row_id}",
            "job_key": f"job:{row_id}",
            "day_key": f"tenant-day:{tenant_id}:2026-01-01",
            "month_key": f"tenant-month:{tenant_id}:2026-01",
            "estimate": estimate,
            "actual_cost": actual_cost,
            "state": state,
            "lease_token": lease_token,
        },
    )


def test_spend_bucket_type_rejects_unknown_vocabulary(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_spend_ceiling_bucket_type"),
        engine.begin() as conn,
    ):
        _insert_spend_bucket(conn, tenant_id, bucket_type="tenant_week")


@pytest.mark.parametrize("bucket_type", ["job", "tenant_day", "tenant_month"])
def test_spend_bucket_type_accepts_every_supported_scope(
    engine: Engine, tenant_id, bucket_type: str
) -> None:
    with engine.begin() as conn:
        _insert_spend_bucket(conn, tenant_id, bucket_type=bucket_type)


@pytest.mark.parametrize(
    ("column", "constraint"),
    [
        ("reserved", "ck_spend_ceiling_bucket_non_negative"),
        ("spent", "ck_spend_ceiling_bucket_non_negative"),
        ("ceiling", "ck_spend_ceiling_bucket_ceiling_non_negative"),
    ],
)
def test_spend_bucket_amounts_reject_the_smallest_negative_value(
    engine: Engine, tenant_id, column: str, constraint: str
) -> None:
    values = {"ceiling": "100", "reserved": "0", "spent": "0", column: "-0.0001"}
    with pytest.raises(IntegrityError, match=constraint), engine.begin() as conn:
        _insert_spend_bucket(conn, tenant_id, **values)


def test_spend_bucket_amounts_accept_zero_and_recorded_overage(engine: Engine, tenant_id) -> None:
    """A genuine overage may make spent exceed ceiling; only negativity is forbidden."""
    with engine.begin() as conn:
        _insert_spend_bucket(conn, tenant_id, ceiling="0", reserved="0", spent="0")
        _insert_spend_bucket(conn, tenant_id, ceiling="10", reserved="5", spent="11")


def test_spend_reservation_estimate_rejects_a_negative_value(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_spend_reservation_estimate_non_negative"),
        engine.begin() as conn,
    ):
        _insert_spend_reservation(conn, tenant_id, estimate="-0.0001")


@pytest.mark.parametrize("actual_cost", [None, "0", "3.2500"])
def test_spend_reservation_accepts_absent_or_non_negative_actual_cost(
    engine: Engine, tenant_id, actual_cost
) -> None:
    with engine.begin() as conn:
        _insert_spend_reservation(conn, tenant_id, estimate="0", actual_cost=actual_cost)


def test_spend_reservation_rejects_a_negative_actual_cost(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_spend_reservation_actual_non_negative"),
        engine.begin() as conn,
    ):
        _insert_spend_reservation(conn, tenant_id, actual_cost="-0.0001")


def test_spend_reservation_rejects_an_unknown_state(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_spend_reservation_state"),
        engine.begin() as conn,
    ):
        _insert_spend_reservation(conn, tenant_id, state="cancelled", lease_token=None)


@pytest.mark.parametrize("state", ["reconciled", "expired_spent", "released"])
def test_spend_reservation_accepts_every_terminal_state(
    engine: Engine, tenant_id, state: str
) -> None:
    with engine.begin() as conn:
        _insert_spend_reservation(conn, tenant_id, state=state, lease_token=None)


@pytest.mark.parametrize(("state", "lease_token"), [("reserved", None), ("reconciled", _ACTOR)])
def test_spend_reservation_rejects_lease_token_state_mismatches(
    engine: Engine, tenant_id, state: str, lease_token
) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_spend_reservation_lease_token_iff_reserved"),
        engine.begin() as conn,
    ):
        _insert_spend_reservation(conn, tenant_id, state=state, lease_token=lease_token)


def test_spend_reservation_accepts_reserved_with_a_lease_token(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        _insert_spend_reservation(conn, tenant_id)


# ---------------------------------------------------------------------------
# Migration 0020 pilot-login constraints
# ---------------------------------------------------------------------------


def _insert_pilot_credential(
    conn,
    tenant_id,
    *,
    algorithm: str = "pbkdf2_hmac_sha256",
    iterations: int = 100_000,
    salt: bytes = b"0123456789abcdef",
    password_hash: bytes = b"x" * 32,
) -> None:
    conn.execute(
        text(
            "INSERT INTO pilot_credential "
            "(id, tenant_id, user_id, algorithm, iterations, salt, password_hash) "
            "VALUES (:id, :tenant_id, :user_id, :algorithm, :iterations, :salt, :password_hash)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": _make_user(conn, tenant_id),
            "algorithm": algorithm,
            "iterations": iterations,
            "salt": salt,
            "password_hash": password_hash,
        },
    )


def _insert_pilot_session(
    conn,
    tenant_id,
    *,
    token_hash: bytes = b"x" * 32,
    issued_at: str = _EARLY,
    expires_at: str = _LATE,
    revoked_at: str | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO pilot_session "
            "(id, tenant_id, user_id, token_hash, issued_at, expires_at, revoked_at) "
            "VALUES (:id, :tenant_id, :user_id, :token_hash, :issued_at, :expires_at, :revoked_at)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "user_id": _make_user(conn, tenant_id),
            "token_hash": token_hash,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "revoked_at": revoked_at,
        },
    )


def _insert_pilot_login_attempt(conn, *, caller_key: str, count: int) -> None:
    conn.execute(
        text(
            "INSERT INTO pilot_login_attempt (caller_key, window_start, count) "
            "VALUES (:caller_key, :window_start, :count)"
        ),
        {"caller_key": caller_key, "window_start": _EARLY, "count": count},
    )


def test_pilot_credential_algorithm_rejects_unknown_values(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_pilot_credential_algorithm"),
        engine.begin() as conn,
    ):
        _insert_pilot_credential(conn, tenant_id, algorithm="argon2id")


@pytest.mark.parametrize(
    ("salt", "password_hash", "iterations"),
    [
        (b"short", b"x" * 32, 100_000),
        (b"0123456789abcdef", b"short", 100_000),
        (b"0123456789abcdef", b"x" * 32, 99_999),
    ],
)
def test_pilot_credential_material_rejects_invalid_shape(
    engine: Engine, tenant_id, salt: bytes, password_hash: bytes, iterations: int
) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_pilot_credential_material"),
        engine.begin() as conn,
    ):
        _insert_pilot_credential(
            conn,
            tenant_id,
            salt=salt,
            password_hash=password_hash,
            iterations=iterations,
        )


def test_pilot_credential_material_accepts_boundary_values(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        _insert_pilot_credential(
            conn, tenant_id, iterations=100_000, salt=b"0" * 16, password_hash=b"x" * 32
        )


@pytest.mark.parametrize(
    ("issued_at", "expires_at", "revoked_at"),
    [
        (_EARLY, _EARLY, None),
        (_LATE, _EARLY, None),
        (_LATE, _LATE, _EARLY),
    ],
)
def test_pilot_session_window_rejects_invalid_temporal_order(
    engine: Engine,
    tenant_id,
    issued_at: str,
    expires_at: str,
    revoked_at: str | None,
) -> None:
    with pytest.raises(IntegrityError, match="ck_pilot_session_window"), engine.begin() as conn:
        _insert_pilot_session(
            conn,
            tenant_id,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked_at=revoked_at,
        )


def test_pilot_session_token_hash_rejects_non_sha256_width(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError, match="ck_pilot_session_token_hash"), engine.begin() as conn:
        _insert_pilot_session(conn, tenant_id, token_hash=b"short")


def test_pilot_session_constraints_accept_valid_rows(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        _insert_pilot_session(
            conn, tenant_id, token_hash=b"x" * 32, issued_at=_EARLY, expires_at=_LATE
        )
        _insert_pilot_session(
            conn,
            tenant_id,
            token_hash=b"y" * 32,
            issued_at=_EARLY,
            expires_at=_LATE,
            revoked_at=_LATE,
        )


def test_pilot_login_attempt_count_rejects_negative_values(engine: Engine) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_pilot_login_attempt_count"),
        engine.begin() as conn,
    ):
        _insert_pilot_login_attempt(conn, caller_key=f"caller-{uuid.uuid4()}", count=-1)


def test_pilot_login_attempt_count_accepts_zero_and_above(engine: Engine) -> None:
    with engine.begin() as conn:
        _insert_pilot_login_attempt(conn, caller_key=f"caller-{uuid.uuid4()}", count=0)
        _insert_pilot_login_attempt(conn, caller_key=f"caller-{uuid.uuid4()}", count=1)


# ---------------------------------------------------------------------------
# The catalogue, for the two things no attempted write can reach
# ---------------------------------------------------------------------------


def _live_check_constraints(engine: Engine) -> dict[tuple[str, str], tuple[str, bool]]:
    """Every CHECK in `public`, keyed by `(table, name)`.

    Keyed by both because PostgreSQL allows one name on two tables, and a
    dictionary keyed on the name alone silently keeps whichever row came last.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.relname, c.conname, pg_get_constraintdef(c.oid), c.convalidated "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE c.contype = 'c' AND n.nspname = 'public'"
            )
        ).all()
    found: dict[tuple[str, str], tuple[str, bool]] = {}
    for table, name, definition, validated in rows:
        key = (table, name)
        assert key not in found, f"{table}.{name} is defined twice, which should be impossible"
        found[key] = (definition, validated)
    return found


def test_every_check_constraint_is_validated(engine: Engine) -> None:
    """`NOT VALID` is invisible to every attempted write in this file.

    Verified against PostgreSQL 16.15: a CHECK added `NOT VALID` rejects new
    inserts and updates identically to a validated one. What `NOT VALID` skips
    is the initial scan of rows already in the table — so the constraint is
    enforced from that moment on, and simply **was never checked** against the
    existing data. That is weaker than saying the old rows violate it; they may
    or may not, and nobody has looked. Either way the schema is asserting
    something it has not established, which is what this test refuses.

    No write can tell the difference. `pg_constraint.convalidated` is the only
    thing that can, which is why this reads the catalogue instead of attempting
    anything.
    """
    found = _live_check_constraints(engine)

    missing = sorted(set(CHECK_CONSTRAINT_DEFINITIONS) - set(found))
    assert not missing, f"these CHECK constraints are not in the database at all: {missing}"

    unvalidated = sorted(key for key, (_, validated) in found.items() if not validated)
    assert not unvalidated, (
        "these CHECK constraints are NOT VALID, so they have never been checked "
        f"against the rows already in their table: {unvalidated}"
    )


@pytest.mark.parametrize("key", sorted(CHECK_CONSTRAINT_DEFINITIONS))
def test_the_constraint_expression_is_exactly_as_declared(
    engine: Engine, key: tuple[str, str]
) -> None:
    """The expression itself, which no attempted write can pin.

    A write test proves a constraint refuses the values it tried. It says
    nothing about the values it did not: `ck_resource_grant_effect` widened to
    admit `'audit'`, `ck_outbox_status` widened to admit `'cancelled'`, or
    either numeric clause relaxed to `>= -0.5`, passes every behavioural test in
    this file. Enumerating the counterexamples is hopeless — the space is every
    string and every number. Comparing the rendered definition closes the whole
    class in one assertion.

    This does not replace the behavioural tests. A definition that reads
    correctly and is not enforced — `NOT VALID`, or a constraint on a column the
    writes do not touch — passes here and fails there. The two are load-bearing
    in different directions.
    """
    found = _live_check_constraints(engine)
    assert key in found, f"{key[0]}.{key[1]} is not in the database"
    definition, _ = found[key]
    assert definition == CHECK_CONSTRAINT_DEFINITIONS[key], (
        f"{key[0]}.{key[1]}'s expression has changed.\n"
        f"  expected: {CHECK_CONSTRAINT_DEFINITIONS[key]}\n"
        f"  actual:   {definition}"
    )


def test_this_file_covers_every_check_constraint_in_the_schema(engine: Engine) -> None:
    """A new CHECK constraint added without a behavioural test fails here.

    Without this, F10's coverage is a claim about a moment rather than a
    property of the schema: the eight constraints that existed when it was
    written stay covered, and the ninth arrives untested.

    **Every CHECK in `public` counts, not every CHECK named `ck_*`.** The first
    version filtered on `conname LIKE 'ck\\_%'`, which made it blind to exactly
    the constraint most likely to be added by someone unfamiliar with the
    convention. Verified: one named `chk_probe_wrong_prefix`, and an unnamed one
    PostgreSQL auto-named `job_command_type_check`, both passed. Dropping the
    filter enforces the naming convention here too.
    """
    actual = set(_live_check_constraints(engine))

    uncovered = sorted(actual - set(CHECK_CONSTRAINT_DEFINITIONS))
    assert not uncovered, (
        "these CHECK constraints are not declared in "
        f"tests/integration/test_check_constraints.py: {uncovered}"
    )

    stale = sorted(set(CHECK_CONSTRAINT_DEFINITIONS) - actual)
    assert not stale, f"this file declares CHECK constraints that no longer exist: {stale}"


def test_every_declared_constraint_says_where_it_is_exercised(engine: Engine) -> None:
    """Declaring a constraint's expression is not the same as testing its behaviour.

    `CHECK_CONSTRAINT_DEFINITIONS` pins what a constraint *says*. It would be
    satisfied by a constraint nothing ever writes against. `BEHAVIOURAL_COVERAGE`
    is the second half — where the forbidden and permitted writes for each one
    actually live — and this keeps the two lists in step, so a constraint cannot
    be added to the first and quietly left out of the second.
    """
    undocumented = sorted(set(CHECK_CONSTRAINT_DEFINITIONS) - set(BEHAVIOURAL_COVERAGE))
    assert not undocumented, (
        f"these constraints have a pinned expression but no record of where "
        f"their behaviour is exercised: {undocumented}"
    )
    orphaned = sorted(set(BEHAVIOURAL_COVERAGE) - set(CHECK_CONSTRAINT_DEFINITIONS))
    assert not orphaned, f"BEHAVIOURAL_COVERAGE names constraints that are not declared: {orphaned}"
