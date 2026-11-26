#!/usr/bin/env python3
"""Unit tests for Antigravity CLI status line quota tracking and rendering."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import status


def make_payload(model="Gemini 4 Neon (High)", quota=None, extra=None):
    future_5h = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_wk = (datetime.now(timezone.utc) + timedelta(days=5, hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "agent_state": "working",
        "context_window": {
            "remaining_percentage": 92.4,
            "total_input_tokens": 34000,
            "total_output_tokens": 1200,
        },
        "conversation_id": "conv-1",
        "cwd": "/tmp",
        "email": "user@example.com",
        "model": {"id": model, "display_name": model} if isinstance(model, str) else model,
        "plan_tier": "Google AI Pro",
        "quota": {
            "3p-5h": {
                "remaining_fraction": 1,
                "reset_in_seconds": 0,
                "reset_time": "1970-01-01T00:00:00Z",
            },
            "3p-weekly": {
                "remaining_fraction": 1,
                "reset_in_seconds": 0,
                "reset_time": "1970-01-01T00:00:00Z",
            },
            "gemini-5h": {
                "remaining_fraction": 0.97,
                "reset_in_seconds": 12000,
                "reset_time": future_5h,
            },
            "gemini-weekly": {
                "remaining_fraction": 0.85,
                "reset_in_seconds": 475200,
                "reset_time": future_wk,
            },
        } if quota is None else quota,
        "sandbox": {"enabled": False},
        "terminal_width": 200,
    }
    if extra:
        payload.update(extra)
    return payload


def extract_quota_segment(rendered: str) -> str:
    plain = status.strip_ansi(rendered)
    return [seg.strip() for seg in plain.split("│")][-2]


class QuotaTrackingTests(unittest.TestCase):
    def setUp(self):
        # Prevent fallback from querying live processes or touching ~/.antigravity cache
        self.patcher = mock.patch.object(status, "refresh_quota_if_needed", return_value={})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_standard_gemini_models_use_gemini_5h_and_weekly(self):
        for model in (
            "Gemini 4 Neon (High)",
            "Gemini 4 Argon (Medium)",
            "Gemini 4 Hydrogen (High)",
            "Gemini 4 Carbon (High)",
            "Gemini 3.1 Pro (High)",
            "Orchestrator (Neon)",
            "Gemini Pro3",
        ):
            with self.subTest(model=model):
                d = make_payload(model=model)
                q = status.load_quota_for_model(model, d)
                self.assertEqual(q["source"], "payload")
                self.assertAlmostEqual(q["5h"]["remaining_percentage"], 97.0)
                self.assertAlmostEqual(q["weekly"]["remaining_percentage"], 85.0)
                seg = extract_quota_segment(status.render(d))
                self.assertIn("⬡ 5h: 97%", seg)
                self.assertIn("Wk: 85%", seg)
                self.assertNotIn("(now)", seg)

    def test_third_party_models_use_3p_and_hide_epoch_zero_reset(self):
        for model in (
            "Claude Opus 4.6 (Thinking)",
            "Claude Sonnet 4.6 (Thinking)",
            "Claude Haiku 4.5",
            "GPT-OSS 120B (Medium)",
            "GPT-5",
            "o1-preview",
            "o3-mini",
            "o4-mini",
        ):
            with self.subTest(model=model):
                d = make_payload(model=model)
                q = status.load_quota_for_model(model, d)
                self.assertEqual(q["source"], "payload")
                self.assertAlmostEqual(q["5h"]["remaining_percentage"], 100.0)
                self.assertAlmostEqual(q["weekly"]["remaining_percentage"], 100.0)
                self.assertEqual(q["5h"]["refreshes_in"], "")
                self.assertEqual(q["weekly"]["refreshes_in"], "")
                seg = extract_quota_segment(status.render(d))
                self.assertEqual(seg, "⬡ 5h: 100% · Wk: 100%")

    def test_active_3p_bucket_shows_percentages_and_reset_countdown(self):
        future_5h = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        future_wk = (datetime.now(timezone.utc) + timedelta(days=3, hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = make_payload(
            model="Claude Opus 4.6 (Thinking)",
            quota={
                "3p-5h": {"remaining_fraction": 0.42, "reset_time": future_5h},
                "3p-weekly": {"remaining_fraction": 0.65, "reset_time": future_wk},
                "gemini-5h": {"remaining_fraction": 0.99, "reset_time": future_5h},
                "gemini-weekly": {"remaining_fraction": 0.99, "reset_time": future_wk},
            },
        )
        seg = extract_quota_segment(status.render(d))
        self.assertIn("⬡ 5h: 42%", seg)
        self.assertIn("Wk: 65%", seg)
        self.assertIn("2h", seg)
        self.assertIn("3d", seg)

    def test_dedicated_argon_bucket_used_when_present_without_affecting_neon(self):
        future_wk = (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        quota = make_payload()["quota"]
        quota["gemini-argon-wtu-weekly"] = {
            "remaining_fraction": 0.55,
            "reset_time": future_wk,
        }

        d_argon = make_payload(model="Gemini 4 Argon (Medium)", quota=copy.deepcopy(quota))
        q_argon = status.load_quota_for_model("Gemini 4 Argon (Medium)", d_argon)
        self.assertIsNone(q_argon["5h"])
        self.assertAlmostEqual(q_argon["weekly"]["remaining_percentage"], 55.0)
        self.assertIn("⬡ Wk: 55%", extract_quota_segment(status.render(d_argon)))

        d_neon = make_payload(model="Gemini 4 Neon (High)", quota=copy.deepcopy(quota))
        q_neon = status.load_quota_for_model("Gemini 4 Neon (High)", d_neon)
        self.assertAlmostEqual(q_neon["5h"]["remaining_percentage"], 97.0)
        self.assertAlmostEqual(q_neon["weekly"]["remaining_percentage"], 85.0)

    def test_dedicated_argon_5h_and_weekly_both_supported(self):
        future_5h = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        future_wk = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        quota = make_payload()["quota"]
        quota["gemini-argon-5h"] = {"remaining_fraction": 0.30, "reset_time": future_5h}
        quota["gemini-argon-wtu-weekly"] = {"remaining_fraction": 0.60, "reset_time": future_wk}

        d = make_payload(model="Gemini 4 Argon (High)", quota=quota)
        q = status.load_quota_for_model("Gemini 4 Argon (High)", d)
        self.assertAlmostEqual(q["5h"]["remaining_percentage"], 30.0)
        self.assertAlmostEqual(q["weekly"]["remaining_percentage"], 60.0)

    def test_no_cross_family_fallback_when_3p_missing(self):
        future_wk = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = make_payload(
            model="Claude Opus 4.6 (Thinking)",
            quota={"gemini-weekly": {"remaining_fraction": 0.90, "reset_time": future_wk}},
        )
        q = status.load_quota_for_model("Claude Opus 4.6 (Thinking)", d)
        self.assertEqual(q, {})
        self.assertEqual(extract_quota_segment(status.render(d)), "⬡ Quota: sync /usage")

    def test_model_id_used_when_display_name_is_generic(self):
        d = make_payload(
            model={"id": "claude-opus-4-6", "display_name": "Primary Assistant"},
        )
        seg = extract_quota_segment(status.render(d))
        self.assertEqual(seg, "⬡ 5h: 100% · Wk: 100%")

    def test_disabled_buckets_and_remaining_amount(self):
        d_disabled = make_payload(
            model="Gemini 4 Neon (High)",
            quota={
                "gemini-5h": {"remaining_fraction": 0, "disabled": True},
                "gemini-weekly": {"remaining_fraction": 0, "disabled": True},
            },
        )
        self.assertEqual(extract_quota_segment(status.render(d_disabled)), "⬡ Quota: disabled")

        d_amount = make_payload(
            model="Gemini 4 Neon (High)",
            quota={
                "gemini-5h": {"remaining_amount": 120, "reset_in_seconds": 3600},
                "gemini-weekly": {"remaining_amount": 500, "reset_in_seconds": 86400},
            },
        )
        self.assertEqual(extract_quota_segment(status.render(d_amount)), "⬡ 5h: 120 (1h) · Wk: 500 (1d)")

    def test_null_fields_do_not_crash_render(self):
        d = make_payload(
            model=None,
            quota={
                "gemini-5h": {"remaining_fraction": None, "reset_time": None, "reset_in_seconds": None},
                "gemini-weekly": {"remaining_fraction": 0.75, "reset_in_seconds": 7200},
            },
            extra={"context_window": None, "sandbox": None, "agent_state": None},
        )
        rendered = status.strip_ansi(status.render(d))
        self.assertIn("AGY", rendered)
        self.assertIn("⬡ Wk: 75% (2h)", rendered)

    def test_alternative_window_key_names(self):
        d = make_payload(
            model="Gemini 4 Neon (High)",
            quota={
                "gemini-five-hour": {"remaining_fraction": 0.80, "reset_in_seconds": 3600},
                "gemini-seven-day": {"remaining_fraction": 0.90, "reset_in_seconds": 172800},
            },
        )
        seg = extract_quota_segment(status.render(d))
        self.assertEqual(seg, "⬡ 5h: 80% (1h) · Wk: 90% (2d)")

    def test_past_real_reset_time_still_shows_now(self):
        just_passed = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = make_payload(
            model="Gemini 4 Neon (High)",
            quota={"gemini-5h": {"remaining_fraction": 0.0, "reset_time": just_passed}},
        )
        self.assertEqual(extract_quota_segment(status.render(d)), "⬡ 5h: 0% (now)")


if __name__ == "__main__":
    unittest.main()
