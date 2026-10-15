"""Mission visibility stays an honest, deterministic view of board records."""
from __future__ import annotations

import copy
import unittest
from html.parser import HTMLParser

import support

dashboard = support.helper("dashboard")
SHA = "a" * 40


def story(number=1, state="ready", **overrides):
    value = {
        "id": number, "epic": 1, "stream": "core", "type": "story",
        "title": f"Feature {number}", "state": state,
        "status": {"planned": "backlog", "ready": "ready-for-dev",
                   "review": "in-review"}.get(state, state),
        "owner": None, "claim": {"live": False}, "receipts": {},
        "history": [], "findings": [],
    }
    return value | overrides


def epic(number=1, **overrides):
    return {
        "id": number, "stream": "core", "title": f"Milestone {number}",
        "status": "awaiting-acceptance", "outcome": "Working feature set",
        "done_when": ["feature proof is recorded"], "acceptance": None,
    } | overrides


def roadmap(stories=None, epics=None):
    stories = [story()] if stories is None else stories
    return {
        "revision": 2, "generated_at": "2026-01-02T03:04:05Z",
        "stories": stories, "epics": [epic()] if epics is None else epics,
        "streams": [{"id": "core", "title": "Core", "status": "active",
                     "counts": {state: sum(s["state"] == state for s in stories)
                                for state in dashboard.ALL_STATES}, "critical_path": []}],
        "frontier": {"ready": [], "waiting_on_prereq": []}, "blockers": [],
        "diagnostics": {"unpinned_gates": [], "undeclared_after": [],
                        "order_conflicts": [], "inconsistencies": []},
        "problems": [], "decision_queue": [],
    }


def attempt(**overrides):
    return {
        "type": "agent-attempt", "subject_sha": SHA, "agent": "worker-1",
        "role": "sf-engineer", "skill": "software-factory", "requested_model": "requested-large",
        "effective_model": "observed-small", "phase": "implementation",
        "status": "reported-complete", "recorded_at": "2026-01-02T03:04:05Z",
        "summary": "Implemented feature; awaits independent review",
    } | overrides


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class MissionDashboardTests(unittest.TestCase):
    def test_counts_keep_review_built_cancellation_and_human_acceptance_distinct(self):
        stories = [story(index, state) for index, state in enumerate(dashboard.ALL_STATES, 1)]
        plan = roadmap(stories, [epic(), epic(2, status="done", acceptance={
            "by": "human", "at": "2026-01-01T00:00:00Z"})])
        rendered = dashboard.render_html(plan)
        self.assertIn("1/7 stories done", rendered)
        self.assertIn("1/2 epics with recorded human acceptance", rendered)
        for state in dashboard.ALL_STATES:
            self.assertIn(f'{state}: <strong>1</strong>', rendered)
        self.assertIn("human acceptance not recorded", rendered)
        self.assertIn("human acceptance recorded at 2026-01-01T00:00:00Z", rendered)
        self.assertIn("Review and built are separate from done", rendered)
        self.assertIn("Cancelled work is not completed work", rendered)

    def test_all_features_remain_visible_in_each_milestone_checklist(self):
        states = ["planned", "ready", "in-progress", "review", "built", "done", "cancelled"]
        stories = [story(index, state) for index, state in enumerate(states, 1)]
        rendered = dashboard.render_milestones(roadmap(stories, [epic(), epic(2)]))
        for index, state in enumerate(states, 1):
            self.assertIn(f"#{index} Feature {index}", rendered)
            self.assertIn(f"{state} / {stories[index - 1]['status']}", rendered)
        self.assertIn("□ #1 Feature 1", rendered)
        self.assertIn("✓ #6 Feature 6", rendered)
        self.assertIn("× #7 Feature 7", rendered)
        self.assertIn("no features recorded", rendered)

    def test_legacy_records_do_not_invent_attempts_models_or_acceptance(self):
        plan = roadmap([story(receipts={"tests": {"subject_sha": SHA, "result": "pass"}})],
                       [epic(status="done")])
        rendered = dashboard.render_html(plan)
        self.assertIn("historical agents and models are unknown", rendered)
        self.assertIn("0/1 epics with recorded human acceptance", rendered)
        self.assertIn("time unknown", rendered)
        self.assertIn("tests: pass", rendered)
        self.assertIn("unassigned", rendered)

    def test_acceptance_requires_a_human_record_on_a_done_epic(self):
        for status, acceptance in (
            ("awaiting-acceptance", {"by": "human", "at": "2026-01-01T00:00:00Z"}),
            ("done", {"by": "orchestrator", "at": "2026-01-01T00:00:00Z"}),
            ("done", {"by": "human", "at": "unknown"}),
            ("done", "invalid optional metadata"),
        ):
            with self.subTest(status=status, acceptance=acceptance):
                plan = roadmap([story(state="done")], [epic(status=status, acceptance=acceptance)])
                rendered = dashboard.render_html(plan)
                self.assertIn("1/1 stories done", rendered)
                self.assertIn("0/1 epics with recorded human acceptance", rendered)
                self.assertIn("human acceptance not recorded", rendered)

    def test_requested_model_does_not_replace_reported_effective_model(self):
        plan = roadmap([story(receipts={"attempt-1": attempt()})])
        rendered = dashboard.render_attempts(plan)
        self.assertIn("<td>requested-large</td><td>observed-small</td>", rendered)
        self.assertIn("implementation / reported-complete", rendered)
        self.assertIn("worker-1 · sf-engineer · software-factory", rendered)
        self.assertIn(SHA, rendered)
        self.assertIn("not verified runtime telemetry", rendered)
        for effective in (None, "absent"):
            receipt = attempt(effective_model=effective)
            if effective == "absent":
                del receipt["effective_model"]
            plan["stories"][0]["receipts"] = {"attempt-1": receipt}
            rendered = dashboard.render_attempts(plan)
            self.assertIn("<td>requested-large</td><td>unknown</td>", rendered)

    def test_claim_is_an_assignment_and_never_a_running_process_claim(self):
        plan = roadmap([story(owner="worker", claim={"live": True, "owner": "worker"})])
        rendered = dashboard.render_html(plan)
        self.assertIn("claim: recorded assignment (worker)", rendered)
        self.assertIn("Claims describe assignments and do not prove a process is running", rendered)
        self.assertNotIn("claim: live", rendered)

    def test_malformed_optional_attempt_metadata_is_ignored_safely(self):
        malformed = [
            {"phase": ["review"]}, {"status": "done"}, {"agent": {"name": "worker"}},
            {"recorded_at": "yesterday"}, {"recorded_at": "2026-01-01T00:00:00"},
            {"effective_model": ["model"]}, {"summary": None}, {"requested_model": ""},
            {"type": "other"}, {"subject_sha": ""},
        ]
        for metadata in malformed:
            with self.subTest(metadata=metadata):
                plan = roadmap([story(receipts={"attempt-1": attempt(**metadata)})])
                rendered = dashboard.render_html(plan)
                self.assertIn("no valid agent-attempt metadata recorded", rendered)
                self.assertNotIn("<td>worker-1 ·", rendered)

    def test_activity_orders_timezone_offsets_chronologically_with_stable_ties(self):
        plan = roadmap([
            story(2, findings=[{"at": "2026-01-02T02:00:00Z", "by": "b", "text": "tie-story2"}]),
            story(1, history=[{"at": "2026-01-01T18:00:00-08:00", "by": "a", "from": "ready",
                               "to": "in-progress"}], findings=[
                {"at": "2026-01-02T03:00:00+02:00", "by": "a", "text": "older"},
                {"at": "2026-01-02T02:00:00Z", "by": "a", "text": "tie-story1"},
                {"at": "2026-01-02T02:00:00Z", "by": "a", "text": "tie-source-order"},
                {"at": "2026-01-02T00:00:00-03:00", "by": "a", "text": "newest"},
                {"at": "2026-01-02T23:59:59", "by": "a", "text": "undated"},
            ], receipts={"z": {"subject_sha": SHA}, "a": {"subject_sha": SHA}}),
        ])
        events = dashboard.recorded_activity(plan)
        self.assertIn("newest", events[0]["text"])
        self.assertIn("tie-story1", events[1]["text"])
        self.assertIn("tie-source-order", events[2]["text"])
        self.assertEqual(events[3]["kind"], "transition")
        self.assertIn("tie-story2", events[4]["text"])
        self.assertIn("older", events[5]["text"])
        self.assertIn("undated", events[6]["text"])
        self.assertEqual([event["key"] for event in events[7:]], ["a", "z"])
        rendered = dashboard.render_activity(plan)
        plan["stories"].reverse()
        self.assertEqual(rendered, dashboard.render_activity(plan))
        self.assertIn("2026-01-02T03:00:00Z", rendered)
        self.assertIn("3 with unknown time", rendered)

    def test_recent_activity_is_bounded_with_an_explicit_total(self):
        findings = [{"at": f"2026-01-02T03:04:{index:02d}Z", "by": "worker",
                     "text": f"event-{index:02d}"} for index in range(45)]
        rendered = dashboard.render_activity(roadmap([story(findings=findings)]))
        self.assertIn("Showing 40 of 45 recorded events (limit 40; 0 with unknown time)", rendered)
        self.assertEqual(rendered.count("<li>"), 40)
        self.assertIn("event-44", rendered)
        self.assertNotIn("event-04", rendered)

    def test_all_new_record_fields_are_html_escaped(self):
        malicious = '<img src="https://invalid.example/asset" onerror="alert(1)">'
        receipt = attempt(agent=malicious, role=malicious, skill=malicious,
                          requested_model=malicious, effective_model=malicious,
                          summary=malicious, subject_sha=malicious)
        plan = roadmap([story(title=malicious, owner=malicious, receipts={malicious: receipt},
                              history=[{"at": "2026-01-02T03:04:05Z", "by": malicious,
                                        "from": malicious, "to": malicious}],
                              findings=[{"at": "2026-01-02T03:04:05Z", "by": malicious,
                                         "text": malicious}])], [epic(title=malicious)])
        rendered = dashboard.render_html(plan)
        parser = Elements()
        parser.feed(rendered)
        self.assertNotIn("img", [tag for tag, _ in parser.elements])
        self.assertNotIn(malicious, rendered)
        self.assertIn("&lt;img src=&quot;", rendered)

    def test_snapshot_is_deterministic_offline_and_keeps_previous_sections(self):
        plan = roadmap([story(receipts={"attempt-1": attempt()})])
        original = copy.deepcopy(plan)
        rendered = dashboard.render_html(plan)
        self.assertEqual(plan, original)
        self.assertEqual(rendered, dashboard.render_html(copy.deepcopy(plan)))
        self.assertIn("Static snapshot at the generated time above", rendered)
        self.assertIn("generated 2026-01-02T03:04:05Z", rendered)
        for section in ("overview", "milestones", "attempts", "activity", "frontier", "streams",
                        "blockers", "critical-path", "acceptance", "diagnostics", "problems", "decisions"):
            self.assertIn(f'id="{section}"', rendered)
        parser = Elements()
        parser.feed(rendered)
        self.assertFalse({"script", "iframe", "link", "img", "audio", "video"}
                         & {tag for tag, _ in parser.elements})
        self.assertFalse(any("src" in attrs or "href" in attrs for _, attrs in parser.elements))


if __name__ == "__main__":
    unittest.main()
