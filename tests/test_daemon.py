import pytest

from aerospace_dwindle.daemon import Daemon, Settings


class FakeAeroSpace:
    def __init__(self):
        self.calls = []

    def split(self, wid, orientation):
        self.calls.append(("split", wid, orientation))
        return 0

    def refresh(self):
        self.calls.append(("refresh",))
        return 0


class Sizes:
    """window_size fake: per window a list of successive reads (last repeats)."""

    def __init__(self, **by_wid):
        self.reads = {int(k[1:]): list(v) for k, v in by_wid.items()}

    def __call__(self, wid):
        seq = self.reads.get(wid)
        if not seq:
            return None
        return seq.pop(0) if len(seq) > 1 else seq[0]


def make(sizes, **settings):
    aero = FakeAeroSpace()
    sleeps = []
    d = Daemon(aero, sizes, Settings(**settings), sleep=sleeps.append)
    return d, aero, sleeps


@pytest.mark.parametrize(
    "size, orientation",
    [((800, 600), "horizontal"), ((600, 800), "vertical"), ((500, 500), "horizontal")],
)
def test_window_detected_splits_along_longer_edge(size, orientation):
    d, aero, _ = make(Sizes(w1=[size]))
    d.handle_line('{"_event":"window-detected","windowId":1,"workspace":"M"}')
    assert aero.calls == [("split", 1, orientation)]


def test_focus_changed_refreshes_after_delay():
    d, aero, sleeps = make(Sizes(w1=[(800, 600)]), refresh_delay=0.05)
    d.handle_line('{"_event":"focus-changed","windowId":1,"workspace":"M"}')
    assert aero.calls == [("refresh",)]
    assert sleeps == [0.05]


def test_focus_changed_without_window_still_refreshes():
    d, aero, _ = make(Sizes())
    d.handle({"_event": "focus-changed", "workspace": "M"})
    assert aero.calls == [("refresh",)]


def test_on_focus_splits_focused_window():
    d, aero, _ = make(Sizes(w1=[(600, 800)]), on_focus=True)
    d.handle({"_event": "focus-changed", "windowId": 1})
    assert aero.calls == [("split", 1, "vertical")]


def test_waits_for_size_to_settle():
    d, aero, sleeps = make(
        Sizes(w1=[(100, 900), (500, 600), (900, 600), (900, 600)]), settle_step=0.02
    )
    d.handle({"_event": "window-detected", "windowId": 1})
    assert aero.calls == [("split", 1, "horizontal")]
    assert sleeps == [0.02] * 3


def test_settle_gives_up_and_uses_last_size():
    d, aero, sleeps = make(
        Sizes(w1=[(1, 9), (2, 9), (3, 9), (9, 1), (9, 2)]), settle_tries=3
    )
    d.handle({"_event": "window-detected", "windowId": 1})
    assert aero.calls == [("split", 1, "horizontal")]  # last read: 9x1
    assert len(sleeps) == 3


def test_vanished_window_is_not_split():
    d, aero, _ = make(Sizes())
    d.handle({"_event": "window-detected", "windowId": 7})
    assert aero.calls == []


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[1, 2]",
        '{"_event":"window-detected","workspace":"M"}',
        '{"_event":"mode-changed","mode":"main"}',
        '{"_event":"focused-workspace-changed","windowId":1}',
    ],
)
def test_ignored_lines(line):
    d, aero, _ = make(Sizes(w1=[(800, 600)]))
    d.handle_line(line)
    assert aero.calls == []


def test_run_processes_stream_in_order():
    d, aero, _ = make(Sizes(w1=[(800, 600)], w2=[(400, 600)]))
    d.run(
        [
            '{"_event":"window-detected","windowId":1}\n',
            '{"_event":"focus-changed","windowId":1}\n',
            '{"_event":"window-detected","windowId":2}\n',
        ]
    )
    assert aero.calls == [
        ("split", 1, "horizontal"),
        ("refresh",),
        ("split", 2, "vertical"),
    ]
