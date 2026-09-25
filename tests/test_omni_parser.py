import unittest
import numpy as np
from src.vision.omni_parser import OmniVisualParser


class TestOmniVisualParser(unittest.TestCase):
    def setUp(self):
        self.parser = OmniVisualParser(viewport_size=(1920, 1080))
        # Create a synthetic canvas frame with several distinct simulated UI buttons/inputs
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        # Draw a simulated button with bright border at (200, 150)
        self.frame[150:190, 200:360] = 50
        self.frame[150:152, 200:360] = 220
        self.frame[188:190, 200:360] = 220
        self.frame[150:190, 200:202] = 220
        self.frame[150:190, 358:360] = 220

        # Draw a simulated text box at (600, 300)
        self.frame[300:340, 600:850] = 30
        self.frame[300:302, 600:850] = 200
        self.frame[338:340, 600:850] = 200
        self.frame[300:340, 600:602] = 200
        self.frame[300:340, 848:850] = 200

    def test_parse_interactables(self):
        elements = self.parser.parse_interactables(self.frame)
        self.assertTrue(len(elements) > 0)

        first_el = elements[0]
        self.assertIn("visual_index", first_el)
        self.assertEqual(first_el["visual_index"], 1)
        self.assertIn("bounding_box", first_el)
        self.assertIn("center_coord", first_el)
        self.assertTrue(first_el["center_coord"][0] > 0)
        self.assertTrue(first_el["center_coord"][1] > 0)

    def test_map_coordinate(self):
        elements = self.parser.parse_interactables(self.frame)
        coord = self.parser.map_coordinate(1)
        self.assertEqual(coord, elements[0]["center_coord"])

    def test_pii_filtering(self):
        # Place a PII bounding box exactly overlapping an element
        pii_boxes = [{"type": "CREDIT_CARD", "x": 200, "y": 150, "width": 160, "height": 40}]
        elements = self.parser.parse_interactables(self.frame, pii_boxes=pii_boxes)

        # Confirm no candidate directly centers inside the masked PII box
        for el in elements:
            cx, cy = el["center_coord"]
            is_inside_pii = (200 <= cx <= 360) and (150 <= cy <= 190)
            self.assertFalse(is_inside_pii)


if __name__ == "__main__":
    unittest.main()
