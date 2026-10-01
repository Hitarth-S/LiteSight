import pytest
import os
import json
from server import SERVER_EXECUTOR
from src.vision.omni_parser import OmniVisualParser
from src.state.personalization import RetrievalAugmentedPersonalization


def test_resolve_fast_path_retains_intent_keyword_hits():
    """
    Verifies that filter and cart intent bonuses are NOT wiped out by keyword_hits resetting.
    """
    elements = [
        {
            "index": 1,
            "tag": "span",
            "role": "link",
            "label": "4 Stars & Up and other customer ratings for this category",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 300, "width": 180, "height": 30}
        },
        {
            "index": 2,
            "tag": "a",
            "role": "link",
            "label": "Electronics and computers store portal",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 400, "width": 180, "height": 30}
        }
    ]

    action = SERVER_EXECUTOR._resolve_fast_path_action("click the 4 star or above filter", elements)
    assert action is not None
    assert action["operation"] == "CLICK"
    assert action["target_index"] == 1


def test_elements_without_explicit_is_visible_are_not_dropped():
    """
    Verifies that candidate elements without explicit 'is_visible: True' (default from extension or API)
    are properly evaluated rather than dropped.
    """
    elements = [
        {
            "index": 42,
            "tag": "button",
            "role": "button",
            "label": "Submit Application",
            "value": "",
            # 'is_visible' intentionally omitted
            "bounding_box": {"x": 200, "y": 500, "width": 140, "height": 45}
        }
    ]

    action = SERVER_EXECUTOR._resolve_fast_path_action("click submit application", elements)
    assert action is not None
    assert action["target_index"] == 42
    assert action["operation"] == "CLICK"


def test_omni_parser_iou_handles_diverse_bounding_box_structures():
    """
    Verifies that _calculate_iou does not raise KeyError when comparing against
    various PII box representations (list, tuple, dict with bbox, bounding_box).
    """
    parser = OmniVisualParser()

    cand = {"x": 100, "y": 100, "width": 200, "height": 50}

    # Format 1: standard dict with x, y, width, height
    pii_1 = {"x": 120, "y": 110, "width": 150, "height": 40}
    iou1 = parser._calculate_iou(cand, pii_1)
    assert iou1 > 0.0

    # Format 2: bbox as list [x, y, w, h]
    pii_2 = {"bbox": [120, 110, 150, 40]}
    iou2 = parser._calculate_iou(cand, pii_2)
    assert iou2 > 0.0

    # Format 3: nested bounding_box dict
    pii_3 = {"bounding_box": {"x": 120, "y": 110, "width": 150, "height": 40}}
    iou3 = parser._calculate_iou(cand, pii_3)
    assert iou3 > 0.0

    # Format 4: non-overlapping box
    pii_4 = {"x": 800, "y": 800, "width": 50, "height": 50}
    iou4 = parser._calculate_iou(cand, pii_4)
    assert iou4 == 0.0


def test_personalization_deduplication(tmp_path):
    """
    Verifies that repeated preference additions for the same domain do not accumulate duplicates.
    """
    db_file = str(tmp_path / "test_prefs.json")
    rap = RetrievalAugmentedPersonalization(db_path=db_file)

    rap.learn_preference("example.com", "Always use dark mode.")
    rap.learn_preference("example.com", "Always use dark mode.")
    rap.learn_preference("example.com", "Always use dark mode.")

    matches = [p for p in rap.preferences if p.get("domain") == "example.com"]
    assert len(matches) == 1
