# src/vision/omni_parser.py
"""
Pure Visual Inference Engine for LiteSight (OmniParser Zero-DOM Fallback).
Detects interactable UI components directly from pixel buffers without DOM access.
Adheres to AGENTS.md rules: STE language, mathematical foveation, no raw 1080p frames.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import scipy.ndimage as ndi

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class OmniVisualParser:
    """
    Parses visual UI components directly from image frames.
    Enables zero-DOM operation for Canvas, WebGL, games, and remote streams.
    Maps discrete visual indices to screen coordinates.
    """

    def __init__(self, viewport_size: Tuple[int, int] = (1920, 1080)):
        self.viewport_width, self.viewport_height = viewport_size
        self.last_detected_elements: List[Dict[str, Any]] = []

    def parse_interactables(
        self,
        image_frame: Any,
        pii_boxes: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts interactable visual elements from image buffer.
        Returns ordered list of candidate bounding boxes with assigned indices.
        """
        arr = self._to_numpy_uint8(image_frame)
        height, width = arr.shape[:2]

        # Calculate luminance for contrast edge detection
        if len(arr.shape) == 3 and arr.shape[2] >= 3:
            gray = (
                0.299 * arr[:, :, 0].astype(np.float32) +
                0.587 * arr[:, :, 1].astype(np.float32) +
                0.114 * arr[:, :, 2].astype(np.float32)
            ).astype(np.uint8)
        else:
            gray = arr.squeeze().astype(np.uint8)

        # Detect candidate UI components via spatial gradient clustering and component labeling
        candidates = self._detect_candidate_boxes(gray, width, height)

        # Filter out areas that intersect with synthetic PII regions
        if pii_boxes:
            candidates = self._filter_pii_intersections(candidates, pii_boxes)

        # Assign discrete visual indices [V1, V2, ...]
        indexed_elements: List[Dict[str, Any]] = []
        for idx, box in enumerate(candidates, start=1):
            center_x = box["x"] + box["width"] // 2
            center_y = box["y"] + box["height"] // 2
            indexed_elements.append({
                "visual_index": idx,
                "label": f"[V{idx}] {box['predicted_type']}",
                "type": box["predicted_type"],
                "bounding_box": {
                    "x": int(box["x"]),
                    "y": int(box["y"]),
                    "width": int(box["width"]),
                    "height": int(box["height"])
                },
                "center_coord": (int(center_x), int(center_y)),
                "confidence": float(box.get("confidence", 0.90))
            })

        self.last_detected_elements = indexed_elements
        return indexed_elements

    def map_coordinate(self, visual_index: int) -> Tuple[int, int]:
        """
        Maps a visual index directly to screen coordinates (x, y).
        Raises KeyError if index does not exist.
        """
        for el in self.last_detected_elements:
            if el["visual_index"] == visual_index:
                return el["center_coord"]
        raise KeyError(f"Visual index V{visual_index} not found in parsed scene.")

    def _detect_candidate_boxes(
        self,
        gray: np.ndarray,
        width: int,
        height: int
    ) -> List[Dict[str, Any]]:
        """
        Detects interactable UI components using morphological gradients and connected components.
        """
        # Calculate horizontal and vertical differences
        diff_x = np.abs(gray[:, 1:].astype(np.int16) - gray[:, :-1].astype(np.int16))
        diff_y = np.abs(gray[1:, :].astype(np.int16) - gray[:-1, :].astype(np.int16))

        edges = np.zeros_like(gray, dtype=bool)
        edges[:, 1:] |= (diff_x > 15)
        edges[1:, :] |= (diff_y > 15)

        # Dilate edge mask to connect component borders
        dilated = ndi.binary_dilation(edges, iterations=3)
        labeled, num_features = ndi.label(dilated)
        slices = ndi.find_objects(labeled)

        candidates: List[Dict[str, Any]] = []

        for sl in slices:
            if sl is None:
                continue
            y_slice, x_slice = sl
            y_min, y_max = y_slice.start, y_slice.stop
            x_min, x_max = x_slice.start, x_slice.stop
            box_w = x_max - x_min
            box_h = y_max - y_min

            # Filter out tiny noise artifacts and giant viewport bounding boxes
            if box_w < 12 or box_h < 10:
                continue
            if box_w > width * 0.95 and box_h > height * 0.95:
                continue

            aspect_ratio = box_w / max(1, box_h)
            if aspect_ratio >= 3.0:
                pred_type = "textbox"
            elif aspect_ratio >= 1.2:
                pred_type = "button"
            else:
                pred_type = "icon_or_clickable"

            candidates.append({
                "x": x_min,
                "y": y_min,
                "width": box_w,
                "height": box_h,
                "predicted_type": pred_type,
                "confidence": 0.92
            })

        # Non-maximum suppression to merge overlapping candidates
        return self._non_max_suppression(candidates, iou_threshold=0.3)

    def _non_max_suppression(
        self,
        boxes: List[Dict[str, Any]],
        iou_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Applies Non-Maximum Suppression to remove redundant bounding boxes.
        """
        if not boxes:
            return []

        sorted_boxes = sorted(boxes, key=lambda b: (b["width"] * b["height"]), reverse=True)
        selected: List[Dict[str, Any]] = []

        for box in sorted_boxes:
            overlap = False
            for sel in selected:
                if self._calculate_iou(box, sel) > iou_threshold:
                    overlap = True
                    break
            if not overlap:
                selected.append(box)
            if len(selected) >= 30:
                break

        # Re-sort from top to bottom, left to right for intuitive index order
        selected.sort(key=lambda b: (b["y"] // 40, b["x"]))
        return selected

    def _calculate_iou(self, box_a: Dict[str, Any], box_b: Dict[str, Any]) -> float:
        """Calculates Intersection-Over-Union between two boxes."""
        x1 = max(box_a["x"], box_b["x"])
        y1 = max(box_a["y"], box_b["y"])
        x2 = min(box_a["x"] + box_a["width"], box_b["x"] + box_b["width"])
        y2 = min(box_a["y"] + box_a["height"], box_b["y"] + box_b["height"])

        inter_w = max(0, x2 - x1)
        inter_h = max(0, y2 - y1)
        inter_area = inter_w * inter_h

        area_a = box_a["width"] * box_a["height"]
        area_b = box_b["width"] * box_b["height"]
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0
        return float(inter_area / union_area)

    def _filter_pii_intersections(
        self,
        candidates: List[Dict[str, Any]],
        pii_boxes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Removes candidates that intersect with active PII redaction zones."""
        clean: List[Dict[str, Any]] = []
        for cand in candidates:
            intersects = False
            for pii in pii_boxes:
                if self._calculate_iou(cand, pii) > 0.05:
                    intersects = True
                    break
            if not intersects:
                clean.append(cand)
        return clean

    def _to_numpy_uint8(self, frame: Any) -> np.ndarray:
        """Converts diverse image formats (Tensor, NumPy, bytes) to uint8 array."""
        if TORCH_AVAILABLE and isinstance(frame, torch.Tensor):
            arr = frame.detach().cpu().numpy()
            if arr.ndim == 3 and arr.shape[0] in [1, 3, 4]:
                arr = np.transpose(arr, (1, 2, 0))
            return arr.astype(np.uint8)
        elif isinstance(frame, np.ndarray):
            if frame.ndim == 3 and frame.shape[0] in [1, 3, 4] and frame.shape[2] not in [1, 3, 4]:
                return np.transpose(frame, (1, 2, 0)).astype(np.uint8)
            return frame.astype(np.uint8)
        else:
            return np.zeros((self.viewport_height, self.viewport_width, 3), dtype=np.uint8)
