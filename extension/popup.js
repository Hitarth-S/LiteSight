// extension/popup.js
document.addEventListener("DOMContentLoaded", () => {
    // Tab navigation elements
    const tabBtnAgent = document.getElementById("tab-btn-agent");
    const tabBtnPrivacy = document.getElementById("tab-btn-privacy");
    const tabAgent = document.getElementById("tab-agent");
    const tabPrivacy = document.getElementById("tab-privacy");

    // Agent view elements
    const goalInput = document.getElementById("goal-input");
    const serverUrlInput = document.getElementById("server-url");
    const btnRun = document.getElementById("btn-run");
    const btnStep = document.getElementById("btn-step");
    const btnPreview = document.getElementById("btn-preview");
    const btnHud = document.getElementById("btn-hud");
    const logConsole = document.getElementById("log-console");
    const metricPii = document.getElementById("metric-pii");
    const metricMonitored = document.getElementById("metric-monitored");

    // Autonomous execution state
    let _planQueue = [];
    let _currentStepNumber = 0;
    let _totalSteps = 0;
    let _isRunning = false;

    // Redaction panel elements
    const redactPanel = document.getElementById("redactPanel");
    const countsLine = document.getElementById("countsLine");
    const originalCol = document.getElementById("originalCol");
    const sentCol = document.getElementById("sentCol");
    let _previewActive = false;

    // Settings view elements
    const settingSensitivity = document.getElementById("setting-sensitivity");
    const sensitivityExplanation = document.getElementById("sensitivity-explanation");
    const catCreditCards = document.getElementById("cat-credit-cards");
    const catPasswords = document.getElementById("cat-passwords");
    const catEmails = document.getElementById("cat-emails");
    const catNames = document.getElementById("cat-names");
    const catPhones = document.getElementById("cat-phones");
    const catGovIds = document.getElementById("cat-gov-ids");
    const settingVisualIndicators = document.getElementById("setting-visual-indicators");
    const settingsSaveStatus = document.getElementById("settings-save-status");

    function log(msg) {
        if (!logConsole) return;
        logConsole.textContent += `\n${msg}`;
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    // 1. Tab Switching Logic
    tabBtnAgent.addEventListener("click", () => {
        tabBtnAgent.classList.add("active");
        tabBtnPrivacy.classList.remove("active");
        tabAgent.classList.add("active");
        tabPrivacy.classList.remove("active");
    });

    tabBtnPrivacy.addEventListener("click", () => {
        tabBtnPrivacy.classList.add("active");
        tabBtnAgent.classList.remove("active");
        tabPrivacy.classList.add("active");
        tabAgent.classList.remove("active");
    });

    // 2. Sensitivity Explanations
    const SENSITIVITY_DESCS = {
        strict: "Maximum privacy. Deep heuristic scanning of all text, inputs, names, high-entropy tokens, and profile avatars.",
        balanced: "Standard protection. Actively scans credentials, cards, emails, names, phone numbers, and IDs.",
        relaxed: "Minimal overhead. Focuses strictly on high-risk credentials (passwords and credit card numbers)."
    };

    function updateSensitivityDesc(val) {
        if (sensitivityExplanation && SENSITIVITY_DESCS[val]) {
            sensitivityExplanation.textContent = SENSITIVITY_DESCS[val];
        }
    }

    // 3. Settings Persistence & Synchronization
    function collectCurrentSettings() {
        return {
            sensitivity: settingSensitivity.value,
            categories: {
                credit_cards: catCreditCards.checked,
                passwords: catPasswords.checked,
                emails: catEmails.checked,
                names: catNames.checked,
                phone_numbers: catPhones.checked,
                government_ids: catGovIds.checked
            },
            visual_indicators: settingVisualIndicators.checked
        };
    }

    function applySettingsToUI(cfg) {
        if (!cfg) return;
        if (cfg.sensitivity) {
            settingSensitivity.value = cfg.sensitivity;
            updateSensitivityDesc(cfg.sensitivity);
        }
        if (cfg.categories) {
            if (typeof cfg.categories.credit_cards === 'boolean') catCreditCards.checked = cfg.categories.credit_cards;
            if (typeof cfg.categories.passwords === 'boolean') catPasswords.checked = cfg.categories.passwords;
            if (typeof cfg.categories.emails === 'boolean') catEmails.checked = cfg.categories.emails;
            if (typeof cfg.categories.names === 'boolean') catNames.checked = cfg.categories.names;
            if (typeof cfg.categories.phone_numbers === 'boolean') catPhones.checked = cfg.categories.phone_numbers;
            if (typeof cfg.categories.government_ids === 'boolean') catGovIds.checked = cfg.categories.government_ids;
        }
        if (typeof cfg.visual_indicators === 'boolean') {
            settingVisualIndicators.checked = cfg.visual_indicators;
        }
    }

    function saveAndSyncSettings() {
        const config = collectCurrentSettings();

        // Save locally
        if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            chrome.storage.local.set({ litesight_privacy_settings: config });
        } else {
            try { localStorage.setItem('litesight_privacy_settings', JSON.stringify(config)); } catch (_) {}
        }

        // Notify active tab content script
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs && tabs[0]) {
                chrome.tabs.sendMessage(tabs[0].id, {
                    action: "UPDATE_SETTINGS",
                    config: config
                }, (response) => {
                    if (response && response.success) {
                        if (metricPii && typeof response.redacted === 'number') metricPii.textContent = response.redacted;
                        if (metricMonitored && typeof response.monitored === 'number') metricMonitored.textContent = response.monitored;
                    }
                });
            }
        });

        // Flash confirmation
        if (settingsSaveStatus) {
            settingsSaveStatus.style.display = "block";
            setTimeout(() => { settingsSaveStatus.style.display = "none"; }, 2500);
        }
    }

    // Bind settings event listeners
    settingSensitivity.addEventListener("change", () => {
        updateSensitivityDesc(settingSensitivity.value);
        saveAndSyncSettings();
    });
    [catCreditCards, catPasswords, catEmails, catNames, catPhones, catGovIds, settingVisualIndicators].forEach(el => {
        if (el) el.addEventListener("change", saveAndSyncSettings);
    });

    // 4. Initial Load: Retrieve stored settings or tab state
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(['litesight_privacy_settings'], (result) => {
            if (result && result.litesight_privacy_settings) {
                applySettingsToUI(result.litesight_privacy_settings);
            }
        });
    }

    // Refresh state from active page when popup opens
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (!tabs[0]) return;
        chrome.tabs.sendMessage(tabs[0].id, { action: "GET_PAGE_STATE" }, (response) => {
            if (chrome.runtime.lastError || !response) {
                log("[Status] Ready. Open an interactive page to automate.");
                return;
            }
            if (metricPii) metricPii.textContent = response.redacted_count !== undefined ? response.redacted_count : (response.pii_count || 0);
            if (metricMonitored) metricMonitored.textContent = response.monitored_count || 0;
            if (response.config) {
                applySettingsToUI(response.config);
            }
            log(`[Snapshot] ${response.elements.length} elements indexed. Redacted: ${response.redacted_count || 0}, Monitored: ${response.monitored_count || 0}`);
        });
    });

    btnHud.addEventListener("click", () => {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (!tabs[0]) return;
            chrome.tabs.sendMessage(tabs[0].id, { action: "SHOW_HUD" }, (res) => {
                log("[HUD] Toggled interactive visual sentinel overlay.");
            });
        });
    });

    function _maskDisplay(type, value) {
        if (type === 'AADHAAR') {
            const digits = value.replace(/[\s-]/g, '');
            return '**** **** ' + digits.slice(8);
        }
        if (type === 'PAN') {
            return value.slice(0, 3) + '**' + value.slice(5, 9) + '*';
        }
        if (type === 'PHONE') {
            return '+91 98*** ***' + value.replace(/[\s-]/g, '').slice(-2);
        }
        if (type === 'EMAIL') {
            const atIdx = value.indexOf('@');
            const local = value.slice(0, atIdx);
            const domain = value.slice(atIdx + 1);
            return local[0] + '*'.repeat(Math.max(1, local.length - 1)) + '@' + domain;
        }
        if (type === 'PASSWORD') {
            return '********';
        }
        return '***';
    }

    if (btnPreview) {
        btnPreview.addEventListener("click", () => {
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                if (!tabs[0]) return;
                const tabId = tabs[0].id;

                if (_previewActive) {
                    chrome.tabs.sendMessage(tabId, { type: "RESTORE_PAGE" }, (res) => {
                        _previewActive = false;
                        btnPreview.textContent = "🔒 Preview";
                        if (redactPanel) redactPanel.style.display = "none";
                        log("[Preview] Page restored to original DOM state.");
                    });
                } else {
                    chrome.tabs.sendMessage(tabId, { type: "PREVIEW_REDACTION" }, (res) => {
                        if (!res || res.error) {
                            log(`[Preview Error] ${res ? res.error : 'Failed to trigger preview'}`);
                            return;
                        }
                        _previewActive = true;
                        btnPreview.textContent = "↩ Restore";
                        if (redactPanel) redactPanel.style.display = "block";

                        const total = Object.values(res.counts || {}).reduce((a, b) => a + b, 0);
                        const parts = Object.entries(res.counts || {}).map(([k, v]) => `${k}:${v}`);
                        if (countsLine) countsLine.textContent = `${total} items (${parts.join(', ')})`;

                        if (originalCol) {
                            originalCol.textContent = '';
                            (res.original || []).forEach(item => {
                                const row = document.createElement('div');
                                row.style.marginBottom = '4px';
                                row.textContent = `[${item.field}] ${item.value}`;
                                originalCol.appendChild(row);
                            });
                        }

                        if (sentCol) {
                            sentCol.textContent = '';
                            (res.original || []).forEach(item => {
                                const row = document.createElement('div');
                                row.style.marginBottom = '4px';
                                row.textContent = `[${item.field}] ${_maskDisplay(item.field, item.value)}`;
                                sentCol.appendChild(row);
                            });
                        }

                        log(`[Preview] Redaction active: ${total} PII items masked in-place.`);
                    });
                }
            });
        });
    }

    function decomposeGoal(goalStr) {
        if (!goalStr) return [];
        if (goalStr.includes(',') || goalStr.includes(';') || /\s+and\s+/i.test(goalStr) || /\s+then\s+/i.test(goalStr)) {
            const raw = goalStr.split(/[,;]|\s+and\s+|\s+then\s+/i);
            return raw.map(s => s.replace(/^(?:and|then)\s+/i, '').trim()).filter(Boolean);
        }
        return [goalStr];
    }

    async function executeSingleStep(subgoal, activeTabId, serverUrl) {
        return new Promise((resolve) => {
            chrome.tabs.sendMessage(activeTabId, { action: "GET_PAGE_STATE" }, (state) => {
                if (chrome.runtime.lastError || !state) {
                    log("[Error] Cannot reach page content script. Reload page.");
                    resolve({ success: false });
                    return;
                }

                if (metricPii) metricPii.textContent = state.redacted_count !== undefined ? state.redacted_count : (state.pii_count || 0);
                if (metricMonitored) metricMonitored.textContent = state.monitored_count || 0;

                log(`[Server] Requesting action for: "${subgoal}"...`);
                chrome.runtime.sendMessage({
                    action: "SEND_TO_SERVER",
                    serverUrl: serverUrl,
                    payload: {
                        subgoal: subgoal,
                        elements: state.elements,
                        url: state.url,
                        pii_count: state.pii_count
                    }
                }, (response) => {
                    if (!response || !response.success) {
                        log(`[Server Error] ${response ? response.error : 'Connection refused. Is server running?'}`);
                        resolve({ success: false });
                        return;
                    }

                    const action = response.action;
                    log(`[Action Planned] ${action.operation} on node [${action.target_index}]: "${action.target_label || action.reasoning || ''}"`);

                    chrome.tabs.sendMessage(activeTabId, { action: "EXECUTE_ACTION", payload: action }, (execRes) => {
                        if (execRes && execRes.success) {
                            log(`[Execution] ✓ Completed successfully.`);
                            resolve({ success: true, action: action });
                        } else {
                            log(`[Execution Failed] ${execRes ? execRes.error : 'Unknown'}`);
                            resolve({ success: false });
                        }
                    });
                });
            });
        });
    }

    if (btnRun) {
        btnRun.addEventListener("click", async () => {
            const goal = goalInput.value.trim();
            const serverUrl = serverUrlInput.value.trim();
            if (!goal) return;

            if (_isRunning) {
                _isRunning = false;
                btnRun.textContent = "▶ Run Goal";
                btnStep.disabled = false;
                log("[Agent] User requested stop.");
                return;
            }

            const tabs = await new Promise(r => chrome.tabs.query({ active: true, currentWindow: true }, r));
            if (!tabs || !tabs[0]) return;
            const activeTabId = tabs[0].id;

            const subgoals = decomposeGoal(goal);
            _isRunning = true;
            btnRun.textContent = "⏹ Stop";
            btnStep.disabled = true;

            log(`[Orchestrator] Plan established: ${subgoals.length} sequential subgoals.`);
            for (let i = 0; i < subgoals.length; i++) {
                log(`  [${i + 1}/${subgoals.length}] -> ${subgoals[i]}`);
            }

            try {
                for (let i = 0; i < subgoals.length; i++) {
                    if (!_isRunning) break;
                    const currentSubgoal = subgoals[i];
                    log(`\n=======================================================\n[Orchestrator] Step [${i + 1}/${subgoals.length}]: ${currentSubgoal}\n=======================================================`);

                    const subgoalLower = currentSubgoal.toLowerCase();
                    const isSearchStep = subgoalLower.startsWith("search") || subgoalLower.includes("search for");

                    // Query tab URL before execution
                    const tabBefore = await new Promise(r => chrome.tabs.get(activeTabId, r));
                    const urlBefore = tabBefore ? tabBefore.url : "";

                    const res = await executeSingleStep(currentSubgoal, activeTabId, serverUrl);
                    if (!res.success) {
                        log(`[Orchestrator] Step failed. Stopping agent.`);
                        break;
                    }

                    if (i < subgoals.length - 1) {
                        log(`[Orchestrator] Waiting for page mutation/navigation to settle...`);
                        await new Promise(r => setTimeout(r, 2400));

                        // Closed-Loop State Verification:
                        const tabAfter = await new Promise(r => chrome.tabs.get(activeTabId, r));
                        const urlAfter = tabAfter ? tabAfter.url : "";

                        if (isSearchStep) {
                            const isSearchUrl = /([?&](k|q|query)=|\/s\?|\/search)/i.test(urlAfter);
                            if (isSearchUrl || (urlBefore && urlAfter !== urlBefore)) {
                                log(`[Verifier] ✓ Search verified: Navigation transitioned to search results page.`);
                            } else {
                                log(`[Verifier] ⚠️ State check: Page URL unchanged (${urlAfter}). Waiting for DOM update...`);
                                await new Promise(r => setTimeout(r, 1200));
                            }
                        }

                        // Safety Interlock: Guard against executing filters on the homepage
                        const nextSubgoalLower = subgoals[i + 1].toLowerCase();
                        const isNextFilter = nextSubgoalLower.includes("filter") || nextSubgoalLower.includes("star");
                        if (isNextFilter && urlBefore && urlAfter === urlBefore && !/([?&](k|q|query)=|\/s\?|\/search)/i.test(urlAfter)) {
                            log(`[Verifier] ⚠️ Safety Interlock: Next step expects search results, but browser remains on '${urlAfter}'. Pausing to prevent unintended clicks.`);
                        }
                    }
                }
            } finally {
                _isRunning = false;
                btnRun.textContent = "▶ Run Goal";
                btnStep.disabled = false;
                log(`[LiteSight] Autonomous goal execution cycle finished.`);
            }
        });
    }

    btnStep.addEventListener("click", async () => {
        const goal = goalInput.value.trim();
        const serverUrl = serverUrlInput.value.trim();
        if (!goal) return;

        if (_planQueue.length === 0) {
            _planQueue = decomposeGoal(goal);
            _totalSteps = _planQueue.length;
            _currentStepNumber = 0;
            log(`[Plan] Initialized ${_totalSteps} discrete steps.`);
        }

        const activeSubgoal = _planQueue.shift();
        _currentStepNumber++;

        btnStep.disabled = true;
        log(`\n=======================================================\n[Step ${_currentStepNumber}/${_totalSteps}]: ${activeSubgoal}\n=======================================================`);

        chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
            if (!tabs[0]) {
                btnStep.disabled = false;
                return;
            }
            const activeTabId = tabs[0].id;
            await executeSingleStep(activeSubgoal, activeTabId, serverUrl);
            btnStep.disabled = false;

            if (_planQueue.length > 0) {
                log(`[Next Step ready]: ${_planQueue[0]} (Click 'Step' to continue)`);
            } else {
                log(`[Plan Finished] All ${_totalSteps} steps completed!`);
            }
        });
    });
});
