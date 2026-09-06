import torch
import torch.nn.functional as F
from typing import Tuple, List, Any, Dict

class FoveatedTokenizer:
    def __init__(self, base_resolution: Tuple[int, int] = (1920, 1080), patch_size: int = 224):
        self.base_resolution = base_resolution
        self.patch_size = patch_size

    def compress(self, image_tensor: torch.Tensor, foveation_center: Tuple[int, int]) -> List[Dict[str, Any]]:
        """
        Extracts high-resolution patches centered strictly on the active interaction point
        and progressively downsamples surrounding patches on an irregular grid.
        
        Args:
            image_tensor: The raw input image tensor (Channels, Height, Width).
            foveation_center: The (x, y) coordinates of the active interaction point.
            
        Returns:
            A list of compressed foveated tokens.
        """
        x, y = foveation_center
        tokens = []
        
        # 1. Extract high-resolution patch directly at foveation_center
        high_res_patch = self._extract_patch(image_tensor, center=(x, y), crop_size=self.patch_size)
        tokens.append({"type": "high_res", "center": (x, y), "data": high_res_patch, "scale": 1.0})
        
        # 2. Extract progressively downsampled patches for local context
        # We grab a region twice as large, then downsample it to patch_size
        mid_res_patch = self._extract_patch(image_tensor, center=(x, y), crop_size=self.patch_size * 2)
        mid_res_downsampled = F.interpolate(
            mid_res_patch.unsqueeze(0).float(), 
            size=(self.patch_size, self.patch_size), 
            mode='bilinear', 
            align_corners=False
        ).squeeze(0)
        tokens.append({"type": "mid_res_surround", "center": (x, y), "data": mid_res_downsampled, "scale": 0.5})
        
        # 3. Global context (the entire image downsampled to patch_size)
        global_downsampled = F.interpolate(
            image_tensor.unsqueeze(0).float(), 
            size=(self.patch_size, self.patch_size), 
            mode='bilinear', 
            align_corners=False
        ).squeeze(0)
        tokens.append({
            "type": "low_res_global", 
            "center": (self.base_resolution[0] // 2, self.base_resolution[1] // 2), 
            "data": global_downsampled, 
            "scale": self.patch_size / max(self.base_resolution)
        })
        
        return tokens

    def _extract_patch(self, image: torch.Tensor, center: Tuple[int, int], crop_size: int) -> torch.Tensor:
        """
        Safely crops a square region from the image tensor at the given center coordinate.
        Pads with zeros if the crop goes out of bounds to ensure the patch is always crop_size.
        """
        x, y = center
        c, h, w = image.shape
        
        half_crop = crop_size // 2
        
        # Determine valid bounds for the slice
        top = max(0, y - half_crop)
        bottom = min(h, y + half_crop)
        left = max(0, x - half_crop)
        right = min(w, x + half_crop)
        
        # Slice the valid portion
        sliced = image[:, top:bottom, left:right]
        
        # If the patch is out of bounds (e.g. corner of screen), we pad it
        pad_top = max(0, half_crop - y)
        pad_bottom = max(0, (y + half_crop) - h)
        pad_left = max(0, half_crop - x)
        pad_right = max(0, (x + half_crop) - w)
        
        if pad_top > 0 or pad_bottom > 0 or pad_left > 0 or pad_right > 0:
            # F.pad format is (pad_left, pad_right, pad_top, pad_bottom)
            sliced = F.pad(sliced, (pad_left, pad_right, pad_top, pad_bottom), mode="constant", value=0)
            
        return sliced
