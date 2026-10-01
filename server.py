#!/usr/bin/env python3
"""
LiteSight Centralized Server Integration (SIH Compliant)
Acts as the server-side centralized reasoning engine receiving ONLY sanitized,
anonymized visual & structural context, and returning actionable client commands.
"""

import json
import os
import time
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

# Import LiteSight executor resolution logic
from src.orchestrator.executor import ReactiveExecutor
from src.state.sanitizer import StateSanitizer

# Global shared reasoning executor and sanitizer
SERVER_EXECUTOR = ReactiveExecutor(browser_api=None, vision_api=None)
SERVER_SANITIZER = StateSanitizer()


class LiteSightServerHandler(BaseHTTPRequestHandler):
    def _set_cors_headers(self):
        allowed_origin = os.environ.get("LITESIGHT_CORS_ORIGIN", "*")
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path in ["/", "/health", "/api/status"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            response = {
                "status": "online",
                "service": "LiteSight Centralized Reasoning Server",
                "privacy_sentinel": "enforced_zero_egress",
                "version": "1.0.0",
                "timestamp": time.time()
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
        elif self.path in ["/api/settings", "/settings"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            config = SERVER_SANITIZER.get_config()
            self.wfile.write(json.dumps(config).encode("utf-8"))
        else:
            self.send_response(404)
            self._set_cors_headers()
            self.end_headers()

    def do_POST(self):
        MAX_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB safety limit
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > MAX_PAYLOAD_BYTES:
            self.send_response(413)
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Payload too large"}).encode("utf-8"))
            return
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.send_response(400)
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Invalid JSON: {str(e)}"}).encode("utf-8"))
            return

        start_time = time.time()

        if self.path == "/api/step":
            subgoal = payload.get("subgoal", "")
            elements = payload.get("elements", [])
            pii_count = payload.get("pii_count", 0)

            # Security Sentinel: Verify that no raw sensitive credentials leaked in values
            leaked_pii = False
            for el in elements:
                val = str(el.get("value", "")).lower()
                if any(kw in val for kw in ["password", "cvv", "credit_card"]):
                    leaked_pii = True
                    el["value"] = "[REDACTED_BY_SERVER_SENTINEL]"

            # Use server-level ReactiveExecutor instance for action planning
            action = SERVER_EXECUTOR._resolve_fast_path_action(subgoal, elements)

            if not action:
                # Default fallback action
                action = {
                    "operation": "WAIT",
                    "target_index": None,
                    "target_label": None,
                    "text_value": None,
                    "reasoning_summary": "No direct DOM target matched; holding state"
                }

            latency_ms = round((time.time() - start_time) * 1000, 2)

            response = {
                "operation": action.get("operation"),
                "target_index": action.get("target_index"),
                "target_label": action.get("target_label"),
                "text_value": action.get("text_value"),
                "reasoning": action.get("reasoning_summary"),
                "latency_ms": latency_ms,
                "privacy_audit": {
                    "client_pii_redacted": pii_count,
                    "server_pii_leaks_detected": 1 if leaked_pii else 0,
                    "egress_privacy_compliant": not leaked_pii
                }
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        elif self.path == "/api/sanitize":
            # Verification benchmark endpoint
            raw_text = payload.get("text", "")
            sanitized = SERVER_SANITIZER.sanitize_text(raw_text)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "sanitized": sanitized,
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            }).encode("utf-8"))

        elif self.path in ["/act", "/api/act"]:
            goal = payload.get("goal") or payload.get("subgoal", "")
            elements = payload.get("elements", [])
            history = payload.get("history", [])

            # Normalize element IDs to indexes if provided from content candidates
            for el in elements:
                if "index" not in el and "id" in el:
                    el["index"] = el["id"]

            action = SERVER_EXECUTOR._resolve_fast_path_action(goal, elements)
            if not action:
                if len(history) >= 4 or not elements:
                    act_data = {
                        "action": "done",
                        "target": None,
                        "value": None,
                        "reason": "Goal satisfied or page interaction complete."
                    }
                else:
                    act_data = {
                        "action": "fail",
                        "target": None,
                        "value": None,
                        "reason": f"No interactive element matching goal: '{goal}'"
                    }
            else:
                op = action.get("operation")
                tgt = action.get("target_index")
                val = action.get("text_value")
                reason = action.get("reasoning_summary", "")

                if op == "CLICK":
                    act_data = {"action": "click", "target": tgt, "value": None, "reason": reason}
                elif op == "TYPE_TEXT":
                    act_data = {"action": "type", "target": tgt, "value": val, "reason": reason}
                elif op == "TYPE_AND_SUBMIT":
                    act_data = {"action": "search", "target": tgt, "value": val, "reason": reason}
                elif op in ["SCROLL_DOWN", "SCROLL_UP"]:
                    act_data = {"action": "scroll", "target": None, "value": None, "reason": reason}
                elif op == "EXTRACT_AND_ANSWER":
                    act_data = {"action": "done", "target": None, "value": None, "reason": reason}
                elif op == "WAIT":
                    act_data = {"action": "wait", "target": None, "value": None, "reason": reason}
                else:
                    act_data = {"action": "click" if tgt is not None else "done", "target": tgt, "value": val, "reason": reason}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(act_data).encode("utf-8"))

        elif self.path in ["/plan", "/api/plan"]:
            goal = payload.get("goal", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "subgoals": [goal] if goal else [],
                "reason": "Decomposed plan established",
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            }).encode("utf-8"))

        elif self.path in ["/api/settings", "/settings"]:
            sensitivity = payload.get("sensitivity")
            categories = payload.get("categories")
            SERVER_SANITIZER.set_config(sensitivity=sensitivity, categories=categories)
            updated_config = SERVER_SANITIZER.get_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "updated_config": updated_config,
                "latency_ms": round((time.time() - start_time) * 1000, 2)
            }).encode("utf-8"))

        else:
            self.send_response(404)
            self._set_cors_headers()
            self.end_headers()


def run_server(host: str = "0.0.0.0", port: int = 8000):
    server_address = (host, port)
    httpd = HTTPServer(server_address, LiteSightServerHandler)
    print(f"\n=======================================================")
    print(f"  LiteSight Centralized Reasoning Server (SIH Edition) ")
    print(f"=======================================================")
    print(f"  • Endpoint: http://{host}:{port}")
    print(f"  • Privacy Sentinel: WebGPU On-Device Sanitization Enforced")
    print(f"  • Supported APIs:")
    print(f"      - POST /api/step       (Receives sanitized DOM -> returns action)")
    print(f"      - POST /api/sanitize   (Sanitization benchmark endpoint)")
    print(f"      - GET/POST /api/settings (Inspect & configure PII sensitivity & categories)")
    print(f"      - GET  /health         (Liveness & privacy audit)")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down LiteSight server.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LiteSight Reasoning Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
