"""Rendering helpers, formatting, presets, key decoding and layout invariants."""

import pytest

from pybtop import fmt
from pybtop.app import App, CliOptions
from pybtop.config import Config
from pybtop.defaults import DEFAULTS
from pybtop.keys import KeyDecoder, MouseEvent
from pybtop.presets import PresetError, parse_preset_string, select_preset
from pybtop.render import ansi
from pybtop.ui import layout
from pybtop.ui.pen import c_round, graph_rows


def test_graph_rows_fill_from_the_bottom_with_two_samples_per_cell():
    assert graph_rows([0.0, 100.0], width=1, height=1, no_zero=False) == ["\u28b8"]  # left empty, right full
    assert graph_rows([100.0, 100.0], width=1, height=1, no_zero=False) == ["\u28ff"]


def test_graph_rows_leaves_missing_history_blank():
    rows = graph_rows([100.0], width=2, height=1, no_zero=False)
    assert rows == [" " + "\u28b8"]


def test_graph_rows_bottom_row_shows_baseline_when_no_zero():
    assert graph_rows([0.0, 0.0], width=1, height=2, no_zero=True) == [" ", "\u28c0"]


def test_c_round_rounds_halves_away_from_zero():
    assert c_round(58.5) == 59
    assert c_round(2.5) == 3


def test_floating_humanizer_matches_btop_samples():
    assert fmt.floating_humanizer(0) == "0 Byte"
    assert fmt.floating_humanizer(1024) == "1.00 KiB"
    assert fmt.floating_humanizer(123456789) == "117 MiB"
    assert fmt.floating_humanizer(1234567, shorten=True) == "1.2M"
    assert fmt.floating_humanizer(1000, base10=True) == "1.00 KB"

    assert ansi.rgb_to_256((0, 0, 0)) == 16
    assert ansi.rgb_to_256((255, 255, 255)) == 231


def test_parse_color_accepts_hex_grey_and_decimal_triples():
    assert ansi.parse_color("#ff0000") == (255, 0, 0)
    assert ansi.parse_color("#40") == (64, 64, 64)
    assert ansi.parse_color("0 128 255") == (0, 128, 255)
    assert ansi.parse_color("") is None


@pytest.mark.parametrize(
    "value, expected",
    [(0, "0 Byte"), (13.0 * 2**30, "13.0 GiB"), (251 * 2**30, "251 GiB"), (1.78 * 2**40, "1.78 TiB"), (6.14 * 2**20, "6.14 MiB")],
)
def test_humanize_bytes_keeps_three_significant_characters(value, expected):
    assert fmt.humanize_bytes(value) == expected


def test_rate_and_bits_use_binary_units_by_default():
    assert fmt.humanize_rate(8.72 * 1024) == "8.72 KiB/s"
    assert fmt.humanize_bits_rate(1024) == "8.00 Kibps"


def test_preset_string_round_trips_and_validates_entries():
    presets = parse_preset_string("cpu:1:default,proc:0:default cpu:0:block,net:0:tty")
    assert [p.boxes for p in presets] == [["cpu", "proc"], ["cpu", "net"]]
    assert presets[0].entry("cpu").position == 1
    assert presets[1].entry("cpu").symbol == "block"
    with pytest.raises(PresetError):
        parse_preset_string("bogus:0:default")
    with pytest.raises(PresetError):
        parse_preset_string("cpu:2:default")
    with pytest.raises(PresetError):
        parse_preset_string(" ".join(["cpu:0:default"] * 10))


def test_selecting_past_the_last_preset_clamps_to_it():
    presets = parse_preset_string("cpu:0:default net:0:default")
    assert select_preset(presets, 9).boxes == ["net"]
    assert select_preset(presets, 0) is None


def test_key_decoder_recognises_arrows_and_waits_for_partial_sequences():
    dec = KeyDecoder()
    assert dec.feed(b"\x1b[A") == ["up"]
    assert dec.feed(b"\x1b[") == []  # incomplete: held
    assert dec.feed(b"5~") == ["pgup"]
    assert dec.feed(b"\x1b") == []  # lone ESC waits for the timeout
    assert dec.flush() == ["esc"]


def test_key_decoder_drops_unknown_csi_without_emitting_its_bytes():
    dec = KeyDecoder()
    assert dec.feed(b"\x1b[99;2Xq") == ["q"]


def test_key_decoder_reads_sgr_clicks_and_wheel_and_ignores_releases_and_other_buttons():
    dec = KeyDecoder()
    keys = dec.feed(b"\x1b[<0;12;5M\x1b[<64;3;4M\x1b[<0;12;5m\x1b[<2;1;1M\x1b[<65;7;8M")
    assert keys == [MouseEvent("click", 12, 5), MouseEvent("scroll_up", 3, 4), MouseEvent("scroll_down", 7, 8)]


def test_key_decoder_holds_a_split_mouse_report_and_flush_never_replays_its_digits():
    dec = KeyDecoder()
    assert dec.feed(b"\x1b[<0;12;") == []
    assert dec.feed(b"5M") == [MouseEvent("click", 12, 5)]
    assert dec.feed(b"\x1b[<0;1") == []
    assert dec.flush() == []  # the digits would otherwise act as keys (1-5 toggle boxes)


def test_layout_boxes_do_not_overlap_and_fill_the_screen():
    for width, height in [(80, 24), (120, 40), (160, 50)]:
        rects = layout.compute(width, height, gpu_count=4)
        covered = set()
        for rect in rects.values():
            for r in range(rect.row, rect.row + rect.height):
                for c in range(rect.col, rect.col + rect.width):
                    assert (r, c) not in covered, f"overlap at {(r, c)} for {width}x{height}"
                    covered.add((r, c))
        assert len(covered) == width * height


def test_layout_matches_btop_120x40_rows_with_four_gpus():
    rects = layout.compute(120, 40, gpu_count=4)
    assert (rects["cpu"].row, rects["cpu"].height) == (0, 17)
    assert (rects["mem"].row, rects["mem"].height) == (17, 11)
    assert (rects["net"].row, rects["net"].height) == (28, 12)
    assert (rects["proc"].col, rects["proc"].width) == (54, 66)


def test_elapsed_text_drops_seconds_once_a_day_has_passed():
    assert fmt.elapsed_text(3723) == "01:02:03"
    assert fmt.elapsed_text(90061) == "1d 01:01"


def test_mouse_clicks_open_and_hide_the_detail_panel_and_fold_tree_rows(tmp_path):
    app = App(Config(DEFAULTS), CliOptions(), str(tmp_path))
    app.render(120, 40)
    x, y, _, _, top, _ = app.proc_area
    row_click = MouseEvent("click", x + 15, top + 3)  # second visible process row
    app.handle_key(row_click)
    app.render(120, 40)
    assert app.selected_index == 1
    app.handle_key(row_click)  # clicking the selected row opens its detail
    assert app.detail is not None and app.detail.pid == app.selected_pid
    app.render(120, 40)
    hide = next(m for m in app.mouse_map if m[0] == "enter" and m[1] == y)  # 'hide ↵' on the panel's top border
    app.handle_key(MouseEvent("click", hide[2], hide[1]))
    assert app.detail is None

    app.handle_key("e")  # tree view: Space folds the selected parent and unfolds it again
    parents = {p.ppid for p in app.procs}
    index = next(i for i, p in enumerate(app.procs) if p.pid in parents)
    app._set_selection(index)
    shown = len(app.procs)
    app.handle_key("space")
    assert app.procs[index].pid in app.collapsed and len(app.procs) < shown
    app.handle_key("space")
    assert not app.collapsed and len(app.procs) == shown
