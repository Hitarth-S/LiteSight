import unittest
import numpy as np
from src.federation.differential_privacy import DifferentialPrivacyEngine
from src.federation.client import FederatedClient


class TestDifferentialPrivacy(unittest.TestCase):
    def setUp(self):
        self.engine = DifferentialPrivacyEngine(epsilon=1.0, delta=1e-5, clip_norm=2.0)

    def test_clipping(self):
        # Create a large vector with norm > clip_norm
        large_vector = np.array([3.0, 4.0], dtype=np.float32)  # norm is 5.0
        clipped, norm = self.engine.clip_vector(large_vector)

        self.assertAlmostEqual(norm, 5.0, places=4)
        clipped_norm = float(np.linalg.norm(clipped))
        self.assertAlmostEqual(clipped_norm, 2.0, places=4)

    def test_noise_addition(self):
        vector = np.zeros(100, dtype=np.float32)
        res = self.engine.privatize_weights(vector)

        priv_weights = res["privatized_weights"]
        self.assertEqual(priv_weights.shape, vector.shape)
        # Verify noise was added (variance > 0)
        self.assertTrue(np.var(priv_weights) > 0.0)
        self.assertEqual(res["epsilon_spent"], 1.0)
        self.assertEqual(res["delta_spent"], 1e-5)

    def test_federated_client_payload(self):
        client = FederatedClient(client_id="test_client_01", epsilon=0.5, clip_norm=1.5, weight_dimension=32)
        trajectories = [
            {"goal": "locate search input", "url": "https://example.com"},
            {"goal": "type query and submit", "url": "https://example.com"}
        ]
        payload = client.generate_privatized_update(trajectories, layer_name="lora_action_head")

        self.assertEqual(payload.client_id, "test_client_01")
        self.assertEqual(payload.layer_name, "lora_action_head")
        self.assertEqual(payload.sample_count, 2)
        self.assertEqual(len(payload.privatized_delta), 32)

        # Ensure dictionary serialization works for transport
        p_dict = payload.to_dict()
        self.assertIn("client_id", p_dict)
        self.assertIn("privatized_delta", p_dict)
        self.assertIn("privacy_budget", p_dict)


if __name__ == "__main__":
    unittest.main()
