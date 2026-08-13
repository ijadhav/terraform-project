const chatBox = document.getElementById('chatBox');
    const promptInput = document.getElementById('promptInput');
    const sendButton = document.getElementById('sendButton');
    const statusText = document.getElementById('statusText');
    const threadBadge = document.getElementById('threadBadge');
    const threadLinkBadge = document.getElementById('threadLinkBadge');
    const prStatusPanel = document.getElementById('prStatusPanel');

    const ticketLinkBanner = document.getElementById('ticketLinkBanner');
    const jiraTicketInput = document.getElementById('jiraTicketInput');
    const saveJiraButton = document.getElementById('saveJiraButton');
    const jiraStatusText = document.getElementById('jiraStatusText');
    const ticketSearchInput = document.getElementById('ticketSearchInput');
    const ticketList = document.getElementById('ticketList');
    const newTicketButton = document.getElementById('newTicketButton');

    const commitConfirmBox = document.getElementById('commitConfirmBox');
    const commitConfirmText = document.getElementById('commitConfirmText');
    const commitYesButton = document.getElementById('commitYesButton');
    const commitNoButton = document.getElementById('commitNoButton');

    const THREADS_STORAGE_KEY = 'terrabotThreadsByTicket';
    const ACTIVE_TICKET_STORAGE_KEY = 'terrabotActiveTicket';
    const CHAT_HISTORY_STORAGE_KEY = 'terrabotChatHistoryByTicket';

    const authUser = document.getElementById('authUser');
    const logoutButton = document.getElementById('logoutButton');

    let chatHistoryByTicket = JSON.parse(sessionStorage.getItem(CHAT_HISTORY_STORAGE_KEY) || '{}');
    let threadsByTicket = JSON.parse(sessionStorage.getItem(THREADS_STORAGE_KEY) || '{}');
    let activeTicket = sessionStorage.getItem(ACTIVE_TICKET_STORAGE_KEY) || null;
    let pendingInfraChange = null;
    let pendingModuleVariableForm = null;
    let prStatusPollTimer = null;
    const PR_STATUS_POLL_MS = 45000;

    function escapeHtml(text) {
      if (!text) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function extractTicketNumber(value) {
      const text = (value || '').trim();
      if (!text) return '';

      const patterns = [
        /\/browse\/([A-Z][A-Z0-9]+-\d+)/i,
        /[?&]selectedIssue=([A-Z][A-Z0-9]+-\d+)/i,
        /[?&]ticket=([A-Z][A-Z0-9]+-\d+)/i,
        /\b([A-Z][A-Z0-9]+-\d+)\b/i
      ];

      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match && match[1]) {
          return match[1].toUpperCase();
        }
      }
      return '';
    }

    function isValidTicketLink(ticket) {
      const value = (ticket || '').trim();
      if (!value) return false;
      if (/^https?:\/\//i.test(value) && extractTicketNumber(value)) return true;
      return /^STO-\d{4,}$/i.test(value);
    }

    function normalizeTicketInput(ticket) {
      return (ticket || '').trim();
    }

    function generateShortTitle(text) {
      const cleaned = (text || '')
        .replace(/\s+/g, ' ')
        .replace(/[^\w\s-]/g, '')
        .trim();

      if (!cleaned) return 'New Request';

      return cleaned
        .split(' ')
        .slice(0, 5)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
    }

    function buildThreadLabel(thread) {
      const title = (thread.threadTitle || 'New Request').trim();
      const ticket = (thread.ticketNumber || thread.jiraTicket || 'UNASSIGNED').trim();
      return `${title} - ${ticket}`;
    }

    function getCurrentThreadState() {
      if (!activeTicket || !threadsByTicket[activeTicket]) {
        return null;
      }
      return threadsByTicket[activeTicket];
    }

    function persistThreads() {
      sessionStorage.setItem(THREADS_STORAGE_KEY, JSON.stringify(threadsByTicket));
    }

    function persistChatHistory() {
      sessionStorage.setItem(CHAT_HISTORY_STORAGE_KEY, JSON.stringify(chatHistoryByTicket));
    }

    function setCurrentThreadState(updates) {
      if (!activeTicket) return;

      const current = threadsByTicket[activeTicket] || {
        jiraTicket: activeTicket,
        ticketNumber: activeTicket,
        ticketLink: '',
        threadId: null,
        threadTitle: 'New Request',
        threadLabel: activeTicket,
        createdAt: new Date().toISOString()
      };

      const next = { ...current, ...updates };
      next.threadLabel = buildThreadLabel(next);

      threadsByTicket[activeTicket] = next;
      persistThreads();
    }

    function ensureTicketChatHistory(ticket) {
      if (!ticket) return;

      if (!chatHistoryByTicket[ticket]) {
        const thread = threadsByTicket[ticket];
        const introLabel = thread?.threadLabel || ticket;
        chatHistoryByTicket[ticket] = [
          {
            type: 'bot',
            text: `Hello 👋! I'm Terrabot. This is the thread for ${introLabel}. How can I help you today?`
          }
        ];
        persistChatHistory();
      }
    }

    function saveMessageToTicket(ticket, message) {
      if (!ticket) return;
      ensureTicketChatHistory(ticket);
      chatHistoryByTicket[ticket].push(message);
      persistChatHistory();
    }

    function appendMessage(text, type = 'bot') {
      const message = document.createElement('div');
      message.className = `message ${type}`;
      message.textContent = text;
      chatBox.appendChild(message);
      chatBox.scrollTop = chatBox.scrollHeight;

      if (activeTicket) {
        saveMessageToTicket(activeTicket, {
          type,
          text,
          isHtml: false
        });
      }
    }

    function appendHtmlMessage(html, type = 'bot') {
      const message = document.createElement('div');
      message.className = `message ${type}`;
      message.innerHTML = html;
      chatBox.appendChild(message);
      chatBox.scrollTop = chatBox.scrollHeight;

      if (activeTicket) {
        saveMessageToTicket(activeTicket, {
          type,
          text: html,
          isHtml: true
        });
      }
    }

    function buildVariablePlaceholder(field) {
      const typeText = field.type ? `Type: ${field.type}` : 'Enter a value';
      if (field.sensitive) return `${typeText}; approved value or repo reference`;
      return `${typeText}; for strings use text or "quoted text"`;
    }

    function appendModuleVariableWidget(formData) {
      pendingModuleVariableForm = formData || null;
      const fields = Array.isArray(formData?.fields) ? formData.fields : [];
      if (!fields.length) return;

      const wrapper = document.createElement('div');
      wrapper.className = 'message bot variable-widget-message';

      const rows = fields.map((field, index) => {
        const safeName = String(field.name || `variable_${index + 1}`);
        const name = escapeHtml(safeName);
        const description = escapeHtml(field.description || 'No description provided.');
        const type = escapeHtml(field.type || 'string');
        const sensitive = field.sensitive
          ? '<span class="variable-widget-badge warning">approval required</span>'
          : '<span class="variable-widget-badge">safe value</span>';
        const placeholder = escapeHtml(buildVariablePlaceholder(field));
        return `
          <label class="variable-widget-row">
            <div class="variable-widget-row-main">
              <div>
                <div class="variable-widget-name">${name}</div>
                <div class="variable-widget-description">${description}</div>
              </div>
              <div class="variable-widget-meta"><span>${type}</span>${sensitive}</div>
            </div>
            <input
              class="variable-widget-input"
              type="text"
              data-variable-name="${escapeHtml(safeName)}"
              placeholder="${placeholder}"
              autocomplete="off"
            />
          </label>
        `;
      }).join('');

      wrapper.innerHTML = `
        <div class="variable-widget-card">
          <div class="variable-widget-header">
            <div>
              <div class="variable-widget-title">${escapeHtml(formData.title || 'Module variable values required')}</div>
              <div class="variable-widget-subtitle">${escapeHtml(formData.description || 'Provide approved values before Terrabot creates the PR preview.')}</div>
            </div>
            <div class="variable-widget-cloud">${escapeHtml(formData.cloud || '')}</div>
          </div>
          <div class="variable-widget-help">
            Values entered here are applied as approved Terraform module variable defaults. Terrabot will not invent AMIs, subnet IDs, security group IDs, account IDs, ARNs, passwords, keys, or tokens.
          </div>
          <div class="variable-widget-fields">${rows}</div>
          <div class="variable-widget-actions">
            <button type="button" class="secondary-action-btn variable-widget-cancel">Cancel</button>
            <button type="button" class="primary-action-btn variable-widget-submit">Generate PR Preview</button>
          </div>
        </div>
      `;

      const submitButton = wrapper.querySelector('.variable-widget-submit');
      const cancelButton = wrapper.querySelector('.variable-widget-cancel');
      const inputs = Array.from(wrapper.querySelectorAll('.variable-widget-input'));

      submitButton.addEventListener('click', async () => {
        const values = {};
        inputs.forEach(input => {
          const key = input.getAttribute('data-variable-name');
          const value = (input.value || '').trim();
          if (key && value) values[key] = value;
        });

        const missing = fields
          .map(field => field.name)
          .filter(name => name && !values[name]);

        if (missing.length) {
          appendMessage(`Please provide values for: ${missing.join(', ')}`, 'error');
          return;
        }

        await submitModuleVariableValues(values);
      });

      cancelButton.addEventListener('click', () => {
        pendingModuleVariableForm = null;
        wrapper.remove();
        appendMessage('Module variable value entry cancelled. You can restart the request when ready.', 'bot');
      });

      chatBox.appendChild(wrapper);
      chatBox.scrollTop = chatBox.scrollHeight;
    }

    async function submitModuleVariableValues(variableValues) {
      const current = getCurrentThreadState();
      if (!activeTicket || !current) return;

      setLoading(true);

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'submit_module_variable_values',
            variable_values: variableValues,
            thread_id: current.threadId,
            jira_ticket: current.ticketLink || current.ticketNumber,
            ticket_link: current.ticketLink || '',
            ticket_title: current.threadTitle || 'New Request'
          })
        });

        const data = await response.json();
        updatePrStatusFromResponse(data);

        if (!response.ok || data.ok === false) {
          if (data.mode === 'module_variable_values' && data.variable_form) {
            appendMessage(data.reply || 'More module variable values are required.', 'bot');
            appendModuleVariableWidget(data.variable_form);
            return;
          }
          throw new Error(data.reply || data.error || 'Failed to submit module variable values.');
        }

        pendingModuleVariableForm = null;
        if (data.mode === 'infra_preview') {
          showCommitConfirm(data);
          appendMessage(data.reply || 'Terraform changes are ready. Confirm whether to commit them.', 'bot');
        } else {
          appendMessage(data.reply || 'Module variable values submitted.', 'bot');
        }
      } catch (error) {
        appendMessage('Error: ' + error.message, 'error');
      } finally {
        setLoading(false);
        updateTicketInputUI();
      }
    }

    function clearChatBox() {
      chatBox.innerHTML = '';
    }

    function renderChatForTicket(ticket) {
      clearChatBox();

      if (!ticket || !threadsByTicket[ticket]) {
        const welcome = document.createElement('div');
        welcome.className = 'message bot';
        welcome.textContent = "Hello 👋! I'm Terrabot. How can I help you today?";
        chatBox.appendChild(welcome);
        return;
      }

      ensureTicketChatHistory(ticket);

      const messages = chatHistoryByTicket[ticket] || [];
      messages.forEach(msg => {
        const message = document.createElement('div');
        message.className = `message ${msg.type || 'bot'}`;

        if (msg.isHtml) {
          message.innerHTML = msg.text || '';
        } else {
          message.textContent = msg.text || '';
        }

        chatBox.appendChild(message);
      });

      chatBox.scrollTop = chatBox.scrollHeight;
    }

    function renderTicketList() {
      ticketList.innerHTML = '';

      const query = (ticketSearchInput.value || '').trim().toLowerCase();

      const orderedTickets = Object.entries(threadsByTicket)
        .sort((a, b) => {
          const aTime = new Date(a[1].createdAt || 0).getTime();
          const bTime = new Date(b[1].createdAt || 0).getTime();
          return bTime - aTime;
        })
        .filter(([ticket, thread]) => {
          const haystack = [
            ticket,
            thread.threadLabel,
            thread.threadTitle,
            thread.ticketLink
          ].join(' ').toLowerCase();

          return haystack.includes(query);
        });

      if (!orderedTickets.length) {
        const empty = document.createElement('div');
        empty.className = 'ticket-empty';
        empty.textContent = 'No tickets found.';
        ticketList.appendChild(empty);
        return;
      }

      orderedTickets.forEach(([ticket, thread]) => {
        const item = document.createElement('div');
        item.className = 'ticket-item';
        if (ticket === activeTicket) {
          item.classList.add('active');
        }

        item.innerHTML = `
          <div class="ticket-item-title">${escapeHtml(thread.threadLabel || ticket)}</div>
          
        `;

        item.addEventListener('click', () => switchToTicket(ticket));
        ticketList.appendChild(item);
      });
    }

    function updateThreadBadge() {
      const current = getCurrentThreadState();

      if (current) {
        threadBadge.textContent = `Current thread: ${current.threadLabel || activeTicket}`;
      } else {
        threadBadge.textContent = 'Current thread: New';
      }
    }

    function updateThreadLinkBadge() {
      const current = getCurrentThreadState();

      if (current && current.ticketLink) {
        threadLinkBadge.style.display = 'inline-block';
        threadLinkBadge.innerHTML = `Ticket link: <a href="${escapeHtml(current.ticketLink)}" target="_blank" rel="noopener noreferrer">${escapeHtml(current.ticketNumber || current.jiraTicket || current.ticketLink)}</a>`;
      } else {
        threadLinkBadge.style.display = 'none';
        threadLinkBadge.innerHTML = '';
      }
    }

    function normalizePrEntries(threadPrs) {
      if (!threadPrs || typeof threadPrs !== 'object') return [];

      const preferred = ['azure_module', 'azure_module_population', 'azure_consumer', 'aws'];
      const aliases = new Set(['azure', 'azure_population']);
      const seen = new Set();
      const entries = [];

      preferred.forEach(key => {
        const value = threadPrs[key];
        if (value && typeof value === 'object') {
          entries.push([key, value]);
          seen.add(key);
        }
      });

      Object.entries(threadPrs).forEach(([key, value]) => {
        if (seen.has(key) || aliases.has(key) || !value || typeof value !== 'object') return;
        entries.push([key, value]);
      });

      return entries;
    }

    function updatePrStatusFromResponse(data) {
      if (!activeTicket) return;
      const current = getCurrentThreadState();
      if (!current) return;

      if (!data || !data.thread_prs || typeof data.thread_prs !== 'object') {
        return;
      }

      setCurrentThreadState({
        prStatus: data.thread_prs,
        prStatusUpdatedAt: new Date().toISOString()
      });
      renderPrStatusPanel();
    }

    function normalizePrStatusValue(pr) {
      if (!pr || typeof pr !== 'object') return 'unknown';

      const rawCandidates = [
        pr.status,
        pr.latest_pr_state,
        pr.state,
        pr.pr_state
      ]
        .filter(Boolean)
        .map(value => String(value).trim().toLowerCase());

      if (
        pr.merged === true ||
        pr.latest_pr_merged === true ||
        Boolean(pr.merged_at) ||
        rawCandidates.includes('merged')
      ) {
        return 'merged';
      }

      if (
        pr.closed === true ||
        Boolean(pr.closed_at) ||
        rawCandidates.includes('closed') ||
        rawCandidates.includes('declined')
      ) {
        return 'closed';
      }

      if (pr.has_open_pr === true || rawCandidates.includes('open')) {
        return 'open';
      }

      if (rawCandidates.includes('pending')) return 'pending';
      if (rawCandidates.includes('error') || pr.auto_population_error || pr.auto_consumer_error) return 'error';

      if (rawCandidates.length) return rawCandidates[0];
      if (pr.pr_number || pr.pr_url) return 'unknown';
      return 'pending';
    }

    function normalizePrStatusClass(status) {
      const value = String(status || 'unknown').toLowerCase();
      return ['open', 'closed', 'merged', 'pending', 'unknown', 'error'].includes(value)
        ? value
        : 'unknown';
    }

    function formatPrDate(value, label) {
      if (!value) return '';
      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) return ` · ${label} ${escapeHtml(value)}`;
      return ` · ${label} ${escapeHtml(parsed.toLocaleString())}`;
    }

    function renderPrStatusPanel() {
      const current = getCurrentThreadState();
      const entries = normalizePrEntries(current?.prStatus);

      if (!entries.length) {
        prStatusPanel.style.display = 'none';
        prStatusPanel.innerHTML = '';
        return;
      }

      const rows = entries.map(([key, pr]) => {
        const status = normalizePrStatusValue(pr);
        const statusClass = normalizePrStatusClass(status);
        const prNumber = pr.pr_number ? `PR #${escapeHtml(pr.pr_number)}` : 'PR';
        const url = pr.pr_url
          ? `${prNumber} <a class="pr-open-btn" href="${escapeHtml(pr.pr_url)}" target="_blank" rel="noopener noreferrer">Open PR</a>`
          : 'PR pending';
        const repo = pr.repo_full_name || pr.target_module_repo_full_name || pr.repo_target || pr.folder || '';
        const mergedAt = formatPrDate(pr.merged_at, 'merged');
        const closedAt = !pr.merged_at ? formatPrDate(pr.closed_at, 'closed') : '';
        const errorText = pr.auto_population_error || pr.auto_consumer_error || '';
        const errorHtml = errorText ? `<br><span style="color: var(--danger);">${escapeHtml(errorText)}</span>` : '';

        return `
          <div class="pr-status-row">
            <div class="pr-status-stage">
              <strong>${escapeHtml(pr.stage || key)}</strong><br>
              ${url}${repo ? ` · ${escapeHtml(repo)}` : ''}${mergedAt}${closedAt}${errorHtml}
            </div>
            <div class="pr-status-pill ${escapeHtml(statusClass)}">${escapeHtml(status)}</div>
          </div>
        `;
      }).join('');

      const updatedAt = current?.prStatusUpdatedAt
        ? `<div style="font-size:12px;color:var(--muted);margin-bottom:6px;">Last checked ${escapeHtml(new Date(current.prStatusUpdatedAt).toLocaleString())}</div>`
        : '';

      prStatusPanel.innerHTML = `<div class="pr-status-title">PR approval workflow</div>${updatedAt}${rows}`;
      prStatusPanel.style.display = 'block';
    }

    async function refreshPrStatus({ silent = true } = {}) {
      const current = getCurrentThreadState();
      if (!current?.threadId || !activeTicket) return;

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'refresh_pr_status',
            thread_id: current.threadId,
            jira_ticket: current.ticketLink || current.ticketNumber,
            ticket_link: current.ticketLink || '',
            ticket_title: current.threadTitle || 'New Request'
          })
        });
        const data = await response.json();

        if (!response.ok || data.ok === false) {
          throw new Error(data.reply || data.error || 'Failed to refresh PR status.');
        }

        updatePrStatusFromResponse(data);

        if (Array.isArray(data.events) && data.events.length) {
          const latestThread = getCurrentThreadState() || current;
          const alreadySeen = new Set(latestThread.prStatusEvents || []);
          const newEvents = data.events.filter(eventText => !alreadySeen.has(eventText));
          if (newEvents.length) {
            setCurrentThreadState({
              prStatusEvents: [...alreadySeen, ...newEvents]
            });
            newEvents.forEach(eventText => appendMessage(eventText, 'bot'));
          }
        } else if (!silent && data.reply) {
          appendMessage(data.reply, 'bot');
        }
      } catch (error) {
        if (!silent) appendMessage('Error refreshing PR status: ' + error.message, 'error');
      }
    }

    function restartPrStatusPolling() {
      if (prStatusPollTimer) {
        clearInterval(prStatusPollTimer);
        prStatusPollTimer = null;
      }

      const current = getCurrentThreadState();
      if (!current?.threadId) return;

      refreshPrStatus({ silent: true });
      prStatusPollTimer = setInterval(() => refreshPrStatus({ silent: true }), PR_STATUS_POLL_MS);
    }

    function updateTicketInputUI() {
      const current = getCurrentThreadState();

      if (current) {
        jiraTicketInput.value = current.ticketLink || current.ticketNumber || '';
        jiraStatusText.textContent = `Ticket saved: ${current.threadLabel || activeTicket}`;
        jiraStatusText.className = 'ticket-status success';
        ticketLinkBanner.style.display = 'none';
        promptInput.disabled = false;
        sendButton.disabled = false;
      } else {
        jiraTicketInput.value = '';
        jiraStatusText.textContent = 'Enter a valid ticket link before sending prompts.';
        jiraStatusText.className = 'ticket-status';
        ticketLinkBanner.style.display = 'flex';
        promptInput.disabled = true;
        sendButton.disabled = true;
      }
    }

    function hideCommitConfirm() {
      pendingInfraChange = null;
      commitConfirmBox.style.display = 'none';
      commitConfirmText.textContent = 'Terraform changes are ready. Do you want to commit these changes to the PR?';
    }

    function showCommitConfirm(data) {
      pendingInfraChange = data.pending_change_id || null;

      const filesText = Array.isArray(data.files) && data.files.length
        ? ` Files: ${data.files.join(', ')}.`
        : '';

      commitConfirmText.textContent =
        `${data.reply || 'Terraform changes are ready. Do you want to commit these changes to the PR?'} Cloud: ${data.cloud || 'N/A'}.${filesText}`;

      commitConfirmBox.style.display = 'block';
    }

    function setLoading(isLoading) {
      jiraTicketInput.disabled = isLoading;
      saveJiraButton.disabled = isLoading;
      newTicketButton.disabled = isLoading;
      ticketSearchInput.disabled = isLoading;
      promptInput.disabled = isLoading || !activeTicket;
      sendButton.disabled = isLoading || !activeTicket;
      commitYesButton.disabled = isLoading;
      commitNoButton.disabled = isLoading;
      sendButton.textContent = isLoading ? 'Sending...' : 'Send';
      statusText.textContent = isLoading ? 'Waiting for Terrabot response...' : '';
    }

    function renderInfraResponse(data) {
      const current = getCurrentThreadState();
      const prLink = data.pr_url
        ? `<a href="${data.pr_url}" target="_blank" rel="noopener noreferrer">${escapeHtml(data.pr_url)}</a>`
        : 'Not available';

      const html = `
        <div><strong>${escapeHtml(data.reply || 'Operation completed.')}</strong></div>
        <div style="margin-top:8px;"><strong>PR URL:</strong> ${prLink}</div>
        <div style="margin-top:8px;"><strong>Ticket:</strong> ${escapeHtml(current?.threadLabel || activeTicket || 'Not provided')}</div>
      `;

      appendHtmlMessage(html, 'bot');
    }

    function createNewTicket() {
      hideCommitConfirm();
      pendingModuleVariableForm = null;

      activeTicket = null;
      sessionStorage.removeItem(ACTIVE_TICKET_STORAGE_KEY);

      updateThreadBadge();
      updateThreadLinkBadge();
      updateTicketInputUI();
      renderPrStatusPanel();
      restartPrStatusPolling();
      renderTicketList();
      renderChatForTicket(null);

      jiraTicketInput.value = '';
      jiraStatusText.textContent = 'Paste a ticket link to create a new thread.';
      jiraStatusText.className = 'ticket-status';
      ticketLinkBanner.style.display = 'flex';
      jiraTicketInput.focus();
    }

    function saveTicketLink() {
      const entered = normalizeTicketInput(jiraTicketInput.value);
      const ticketNumber = extractTicketNumber(entered);

      if (!isValidTicketLink(entered)) {
        jiraStatusText.textContent = 'Invalid ticket link. Paste a valid ticket link containing a ticket like STO-1234.';
        jiraStatusText.className = 'ticket-status error';
        promptInput.disabled = true;
        sendButton.disabled = true;
        jiraTicketInput.focus();
        return;
      }

      if (!threadsByTicket[ticketNumber]) {
        threadsByTicket[ticketNumber] = {
          jiraTicket: ticketNumber,
          ticketNumber,
          ticketLink: /^https?:\/\//i.test(entered) ? entered : '',
          threadId: null,
          threadTitle: 'New Request',
          threadLabel: `New Request - ${ticketNumber}`,
          createdAt: new Date().toISOString()
        };
      } else {
        threadsByTicket[ticketNumber] = {
          ...threadsByTicket[ticketNumber],
          jiraTicket: ticketNumber,
          ticketNumber,
          ticketLink: /^https?:\/\//i.test(entered) ? entered : threadsByTicket[ticketNumber].ticketLink || '',
          threadLabel: buildThreadLabel(threadsByTicket[ticketNumber])
        };
      }

      persistThreads();
      ensureTicketChatHistory(ticketNumber);

      activeTicket = ticketNumber;
      sessionStorage.setItem(ACTIVE_TICKET_STORAGE_KEY, activeTicket);

      hideCommitConfirm();
      updateThreadBadge();
      updateThreadLinkBadge();
      renderTicketList();
      updateTicketInputUI();
      renderPrStatusPanel();
      restartPrStatusPolling();
      renderChatForTicket(activeTicket);
      promptInput.focus();
    }

    function switchToTicket(ticket) {
      if (!ticket || !threadsByTicket[ticket]) return;

      activeTicket = ticket;
      sessionStorage.setItem(ACTIVE_TICKET_STORAGE_KEY, activeTicket);

      ensureTicketChatHistory(ticket);

      hideCommitConfirm();
      updateThreadBadge();
      updateThreadLinkBadge();
      renderTicketList();
      updateTicketInputUI();
      renderPrStatusPanel();
      restartPrStatusPolling();
      renderChatForTicket(ticket);
      promptInput.focus();
    }

    async function sendPrompt() {
      const prompt = promptInput.value.trim();
      const current = getCurrentThreadState();

      if (!activeTicket || !current) {
        ticketLinkBanner.style.display = 'flex';
        jiraStatusText.textContent = 'Please save a valid ticket link before sending prompts.';
        jiraStatusText.className = 'ticket-status error';
        jiraTicketInput.focus();
        return;
      }

      if (!prompt) {
        statusText.textContent = 'Please enter a prompt.';
        return;
      }

      appendMessage(prompt, 'user');
      promptInput.value = '';
      setLoading(true);
      hideCommitConfirm();

      const fallbackTitle = current.threadTitle && current.threadTitle !== 'New Request'
        ? current.threadTitle
        : generateShortTitle(prompt);

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt,
            thread_id: current?.threadId || null,
            jira_ticket: current.ticketLink || current.ticketNumber,
            ticket_link: current.ticketLink || '',
            ticket_title: fallbackTitle,
            pending_change_id: pendingInfraChange
          })
        });

        const data = await response.json();

        const returnedTicketNumber = data.ticket_number || current.ticketNumber || activeTicket;
        const preservedLink = data.ticket_link || current.ticketLink || '';

        if (returnedTicketNumber && returnedTicketNumber !== activeTicket && threadsByTicket[activeTicket]) {
          const existingThread = threadsByTicket[activeTicket];
          delete threadsByTicket[activeTicket];
          threadsByTicket[returnedTicketNumber] = {
            ...existingThread,
            jiraTicket: returnedTicketNumber,
            ticketNumber: returnedTicketNumber
          };

          if (chatHistoryByTicket[activeTicket]) {
            chatHistoryByTicket[returnedTicketNumber] = chatHistoryByTicket[activeTicket];
            delete chatHistoryByTicket[activeTicket];
            persistChatHistory();
          }

          activeTicket = returnedTicketNumber;
          sessionStorage.setItem(ACTIVE_TICKET_STORAGE_KEY, activeTicket);
        }

        if (data.thread_id || activeTicket) {
          setCurrentThreadState({
            threadId: data.thread_id || current.threadId,
            jiraTicket: returnedTicketNumber,
            ticketNumber: returnedTicketNumber,
            ticketLink: preservedLink,
            threadTitle: data.ticket_title || fallbackTitle,
            threadLabel: data.conversation_label || `${data.ticket_title || fallbackTitle} - ${returnedTicketNumber}`
          });
        }

        updatePrStatusFromResponse(data);
        updateThreadBadge();
        updateThreadLinkBadge();
        renderTicketList();

        if (!response.ok || !data.ok) {
          const fallbackText = data.reply || data.error || 'Failed to get response from backend.';
          if (data.mode === 'module_variable_values') {
            appendMessage(fallbackText, 'bot');
            appendModuleVariableWidget(data.variable_form || { fields: data.missing_variables || [] });
            return;
          }
          if (data.mode === 'chat' || data.mode === 'clarification') {
            appendMessage(fallbackText, 'bot');
            return;
          }
          throw new Error(fallbackText);
        }

        if (data.mode === 'module_variable_values') {
          appendMessage(data.reply || 'Module variable values are required before Terrabot can create the PR preview.', 'bot');
          appendModuleVariableWidget(data.variable_form || { fields: data.missing_variables || [] });
        } else if (data.mode === 'infra_preview') {
          showCommitConfirm(data);
          appendMessage(data.reply || 'Terraform changes are ready. Confirm whether to commit them.', 'bot');
        } else if (data.mode === 'infra') {
          renderInfraResponse(data);
        } else {
          appendMessage(data.reply || 'No response returned.', 'bot');
        }
      } catch (error) {
        appendMessage('Error: ' + error.message, 'error');
      } finally {
        setLoading(false);
        updateTicketInputUI();
        promptInput.focus();
      }
    }

    async function commitPendingChange() {
      const current = getCurrentThreadState();
      if (!current?.threadId || !activeTicket || !pendingInfraChange) return;

      setLoading(true);

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'commit_pending',
            thread_id: current.threadId,
            jira_ticket: current.ticketLink || current.ticketNumber,
            ticket_link: current.ticketLink || '',
            ticket_title: current.threadTitle || 'New Request',
            pending_change_id: pendingInfraChange
          })
        });

        const data = await response.json();

        if (!response.ok || !data.ok) {
          throw new Error(data.reply || data.error || 'Failed to commit pending changes.');
        }

        hideCommitConfirm();

        if (data.thread_id) {
          setCurrentThreadState({
            threadId: data.thread_id,
            jiraTicket: data.ticket_number || current.ticketNumber,
            ticketNumber: data.ticket_number || current.ticketNumber,
            ticketLink: data.ticket_link || current.ticketLink,
            threadTitle: data.ticket_title || current.threadTitle,
            threadLabel: data.conversation_label || current.threadLabel
          });
        }

        updatePrStatusFromResponse(data);
        updateThreadBadge();
        updateThreadLinkBadge();
        renderTicketList();

        if (data.mode === 'infra') {
          renderInfraResponse(data);
        } else {
          appendMessage(data.reply || 'Changes committed.', 'bot');
        }
      } catch (error) {
        appendMessage('Error: ' + error.message, 'error');
      } finally {
        setLoading(false);
        updateTicketInputUI();
      }
    }

    async function discardPendingChange() {
      const current = getCurrentThreadState();
      if (!current?.threadId || !activeTicket || !pendingInfraChange) {
        hideCommitConfirm();
        return;
      }

      setLoading(true);

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'discard_pending',
            thread_id: current.threadId,
            jira_ticket: current.ticketLink || current.ticketNumber,
            ticket_link: current.ticketLink || '',
            ticket_title: current.threadTitle || 'New Request',
            pending_change_id: pendingInfraChange
          })
        });

        const data = await response.json();
        hideCommitConfirm();
        appendMessage(data.reply || 'Okay, I did not commit those infrastructure changes.', 'bot');
      } catch (error) {
        appendMessage('Error: ' + error.message, 'error');
      } finally {
        setLoading(false);
        updateTicketInputUI();
      }
    }
    async function loadAuthenticatedUser() {
      try {
        const response = await fetch("/auth/me", {
           method: 'GET',
           credentials: 'same-origin'
        });

        if (response.status === 401) {
          window.location.href =
            "/.auth/login/okta?post_login_redirect_uri=/index";
          return;
        }

        const data = await response.json();

        authUser.textContent =
          data.user?.email || 'Authenticated user';
      } catch (err) {
         authUser.textContent = 'Authentication failed';
      }
    }

    logoutButton.addEventListener('click', () => {
      sessionStorage.clear();

      window.location.href =
        "/.auth/logout?post_logout_redirect_uri=/index";
    });

    loadAuthenticatedUser();

    saveJiraButton.addEventListener('click', saveTicketLink);
    newTicketButton.addEventListener('click', createNewTicket);
    sendButton.addEventListener('click', sendPrompt);
    commitYesButton.addEventListener('click', commitPendingChange);
    commitNoButton.addEventListener('click', discardPendingChange);
    ticketSearchInput.addEventListener('input', renderTicketList);

    jiraTicketInput.addEventListener('keydown', function(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        saveTicketLink();
      }
    });

    promptInput.addEventListener('keydown', function(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        sendPrompt();
      }
    });

    updateThreadBadge();
    updateThreadLinkBadge();
    renderTicketList();
    updateTicketInputUI();
    renderPrStatusPanel();
    restartPrStatusPolling();
    hideCommitConfirm();

    if (activeTicket && threadsByTicket[activeTicket]) {
      ensureTicketChatHistory(activeTicket);
      renderChatForTicket(activeTicket);
    } else {
      renderChatForTicket(null);
    }
