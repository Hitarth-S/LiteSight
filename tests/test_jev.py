import pytest
from src.orchestrator.element_table import JevElementTable
from src.orchestrator.jev_policy import JevTypedPolicy


def test_jev_element_table_classification():
    # Input classification
    text_input = {"tag": "input", "type": "text", "role": "textbox", "label": "Search"}
    assert JevElementTable.classify_element(text_input) == "input"

    # Select dropdown classification
    dropdown = {"tag": "select", "role": "combobox", "label": "Department"}
    assert JevElementTable.classify_element(dropdown) == "select"

    # Clickable button classification
    btn = {"tag": "button", "role": "button", "label": "Add to Cart"}
    assert JevElementTable.classify_element(btn) == "clickable"

    # Submit button as input tag is clickable
    submit_inp = {"tag": "input", "type": "submit", "role": "button", "label": "Go"}
    assert JevElementTable.classify_element(submit_inp) == "clickable"


def test_jev_element_table_partitioning():
    elements = [
        {"index": 0, "tag": "select", "role": "combobox", "label": "Department", "is_visible": True, "bounding_box": {"x": 10, "y": 20, "width": 50, "height": 30}},
        {"index": 1, "tag": "input", "role": "searchbox", "label": "Search Amazon", "is_visible": True, "bounding_box": {"x": 70, "y": 20, "width": 300, "height": 30}},
        {"index": 2, "tag": "button", "role": "button", "label": "Cart", "is_visible": True, "bounding_box": {"x": 400, "y": 20, "width": 80, "height": 30}},
    ]

    pruned, partitions = JevElementTable.filter_and_summarize(elements)
    assert len(partitions["input"]) == 1
    assert partitions["input"][0]["index"] == 1
    assert len(partitions["select"]) == 1
    assert partitions["select"][0]["index"] == 0
    assert len(partitions["clickable"]) == 1
    assert partitions["clickable"][0]["index"] == 2

    table_text = JevElementTable.format_element_table_text(pruned)
    assert "[  0] select" in table_text
    assert "[  1] input" in table_text
    assert "[  2] clickable" in table_text


def test_jev_typed_policy_search_routing():
    policy = JevTypedPolicy()
    elements = [
        {"index": 8, "tag": "select", "role": "combobox", "label": "Select the department you want to search in", "value": "all", "is_visible": True, "bounding_box": {"x": 100, "y": 50, "width": 60, "height": 40}},
        {"index": 9, "tag": "input", "role": "searchbox", "label": "Search Amazon.in", "value": "", "is_visible": True, "bounding_box": {"x": 160, "y": 50, "width": 400, "height": 40}},
        {"index": 78, "tag": "a", "role": "link", "label": "Laptops", "value": "", "is_visible": True, "bounding_box": {"x": 200, "y": 300, "width": 100, "height": 30}}
    ]

    # Search step MUST match input [9], NEVER department select [8]
    decision = policy.decide_action("search for 'ergonomic mechanical keyboard'", elements)
    assert decision["operation"] == "TYPE_AND_SUBMIT"
    assert decision["target_index"] == 9
    assert decision["text_value"] == "ergonomic mechanical keyboard"


def test_jev_typed_policy_filter_and_cart():
    policy = JevTypedPolicy()
    elements = [
        {"index": 22, "tag": "a", "role": "link", "label": "4 Stars & Up", "is_visible": True, "bounding_box": {"x": 20, "y": 350, "width": 120, "height": 30}},
        {"index": 55, "tag": "button", "role": "button", "label": "Add to Cart", "is_visible": True, "bounding_box": {"x": 300, "y": 460, "width": 120, "height": 35}},
        {"index": 10, "tag": "a", "role": "link", "label": "1 item in cart", "is_visible": True, "bounding_box": {"x": 500, "y": 50, "width": 100, "height": 30}}
    ]

    # Rating filter
    dec_filter = policy.decide_action("apply 4-star filter", elements)
    assert dec_filter["operation"] == "CLICK"
    assert dec_filter["target_index"] == 22

    # Add to cart
    dec_cart = policy.decide_action("add the top result to cart", elements)
    assert dec_cart["operation"] == "CLICK"
    assert dec_cart["target_index"] == 55

    # Proceed to cart
    dec_view = policy.decide_action("proceed to cart", elements)
    assert dec_view["operation"] == "CLICK"
    assert dec_view["target_index"] == 10
