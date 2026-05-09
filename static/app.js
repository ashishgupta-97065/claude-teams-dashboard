(function () {
  'use strict';

  var page = document.body.dataset.page;
  if (page === 'list') initListPage();
  else if (page === 'viewer') initViewerPage();

  // ============================================================
  // LIST PAGE
  // ============================================================

  function initListPage() {
    var repo = document.body.dataset.repo || '';
    var tbody = document.getElementById('ticket-tbody');

    bindRunButtons();
    setInterval(pollTickets, 10000);

    document.getElementById('manual-refresh') && document.getElementById('manual-refresh').addEventListener('click', function (e) {
      e.preventDefault();
      pollTickets();
    });

    function pollTickets() {
      var spinner = document.getElementById('refresh-spinner');
      if (spinner) spinner.style.display = 'inline-block';

      fetch('/api/tickets')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (spinner) spinner.style.display = 'none';
          updateRefreshTime(data.fetched_at);
          updateErrorBanner(data.error, data.stale);

          var tickets = data.tickets || [];
          if (!tbody) return;

          var existingRows = {};
          tbody.querySelectorAll('tr[data-ticket]').forEach(function (tr) {
            existingRows[tr.dataset.ticket] = tr;
          });

          tickets.forEach(function (ticket) {
            var key = String(ticket.number);
            if (existingRows[key]) {
              updateRow(existingRows[key], ticket);
            } else {
              var tr = buildRow(ticket);
              tbody.appendChild(tr);
              tr.querySelector('.run-btn') && bindRunBtn(tr.querySelector('.run-btn'));
            }
          });
        })
        .catch(function () {
          if (spinner) spinner.style.display = 'none';
        });
    }

    function updateRefreshTime(fetchedAt) {
      var el = document.getElementById('refresh-time');
      if (!el || !fetchedAt) return;
      try {
        var d = new Date(fetchedAt);
        el.textContent = d.toLocaleTimeString();
      } catch (e) {}
    }

    function updateErrorBanner(error, stale) {
      var banner = document.getElementById('error-banner');
      if (!banner) {
        if (error) {
          banner = document.createElement('div');
          banner.id = 'error-banner';
          banner.className = 'error-banner';
          banner.setAttribute('role', 'alert');
          banner.innerHTML = '<span></span><button class="btn-icon" aria-label="Dismiss error">&#x2715;</button>';
          banner.querySelector('.btn-icon').addEventListener('click', function () {
            banner.style.display = 'none';
          });
          var table = document.querySelector('.ticket-table') || document.querySelector('.empty-state');
          if (table) table.parentNode.insertBefore(banner, table);
        }
        return;
      }
      if (error) {
        banner.style.display = '';
        var span = banner.querySelector('span');
        if (span) span.textContent = 'GitHub fetch failed: ' + error + '. Showing last cached data.';
      } else {
        banner.style.display = 'none';
      }
    }

    function statusClass(status) {
      if (status === 'open') return 'pill-open';
      if (status === 'in-progress') return 'pill-inprogress';
      return 'pill-closed';
    }

    function statusLabel(status) {
      if (status === 'open') return 'OPEN';
      if (status === 'in-progress') return 'IN-PROGRESS';
      return 'CLOSED';
    }

    function updateRow(tr, ticket) {
      var pillEl = tr.querySelector('.pill');
      if (pillEl) {
        pillEl.className = 'pill ' + statusClass(ticket.status);
        pillEl.setAttribute('aria-label', 'Status: ' + statusLabel(ticket.status));
        var dotEl = pillEl.querySelector('.pulse-dot');
        if (ticket.status === 'in-progress' && !dotEl) {
          var dot = document.createElement('span');
          dot.className = 'pulse-dot';
          dot.setAttribute('aria-hidden', 'true');
          pillEl.insertBefore(dot, pillEl.firstChild);
        } else if (ticket.status !== 'in-progress' && dotEl) {
          dotEl.remove();
        }
        pillEl.lastChild.textContent = statusLabel(ticket.status);
        if (!pillEl.lastChild.nodeType === Node.TEXT_NODE) {
          pillEl.appendChild(document.createTextNode(statusLabel(ticket.status)));
        }
        var textNodes = Array.from(pillEl.childNodes).filter(function (n) { return n.nodeType === Node.TEXT_NODE; });
        textNodes.forEach(function (n) { n.textContent = ''; });
        pillEl.appendChild(document.createTextNode(statusLabel(ticket.status)));
      }
      var btn = tr.querySelector('.run-btn');
      if (btn) {
        btn.disabled = ticket.status !== 'open';
        btn.title = ticket.status === 'in-progress' ? 'Already running' : (ticket.status === 'closed' ? 'Closed ticket' : 'Run pipeline');
      }
    }

    function buildRow(ticket) {
      var tr = document.createElement('tr');
      tr.className = 'ticket-row';
      tr.tabIndex = 0;
      tr.dataset.ticket = ticket.number;
      tr.addEventListener('click', function () {
        window.open('/run/' + ticket.number, '_blank');
      });
      tr.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') window.open('/run/' + ticket.number, '_blank');
      });

      var sClass = statusClass(ticket.status);
      var sLabel = statusLabel(ticket.status);
      var dotHtml = ticket.status === 'in-progress' ? '<span class="pulse-dot" aria-hidden="true"></span>' : '';
      var disabled = ticket.status !== 'open' ? ' disabled' : '';
      var title = ticket.status === 'in-progress' ? 'Already running' : (ticket.status === 'closed' ? 'Closed ticket' : 'Run pipeline');

      tr.innerHTML = '<td class="col-num"><a href="/run/' + ticket.number + '" target="_blank">#' + ticket.number + '</a></td>'
        + '<td class="col-title">' + escHtml(ticket.title) + '</td>'
        + '<td class="col-status"><span class="pill ' + sClass + '" aria-label="Status: ' + sLabel + '">' + dotHtml + sLabel + '</span></td>'
        + '<td class="col-action"><button class="btn btn-primary run-btn" data-ticket="' + ticket.number + '"' + disabled + ' title="' + title + '">Run</button></td>';

      tr.querySelectorAll('td').forEach(function (td) {
        if (td.classList.contains('col-action')) {
          td.addEventListener('click', function (e) { e.stopPropagation(); });
        }
        if (td.classList.contains('col-num')) {
          td.addEventListener('click', function (e) { e.stopPropagation(); });
        }
      });
      return tr;
    }

    function bindRunButtons() {
      document.querySelectorAll('.run-btn').forEach(bindRunBtn);
    }

    function bindRunBtn(btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (btn.disabled) return;
        var n = btn.dataset.ticket;
        btn.disabled = true;
        var origText = btn.textContent;
        btn.textContent = '…';

        fetch('/run/' + n, { method: 'POST' })
          .then(function (r) {
            if (r.ok || r.status === 202) {
              window.open('/run/' + n, '_blank');
            }
            btn.textContent = origText;
          })
          .catch(function () {
            btn.textContent = origText;
            btn.disabled = false;
          });
      });
    }
  }

  // ============================================================
  // VIEWER PAGE  (Ticket #5 redesign)
  // ============================================================

  function initViewerPage() {
    var ctx = window.__VIEWER_CTX__;
    if (!ctx) return;

    var ticketId  = ctx.ticketId;
    var worksite  = ctx.worksite;
    var sseBase   = ctx.sseBase || '';

    // ---- State ----
    var state = {
      runActive:       false,
      phase:           null,
      iteration:       null,
      totals:          { cost: 0, turns: 0 },
      groups:          [],
      expandedFolders: new Set(),
      selectedFile:    null,
      treeData:        null,
      treeMtimes:      new Map(),
      pollTimer:       null,
      sseBackoffMs:    1000,
    };

    // ---- TimeFmt ----
    var TimeFmt = {
      relative: function (unixSeconds) {
        if (!unixSeconds) return '';
        var now = Date.now() / 1000;
        var diff = Math.floor(now - unixSeconds);
        if (diff < 5)  return 'just now';
        if (diff < 60) return diff + 's ago';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        return Math.floor(diff / 3600) + 'h ago';
      },
    };

    // ---- Renderers ----
    var Renderers = {
      escapeHtml: function (s) {
        return String(s)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      },
      renderPlain: function (text) {
        return '<pre class="preview-plain">' + Renderers.escapeHtml(text) + '</pre>';
      },
      renderMarkdown: function (text) {
        // Minimal: render as plain text; headings styled
        var lines = text.split('\n').map(function (line) {
          var m = line.match(/^(#{1,6})\s+(.*)$/);
          if (m) {
            var lvl = m[1].length;
            return '<h' + lvl + ' class="md-h">' + Renderers.escapeHtml(m[2]) + '</h' + lvl + '>';
          }
          if (line.startsWith('```')) return '';
          return '<div class="md-line">' + Renderers.escapeHtml(line) + '</div>';
        });
        return '<div class="preview-md">' + lines.join('') + '</div>';
      },
      renderPython: function (text) {
        // Minimal keyword highlighting
        var escaped = Renderers.escapeHtml(text);
        escaped = escaped.replace(/(#[^\n]*)/g, '<span class="tok-comment">$1</span>');
        escaped = escaped.replace(/\b(def|class|import|from|return|if|elif|else|for|while|in|and|or|not|is|None|True|False|with|as|try|except|finally|raise|yield|pass|break|continue|lambda|global|nonlocal|del|assert)\b/g,
          '<span class="tok-keyword">$1</span>');
        escaped = escaped.replace(/(&#34;&#34;&#34;[\s\S]*?&#34;&#34;&#34;|&#34;[^&#34;]*&#34;|&#39;[^&#39;]*&#39;)/g,
          '<span class="tok-string">$1</span>');
        return '<pre class="preview-py">' + escaped + '</pre>';
      },
      renderJson: function (text) {
        try {
          var pretty = JSON.stringify(JSON.parse(text), null, 2);
          return '<pre class="preview-json">' + Renderers.escapeHtml(pretty) + '</pre>';
        } catch (e) {
          return Renderers.renderPlain(text);
        }
      },
    };

    // ---- Parsers ----
    var Parsers = {
      parseDoneMessage: function (text) {
        var m = text.match(/\$([0-9]+(?:\.[0-9]+)?)\s*[,;]\s*([0-9]+)\s*turns?/i);
        if (!m) return null;
        return { cost: parseFloat(m[1]), turns: parseInt(m[2], 10) };
      },
      parseStarting: function (text) {
        return /starting|pipeline start/i.test(text);
      },
    };

    // ---- Phase ----
    var Phase = {
      detect: function (text) {
        if (/define/i.test(text)) return { phase: 'define' };
        var em = text.match(/execute.*iteration\s+(\d+)/i);
        if (em) return { phase: 'execute', iteration: parseInt(em[1], 10) };
        if (/run\s+complete/i.test(text)) return { phase: 'done' };
        return null;
      },
    };

    // ---- TopBar ----
    var TopBar = {
      phaseEl:    document.getElementById('phase-pill'),
      costEl:     document.getElementById('total-cost'),
      turnsEl:    document.getElementById('total-turns'),
      runBtn:     document.getElementById('run-btn'),

      setPhase: function (phase) {
        var el = TopBar.phaseEl;
        if (!el) return;
        el.className = 'phase-pill' + (phase ? ' phase-' + phase : '');
        el.textContent = phase ? phase.toUpperCase() : '—';
      },
      addCost: function (delta) {
        state.totals.cost += delta;
        if (TopBar.costEl) TopBar.costEl.textContent = state.totals.cost.toFixed(2);
      },
      addTurns: function (delta) {
        state.totals.turns += delta;
        if (TopBar.turnsEl) TopBar.turnsEl.textContent = String(state.totals.turns);
      },
      setRunActive: function (active) {
        state.runActive = active;
        var btn = TopBar.runBtn;
        if (!btn) return;
        btn.textContent = active ? 'Cancel' : 'Run';
        btn.className   = active ? 'btn btn-danger' : 'btn btn-primary';
      },
      bindRunButton: function () {
        var btn = TopBar.runBtn;
        if (!btn) return;
        btn.addEventListener('click', function () {
          if (state.runActive) {
            fetch('/api/run/' + ticketId + '/cancel', { method: 'POST' })
              .then(function () { TopBar.setRunActive(false); })
              .catch(function () {});
          } else {
            btn.disabled = true;
            fetch('/run/' + ticketId, { method: 'POST' })
              .then(function (r) {
                btn.disabled = false;
                if (r.ok || r.status === 202) {
                  TopBar.setRunActive(true);
                  SseClient.connect();
                }
              })
              .catch(function () { btn.disabled = false; });
          }
        });
      },
    };

    // ---- Timeline ----
    var timelineEl = document.getElementById('timeline');

    var Timeline = {
      append: function (event) {
        if (!timelineEl) return;

        // Remove empty placeholder
        var empty = timelineEl.querySelector('.timeline-empty');
        if (empty) empty.remove();

        var agentName = event.agent || 'unknown';
        var text = event.text || '';
        var ts   = event.timestamp || '';

        // Find or create group
        var group = state.groups.length > 0 ? state.groups[state.groups.length - 1] : null;
        var isOrch = agentName === 'orchestrator';

        // Start new group if agent changes or orchestrator banner
        if (!group || group.agent !== agentName || (isOrch && group.lastTs !== ts)) {
          group = Timeline._newGroup(agentName);
        }

        // Phase detection for orchestrator messages
        if (isOrch) {
          var phaseInfo = Phase.detect(text);
          if (phaseInfo) {
            if (phaseInfo.phase !== state.phase) {
              state.phase = phaseInfo.phase;
              state.iteration = phaseInfo.iteration || null;
              Timeline.insertPhaseDivider(
                phaseInfo.phase.toUpperCase() +
                (phaseInfo.iteration ? ' — Iteration ' + phaseInfo.iteration : '')
              );
              TopBar.setPhase(phaseInfo.phase);
              if (phaseInfo.phase === 'done') {
                TopBar.setRunActive(false);
                SseClient.disconnect();
              }
            }
          }
          // Cost/turns accumulation
          var done = Parsers.parseDoneMessage(text);
          if (done) {
            TopBar.addCost(done.cost);
            TopBar.addTurns(done.turns);
          }
        }

        // Append bubble
        var bubble = document.createElement('div');
        bubble.className = 'chat-bubble';
        var tsFormatted = ts
          ? TimeFmt.relative(new Date(ts).getTime() / 1000)
          : '';
        bubble.innerHTML =
          '<span class="bubble-ts" data-ts="' + Renderers.escapeHtml(ts) + '">' +
          Renderers.escapeHtml(tsFormatted) + '</span>' +
          Renderers.escapeHtml(text);

        group.bubblesEl.appendChild(bubble);
        group.lastTs = ts;

        // Update status pill
        if (group.pillEl) group.pillEl.className = 'agent-status-pill pill-running';

        // Auto-scroll
        var SCROLL_THRESHOLD = 40;
        var distFromBottom = timelineEl.scrollHeight - timelineEl.scrollTop - timelineEl.clientHeight;
        if (distFromBottom <= SCROLL_THRESHOLD) {
          timelineEl.scrollTop = timelineEl.scrollHeight;
        }
      },

      _newGroup: function (agentName) {
        var groupEl   = document.createElement('div');
        groupEl.className = 'agent-group';

        var headerEl  = document.createElement('div');
        headerEl.className = 'agent-group-header';

        var pillEl = document.createElement('span');
        pillEl.className = 'agent-status-pill';
        pillEl.textContent = 'RUNNING';

        headerEl.appendChild(pillEl);
        headerEl.appendChild(document.createTextNode(agentName.toUpperCase()));

        var bubblesEl = document.createElement('div');
        bubblesEl.className = 'agent-bubbles';

        groupEl.appendChild(headerEl);
        groupEl.appendChild(bubblesEl);
        if (timelineEl) timelineEl.appendChild(groupEl);

        var group = {
          agent: agentName,
          headerEl: headerEl,
          bubblesEl: bubblesEl,
          pillEl: pillEl,
          lastTs: null,
          status: 'running',
        };
        state.groups.push(group);
        return group;
      },

      insertPhaseDivider: function (label) {
        if (!timelineEl) return;
        var div = document.createElement('div');
        div.className = 'phase-divider';
        div.textContent = label;
        timelineEl.appendChild(div);
      },

      refreshTimestamps: function () {
        if (!timelineEl) return;
        timelineEl.querySelectorAll('.bubble-ts[data-ts]').forEach(function (el) {
          var ts = el.dataset.ts;
          if (ts) {
            el.textContent = TimeFmt.relative(new Date(ts).getTime() / 1000);
          }
        });
      },

      showReconnectToast: function (ms) {
        var existing = document.getElementById('reconnect-toast');
        if (existing) existing.remove();
        if (!timelineEl) return;
        var toast = document.createElement('div');
        toast.id = 'reconnect-toast';
        toast.className = 'reconnect-toast';
        toast.textContent = 'Reconnecting in ' + Math.round(ms / 1000) + 's…';
        timelineEl.appendChild(toast);
      },

      hideReconnectToast: function () {
        var toast = document.getElementById('reconnect-toast');
        if (toast) toast.remove();
      },

      jumpToLatest: function () {
        if (timelineEl) timelineEl.scrollTop = timelineEl.scrollHeight;
      },
    };

    // ---- SseClient ----
    var SseClient = {
      _reader: null,
      _abortCtrl: null,

      connect: function () {
        SseClient.disconnect();
        Timeline.hideReconnectToast();

        var url = sseBase + '/stream/' + worksite + '/' + ticketId;
        var abortCtrl = new AbortController();
        SseClient._abortCtrl = abortCtrl;

        fetch(url, { signal: abortCtrl.signal })
          .then(function (resp) {
            if (!resp.ok) { SseClient._scheduleReconnect(); return; }
            state.sseBackoffMs = 1000; // reset on successful connect
            state.runActive = true;
            TopBar.setRunActive(true);

            var reader = resp.body.getReader();
            SseClient._reader = reader;
            var decoder = new TextDecoder();
            var buffer = '';

            function pump() {
              reader.read().then(function (result) {
                if (result.done) { SseClient._scheduleReconnect(); return; }
                buffer += decoder.decode(result.value, { stream: true });
                var lines = buffer.split('\n');
                buffer = lines.pop();
                for (var i = 0; i < lines.length; i++) {
                  var line = lines[i].trim();
                  if (!line.startsWith('data:')) continue;
                  var raw = line.slice(5).trim();
                  if (!raw) continue;
                  try {
                    var evt = JSON.parse(raw);
                    SseClient._handleEvent(evt);
                  } catch (e) {}
                }
                pump();
              }).catch(function () { SseClient._scheduleReconnect(); });
            }
            pump();
          })
          .catch(function () { SseClient._scheduleReconnect(); });
      },

      disconnect: function () {
        if (SseClient._abortCtrl) {
          SseClient._abortCtrl.abort();
          SseClient._abortCtrl = null;
        }
        SseClient._reader = null;
      },

      _handleEvent: function (data) {
        if (!data) return;
        if (data.agent === '_system') {
          try {
            var inner = typeof data.text === 'string' ? JSON.parse(data.text) : data.text;
            if (inner.event === 'run_finished') {
              TopBar.setRunActive(false);
              SseClient.disconnect();
            }
          } catch (e) {}
          return;
        }
        Timeline.append(data);
      },

      _scheduleReconnect: function () {
        if (state.phase === 'done') return;
        var delay = state.sseBackoffMs;
        Timeline.showReconnectToast(delay);
        state.sseBackoffMs = Math.min(state.sseBackoffMs * 2, 30000);
        setTimeout(function () {
          Timeline.hideReconnectToast();
          SseClient.connect();
        }, delay);
      },
    };

    // ---- Preview ----
    var Preview = {
      showFile: function (path) {
        state.selectedFile = path;
        var previewEl = document.getElementById('preview');
        if (!previewEl) return;

        var ext = path.split('.').pop().toLowerCase();
        var url = '/api/workspace/' + ticketId + '/file?path=' + encodeURIComponent(path);

        fetch(url)
          .then(function (resp) {
            var truncated = resp.headers.get('x-truncated') === 'true';
            var origSize  = resp.headers.get('x-original-size');
            return resp.text().then(function (text) {
              return { text: text, truncated: truncated, origSize: origSize };
            });
          })
          .then(function (result) {
            var banner = '';
            if (result.truncated && result.origSize) {
              var mb = (parseInt(result.origSize, 10) / 1048576).toFixed(1);
              banner = '<div class="preview-truncated-banner">Showing first 1 MB of ' + mb + ' MB</div>';
            }
            var rendered = '';
            if (ext === 'md') {
              rendered = Renderers.renderMarkdown(result.text);
            } else if (ext === 'py') {
              rendered = Renderers.renderPython(result.text);
            } else if (ext === 'json') {
              rendered = Renderers.renderJson(result.text);
            } else {
              rendered = Renderers.renderPlain(result.text);
            }
            previewEl.innerHTML = banner + rendered;
          })
          .catch(function () {
            previewEl.innerHTML = '<div class="preview-empty">Failed to load file.</div>';
          });
      },
    };

    // ---- Tree ----
    var Tree = {
      startPolling: function () {
        Tree._fetchAndRender();
        if (state.runActive) {
          state.pollTimer = setInterval(Tree._fetchAndRender, 3000);
        }
      },

      stopPolling: function () {
        if (state.pollTimer !== null) {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
        }
      },

      _fetchAndRender: function () {
        fetch('/api/workspace/' + ticketId + '/files')
          .then(function (r) {
            if (!r.ok) return null;
            return r.json();
          })
          .then(function (data) {
            if (!data) return;
            state.treeData = data.entries || [];
            Tree.render(state.treeData);
          })
          .catch(function () {});
      },

      render: function (entries) {
        var treeEl = document.getElementById('tree');
        if (!treeEl) return;
        treeEl.innerHTML = '';

        if (!entries || entries.length === 0) {
          treeEl.innerHTML = '<div class="tree-empty">No files yet.</div>';
          return;
        }

        entries.forEach(function (entry) {
          var row = document.createElement('div');
          var depth = (entry.path.match(/\//g) || []).length;
          row.className = 'tree-row';
          row.style.paddingLeft = (8 + depth * 14) + 'px';
          row.dataset.path = entry.path;

          var prevMtime = state.treeMtimes.get(entry.path);
          if (prevMtime !== undefined && prevMtime !== entry.modified) {
            row.classList.add('row-flash');
            requestAnimationFrame(function () { row.classList.remove('row-flash'); });
          }
          state.treeMtimes.set(entry.path, entry.modified);

          if (entry.is_dir) {
            var expanded = state.expandedFolders.has(entry.path);
            row.innerHTML = '<span class="tree-icon">' + (expanded ? '▾' : '▸') + '</span>' +
              Renderers.escapeHtml(entry.path.split('/').pop());
            row.addEventListener('click', function () { Tree.toggleFolder(entry.path); });
          } else {
            row.innerHTML = '<span class="tree-icon">·</span>' +
              Renderers.escapeHtml(entry.path.split('/').pop());
            if (entry.path === state.selectedFile) row.classList.add('selected');
            row.addEventListener('click', function () { Tree.selectFile(entry.path); });
          }

          treeEl.appendChild(row);
        });
      },

      toggleFolder: function (path) {
        if (state.expandedFolders.has(path)) {
          state.expandedFolders.delete(path);
        } else {
          state.expandedFolders.add(path);
        }
        if (state.treeData) Tree.render(state.treeData);
      },

      selectFile: function (path) {
        state.selectedFile = path;
        Preview.showFile(path);
        // Re-render to update selection highlight
        if (state.treeData) Tree.render(state.treeData);
      },
    };

    // ---- Visibility handler ----
    function visibilityHandler() {
      if (document.visibilityState === 'visible') {
        if (!state.runActive) {
          Tree._fetchAndRender();
        }
      }
    }

    // ---- Bootstrap ----
    TopBar.bindRunButton();
    SseClient.connect();
    Tree.startPolling();
    setInterval(Timeline.refreshTimestamps, 10000);
    document.addEventListener('visibilitychange', visibilityHandler);
  }

  // ============================================================
  // UTILITIES
  // ============================================================

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

})();
