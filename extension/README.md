# LiteSight Browser Extension (Manifest V3)

Language: Simplified Technical English (STE)

This directory contains the browser extension for LiteSight. The extension runs in popular web browsers (Google Chrome, Brave, Microsoft Edge, and Mozilla Firefox).

---

## 1. What the Extension Does

1. **Scans Page State**: Reads interactive DOM elements and computes accessible labels and bounding boxes.
2. **Detects & Redacts PII Locally**: Identifies sensitive fields (passwords, credit cards, emails, phone numbers, names, government IDs) directly on the device.
3. **Displays In-Page Indicators**:
   - `👁️ MONITORED`: Dashed cyan outline on empty sensitive inputs under active observation.
   - `🛡️ REDACTED`: Emerald green border on inputs containing redacted data.
4. **Sends Sanitized Data to Server**: Sends only anonymized DOM structures and masked tokens to `server.py`.
5. **Executes Action Commands**: Receives commands (`CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_DOWN`) from the server and executes them in the active tab.

---

## 2. Installation Instructions

### Chrome, Brave, or Microsoft Edge
1. Open the browser and go to `chrome://extensions` (or `brave://extensions` / `edge://extensions`).
2. Turn on the **Developer mode** toggle in the top-right corner.
3. Click **Load unpacked**.
4. Select the `extension/` folder:
   ```
   /home/aadi/Clone/LiteSight/extension
   ```
5. The LiteSight 🛡️ icon will appear in your browser toolbar.

### Mozilla Firefox
1. Open Firefox and go to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**.
3. Select the `manifest.json` file inside the `extension/` folder.

---

## 3. End-to-End Workflow with Server

1. **Start the reasoning server**:
   ```bash
   python server.py --host 0.0.0.0 --port 8000
   ```
2. **Open a target web page** in your browser (for example, `http://127.0.0.1:5000` or an e-commerce website).
3. **Open the LiteSight popup** by clicking the toolbar icon:
   - **Agent Control Tab**: Enter your goal (for example, `"login using username -> admin, password -> admin, select role as -> admin"`). Click **Execute Step**.
   - **Privacy Settings Tab**: Select your sensitivity level (`Strict`, `Balanced`, `Relaxed`) and toggle specific PII categories.
4. **Observe the execution**: The extension highlights monitored fields, sends sanitized data to the server, and executes the returned actions in real time.
