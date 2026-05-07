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
  // VIEWER PAGE
  // ============================================================

  function initViewerPage() {
    var body = document.body;
    var ticketNumber = body.dataset.ticket;
    if (!ticketNumber) return;

    var es = null;
    var badgeCounts = {};
    var panelEntryCount = {};

    var MAX_ENTRIES = 1000;
    var SCROLL_THRESHOLD = 40;

    function getPanel(agentName) {
      return document.getElementById('panel-' + agentName);
    }

    function getLog(agentName) {
      return document.getElementById('log-' + agentName);
    }

    function getBadge(agentName) {
      return document.getElementById('badge-' + agentName);
    }

    function getNewBtn(agentName) {
      return document.getElementById('newbtn-' + agentName);
    }

    function formatTs(ts) {
      if (!ts) return '';
      try {
        var d = new Date(ts);
        return '[' + d.toLocaleTimeString() + ']';
      } catch (e) {
        return ts.slice(0, 19).replace('T', ' ');
      }
    }

    function appendEntry(agentName, text, timestamp) {
      var log = getLog(agentName);
      if (!log) return;

      var emptyEl = document.getElementById('empty-' + agentName);
      if (emptyEl) emptyEl.remove();

      var entry = document.createElement('div');
      entry.className = 'log-entry';
      var tsSpan = document.createElement('span');
      tsSpan.className = 'log-ts';
      tsSpan.textContent = formatTs(timestamp);
      var textSpan = document.createElement('span');
      textSpan.className = 'log-text';
      textSpan.textContent = text;
      entry.appendChild(tsSpan);
      entry.appendChild(textSpan);
      log.appendChild(entry);

      panelEntryCount[agentName] = (panelEntryCount[agentName] || 0) + 1;
      trimLog(agentName, log);
      handleAutoScroll(agentName, log);

      var panel = getPanel(agentName);
      if (panel && !panel.open) {
        badgeCounts[agentName] = (badgeCounts[agentName] || 0) + 1;
        var badge = getBadge(agentName);
        if (badge) {
          badge.textContent = '+' + badgeCounts[agentName];
          badge.style.display = 'inline-block';
        }
      }
    }

    function trimLog(agentName, log) {
      var entries = log.querySelectorAll('.log-entry');
      if (entries.length > MAX_ENTRIES) {
        var toRemove = entries.length - MAX_ENTRIES;
        for (var i = 0; i < toRemove; i++) {
          entries[i].remove();
        }
        if (!log.querySelector('.log-trimmed-notice')) {
          var notice = document.createElement('div');
          notice.className = 'log-trimmed-notice';
          notice.textContent = '(older entries trimmed)';
          log.insertBefore(notice, log.firstChild);
        }
      }
    }

    function handleAutoScroll(agentName, log) {
      var newBtn = getNewBtn(agentName);
      var distFromBottom = log.scrollHeight - log.scrollTop - log.clientHeight;
      if (distFromBottom <= SCROLL_THRESHOLD) {
        log.scrollTop = log.scrollHeight;
        if (newBtn) newBtn.style.display = 'none';
      } else {
        if (newBtn) newBtn.style.display = 'inline-flex';
      }
    }

    document.querySelectorAll('.agent-panel').forEach(function (panel) {
      var agentName = panel.dataset.agent;
      var badge = getBadge(agentName);

      panel.addEventListener('toggle', function () {
        if (panel.open) {
          badgeCounts[agentName] = 0;
          if (badge) badge.style.display = 'none';
        }
      });

      var newBtn = getNewBtn(agentName);
      if (newBtn) {
        newBtn.addEventListener('click', function () {
          var log = getLog(agentName);
          if (log) log.scrollTop = log.scrollHeight;
          newBtn.style.display = 'none';
        });
      }
    });

    function setPanelStatus(agentName, status) {
      var panel = getPanel(agentName);
      if (!panel) return;
      panel.dataset.status = status;

      var pill = panel.querySelector('.pill');
      if (!pill) return;

      pill.className = 'pill ' + (status === 'done' ? 'pill-done' : status === 'running' ? 'pill-inprogress' : 'pill-waiting');
      pill.setAttribute('aria-label', 'Status: ' + status.toUpperCase());

      var dot = pill.querySelector('.pulse-dot');
      var check = pill.querySelector('.check-icon');

      if (status === 'running') {
        if (!dot) {
          dot = document.createElement('span');
          dot.className = 'pulse-dot';
          dot.setAttribute('aria-hidden', 'true');
          pill.insertBefore(dot, pill.firstChild);
        }
        if (check) check.remove();
      } else {
        if (dot) dot.remove();
      }

      if (status === 'done') {
        if (!check) {
          check = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          check.setAttribute('class', 'check-icon');
          check.setAttribute('width', '12');
          check.setAttribute('height', '12');
          check.setAttribute('viewBox', '0 0 12 12');
          check.setAttribute('fill', 'none');
          check.setAttribute('aria-hidden', 'true');
          var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('d', 'M2 6l3 3 5-5');
          path.setAttribute('stroke', 'currentColor');
          path.setAttribute('stroke-width', '1.5');
          path.setAttribute('stroke-linecap', 'round');
          path.setAttribute('stroke-linejoin', 'round');
          check.appendChild(path);
          pill.insertBefore(check, pill.firstChild);
        }
      } else {
        if (check) check.remove();
      }

      var textNodes = Array.from(pill.childNodes).filter(function (n) { return n.nodeType === Node.TEXT_NODE; });
      textNodes.forEach(function (n) { n.textContent = ''; });
      pill.appendChild(document.createTextNode(status.toUpperCase()));

      if (status === 'running' && !panel.open) {
        panel.open = true;
      }

      updateProgressIndicator();
    }

    function updateProgressIndicator() {
      var panels = document.querySelectorAll('.agent-panel');
      var doneCount = 0;
      panels.forEach(function (p) {
        if (p.dataset.status === 'done') doneCount++;
      });
      var indicator = document.getElementById('progress-indicator');
      if (indicator) indicator.textContent = doneCount + '/' + panels.length + ' done';
    }

    function showCheckpoint(body) {
      var slot = document.getElementById('checkpoint-slot');
      var bodyEl = document.getElementById('checkpoint-body');
      if (bodyEl && body) bodyEl.textContent = body;
      if (slot) slot.style.display = '';
      var approvedBtn = document.getElementById('btn-approved');
      if (approvedBtn) approvedBtn.focus();
    }

    function hideCheckpoint() {
      var slot = document.getElementById('checkpoint-slot');
      if (slot) slot.style.display = 'none';
    }

    var changesInput = document.getElementById('changes-input');
    var submitChangesBtn = document.getElementById('btn-submit-changes');

    if (changesInput && submitChangesBtn) {
      changesInput.addEventListener('input', function () {
        submitChangesBtn.disabled = changesInput.value.trim().length === 0;
      });
    }

    function submitHumanResponse(bodyText) {
      var submitting = document.getElementById('checkpoint-submitting');
      var approvedBtn = document.getElementById('btn-approved');
      var changesBtn = document.getElementById('btn-submit-changes');
      if (submitting) submitting.style.display = '';
      if (approvedBtn) approvedBtn.disabled = true;
      if (changesBtn) changesBtn.disabled = true;

      var form = new FormData();
      form.append('body', bodyText);

      fetch('/run/' + ticketNumber + '/human_response', {
        method: 'POST',
        body: new URLSearchParams({ body: bodyText }),
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
        .then(function (r) {
          if (r.ok || r.status === 409) {
            setTimeout(hideCheckpoint, 1000);
          }
          if (submitting) submitting.style.display = 'none';
        })
        .catch(function () {
          if (submitting) submitting.style.display = 'none';
          if (approvedBtn) approvedBtn.disabled = false;
          if (changesBtn) changesBtn.disabled = false;
        });
    }

    var approvedBtn = document.getElementById('btn-approved');
    if (approvedBtn) {
      approvedBtn.addEventListener('click', function () {
        submitHumanResponse('APPROVED');
      });
    }

    var submitChangesBtn2 = document.getElementById('btn-submit-changes');
    if (submitChangesBtn2) {
      submitChangesBtn2.addEventListener('click', function () {
        var input = document.getElementById('changes-input');
        if (input && input.value.trim()) {
          submitHumanResponse(input.value);
        }
      });
    }

    function setConnectionStatus(state) {
      var dot = document.getElementById('conn-dot');
      var label = document.getElementById('conn-label');
      if (!dot || !label) return;
      dot.className = 'conn-dot ' + state;
      if (state === 'connected') label.textContent = 'Connected';
      else if (state === 'reconnecting') label.textContent = 'Reconnecting…';
      else label.textContent = 'Disconnected';
    }

    var connStatus = document.getElementById('connection-status');
    if (connStatus) {
      connStatus.addEventListener('click', function () {
        if (es && es.readyState !== EventSource.CLOSED) return;
        openStream();
      });
    }

    function handleSystemEvent(inner) {
      var evt = inner.event;
      if (evt === 'agent_done') {
        setPanelStatus(inner.agent, 'done');
      } else if (evt === 'checkpoint_open') {
        showCheckpoint(inner.body || '');
      } else if (evt === 'checkpoint_closed') {
        hideCheckpoint();
      } else if (evt === 'run_finished') {
        setConnectionStatus('disconnected');
        if (es) es.close();
      } else {
        console.warn('Unknown system event:', evt);
      }
    }

    function openStream() {
      if (es) { try { es.close(); } catch (e) {} }
      setConnectionStatus('reconnecting');

      es = new EventSource('/stream/' + ticketNumber);

      es.onopen = function () {
        setConnectionStatus('connected');
      };

      es.onmessage = function (e) {
        var data;
        try { data = JSON.parse(e.data); } catch (ex) { return; }

        if (data.agent === '_system') {
          var inner;
          try { inner = JSON.parse(data.text); } catch (ex) { return; }
          handleSystemEvent(inner);
          return;
        }

        var agentName = data.agent;
        var currentStatus = (function () {
          var panel = getPanel(agentName);
          return panel ? panel.dataset.status : 'waiting';
        })();

        if (currentStatus === 'waiting') {
          setPanelStatus(agentName, 'running');
        }

        appendEntry(agentName, data.text, data.timestamp);
      };

      es.onerror = function () {
        setConnectionStatus('reconnecting');
        refetchState();
      };
    }

    function refetchState() {
      fetch('/api/tickets/' + ticketNumber + '/state')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var agents = data.agents || {};
          Object.keys(agents).forEach(function (name) {
            var agentData = agents[name];
            var panel = getPanel(name);
            if (panel && panel.dataset.status !== agentData.status) {
              setPanelStatus(name, agentData.status);
            }
          });
          if (data.checkpoint && data.checkpoint.open) {
            showCheckpoint(data.checkpoint.body || '');
          } else {
            hideCheckpoint();
          }
        })
        .catch(function () {});
    }

    openStream();
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
