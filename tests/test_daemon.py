import pytest

from aerospace_dwindle.daemon import Daemon, Settings


class FakeAeroSpace:
    def __init__(self, windows=None, monitors=None):
        self.calls = []
        self.workspaces = windows or {}  # name -> [(wid, layout)]; absent: query fails
        self.monitors = monitors or {}  # workspace -> monitor id

    def split(self, wid, orientation):
        self.calls.append(("split", wid, orientation))
        return 0

    def refresh(self):
        self.calls.append(("refresh",))
        return 0

    def windows(self, workspace):
        self.calls.append(("windows", workspace))
        return self.workspaces.get(workspace)

    def workspace_monitor(self, workspace):
        return self.monitors.get(workspace)

    def flatten(self, workspace):
        self.calls.append(("flatten", workspace))
        return 0

    def set_root_orientation(self, workspace, orientation):
        self.calls.append(("root", workspace, orientation))
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


MONITORS = {1: (3840, 2160), 2: (1080, 1920), 3: (5120, 1440)}


def make(sizes, windows=None, monitors=None, **settings):
    aero = FakeAeroSpace(windows, monitors)
    sleeps = []
    d = Daemon(
        aero, sizes, Settings(**settings), sleep=sleeps.append, monitor_size=MONITORS.get
    )
    return d, aero, sleeps


def without_queries(calls):
    return [c for c in calls if c[0] != "windows"]


@pytest.mark.parametrize(
    "size, orientation",
    [((800, 600), "horizontal"), ((600, 800), "vertical"), ((500, 500), "horizontal")],
)
def test_window_detected_splits_along_longer_edge(size, orientation):
    d, aero, _ = make(Sizes(w1=[size]))
    d.handle_line('{"_event":"window-detected","windowId":1,"workspace":"M"}')
    # workspace query fails in this fake -> size-based split
    assert without_queries(aero.calls) == [("split", 1, orientation)]


def test_focus_changed_queries_workspace_after_delay():
    d, aero, sleeps = make(Sizes(w1=[(800, 600)]), refresh_delay=0.05)
    d.handle_line('{"_event":"focus-changed","windowId":1,"workspace":"M"}')
    assert aero.calls == [("windows", "M")]  # the query is the refresh poke
    assert sleeps == [0.05]


def test_focus_changed_without_workspace_pokes():
    d, aero, _ = make(Sizes())
    d.handle({"_event": "focus-changed"})
    assert aero.calls == [("refresh",)]


def test_on_focus_splits_focused_window():
    d, aero, _ = make(Sizes(w1=[(600, 800)]), on_focus=True)
    d.handle({"_event": "focus-changed", "windowId": 1})  # no workspace info
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


# --- small workspaces: default orientation ----------------------------------

TALL = Sizes(w1=[(600, 900)], w2=[(600, 900)], w3=[(600, 900)], w4=[(600, 900)])


def detected(d, wid, ws="M"):
    d.handle({"_event": "window-detected", "windowId": wid, "workspace": ws})


def focused(d, wid, ws="M"):
    d.handle({"_event": "focus-changed", "windowId": wid, "workspace": ws})


@pytest.mark.parametrize("monitor, root", [(1, "horizontal"), (2, "vertical"), (None, "horizontal")])
def test_single_window_gets_default_orientation_ignoring_frame(monitor, root):
    d, aero, _ = make(TALL, {"M": [(1, "h_tiles")]}, {"M": monitor} if monitor else {})
    detected(d, 1)
    # no split: as only child it would set the root orientation from the frame
    assert without_queries(aero.calls) == [("flatten", "M"), ("root", "M", root)]


def test_explicit_default_orientation():
    d, aero, _ = make(TALL, {"M": [(1, "h_tiles")]}, {"M": 1}, default_orientation="vertical")
    detected(d, 1)
    assert without_queries(aero.calls) == [("flatten", "M"), ("root", "M", "vertical")]


@pytest.mark.parametrize(
    "monitor, root, inner",
    [
        (1, "horizontal", "vertical"),  # 16:9: halves are tall
        (3, "horizontal", "horizontal"),  # 32:9: halves still wide
        (2, "vertical", "horizontal"),  # portrait: halves are wide
        (None, "horizontal", "vertical"),  # unknown monitor: opposite of root
    ],
)
def test_two_windows_side_by_side_and_wrapped(monitor, root, inner):
    windows = {"M": [(1, "v_tiles"), (2, "v_tiles")]}
    d, aero, _ = make(TALL, windows, {"M": monitor} if monitor else {})
    detected(d, 2)
    assert without_queries(aero.calls) == [
        ("flatten", "M"),
        ("root", "M", root),
        ("split", 1, inner),
        ("split", 2, inner),
    ]


def test_three_windows_split_by_size():
    windows = {"M": [(1, "h_tiles"), (2, "v_tiles"), (3, "v_tiles")]}
    d, aero, _ = make(TALL, windows, {"M": 1})
    detected(d, 3)
    assert without_queries(aero.calls) == [("split", 3, "vertical")]


def test_floating_windows_are_ignored_and_not_counted():
    windows = {"M": [(1, "h_tiles"), (2, "v_tiles"), (3, "floating")]}
    d, aero, _ = make(TALL, windows, {"M": 1})
    detected(d, 3)
    assert without_queries(aero.calls) == []
    detected(d, 2)  # 2 tiling windows -> reset despite 3 total
    assert ("flatten", "M") in aero.calls
    assert ("split", 3, "vertical") not in aero.calls


def test_new_window_missing_from_list_falls_back_to_size():
    d, aero, _ = make(TALL, {"M": [(1, "h_tiles")]}, {"M": 1})
    detected(d, 2)
    assert without_queries(aero.calls) == [("split", 2, "vertical")]


def test_close_down_to_two_windows_resets_once():
    windows = {"M": [(1, "h_tiles"), (2, "v_tiles"), (3, "v_tiles")]}
    d, aero, _ = make(TALL, windows, {"M": 1})
    focused(d, 1)  # 3 windows: nothing to do
    assert without_queries(aero.calls) == []
    windows["M"].pop()  # window 3 closed
    focused(d, 2)
    assert without_queries(aero.calls) == [
        ("flatten", "M"),
        ("root", "M", "horizontal"),
        ("split", 1, "vertical"),
        ("split", 2, "vertical"),
    ]
    aero.calls.clear()
    focused(d, 1)  # count unchanged: leave manual changes alone
    assert without_queries(aero.calls) == []


def test_detect_then_focus_resets_once():
    windows = {"M": [(1, "h_tiles")]}
    d, aero, _ = make(TALL, windows, {"M": 1})
    detected(d, 1)
    focused(d, 1)
    assert without_queries(aero.calls) == [("flatten", "M"), ("root", "M", "horizontal")]


def test_focus_on_empty_workspace_does_nothing():
    d, aero, _ = make(TALL, {"M": []}, {"M": 1})
    d.handle({"_event": "focus-changed", "workspace": "M"})
    assert without_queries(aero.calls) == []


def test_counts_are_per_workspace():
    windows = {"A": [(1, "h_tiles")], "B": [(2, "h_tiles")]}
    d, aero, _ = make(TALL, windows, {"A": 1, "B": 2})
    focused(d, 1, "A")
    focused(d, 2, "B")
    focused(d, 1, "A")
    assert without_queries(aero.calls) == [
        ("flatten", "A"),
        ("root", "A", "horizontal"),
        ("flatten", "B"),
        ("root", "B", "vertical"),
    ]
