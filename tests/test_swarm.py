import unittest
import numpy as np
from src.orchestrator.bus import LocalMessageBus
from src.agents.swarm import (
    SwarmCoordinator,
    DOMSensorAgent,
    PrivacySentinelAgent,
    SpeculativeActionAgent,
    VisualGroundingAgent
)
from src.orchestrator.exceptions import PIIRedactionFailure


class TestSwarmArchitecture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = LocalMessageBus()
        self.coordinator = SwarmCoordinator(self.bus)

    async def test_bus_request_response(self):
        async def mock_handler(message):
            cid = message.payload.get("correlation_id")
            await self.bus.reply(cid, {"result": "success", "echo": message.payload.get("data")})

        self.bus.subscribe("test.topic", mock_handler)
        resp = await self.bus.request("test.topic", {"query": "hello"}, timeout=1.0)
        self.assertEqual(resp["result"], "success")
        self.assertEqual(resp["echo"]["query"], "hello")

    async def test_swarm_dispatch_step_success(self):
        dom_snapshot = {
            "timestamp": 12345678,
            "url": "https://example.com",
            "elements": [
                {
                    "index": 1,
                    "tag": "button",
                    "role": "button",
                    "label": "Sign In",
                    "value": "",
                    "is_visible": True,
                    "bounding_box": {"x": 100, "y": 200, "width": 80, "height": 30}
                }
            ]
        }
        privacy_report = {"detectedCount": 1, "unmasked_boxes": []}

        decision = await self.coordinator.dispatch_step(
            subgoal="click sign in button",
            dom_snapshot=dom_snapshot,
            privacy_report=privacy_report
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision["operation"], "CLICK")
        self.assertEqual(decision["target_index"], 1)

    async def test_privacy_sentinel_rejects_unmasked_pii(self):
        dom_snapshot = {"elements": []}
        # Simulate unmasked PII leak
        privacy_report = {
            "detectedCount": 1,
            "unmasked_boxes": [{"type": "CREDIT_CARD", "x": 10, "y": 10, "width": 100, "height": 20}]
        }

        with self.assertRaises(PIIRedactionFailure):
            await self.coordinator.dispatch_step(
                subgoal="click submit",
                dom_snapshot=dom_snapshot,
                privacy_report=privacy_report
            )

    async def test_visual_grounding_fallback(self):
        # Create dummy frame with button box
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[200:250, 300:500] = 200

        result = await self.coordinator.dispatch_visual_fallback(frame, pii_boxes=[])
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("target_coord", result)
        self.assertIn("foveated_tokens_count", result)
        self.assertTrue(result["foveated_tokens_count"] >= 3)


if __name__ == "__main__":
    unittest.main()
