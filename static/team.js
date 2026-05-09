/* Team Manager Console — vanilla JS, single IIFE, no build step */
(function () {
  "use strict";

  // ── State ─────────────────────────────────────────────────────────────────

  var state = {
    agents: [],
    config: null,
    queue: [],
    queueDirty: false,
    configDirty: false,
  };

  // ── Toast ─────────────────────────────────────────────────────────────────

  var toastTimer = null;

  function toast(text, kind) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = text; // never innerHTML
    el.className = "toast visible " + (kind || "");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.className = "toast";
    }, 2000);
  }

  // ── Tabs ──────────────────────────────────────────────────────────────────

  function initTabs() {
    var tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        selectTab(tab);
      });
      tab.addEventListener("keydown", function (e) {
        var idx = tabs.indexOf(tab);
        if (e.key === "ArrowRight") {
          e.preventDefault();
          selectTab(tabs[(idx + 1) % tabs.length]);
          tabs[(idx + 1) % tabs.length].focus();
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          var prev = (idx - 1 + tabs.length) % tabs.length;
          selectTab(tabs[prev]);
          tabs[prev].focus();
        }
      });
    });
  }

  function selectTab(activeTab) {
    var tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    tabs.forEach(function (tab) {
      var panelId = tab.getAttribute("aria-controls");
      var panel = document.getElementById(panelId);
      var isActive = tab === activeTab;
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
      tab.tabIndex = isActive ? 0 : -1;
      if (panel) {
        if (isActive) {
          panel.removeAttribute("hidden");
        } else {
          panel.setAttribute("hidden", "");
        }
      }
    });
  }

  // ── Agents ────────────────────────────────────────────────────────────────

  var ALLOWED_MODELS = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
  ];

  function renderAgents(list) {
    state.agents = list;
    var tbody = document.getElementById("agents-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!list || list.length === 0) {
      var empty = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 5;
      td.className = "muted";
      td.textContent = "No agents found.";
      empty.appendChild(td);
      tbody.appendChild(empty);
      return;
    }

    list.forEach(function (agent) {
      var row = buildAgentRow(agent);
      var detail = buildDetailRow(agent);
      tbody.appendChild(row);
      tbody.appendChild(detail);
    });
  }

  function buildAgentRow(agent) {
    var tr = document.createElement("tr");
    tr.className = "agent-row";

    // Toggle cell
    var tdToggle = document.createElement("td");
    var toggleBtn = document.createElement("button");
    toggleBtn.className = "row-toggle";
    toggleBtn.setAttribute("aria-expanded", "false");
    toggleBtn.setAttribute("aria-label", "Show details");
    toggleBtn.textContent = "▸";
    toggleBtn.addEventListener("click", function () {
      var detailRow = tr.nextElementSibling;
      var expanded = toggleBtn.getAttribute("aria-expanded") === "true";
      if (expanded) {
        detailRow.setAttribute("hidden", "");
        toggleBtn.setAttribute("aria-expanded", "false");
        toggleBtn.textContent = "▸";
      } else {
        detailRow.removeAttribute("hidden");
        toggleBtn.setAttribute("aria-expanded", "true");
        toggleBtn.textContent = "▾";
      }
    });
    tdToggle.appendChild(toggleBtn);
    tr.appendChild(tdToggle);

    // Name
    var tdName = document.createElement("td");
    tdName.className = "mono";
    tdName.textContent = agent.name;
    tr.appendChild(tdName);

    // Model select
    var tdModel = document.createElement("td");
    var sel = document.createElement("select");
    sel.className = "model-select";
    ALLOWED_MODELS.forEach(function (m) {
      var opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m; // textContent safe
      if (m === agent.model) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function () {
      onModelChange(agent.name, sel.value, sel, agent);
    });
    tdModel.appendChild(sel);
    tr.appendChild(tdModel);

    // Tools
    var tdTools = document.createElement("td");
    tdTools.className = "muted mono";
    if (agent.tools && agent.tools.length) {
      tdTools.textContent = agent.tools.join(", ");
    } else {
      tdTools.textContent = "—";
    }
    tr.appendChild(tdTools);

    // Permission mode
    var tdMode = document.createElement("td");
    tdMode.className = "muted";
    tdMode.textContent = agent.permissionMode !== null && agent.permissionMode !== undefined
      ? agent.permissionMode
      : "—";
    tr.appendChild(tdMode);

    return tr;
  }

  function buildDetailRow(agent) {
    var tr = document.createElement("tr");
    tr.className = "detail-row";
    tr.setAttribute("hidden", "");

    var td = document.createElement("td");
    td.colSpan = 5;

    var inner = document.createElement("div");
    inner.className = "detail-row-inner";

    var pathLine = document.createElement("p");
    pathLine.className = "muted mono";
    var pathLabel = document.createTextNode("Path: ");
    var pathValue = document.createTextNode(agent.path);
    pathLine.appendChild(pathLabel);
    pathLine.appendChild(pathValue);
    inner.appendChild(pathLine);

    var promptLabel = document.createElement("p");
    promptLabel.className = "muted";
    promptLabel.textContent = "System prompt:";
    inner.appendChild(promptLabel);

    var pre = document.createElement("pre");
    pre.className = "system-prompt";
    pre.textContent = agent.system_prompt; // textContent prevents XSS
    inner.appendChild(pre);

    td.appendChild(inner);
    tr.appendChild(td);
    return tr;
  }

  function onModelChange(agentName, newModel, selectEl, agent) {
    var originalModel = agent.model;
    fetch("/api/agents/" + encodeURIComponent(agentName), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: newModel }),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (err) {
            throw new Error(err.error || ("HTTP " + res.status));
          });
        }
        return res.json();
      })
      .then(function (updated) {
        // Update state
        var idx = state.agents.findIndex(function (a) { return a.name === agentName; });
        if (idx !== -1) state.agents[idx] = updated;
        agent.model = updated.model;
        toast("Model updated for " + agentName, "success");
      })
      .catch(function (err) {
        // Revert select
        selectEl.value = originalModel;
        toast("Failed to update model: " + err.message, "error");
      });
  }

  // ── Config ────────────────────────────────────────────────────────────────

  function renderConfig(cfg) {
    state.config = cfg;

    var loopCapEl = document.getElementById("cfg-loop-cap");
    var humanModeEl = document.getElementById("cfg-human-mode");
    var agentsList = document.getElementById("cfg-agents-list");

    if (loopCapEl) loopCapEl.value = cfg.loop_cap || 1;
    if (humanModeEl) humanModeEl.value = cfg.human_mode || "no_human";

    if (agentsList) {
      agentsList.innerHTML = "";
      // Build union of cfg.agents and known agent names from state
      var knownNames = state.agents.map(function (a) { return a.name; });
      var cfgAgents = Array.isArray(cfg.agents) ? cfg.agents : [];
      var allNames = Array.from(new Set(knownNames.concat(cfgAgents))).sort();

      allNames.forEach(function (name) {
        var label = buildAgentCheckbox(name, cfgAgents.indexOf(name) !== -1, knownNames.indexOf(name) === -1);
        agentsList.appendChild(label);
      });

      if (allNames.length === 0) {
        var span = document.createElement("span");
        span.className = "muted";
        span.textContent = "No agents available.";
        agentsList.appendChild(span);
      }
    }
  }

  function buildAgentCheckbox(name, checked, isMissing) {
    var label = document.createElement("label");
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.name = "agents";
    cb.value = name;
    cb.checked = checked;
    label.appendChild(cb);

    var nameSpan = document.createElement("span");
    nameSpan.textContent = name; // textContent safe

    if (isMissing) {
      var missingSpan = document.createElement("span");
      missingSpan.className = "muted";
      missingSpan.textContent = " (missing on disk)";
      nameSpan.appendChild(missingSpan);
    }

    label.appendChild(nameSpan);
    return label;
  }

  function onConfigSave(e) {
    if (e) e.preventDefault();

    var loopCapEl = document.getElementById("cfg-loop-cap");
    var humanModeEl = document.getElementById("cfg-human-mode");
    var agentCheckboxes = document.querySelectorAll('#cfg-agents-list input[name="agents"]:checked');

    var loopCap = parseInt(loopCapEl ? loopCapEl.value : "1", 10);
    var humanMode = humanModeEl ? humanModeEl.value : "no_human";
    var agents = Array.from(agentCheckboxes).map(function (cb) { return cb.value; });

    if (!loopCap || loopCap < 1) {
      toast("Loop cap must be at least 1", "error");
      return;
    }

    var saveBtn = document.getElementById("config-save-btn");
    if (saveBtn) saveBtn.disabled = true;

    fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ loop_cap: loopCap, human_mode: humanMode, agents: agents }),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (err) {
            throw new Error(err.error || ("HTTP " + res.status));
          });
        }
        return res.json();
      })
      .then(function (updated) {
        state.config = updated;
        var indicator = document.getElementById("config-saved-indicator");
        if (indicator) {
          indicator.removeAttribute("hidden");
          setTimeout(function () { indicator.setAttribute("hidden", ""); }, 2000);
        }
        toast("Config saved", "success");
      })
      .catch(function (err) {
        toast("Failed to save config: " + err.message, "error");
      })
      .finally(function () {
        if (saveBtn) saveBtn.disabled = false;
      });
  }

  // ── Queue ─────────────────────────────────────────────────────────────────

  function renderQueue(tickets) {
    state.queue = tickets ? tickets.slice() : [];
    state.queueDirty = false;
    var ol = document.getElementById("queue-list");
    if (!ol) return;
    ol.innerHTML = "";

    if (state.queue.length === 0) {
      var empty = document.createElement("li");
      empty.className = "muted";
      empty.textContent = "Queue is empty.";
      ol.appendChild(empty);
      return;
    }

    state.queue.forEach(function (ticketNum) {
      ol.appendChild(buildQueueRow(ticketNum));
    });
  }

  function buildQueueRow(ticketNum) {
    var li = document.createElement("li");
    li.draggable = true;
    li.dataset.ticket = String(ticketNum);

    // Drag grip
    var grip = document.createElement("span");
    grip.className = "queue-grip";
    grip.setAttribute("aria-hidden", "true");
    grip.textContent = "⋮⋮";
    li.appendChild(grip);

    // Ticket number
    var numSpan = document.createElement("span");
    numSpan.className = "queue-ticket-num";
    numSpan.textContent = "#" + ticketNum; // textContent safe
    li.appendChild(numSpan);

    // Up / Down buttons
    var upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "queue-btn-sm";
    upBtn.textContent = "▲";
    upBtn.setAttribute("aria-label", "Move up");
    upBtn.addEventListener("click", function () { reorder(li, "up"); });
    li.appendChild(upBtn);

    var downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "queue-btn-sm";
    downBtn.textContent = "▼";
    downBtn.setAttribute("aria-label", "Move down");
    downBtn.addEventListener("click", function () { reorder(li, "down"); });
    li.appendChild(downBtn);

    // Remove button
    var removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "queue-btn-sm";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", function () {
      li.remove();
      markQueueDirty();
    });
    li.appendChild(removeBtn);

    // Drag-and-drop
    li.addEventListener("dragstart", function (e) {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", ticketNum);
      li.classList.add("dragging");
    });

    li.addEventListener("dragend", function () {
      li.classList.remove("dragging");
      clearDropIndicators();
    });

    li.addEventListener("dragover", function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      clearDropIndicators();
      var rect = li.getBoundingClientRect();
      var mid = rect.top + rect.height / 2;
      if (e.clientY < mid) {
        li.classList.add("drop-above");
      } else {
        li.classList.add("drop-below");
      }
    });

    li.addEventListener("dragleave", function () {
      li.classList.remove("drop-above");
      li.classList.remove("drop-below");
    });

    li.addEventListener("drop", function (e) {
      e.preventDefault();
      var dragging = document.querySelector(".dragging");
      if (!dragging || dragging === li) {
        clearDropIndicators();
        return;
      }
      var rect = li.getBoundingClientRect();
      var mid = rect.top + rect.height / 2;
      var ol = li.parentNode;
      if (e.clientY < mid) {
        ol.insertBefore(dragging, li);
      } else {
        ol.insertBefore(dragging, li.nextSibling);
      }
      clearDropIndicators();
      markQueueDirty();
    });

    return li;
  }

  function clearDropIndicators() {
    document.querySelectorAll(".drop-above, .drop-below").forEach(function (el) {
      el.classList.remove("drop-above");
      el.classList.remove("drop-below");
    });
  }

  // Shared reorder helper — used by both drag-and-drop and keyboard buttons.
  function reorder(li, direction) {
    var ol = li.parentNode;
    if (direction === "up" && li.previousElementSibling) {
      ol.insertBefore(li, li.previousElementSibling);
    } else if (direction === "down" && li.nextElementSibling) {
      ol.insertBefore(li.nextElementSibling, li);
    }
    markQueueDirty();
  }

  function reorderToIndex(li, targetIndex) {
    var ol = li.parentNode;
    var items = Array.from(ol.children);
    var ref = items[targetIndex];
    if (ref && ref !== li) {
      ol.insertBefore(li, ref);
    } else if (!ref) {
      ol.appendChild(li);
    }
    markQueueDirty();
  }

  function markQueueDirty() {
    state.queueDirty = true;
  }

  function onQueueAdd() {
    var input = document.getElementById("queue-add-input");
    var errorEl = document.getElementById("queue-add-error");
    var val = input ? parseInt(input.value, 10) : NaN;

    if (errorEl) errorEl.setAttribute("hidden", "");

    if (!val || val < 1 || isNaN(val)) {
      if (errorEl) {
        errorEl.textContent = "Please enter a positive integer.";
        errorEl.removeAttribute("hidden");
      }
      return;
    }

    var ol = document.getElementById("queue-list");
    // Remove "empty" placeholder if present
    var empties = ol.querySelectorAll("li.muted");
    empties.forEach(function (e) { e.remove(); });

    ol.appendChild(buildQueueRow(val));
    if (input) input.value = "";
    markQueueDirty();
  }

  function onQueueSave() {
    var ol = document.getElementById("queue-list");
    if (!ol) return;

    var items = Array.from(ol.querySelectorAll("li[data-ticket]"));
    var tickets = items.map(function (li) { return parseInt(li.dataset.ticket, 10); });

    var saveBtn = document.getElementById("queue-save-btn");
    if (saveBtn) saveBtn.disabled = true;

    fetch("/api/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickets: tickets }),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (err) {
            throw new Error(err.error || ("HTTP " + res.status));
          });
        }
        return res.json();
      })
      .then(function (data) {
        state.queue = data.tickets;
        state.queueDirty = false;
        var indicator = document.getElementById("queue-saved-indicator");
        if (indicator) {
          indicator.removeAttribute("hidden");
          setTimeout(function () { indicator.setAttribute("hidden", ""); }, 2000);
        }
        toast("Queue saved", "success");
      })
      .catch(function (err) {
        toast("Failed to save queue: " + err.message, "error");
      })
      .finally(function () {
        if (saveBtn) saveBtn.disabled = false;
      });
  }

  // ── Boot ──────────────────────────────────────────────────────────────────

  function boot() {
    initTabs();

    // Wire config form
    var configForm = document.getElementById("config-form");
    if (configForm) configForm.addEventListener("submit", onConfigSave);

    // Wire queue buttons
    var addBtn = document.getElementById("queue-add-btn");
    if (addBtn) addBtn.addEventListener("click", onQueueAdd);

    var addInput = document.getElementById("queue-add-input");
    if (addInput) {
      addInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); onQueueAdd(); }
      });
    }

    var saveQueueBtn = document.getElementById("queue-save-btn");
    if (saveQueueBtn) saveQueueBtn.addEventListener("click", onQueueSave);

    // Parallel fetches
    var agentsPromise = fetch("/api/agents")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderAgents(data);
      })
      .catch(function (err) {
        var tbody = document.getElementById("agents-tbody");
        if (tbody) {
          tbody.innerHTML = "";
          var tr = document.createElement("tr");
          var td = document.createElement("td");
          td.colSpan = 5;
          td.className = "muted";
          td.textContent = "Failed to load agents.";
          tr.appendChild(td);
          tbody.appendChild(tr);
        }
      });

    var configPromise = fetch("/api/config")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (cfg) {
        // Defer renderConfig until agents are loaded so the union works correctly
        agentsPromise.then(function () { renderConfig(cfg); });
      })
      .catch(function (err) {
        var agentsList = document.getElementById("cfg-agents-list");
        if (agentsList) {
          agentsList.innerHTML = "";
          var span = document.createElement("span");
          span.className = "muted";
          span.textContent = "Failed to load config.";
          agentsList.appendChild(span);
        }
      });

    fetch("/api/queue")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderQueue(data.tickets || []);
      })
      .catch(function () {
        var ol = document.getElementById("queue-list");
        if (ol) {
          ol.innerHTML = "";
          var li = document.createElement("li");
          li.className = "muted";
          li.textContent = "Failed to load queue.";
          ol.appendChild(li);
        }
      });
  }

  // Kick off on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
