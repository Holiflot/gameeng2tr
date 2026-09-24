from gameeng2tr.textproc import (
    SubtitleTracker,
    clean_ocr_lines,
    looks_like_text,
    similarity,
    split_sentences,
    split_speaker,
)


def test_clean_joins_lines_and_fixes_common_ocr_errors():
    lines = ["| don’t know what you remem-", "ber, Foundling…"]
    assert clean_ocr_lines(lines) == "I don't know what you remember, Foundling..."


def test_clean_fixes_lowercase_l_as_pronoun():
    assert clean_ocr_lines(["l think l'm lost."]) == "I think I'm lost."
    assert clean_ocr_lines(["all is lost"]) == "all is lost"


def test_clean_strips_edge_noise():
    assert clean_ocr_lines(["~~ Hello there. ::"]) == "Hello there."


def test_looks_like_text_rejects_noise():
    assert looks_like_text("Hello there.")
    assert not looks_like_text("-- ~ .")
    assert not looks_like_text("a")
    assert not looks_like_text("1 2 3 4 5 | ; ;")


def test_split_speaker():
    assert split_speaker("Tiel: You came back.") == ("Tiel", "You came back.")
    assert split_speaker("Old Man: Leave.") == ("Old Man", "Leave.")
    assert split_speaker("Note: this is not a speaker label because it is long") == (
        "Note",
        "this is not a speaker label because it is long",
    )
    assert split_speaker("It was 10:30 when he came.") == ("", "It was 10:30 when he came.")
    assert split_speaker("no speaker here") == ("", "no speaker here")


def test_split_sentences():
    assert split_sentences("Go. Now! Why? \"Fine.\" Ok") == ["Go.", "Now!", "Why?", "\"Fine.\"", "Ok"]


def test_similarity_ignores_case_and_punctuation():
    assert similarity("Hello, there!", "hello there") == 1.0
    assert similarity("", "") == 1.0
    assert similarity("abc", "") == 0.0
    assert similarity("You shall not pass", "You shall not pass.") == 1.0
    assert similarity("You shall not pass", "Completely different") < 0.5


def feed(tracker, texts, start=0.0, step=0.125):
    events = []
    t = start
    for text in texts:
        ev = tracker.update(text, t)
        if ev:
            events.append((ev.kind, ev.text))
        t += step
    return events


def test_tracker_requires_stable_text():
    tr = SubtitleTracker(stable_frames=2)
    assert feed(tr, ["Hello there."]) == []
    tr = SubtitleTracker(stable_frames=2)
    assert feed(tr, ["Hello there.", "Hello there."]) == [("show", "Hello there.")]


def test_tracker_ignores_ocr_jitter():
    tr = SubtitleTracker(stable_frames=2)
    events = feed(tr, ["The Shell remembers.", "The Shell remembers.", "The She1l remembers.", "The Shell remembers."])
    assert events == [("show", "The Shell remembers.")]


def test_tracker_waits_for_typewriter_effect():
    full = "You shouldn't have come back here, Foundling."
    frames = [full[:n] for n in range(8, len(full), 3)] + [full, full]
    events = feed(SubtitleTracker(stable_frames=2), frames)
    assert events == [("show", full)]


def test_tracker_new_subtitle_and_clear():
    tr = SubtitleTracker(stable_frames=2, clear_after=0.5)
    events = feed(tr, ["First line here.", "First line here.", "Second one now.", "Second one now."] + [""] * 6)
    assert events == [("show", "First line here."), ("show", "Second one now."), ("clear", "")]


def test_tracker_short_gap_does_not_clear():
    tr = SubtitleTracker(stable_frames=2, clear_after=0.7)
    events = feed(tr, ["Hold on.", "Hold on.", "", "", "Hold on.", "Hold on."])
    assert events == [("show", "Hold on.")]


def test_tracker_retranslates_when_subtitle_grows():
    tr = SubtitleTracker(stable_frames=2)
    first = "The pale knight waits beyond the gate of the old citadel."
    grown = first + " Do not keep him waiting."
    events = feed(tr, [first, first, grown, grown])
    assert events == [("show", first), ("show", grown)]
