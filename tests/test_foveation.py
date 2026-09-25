import unittest
import numpy as np
from src.vision.foveation import FoveatedTokenizer, TORCH_AVAILABLE

if TORCH_AVAILABLE:
    import torch


class TestFoveatedTokenizer(unittest.TestCase):
    def setUp(self):
        # Set base resolution to 1080p and target patch size to 224x224
        self.tokenizer = FoveatedTokenizer(base_resolution=(1920, 1080), patch_size=224)
        if TORCH_AVAILABLE:
            self.dummy_image = torch.ones((3, 1080, 1920))
        else:
            self.dummy_image = np.ones((3, 1080, 1920), dtype=np.float32)

    def test_center_patch_extraction(self):
        # Extract at the center of the screen
        tokens = self.tokenizer.compress(self.dummy_image, (960, 540))
        high_res = next(t for t in tokens if t["type"] == "high_res")

        # Verify the shape is exactly the target patch size
        self.assertEqual(high_res["data"].shape, (3, 224, 224))
        self.assertEqual(high_res["scale"], 1.0)
        self.assertEqual(high_res["center"], (960, 540))

    def test_out_of_bounds_padding(self):
        # Extract at top-left corner (0, 0), testing zero-padding
        tokens = self.tokenizer.compress(self.dummy_image, (0, 0))
        high_res = next(t for t in tokens if t["type"] == "high_res")

        # Ensure correct padding to 224x224
        self.assertEqual(high_res["data"].shape, (3, 224, 224))

    def test_global_context_downsample(self):
        # Verify global context downsamples the full 1920x1080 image to 224x224
        tokens = self.tokenizer.compress(self.dummy_image, (960, 540))
        global_res = next(t for t in tokens if t["type"] == "low_res_global")

        self.assertEqual(global_res["data"].shape, (3, 224, 224))
        self.assertTrue(global_res["scale"] < 1.0)


if __name__ == "__main__":
    unittest.main()
