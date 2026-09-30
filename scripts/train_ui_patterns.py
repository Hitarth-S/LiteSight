#!/usr/bin/env python3
"""
Autonomous Cross-Site UI Pattern Learner & Statistical Frequency Analyzer
Crawls target websites from a corpus file, analyzes interactive DOM structures,
and computes cross-site frequency distributions to extract the MOST COMMON,
generalized UI patterns (tags, roles, keywords, spatial distributions) across the web.

Generates universal zero-shot knowledge into src/knowledge/ui_patterns.json.
"""

import os
import sys
import re
import json
import time
import asyncio
import argparse
from typing import List, Dict, Any, Set, Tuple
from collections import Counter, defaultdict
from pathlib import Path

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PATTERNS_FILE = PROJECT_ROOT / "src" / "knowledge" / "ui_patterns.json"
SNAPSHOT_JS_PATH = PROJECT_ROOT / "src" / "state" / "snapshot.js"
DEFAULT_WEBSITES_FILE = PROJECT_ROOT / "scripts" / "training_websites.txt"


class UIPatternLearner:
    """
    Statistical Cross-Site UI Pattern Learner.
    Learns generalized patterns by tracking recurrence across DISTINCT web domains.
    """
    def __init__(self, patterns_path: Path = PATTERNS_FILE):
        self.patterns_path = patterns_path
        self.patterns = self._load_patterns()
        with open(SNAPSHOT_JS_PATH, "r", encoding="utf-8") as f:
            self.snapshot_js = f.read()

        # Cross-site frequency accumulators: {intent: Counter(keyword: domain_count)}
        self.domain_keyword_counts: Dict[str, Counter] = defaultdict(Counter)
        self.intent_roles: Dict[str, Counter] = defaultdict(Counter)
        self.intent_tags: Dict[str, Counter] = defaultdict(Counter)
        self.intent_y_positions: Dict[str, List[int]] = defaultdict(list)
        self.domain_hits: Dict[str, Set[str]] = defaultdict(set)  # {intent: set of domains}

    def _load_patterns(self) -> Dict[str, Any]:
        if self.patterns_path.exists():
            with open(self.patterns_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.2.0", "intents": {}}

    def analyze_domain_elements(self, domain: str, elements: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Analyzes DOM interactables for a specific domain, recording occurrences
        into the cross-site statistical frequency corpus.
        """
        site_discovered: Dict[str, Set[str]] = defaultdict(set)
        counts = {
            "SEARCH_INPUT": 0, "FILTER_RATING": 0, "ADD_TO_CART": 0, "VIEW_CART": 0,
            "CLOSE_MODAL": 0, "COOKIE_CONSENT": 0, "LOGIN_INPUT": 0, "PASSWORD_INPUT": 0,
            "SUBMIT_AUTH": 0, "SIGNUP_BUTTON": 0, "BOOKING_CTA": 0, "DOWNLOAD_CTA": 0,
            "SELECT_DROPDOWN": 0
        }

        for el in elements:
            label = el.get("label", "").lower().strip()
            tag = el.get("tag", "").lower()
            role = el.get("role", "").lower()
            box = el.get("bounding_box", {})
            y = box.get("y", 0)

            # Skip empty or giant container labels
            if not label or len(label) > 80:
                continue

            # 1. Search Input Pattern
            if (role in ["textbox", "searchbox", "combobox"] or tag in ["input", "textarea"]) and (
                any(kw in label for kw in ["search", "query", "find", "explore", "lookup"]) or (y < 160 and "search" in f"{tag} {role}")
            ):
                if not any(auth_kw in label for auth_kw in ["user", "email", "pass", "login", "pin"]):
                    counts["SEARCH_INPUT"] += 1
                    self.intent_roles["SEARCH_INPUT"][role] += 1
                    self.intent_tags["SEARCH_INPUT"][tag] += 1
                    self.intent_y_positions["SEARCH_INPUT"].append(y)
                    # Extract salient search terms
                    for phrase in ["search", "query", "find", "lookup", "explore"]:
                        if phrase in label:
                            site_discovered["SEARCH_INPUT"].add(phrase)
                    tokens = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', label) if w not in {"the", "for", "and", "with", "all", "here", "type", "enter"}]
                    if tokens:
                        site_discovered["SEARCH_INPUT"].add(" ".join(tokens[:2]))

            # 2. Rating Filter Pattern
            if re.search(r'\b(4\s*stars?|4\s*(&|and|\+)\s*up|customer\s*ratings?|customer\s*reviews?|4★|four\s*star)\b', label) or "star and above" in label or "star & above" in label:
                counts["FILTER_RATING"] += 1
                self.intent_roles["FILTER_RATING"][role] += 1
                self.intent_tags["FILTER_RATING"][tag] += 1
                site_discovered["FILTER_RATING"].add(label)

            # 3. Add to Cart Pattern
            if any(act in label for act in ["add to cart", "add to basket", "add item", "buy now", "add to bag"]):
                counts["ADD_TO_CART"] += 1
                self.intent_roles["ADD_TO_CART"][role] += 1
                self.intent_tags["ADD_TO_CART"][tag] += 1
                site_discovered["ADD_TO_CART"].add(label)

            # 4. View Cart Pattern
            if re.search(r'\b(cart|basket|shopping\s*cart|view\s*cart|view\s*bag|go\s*to\s*cart|checkout)\b', label) and not any(add_kw in label for add_kw in ["add", "buy"]):
                counts["VIEW_CART"] += 1
                self.intent_roles["VIEW_CART"][role] += 1
                self.intent_tags["VIEW_CART"][tag] += 1
                site_discovered["VIEW_CART"].add(label)

            # 5. Modal / Overlay Close Pattern
            if label in ["✕", "x", "close", "dismiss", "skip", "not now", "no thanks", "maybe later"] or label.endswith("close"):
                counts["CLOSE_MODAL"] += 1
                self.intent_roles["CLOSE_MODAL"][role] += 1
                self.intent_tags["CLOSE_MODAL"][tag] += 1
                site_discovered["CLOSE_MODAL"].add(label)

            # 6. Cookie Consent Pattern
            if any(ck in label for ck in ["accept all", "accept cookies", "allow all", "i agree", "got it", "agree & continue", "accept"]):
                counts["COOKIE_CONSENT"] += 1
                self.intent_roles["COOKIE_CONSENT"][role] += 1
                self.intent_tags["COOKIE_CONSENT"][tag] += 1
                site_discovered["COOKIE_CONSENT"].add(label)

            # 7. Login / Username Input Pattern
            if role in ["textbox", "combobox"] and any(auth in label for auth in ["username", "user name", "email", "phone", "login", "user id", "account"]):
                counts["LOGIN_INPUT"] += 1
                self.intent_roles["LOGIN_INPUT"][role] += 1
                self.intent_tags["LOGIN_INPUT"][tag] += 1
                site_discovered["LOGIN_INPUT"].add(label)

            # 8. Password Input Pattern
            if role in ["textbox"] and (any(pw in label for pw in ["password", "passcode", "pin", "secret"]) or el.get("value") == "[REDACTED]"):
                counts["PASSWORD_INPUT"] += 1
                self.intent_roles["PASSWORD_INPUT"][role] += 1
                self.intent_tags["PASSWORD_INPUT"][tag] += 1
                site_discovered["PASSWORD_INPUT"].add(label)

            # 9. Submit Auth Pattern
            if role in ["button", "link", "input"] and any(sub in label for sub in ["log in", "login", "sign in", "signin", "continue", "submit", "next"]):
                counts["SUBMIT_AUTH"] += 1
                self.intent_roles["SUBMIT_AUTH"][role] += 1
                self.intent_tags["SUBMIT_AUTH"][tag] += 1
                site_discovered["SUBMIT_AUTH"].add(label)

            # 10. Signup Button Pattern
            if role in ["button", "link", "input"] and any(su in label for su in ["sign up", "signup", "register", "create account", "join now", "get started"]):
                counts["SIGNUP_BUTTON"] += 1
                self.intent_roles["SIGNUP_BUTTON"][role] += 1
                self.intent_tags["SIGNUP_BUTTON"][tag] += 1
                site_discovered["SIGNUP_BUTTON"].add(label)

            # 11. Booking CTA Pattern
            if role in ["button", "link", "input"] and any(bk in label for bk in [
                "book now", "search flights", "search trains", "search buses", "find tickets", 
                "check availability", "reserve", "select seats", "find flights", "show trains"
            ]):
                counts["BOOKING_CTA"] += 1
                self.intent_roles["BOOKING_CTA"][role] += 1
                self.intent_tags["BOOKING_CTA"][tag] += 1
                site_discovered["BOOKING_CTA"].add(label)

            # 12. Download CTA Pattern
            if role in ["button", "link", "input"] and any(dl in label for dl in [
                "download", "download now", "get app", "download free", "install", 
                "free download", "clone or download", "download zip"
            ]):
                counts["DOWNLOAD_CTA"] += 1
                self.intent_roles["DOWNLOAD_CTA"][role] += 1
                self.intent_tags["DOWNLOAD_CTA"][tag] += 1
                site_discovered["DOWNLOAD_CTA"].add(label)

            # 13. Dropdown / Select Pattern
            if (role in ["combobox", "listbox"] or tag in ["select"]) and any(sel in label for sel in [
                "select", "choose", "role", "country", "state", "category", "type", "gender", "status", "sort by"
            ]):
                counts["SELECT_DROPDOWN"] += 1
                self.intent_roles["SELECT_DROPDOWN"][role] += 1
                self.intent_tags["SELECT_DROPDOWN"][tag] += 1
                site_discovered["SELECT_DROPDOWN"].add(label)

        # Record domain-level keyword frequencies (prevents 1 site from dominating)
        for intent, kw_set in site_discovered.items():
            self.domain_hits[intent].add(domain)
            for kw in kw_set:
                self.domain_keyword_counts[intent][kw] += 1

        return counts

    def compile_generalized_knowledge(self):
        """
        Synthesizes the cross-site domain statistics into the generalized
        ui_patterns.json file, ranking patterns strictly by universal recurrence.
        """
        intents = self.patterns.get("intents", {})

        for intent_name, kw_counter in self.domain_keyword_counts.items():
            if intent_name not in intents:
                intents[intent_name] = {
                    "roles": ["button", "link"],
                    "tags": ["button", "a"],
                    "label_keywords": [],
                    "spatial_hint": "content",
                    "base_weight": 12
                }

            # 1. Rank keywords by cross-site domain frequency
            existing_keywords = intents[intent_name].get("label_keywords", [])
            for ex in existing_keywords:
                # Seed canonical existing keywords with baseline count
                if ex not in kw_counter:
                    kw_counter[ex] = 1

            # Top most common patterns across domains
            ranked_keywords = [kw for kw, _ in kw_counter.most_common(25)]
            intents[intent_name]["label_keywords"] = ranked_keywords

            # 2. Update most common roles observed across domains
            if self.intent_roles[intent_name]:
                top_roles = [r for r, count in self.intent_roles[intent_name].most_common(5) if r]
                if top_roles:
                    intents[intent_name]["roles"] = list(dict.fromkeys(top_roles + intents[intent_name].get("roles", [])))[:5]

            # 3. Update most common tags observed across domains
            if self.intent_tags[intent_name]:
                top_tags = [t for t, count in self.intent_tags[intent_name].most_common(5) if t]
                if top_tags:
                    intents[intent_name]["tags"] = list(dict.fromkeys(top_tags + intents[intent_name].get("tags", [])))[:5]

        self.patterns["version"] = "1.2.0"
        self.patterns["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.patterns["generalization_metric"] = {
            "total_domains_analyzed": len({d for d_set in self.domain_hits.values() for d in d_set}),
            "intents_covered": len(intents)
        }

        with open(self.patterns_path, "w", encoding="utf-8") as f:
            json.dump(self.patterns, f, indent=2)
        print(f"\n[Learner] Generalized pattern knowledge base updated: {self.patterns_path}", flush=True)

    async def crawl_and_train(self, urls: List[str], headless: bool = True, timeout: int = 15000):
        from playwright.async_api import async_playwright

        print(f"\n=================================================================", flush=True)
        print(f"   LiteSight Cross-Site UI Pattern Generalization Engine        ", flush=True)
        print(f"=================================================================", flush=True)
        print(f"  Target Queue: {len(urls)} diverse real-world domains", flush=True)
        print(f"  Headless: {headless} | Timeout: {timeout}ms per domain", flush=True)
        print(f"  Goal: Extract the MOST COMMON universal patterns across websites", flush=True)
        print(f"=================================================================\n", flush=True)

        crawled_count = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            await context.add_init_script(self.snapshot_js)

            for idx, url in enumerate(urls, 1):
                domain = url.split("//")[-1].split("/")[0]
                print(f"[{idx}/{len(urls)}] Analyzing {domain} ({url})...", flush=True)
                page = await context.new_page()

                try:
                    # Use domcontentloaded for fast extraction without waiting for infinite trackers
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    await page.wait_for_timeout(1000)

                    snapshot = await page.evaluate("""() => {
                        if (typeof window.generateLiteSightSnapshot === 'function') return window.generateLiteSightSnapshot();
                        return { elements: [] };
                    }""")

                    elements = snapshot.get("elements", [])
                    stats = self.analyze_domain_elements(domain, elements)
                    crawled_count += 1

                    matched = [f"{k}:{v}" for k, v in stats.items() if v > 0]
                    matched_str = ", ".join(matched[:4]) if matched else "standard DOM elements"
                    print(f"  ✓ {domain}: {len(elements)} elements. Invariants: [{matched_str}]", flush=True)

                except Exception as e:
                    err_msg = str(e).split("\n")[0][:70]
                    print(f"  ⚠ {domain} notice: {err_msg} (skipped)", flush=True)
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

            await browser.close()

        # Compile and persist statistical knowledge base
        self.compile_generalized_knowledge()

        print(f"\n=================================================================", flush=True)
        print(f"          GENERALIZED UI PATTERN LEARNING SUMMARY               ", flush=True)
        print(f"=================================================================", flush=True)
        print(f"  Domains Analyzed: {crawled_count} / {len(urls)}", flush=True)
        print(f"  Most Common Invariants Extracted Across Domains:", flush=True)
        for intent in sorted(self.domain_keyword_counts.keys()):
            top_kw = [f"'{k}' ({c} domains)" for k, c in self.domain_keyword_counts[intent].most_common(3)]
            if top_kw:
                print(f"    • {intent:<16}: {', '.join(top_kw)}", flush=True)
        print(f"=================================================================\n", flush=True)


def load_urls_from_file(file_path: Path) -> List[str]:
    """Loads URLs from a text file, filtering out blank lines and comments."""
    if not file_path.exists():
        raise FileNotFoundError(f"Websites file not found: {file_path}")

    urls = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                urls.append(stripped)
    return urls


def main():
    parser = argparse.ArgumentParser(description="LiteSight UI Pattern Scraper & Trainer")
    parser.add_argument("--file", type=str, default=str(DEFAULT_WEBSITES_FILE), help="Path to text file containing target URLs")
    parser.add_argument("--urls", nargs="+", default=None, help="Explicit list of URLs to crawl")
    parser.add_argument("--limit", type=int, default=None, help="Max number of websites to crawl")
    parser.add_argument("--timeout", type=int, default=15000, help="Per-site page load timeout in ms")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible headed mode")
    args = parser.parse_args()

    if args.urls:
        urls = args.urls
    else:
        file_path = Path(args.file)
        print(f"[Main] Loading training targets from: {file_path}", flush=True)
        urls = load_urls_from_file(file_path)

    if args.limit and args.limit > 0:
        urls = urls[:args.limit]

    learner = UIPatternLearner()
    asyncio.run(learner.crawl_and_train(urls, headless=not args.headed, timeout=args.timeout))


if __name__ == "__main__":
    main()
