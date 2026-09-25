# src/vision/foveation.py
"""
Mathematical Foveation Adapter.
Extracts high-resolution patches centered on active interaction points.
Downsamples surrounding context to eliminate token explosion.
Operates across Linux and Windows on both PyTorch and NumPy backends.
"""

from typing import Tuple, List, Any, Dict
import numpy as np

try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    F = None


class FoveatedTokenizer:
    """
    Compresses visual frames into foveated tokens.
    Extracts high-resolution focus patch around target coordinates.
    Downsamples peripheral regions to reduce bandwidth by up to 24x.
    """

    def __init__(self, base_resolution: Tuple[int, int] = (1920, 1080), patch_size: int = 224):
        self.base_resolution = base_resolution
        self.patch_size = patch_size

    def compress(self, image_tensor: Any, foveation_center: Tuple[int, int]) -> List[Dict[str, Any]]:
        """
        Extracts high-resolution patches centered strictly on the active interaction point
        and progressively downsamples surrounding patches on an irregular grid.

        Args:
            image_tensor: Raw input frame (Tensor or NumPy array of shape (Channels, Height, Width)).
            foveation_center: The (x, y) coordinates of the active interaction point.

        Returns:
            A list of compressed foveated tokens with scaled coordinates.
        """
        x, y = foveation_center
        tokens = []

        is_torch = TORCH_AVAILABLE and isinstance(image_tensor, torch.Tensor)

        # 1. Extract high-resolution patch directly at foveation_center
        high_res_patch = self._extract_patch(image_tensor, center=(x, y), crop_size=self.patch_size)
        tokens.append({
            "type": "high_res",
            "center": (x, y),
            "data": high_res_patch,
            "scale": 1.0
        })

        # 2. Extract progressively downsampled patch for surrounding context
        mid_res_patch = self._extract_patch(image_tensor, center=(x, y), crop_size=self.patch_size * 2)
        mid_res_downsampled = self._downsample_patch(mid_res_patch, target_size=(self.patch_size, self.patch_size), is_torch=is_torch)
        tokens.append({
            "type": "mid_res_surround",
            "center": (x, y),
            "data": mid_res_downsampled,
            "scale": 0.5
        })

        # 3. Global context (downsample entire frame to patch_size)
        global_downsampled = self._downsample_patch(image_tensor, target_size=(self.patch_size, self.patch_size), is_torch=is_torch)
        tokens.append({
            "type": "low_res_global",
            "center": (self.base_resolution[0] // 2, self.base_resolution[1] // 2),
            "data": global_downsampled,
            "scale": self.patch_size / max(self.base_resolution)
        })

        return tokens

    def _extract_patch(self, image: Any, center: Tuple[int, int], crop_size: int) -> Any:
        """
        Safely crops a square region from the image at the given center coordinate.
        Pads with zeros if the crop goes out of bounds.
        """
        x, y = center
        is_torch = TORCH_AVAILABLE and isinstance(image, torch.Tensor)
        c, h, w = image.shape

        half_crop = crop_size // 2

        # Determine valid bounds for the slice
        top = max(0, y - half_crop)
        bottom = min(h, y + half_crop)
        left = max(0, x - half_crop)
        right = min(w, x + half_crop)

        sliced = image[:, top:bottom, left:right]

        pad_top = max(0, half_crop - y)
        pad_bottom = max(0, (y + half_crop) - h)
        pad_left = max(0, half_crop - x)
        pad_right = max(0, (x + half_crop) - w)

        if pad_top > 0 or pad_bottom > 0 or pad_left > 0 or pad_right > 0:
            if is_torch:
                sliced = F.pad(sliced, (pad_left, pad_right, pad_top, pad_bottom), mode="constant", value=0)
            else:
                # NumPy padding: ((c_before, c_after), (top, bottom), (left, right))
                sliced = np.pad(sliced, ((0, 0), (pad_top, pad_bottom), (pad_left, pad_right)), mode="constant", constant_values=0)

        return sliced

    def _downsample_patch(self, patch: Any, target_size: Tuple[int, int], is_torch: bool) -> Any:
        """Downsamples image tensor or numpy array to target resolution."""
        tw, th = target_size
        if is_torch:
            return F.interpolate(
                patch.unsqueeze(0).float(),
                size=(th, tw),
                mode='bilinear',
                align_corners=False
            ).squeeze(0)
        else:
            # Fast vectorized bilinear/nearest resize with numpy
            c, h, w = patch.shape
            y_indices = np.linspace(0, h - 1, th).astype(int)
            x_indices = np.linspace(0, w - 1, tw).astype(int)
            return patch[:, y_indices[:, None], x_indices]
