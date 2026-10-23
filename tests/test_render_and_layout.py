"""Rendering helpers, formatting, presets, key decoding and layout invariants."""

import itertools

import pytest

from pybtop import fmt
from pybtop.keys import KeyDecoder
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


def test_layout_covers_the_screen_for_every_box_subset_and_position_option():
    boxes = ("cpu", "mem", "net", "proc")
    options = [(bottom, left, below) for bottom in (False, True) for left in (False, True) for below in (False, True)]
    for width, height in [(80, 24), (120, 40), (160, 50)]:
        for count in range(1, 5):
            for subset in itertools.combinations(boxes, count):
                for cpu_bottom, proc_left, mem_below_net in options:
                    rects = layout.compute(width, height, 4, subset, cpu_bottom, proc_left, mem_below_net)
                    assert set(rects) == set(subset)
                    covered = set()
                    for rect in rects.values():
                        for r in range(rect.row, rect.row + rect.height):
                            for c in range(rect.col, rect.col + rect.width):
                                assert (r, c) not in covered, f"overlap {subset} {width}x{height}"
                                covered.add((r, c))
                    assert len(covered) == width * height, f"gap {subset} {width}x{height}"


def test_position_options_move_boxes_like_btop_calc_sizes_at_120x40():
    rects = layout.compute(120, 40, gpu_count=4, cpu_bottom=True, proc_left=True, mem_below_net=True)
    assert (rects["cpu"].row, rects["cpu"].height) == (23, 17)
    assert (rects["net"].row, rects["net"].col, rects["net"].height, rects["net"].width) == (0, 66, 12, 54)
    assert (rects["mem"].row, rects["mem"].col, rects["mem"].height, rects["mem"].width) == (12, 66, 11, 54)
    assert (rects["proc"].row, rects["proc"].col, rects["proc"].height, rects["proc"].width) == (0, 0, 23, 66)


def test_hiding_mem_gives_net_the_whole_left_column_and_hiding_proc_widens_it():
    rects = layout.compute(120, 40, gpu_count=4, shown={"cpu", "net", "proc"})
    assert (rects["net"].row, rects["net"].height, rects["net"].width) == (17, 23, 54)
    rects = layout.compute(120, 40, gpu_count=4, shown={"cpu", "net"})
    assert (rects["net"].row, rects["net"].height, rects["net"].width) == (17, 23, 120)
