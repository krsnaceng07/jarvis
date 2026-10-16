"""Unit tests for Logbook analysis and card parsing.

Mirrors OpenClaw's ``extensions/logbook/src/analyze.test.ts`` 1:1.
"""

from __future__ import annotations

import datetime
import json
import pytest

from extensions.logbook.src.analyze import (
    clock_to_ms,
    parse_cards_json,
    parse_observation_segments,
    pick_keyframe_id,
    revision_window,
    sample_frames,
    select_batch_frames,
    validate_card_coverage,
)

DAY = "2026-07-03"


def day_ms(clock: str) -> int:
    ms = clock_to_ms(DAY, clock)
    if ms is None:
        raise ValueError(f"bad clock {clock}")
    return ms


class TestParseObservationSegments:
    start_ms = day_ms("10:00:00")
    end_ms = day_ms("10:15:00")

    def test_parses_and_clamps_segments(self) -> None:
        raw = json.dumps({
            "segments": [
                {"start": "09:55:00", "end": "10:05:00", "description": "VS Code: editing store.ts"},
                {"start": "10:05:00", "end": "10:20:00", "description": "Chrome: reviewing PR #99"},
            ]
        })
        segments = parse_observation_segments(raw=raw, day=DAY, start_ms=self.start_ms, end_ms=self.end_ms)
        assert len(segments) == 2
        assert segments[0]["startMs"] == self.start_ms
        assert segments[1]["endMs"] == self.end_ms

    def test_returns_empty_on_unparseable(self) -> None:
        assert parse_observation_segments(raw="no json here", day=DAY, start_ms=self.start_ms, end_ms=self.end_ms) == []

    def test_parses_12h_clocks(self) -> None:
        raw = "\n".join([
            "Here you go:",
            "```json",
            json.dumps({"segments": [{"start": "1:05 pm", "end": "1:05:30 pm", "description": "Reviewing"}]}),
            "```",
        ])
        segments = parse_observation_segments(
            raw=raw,
            day=DAY,
            start_ms=day_ms("13:00:00"),
            end_ms=day_ms("13:10:00"),
        )
        assert len(segments) == 1
        assert segments[0]["endMs"] - segments[0]["startMs"] == 30000

    @pytest.mark.parametrize(
        "day_val,clock_val",
        [
            (DAY, "25:00:00"),
            (DAY, "13:05 pm"),
            (DAY, "00:05 am"),
            (DAY, "half past nine"),
            ("not-a-day", "10:00:00"),
        ],
    )
    def test_rejects_malformed_clock(self, day_val: str, clock_val: str) -> None:
        raw = json.dumps([{"start": clock_val, "end": "13:06:00", "description": "Invalid"}])
        assert parse_observation_segments(raw=raw, day=day_val, start_ms=self.start_ms, end_ms=self.end_ms) == []


class TestParseCardsJson:
    window_start_ms = day_ms("10:00:00")
    window_end_ms = day_ms("11:00:00")

    def card(self, overrides: dict | None = None) -> dict:
        base = {
            "startTime": "10:00:00",
            "endTime": "10:30:00",
            "category": "coding",
            "title": "Working on logbook store",
            "summary": "Implemented SQLite store",
            "detailedSummary": "Added frames and cards tables.",
            "distractions": [],
            "appSites": {"primary": "github.com"},
        }
        if overrides:
            base.update(overrides)
        return base

    def test_accepts_valid_card_array(self) -> None:
        result = parse_cards_json(
            raw=f"Here you go:\n{json.dumps([self.card({'category': 'CODING', 'appSites': {'primary': 'https://GitHub.com/openclaw'}})])}\nHope that helps!",
            day=DAY,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
        )
        assert result["ok"] is True
        draft = result["drafts"][0]
        assert draft["category"] == "coding"
        assert draft["appPrimary"] == "github.com"

    def test_maps_unknown_categories_to_other(self) -> None:
        result = parse_cards_json(
            raw=json.dumps([self.card({"category": "quantum-vibes"})]),
            day=DAY,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
        )
        assert result["ok"] is True
        assert result["drafts"][0]["category"] == "other"

    def test_trims_sub_minute_overlaps_and_rejects_large(self) -> None:
        trimmed = parse_cards_json(
            raw=json.dumps([
                self.card({"startTime": "10:00:00", "endTime": "10:30:30"}),
                self.card({"startTime": "10:30:00", "endTime": "11:00:00", "title": "Second"}),
            ]),
            day=DAY,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
        )
        assert trimmed["ok"] is True
        first = trimmed["drafts"][0]
        second = trimmed["drafts"][1]
        assert second["startMs"] == first["endMs"]

        rejected = parse_cards_json(
            raw=json.dumps([
                self.card({"startTime": "10:00:00", "endTime": "10:45:00"}),
                self.card({"startTime": "10:30:00", "endTime": "11:00:00", "title": "Second"}),
            ]),
            day=DAY,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
        )
        assert rejected["ok"] is False
        assert "overlap" in rejected["error"]

    def test_reports_actionable_errors(self) -> None:
        result = parse_cards_json(
            raw=json.dumps([self.card({"startTime": "13:05 pm"})]),
            day=DAY,
            window_start_ms=self.window_start_ms,
            window_end_ms=self.window_end_ms,
        )
        assert result["ok"] is False
        assert "startTime" in result["error"]


class TestSelectBatchFrames:
    window_ms = 15 * 60000
    t0 = day_ms("10:00:00")

    def frame(self, frame_id: int, offset_sec: int) -> dict:
        return {"id": frame_id, "capturedAtMs": self.t0 + offset_sec * 1000}

    def test_keeps_in_progress_window_open(self) -> None:
        frames = [self.frame(1, 0), self.frame(2, 30), self.frame(3, 60)]
        assert select_batch_frames(frames=frames, window_ms=self.window_ms, now_ms=self.t0 + 5 * 60000) is None

    def test_closes_elapsed_window_at_boundary(self) -> None:
        frames = [self.frame(1, 0), self.frame(2, 30), self.frame(3, 60)]
        selection = select_batch_frames(frames=frames, window_ms=self.window_ms, now_ms=self.t0 + self.window_ms + 1000)
        assert selection is not None
        assert selection["frameIds"] == [1, 2, 3]
        assert selection["startMs"] == self.t0
        assert selection["endMs"] == self.t0 + self.window_ms

    def test_splits_on_capture_gaps(self) -> None:
        frames = [self.frame(1, 0), self.frame(2, 30), self.frame(3, 400)]
        selection = select_batch_frames(frames=frames, window_ms=self.window_ms, now_ms=self.t0 + 60000)
        assert selection is not None
        assert selection["frameIds"] == [1, 2]
        assert selection["endMs"] == self.t0 + 30000 + 1

    def test_force_closes_in_progress_window(self) -> None:
        frames = [self.frame(1, 0), self.frame(2, 30)]
        assert select_batch_frames(frames=frames, window_ms=self.window_ms, now_ms=self.t0 + 60000) is None
        forced = select_batch_frames(frames=frames, window_ms=self.window_ms, now_ms=self.t0 + 60000, force=True)
        assert forced is not None
        assert forced["frameIds"] == [1, 2]
        assert forced["endMs"] == self.t0 + 30000 + 1


class TestSampleFrames:
    def test_keeps_small_and_samples_large(self) -> None:
        assert sample_frames([1, 2, 3], 16) == [1, 2, 3]
        assert sample_frames([1, 2, 3], 1) == [1]
        assert sample_frames([1, 2, 3], 0) == []
        sampled = sample_frames(list(range(100)), 16)
        assert len(sampled) <= 16
        assert sampled[0] == 0
        assert sampled[-1] == 99


class TestValidateCardCoverage:
    window = {"windowStartMs": day_ms("10:00:00"), "windowEndMs": day_ms("11:00:00")}

    def span(self, start: str, end: str) -> dict:
        return {"startMs": day_ms(start), "endMs": day_ms(end)}

    def test_accepts_covering_drafts(self) -> None:
        result = validate_card_coverage(
            drafts=[self.span("10:01:00", "10:30:00"), self.span("10:30:00", "10:59:00")],
            required_spans=[self.span("10:00:00", "11:00:00")],
            **self.window,
        )
        assert result["ok"] is True

    def test_rejects_partial_outputs(self) -> None:
        result = validate_card_coverage(
            drafts=[self.span("10:30:00", "11:00:00")],
            required_spans=[self.span("10:00:00", "10:30:00"), self.span("10:30:00", "11:00:00")],
            **self.window,
        )
        assert result["ok"] is False
        assert "not covered" in result["error"]


class TestRevisionWindowAndKeyframe:
    def test_expands_window(self) -> None:
        window = revision_window(
            batch_start_ms=day_ms("10:30:00"),
            batch_end_ms=day_ms("10:45:00"),
            previous_cards=[
                {
                    "id": 1,
                    "day": DAY,
                    "startMs": day_ms("10:00:00"),
                    "endMs": day_ms("10:30:00"),
                    "title": "t",
                    "summary": "s",
                    "detail": "",
                    "category": "coding",
                    "distractions": [],
                }
            ],
        )
        assert window["startMs"] == day_ms("10:00:00")
        assert window["endMs"] == day_ms("10:45:00")

    def test_picks_closest_midpoint_keyframe(self) -> None:
        frames = [
            {"id": 1, "capturedAtMs": day_ms("10:00:00")},
            {"id": 2, "capturedAtMs": day_ms("10:14:00")},
            {"id": 3, "capturedAtMs": day_ms("10:29:00")},
        ]
        keyframe = pick_keyframe_id(
            {"startMs": day_ms("10:00:00"), "endMs": day_ms("10:30:00")},
            frames,
        )
        assert keyframe == 2
