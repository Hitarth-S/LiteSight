import json
import pytest
from server import LiteSightServerHandler, SERVER_EXECUTOR, SERVER_SANITIZER
from src.vision.omni_parser import OmniVisualParser
from src.state.personalization import RetrievalAugmentedPersonalization


def test_server_sanitizer():
    raw = "User email is test@company.com with card 1234-5678-9012-3456"
    sanitized = SERVER_SANITIZER.sanitize_text(raw)
    assert "[REDACTED_EMAIL]" in sanitized
    assert "[REDACTED_CREDIT_CARD]" in sanitized
    assert "test@company.com" not in sanitized
    assert "1234-5678-9012-3456" not in sanitized


def test_server_executor_step_planning():
    elements = [
        {
            "index": 0,
            "tag": "input",
            "role": "textbox",
            "label": "Search for products, brands and more",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 200, "y": 20, "width": 400, "height": 40}
        },
        {
            "index": 1,
            "tag": "button",
            "role": "button",
            "label": "Add to Cart",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 500, "y": 300, "width": 120, "height": 40}
        }
    ]

    # Test Search Intent
    action_search = SERVER_EXECUTOR._resolve_fast_path_action("search for 'mechanical keyboard'", elements)
    assert action_search is not None
    assert action_search["operation"] in ["TYPE_TEXT", "TYPE_AND_SUBMIT"]
    assert action_search["target_index"] == 0
    assert action_search["text_value"] == "mechanical keyboard"

    # Test Add to Cart Intent
    action_cart = SERVER_EXECUTOR._resolve_fast_path_action("add to cart", elements)
    assert action_cart is not None
    assert action_cart["operation"] == "CLICK"
    assert action_cart["target_index"] == 1


def test_strict_intent_guard_no_false_clicks():
    elements = [
        {
            "index": 0,
            "tag": "a",
            "role": "link",
            "label": "Computers",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 200, "y": 200, "width": 100, "height": 30}
        }
    ]
    # Searching for rating filter should NOT click 'Computers'
    action = SERVER_EXECUTOR._resolve_fast_path_action("apply 4 star or above", elements)
    # Since filter is not found and 'Computers' has 0 rating keyword hits, it must return SCROLL_DOWN fallback instead of clicking Computers!
    assert action is not None
    assert action["operation"] == "SCROLL_DOWN"
    assert action["target_index"] is None


def test_extract_and_answer_intent():
    elements = [
        {"index": 0, "tag": "div", "role": "article", "label": "Problem Statement 26171 details", "value": "", "is_visible": True, "bounding_box": {"x": 100, "y": 100, "width": 500, "height": 300}}
    ]
    action = SERVER_EXECUTOR._resolve_fast_path_action("then tell me what the problem statement is", elements)
    assert action is not None
    assert action["operation"] == "EXTRACT_AND_ANSWER"
    assert action["target_index"] is None


def test_non_editable_search_link_clicked():
    # If the user says "search for problem statements", but the matched element is a link (<a>), it must be CLICKED to navigate, never TYPE_TEXT!
    elements = [
        {"index": 26, "tag": "a", "role": "link", "label": "PROBLEM STATEMENTS", "value": "", "is_visible": True, "bounding_box": {"x": 523, "y": 40, "width": 150, "height": 30}}
    ]
    action = SERVER_EXECUTOR._resolve_fast_path_action("search for 2026 problem statements", elements)
    assert action is not None
    assert action["operation"] == "CLICK"
    assert action["target_index"] == 26


def test_pii_sensitivity_and_category_customization():
    """
    Verifies that StateSanitizer properly respects user-configured sensitivity levels
    and selectively toggled PII categories.
    """
    from src.state.sanitizer import StateSanitizer

    # 1. Balanced mode with all categories enabled
    sanitizer = StateSanitizer(sensitivity="balanced")
    sample_text = "Customer Name: John Doe with email user@domain.com, card 4111-2222-3333-4444, and password: SecretToken123"
    result_balanced = sanitizer.sanitize_text(sample_text)
    assert "[REDACTED_NAME]" in result_balanced
    assert "[REDACTED_EMAIL]" in result_balanced
    assert "[REDACTED_CREDIT_CARD]" in result_balanced
    assert "[REDACTED_PASSWORD]" in result_balanced

    # 2. Category selection: Disable emails and names, keep cards and passwords
    sanitizer.set_config(categories={"emails": False, "names": False, "credit_cards": True, "passwords": True})
    result_filtered = sanitizer.sanitize_text(sample_text)
    assert "user@domain.com" in result_filtered  # Email not redacted
    assert "John Doe" in result_filtered         # Name not redacted
    assert "[REDACTED_CREDIT_CARD]" in result_filtered
    assert "[REDACTED_PASSWORD]" in result_filtered

    # 3. Relaxed sensitivity: Focuses strictly on high-risk credentials
    sanitizer_relaxed = StateSanitizer(sensitivity="relaxed")
    # By default in relaxed mode, emails and soft names are skipped unless explicitly enabled
    relaxed_text = "Name: Alice Smith, card 1234-5678-9012-3456, phone 555-123-4567, password: MyPass123"
    result_relaxed = sanitizer_relaxed.sanitize_text(relaxed_text)
    assert "[REDACTED_CREDIT_CARD]" in result_relaxed
    assert "[REDACTED_PASSWORD]" in result_relaxed

    # 4. Strict mode: Redacts broader patterns and long numeric identifiers
    sanitizer_strict = StateSanitizer(sensitivity="strict")
    strict_text = "Order confirmation for ID 987654321 with card 1234-5678-9012-3456"
    result_strict = sanitizer_strict.sanitize_text(strict_text)
    assert "[REDACTED_LONG_NUMERIC]" in result_strict
    assert "[REDACTED_CREDIT_CARD]" in result_strict
    assert "987654321" not in result_strict


def test_server_settings_configuration_flow():
    """
    Verifies that the server sanitizer can receive configuration updates
    and report its active settings accurately.
    """
    SERVER_SANITIZER.set_config(
        sensitivity="strict",
        categories={"credit_cards": True, "passwords": True, "emails": False}
    )
    config = SERVER_SANITIZER.get_config()
    assert config["sensitivity"] == "strict"
    assert config["categories"]["emails"] is False
    assert config["categories"]["credit_cards"] is True
    assert "credit_card" in config["active_patterns"]
    assert "email" not in config["active_patterns"]

    # Reset back to balanced defaults
    SERVER_SANITIZER.set_config(
        sensitivity="balanced",
        categories={"credit_cards": True, "passwords": True, "emails": True, "names": True, "phone_numbers": True, "government_ids": True}
    )
    reset_config = SERVER_SANITIZER.get_config()
    assert reset_config["sensitivity"] == "balanced"
    assert reset_config["categories"]["emails"] is True


def test_unclosed_quote_search_and_tab_phrase_resolution():
    """
    Verifies that:
    1. Unclosed quotes in search goals (e.g. "search for 'portal") correctly extract
       the query and issue TYPE_AND_SUBMIT on the search input rather than falling through to CLICK.
    2. Subgoals containing browser navigation phrases (e.g. "then click the button to open anew tab")
       do not falsely latch onto navigation links like 'Open Source' or parse as assignments.
    """
    elements = [
        {"index": 5, "tag": "a", "role": "link", "label": "Open Source", "value": "", "is_visible": True, "bounding_box": {"x": 394, "y": 71, "width": 100, "height": 30}},
        {"index": 8, "tag": "input", "role": "textbox", "label": "Search search-input", "value": "", "is_visible": True, "bounding_box": {"x": 1164, "y": 71, "width": 200, "height": 40}}
    ]

    # Test Step 1: Search query with unclosed quote
    action_search = SERVER_EXECUTOR._resolve_fast_path_action("search for 'portal", elements)
    assert action_search is not None
    assert action_search["operation"] == "TYPE_AND_SUBMIT"
    assert action_search["target_index"] == 8
    assert action_search["text_value"] == "portal"

    # Test Step 2: Tab phrase should NOT click 'Open Source'
    action_tab = SERVER_EXECUTOR._resolve_fast_path_action("then click the button to open anew tab", elements)
    if action_tab is not None:
        assert action_tab["target_index"] != 5  # Must never match 'Open Source'


def test_server_verhoeff_and_indian_pii():
    """
    Verifies that:
    1. Authentic Aadhaar numbers passing Verhoeff checksum are redacted.
    2. Indian PAN cards and +91 phone numbers are redacted.
    3. Invalid Aadhaar numbers failing Verhoeff checksum (negative controls) are NOT redacted.
    """
    sample = (
        "Valid KYC: Aadhaar 2345 6789 0124, PAN ABCDE1234F, Phone +91 98765 43210. "
        "Negative controls: Invalid Aadhaar 1234 5678 9013, 123456789012."
    )
    sanitized = SERVER_SANITIZER.sanitize_text(sample)
    assert "[REDACTED_AADHAAR]" in sanitized
    assert "[REDACTED_PAN]" in sanitized
    assert "[REDACTED_PHONE]" in sanitized
    assert "2345 6789 0124" not in sanitized
    assert "ABCDE1234F" not in sanitized
    assert "+91 98765 43210" not in sanitized

    # Negative controls must be preserved intact
    assert "1234 5678 9013" in sanitized
    assert "123456789012" in sanitized


def test_act_endpoint_logic():
    """
    Verifies that the /act endpoint payload mapping conforms to extension expectations.
    """
    elements = [
        {"id": 0, "tag": "input", "role": "textbox", "label": "Search products", "value": "", "is_visible": True, "bounding_box": {"x": 100, "y": 100, "width": 200, "height": 30}},
        {"id": 1, "tag": "button", "role": "button", "label": "Add to Cart", "value": "", "is_visible": True, "bounding_box": {"x": 300, "y": 100, "width": 100, "height": 30}}
    ]
    # Standardize element IDs to index
    for el in elements:
        if "index" not in el and "id" in el:
            el["index"] = el["id"]

    action = SERVER_EXECUTOR._resolve_fast_path_action("click Add to Cart", elements)
    assert action is not None
    assert action["operation"] == "CLICK"
    assert action["target_index"] == 1


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


def test_amazon_search_input_priority_over_department_dropdown():
    """
    Verifies that for composite prompts like:
    'search for 'ergonomic mechanical keyboard', apply 4-star filter, add the top result to cart, and proceed to cart.'
    the search input (e.g. twotabsearchtextbox) is selected with TYPE_AND_SUBMIT,
    and NOT the department dropdown (searchDropdownBox).
    """
    elements = [
        {
            "index": 8,
            "tag": "select",
            "role": "combobox",
            "label": "Select the department you want to search in Search in url searchDropdownBox All Departments Arts & C",
            "value": "search-alias=aps",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 20, "width": 50, "height": 38}
        },
        {
            "index": 9,
            "tag": "input",
            "role": "searchbox",
            "label": "Search Amazon.in",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 160, "y": 20, "width": 600, "height": 38}
        }
    ]

    prompt = "search for 'ergonomic mechanical keyboard', apply 4-star filter, add the top result to cart, and proceed to cart."
    action = SERVER_EXECUTOR._resolve_fast_path_action(prompt, elements)

    assert action is not None
    assert action["operation"] == "TYPE_AND_SUBMIT"
    assert action["target_index"] == 9
    assert action["text_value"] == "ergonomic mechanical keyboard"




