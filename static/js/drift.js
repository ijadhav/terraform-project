(function () {
  "use strict";

  var state = {
    providers: {},
    activeProvider: "aws"
  };

  var authUser = null;
  var logoutButton = null;

  document.addEventListener("DOMContentLoaded", function () {
     authUser = document.getElementById("authUser");
     logoutButton = document.getElementById("logoutButton");

     setupAuthControls();
     setupTabs();
     setupRefreshButton();
     setupExplainToggle();
     setupJiraTicketCreation();
     ensureDriftUiStyles();
     refreshDriftStatus(false);
  });

  function setupAuthControls() {
    if (!authUser || !logoutButton) {
      return;
    }

    loadAuthenticatedUser();

    logoutButton.addEventListener("click", function () {
      sessionStorage.clear();

      window.location.href =
        "/.auth/logout?post_logout_redirect_uri=/index";
    });
  }


  async function loadAuthenticatedUser() {
    try {
      var response = await fetch("/auth/me", {
        method: "GET",
        credentials: "same-origin"
      });

      if (response.status === 401) {
        window.location.href =
         "/.auth/login/okta?post_login_redirect_uri=/drift";
        return;
      }

      var data = await response.json();

      authUser.textContent =
        data.user && data.user.email
          ? data.user.email
          : "Authenticated user";
    } catch (err) {
       authUser.textContent = "Authentication failed";
    }
  }

  function setupTabs() {
    var tabs = document.querySelectorAll("[data-provider-tab]");
    for (var i = 0; i < tabs.length; i += 1) {
      tabs[i].addEventListener("click", function () {
        setActiveProvider(this.getAttribute("data-provider-tab"));
      });
    }
  }

  function setActiveProvider(provider) {
    state.activeProvider = provider;

    var tabs = document.querySelectorAll("[data-provider-tab]");
    for (var i = 0; i < tabs.length; i += 1) {
      var isActiveTab = tabs[i].getAttribute("data-provider-tab") === provider;
      tabs[i].classList.toggle("active", isActiveTab);
      tabs[i].setAttribute("aria-selected", isActiveTab ? "true" : "false");
    }

    var panels = document.querySelectorAll("[data-provider-panel]");
    for (var j = 0; j < panels.length; j += 1) {
      var isActivePanel = panels[j].getAttribute("data-provider-panel") === provider;
      panels[j].hidden = !isActivePanel;
      panels[j].classList.toggle("active", isActivePanel);
    }
  }

  function setupRefreshButton() {
    var button = document.getElementById("refreshDriftButton");
    if (!button) return;

    button.textContent = "Refresh Cloud Status";

    button.addEventListener("click", function () {
      button.disabled = true;
      button.textContent = "Refreshing...";

      refreshDriftStatus(true).then(function () {
        button.disabled = false;
        button.textContent = "Refresh Cloud Status";
      }).catch(function () {
        button.disabled = false;
        button.textContent = "Refresh Cloud Status";
      });
    });
  }


  function setupExplainToggle() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest ? event.target.closest("[data-toggle-explain]") : null;
      if (!button) return;

      event.preventDefault();

      var row = button.closest ? button.closest(".commit-drift-row") : null;
      var panel = row ? row.querySelector(".drift-explain-panel") : null;
      if (!panel) return;

      var isHidden = panel.hasAttribute("hidden");
      if (isHidden) {
        panel.removeAttribute("hidden");
        button.textContent = "Hide explanation";
      } else {
        panel.setAttribute("hidden", "hidden");
        button.textContent = "Explain";
      }
    });
  }

  function setupJiraTicketCreation() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest ? event.target.closest("[data-create-jira-ticket]") : null;
      if (!button) return;

      event.preventDefault();

      var card = button.closest ? button.closest(".commit-drift-row") : null;
      var payload = card && card._terrabotJiraPayload ? card._terrabotJiraPayload : null;
      if (!payload) {
        setStatusLine("Unable to create Jira ticket: missing drift details for this card.", "error");
        return;
      }

      button.disabled = true;
      button.textContent = "Creating Jira Ticket...";

      createJiraTicket(payload).then(function (response) {
        var ticket = response.ticket || response.jira_ticket || response.issue || response.jira || {};
        addJiraTicketToCard(card, ticket);
        var ticketUrl = ticket.url || ticket.web_url || ticket.self || "";
        if (ticketUrl && button.parentNode) {
          var link = document.createElement("a");
          link.className = button.className || "small-action-btn jira-create-btn";
          link.href = ticketUrl;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "Open Ticket";
          button.parentNode.replaceChild(link, button);
        } else {
          button.textContent = ticket.key ? "Jira Ticket Created" : "Jira Ticket Created";
          button.disabled = true;
        }
        var assignment = ticket.assignment || {};
        var assignmentText = assignment.assigned ? " and assigned it" : (assignment.message ? "; assignment note: " + assignment.message : "");
        setStatusLine("Created Jira ticket" + (ticket.key ? " " + ticket.key : "") + assignmentText + ".", "success");
      }).catch(function (error) {
        button.disabled = false;
        button.textContent = "Create Jira Ticket";
        button.setAttribute("title", error.message || "Jira ticket creation failed");
        setStatusLine("Unable to create Jira ticket: " + error.message, "error");
      });
    });
  }

  function createJiraTicket(payload) {
    var requests = [
      { url: "/drift-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/api/drift-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/drift/create-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/api/drift/create-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/commit-drift/create-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/api/commit-drift/create-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/commit-drift-jira-ticket", options: jiraPostOptions(payload) },
      { url: "/api/commit-drift-jira-ticket", options: jiraPostOptions(payload) }
    ];

    return fetchJsonWithFallback(requests, 0).then(function (response) {
      if (!response || response.ok === false) {
        throw new Error((response && (response.error || response.reply || response.message)) || "Jira ticket creation failed");
      }
      return response;
    });
  }

  function jiraPostOptions(payload) {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload)
    };
  }

  function addJiraTicketToCard(card, ticket) {
    if (!card || !ticket) return;

    var line = card.querySelector(".jira-status-line");
    if (!line) return;

    var key = ticket.key || ticket.id || "JIRA";
    var url = ticket.url || ticket.web_url || ticket.self || "";
    var link = url
      ? '<a class="jira-ticket-chip" href="' + escapeAttribute(url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(key) + '</a>'
      : '<span class="jira-ticket-chip unavailable">' + escapeHtml(key) + '</span>';

    if (line.textContent && line.textContent.indexOf("Not found") !== -1) {
      line.innerHTML = '<strong>JIRA Link:</strong> ' + link;
      return;
    }

    if (line.innerHTML.indexOf(escapeHtml(key)) === -1) {
      line.innerHTML += " " + link;
    }
  }

  function ensureDriftUiStyles() {
    if (document.getElementById("terrabot-drift-button-spacing")) return;

    var style = document.createElement("style");
    style.id = "terrabot-drift-button-spacing";
    style.textContent = "" +
      ".commit-env-cell{align-items:flex-start!important;gap:10px!important;}" +
      ".commit-cell-actions{display:flex!important;flex-direction:column!important;align-items:flex-start!important;gap:18px!important;margin-top:18px!important;}" +
      ".commit-cell-actions .small-action-btn{min-width:150px!important;text-align:center!important;justify-content:center!important;}" +
      ".env-actions{gap:12px!important;}" +
      ".env-actions .small-action-btn{margin-right:0!important;}" +
      ".jira-create-btn{border-color:rgba(65,129,84,.34)!important;}" +
      ".fix-instruction{margin-top:14px!important;}";
    document.head.appendChild(style);
  }

  function refreshDriftStatus(forceRefresh) {
    var requests = forceRefresh ? [
      {
        url: "/drift-trigger",
        options: {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ provider: "all", refresh: true, force: true })
        }
      },
      {
        url: "/api/drift-trigger",
        options: {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ provider: "all", refresh: true, force: true })
        }
      },
      {
        url: "/drift-status?provider=all&refresh=true",
        options: { method: "GET", headers: { "Accept": "application/json" } }
      },
      {
        url: "/api/commit-drift/status?refresh=true",
        options: { method: "GET", headers: { "Accept": "application/json" } }
      }
    ] : [
      {
        url: "/drift-status?provider=all",
        options: { method: "GET", headers: { "Accept": "application/json" } }
      },
      {
        url: "/api/drift-status?provider=all",
        options: { method: "GET", headers: { "Accept": "application/json" } }
      },
      {
        url: "/api/commit-drift/status",
        options: { method: "GET", headers: { "Accept": "application/json" } }
      }
    ];

    return fetchJsonWithFallback(requests, 0)
      .then(function (payload) {
        var drift = payload.drift || payload.results || payload || {};
        var providers = drift.providers || payload.providers || {};
        var updatedAt = drift.updatedAt || drift.generatedAt || new Date().toISOString();

        state.providers = providers;

        hideOldAlertWidget();
        renderSummary(drift.summary || payload.summary || {});
        renderProvider("aws", providers.aws || {});
        renderProvider("azure", providers.azure || {});
        renderActivity(providers);
        setFooterDates(updatedAt);
      })
      .catch(function (error) {
        console.error("Terrabot drift refresh failed", error);
        setStatusLine("Unable to load drift status: " + error.message, "error");
      });
  }

  function fetchJsonWithFallback(requests, index, lastError) {
    var request = requests[index];
    if (!request) {
      return Promise.reject(lastError || new Error("All drift endpoints failed."));
    }
    return fetch(request.url, request.options).then(function (response) {
      return response.text().then(function (text) {
        var payload = {};
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (parseError) {
            payload = { error: text };
          }
        }

        if (!response.ok || payload.ok === false) {
          var error = new Error(payload.error || payload.reply || payload.message || ("Endpoint " + request.url + " returned " + response.status));
          if (index + 1 < requests.length && (response.status === 404 || response.status === 405 || response.status === 415)) {
            return fetchJsonWithFallback(requests, index + 1, error);
          }
          throw error;
        }

        return payload;
      });
    }).catch(function (error) {
      if (index + 1 < requests.length && (/Failed to fetch|NetworkError|Endpoint .* returned 404|Endpoint .* returned 405|Endpoint .* returned 415/i.test(String(error && error.message || error)))) {
        return fetchJsonWithFallback(requests, index + 1, error);
      }
      throw error;
    });
  }

  function hideOldAlertWidget() {
    var panel = document.getElementById("driftAlertPanel");
    if (panel) {
      panel.hidden = true;
      panel.style.display = "none";
    }
  }

  function renderSummary(summary) {
    setText("summaryTotal", summary.total || 0);
    setText("summaryDrift", summary.drift || 0);
    setText("summaryClean", summary.clean || 0);
    setText("summaryCritical", summary.critical || summary.error || 0);
  }

  function renderProvider(providerKey, providerState) {
    var listId = providerKey === "aws" ? "awsDriftList" : "azureDriftList";
    var scopeId = providerKey === "aws" ? "awsScopeCount" : "azureScopeCount";
    var statusId = providerKey === "aws" ? "awsProviderStatus" : "azureProviderStatus";

    var list = document.getElementById(listId);
    var scope = document.getElementById(scopeId);
    var status = document.getElementById(statusId);

    if (!list) return;

    var sourceRows = providerState.environments || [];
    if (providerKey === "aws") {
      sourceRows = filterAwsRows(sourceRows);
    }

    var rows = consolidateRows(sourceRows);
    var providerStatus = normalizeStatus(calculateProviderStatus(rows) || providerState.status);

    if (scope) scope.textContent = rows.length + " checks";
    if (status) {
      status.textContent = labelStatus(providerStatus);
      status.className = "status-chip " + providerStatus;
    }

    list.innerHTML = "";

    if (!rows.length) {
      list.innerHTML = '<div class="empty-state">No drift data available.</div>';
      return;
    }

    for (var i = 0; i < rows.length; i += 1) {
      list.appendChild(createUnifiedDriftCard(rows[i]));
    }
  }

  function filterAwsRows(rows) {
    var result = [];
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i] || {};
      var text = [row.group, row.group_label, row.groupLabel, row.name, row.summary, row.nprFile, row.prdFile, row.npr_file, row.prd_file].join(" ").toLowerCase();
      if (/(^|[^a-z0-9])(eks|bolt)([^a-z0-9]|$)/i.test(text)) {
        continue;
      }
      result.push(row);
    }
    return result;
  }

  function consolidateRows(rows) {
    var grouped = {};
    var order = [];

    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i] || {};
      var key = row.group || row.group_label || row.groupLabel || row.name || "drift-check";
      var type = row.comparison_type || row.comparisonType || "combined";

      if (!grouped[key]) {
        grouped[key] = {
          key: key,
          label: row.group_label || row.groupLabel || key,
          rows: [],
          nprMain: null,
          prdMain: null,
          nprPrd: null,
          combined: null
        };
        order.push(key);
      }

      grouped[key].rows.push(row);

      if (type === "npr_main") grouped[key].nprMain = row;
      else if (type === "prd_main") grouped[key].prdMain = row;
      else if (type === "npr_prd") grouped[key].nprPrd = row;
      else grouped[key].combined = row;
    }

    var result = [];
    for (var j = 0; j < order.length; j += 1) {
      result.push(grouped[order[j]]);
    }
    return result;
  }

  function createUnifiedDriftCard(group) {
    var base = group.nprPrd || group.combined || group.nprMain || group.prdMain || group.rows[0] || {};
    var driftFound = groupHasDrift(group);
    var nprSha = firstValue([
      base.nprSha, base.npr_sha,
      group.nprMain && group.nprMain.nprSha,
      group.nprMain && group.nprMain.npr_sha,
      group.nprPrd && group.nprPrd.nprSha,
      group.nprPrd && group.nprPrd.npr_sha
    ]);
    var prdSha = firstValue([
      base.prdSha, base.prd_sha,
      group.prdMain && group.prdMain.prdSha,
      group.prdMain && group.prdMain.prd_sha,
      group.nprPrd && group.nprPrd.prdSha,
      group.nprPrd && group.nprPrd.prd_sha
    ]);
    var mainSha = firstValue([
      base.mainSha, base.main_sha,
      group.nprMain && group.nprMain.mainSha,
      group.nprMain && group.nprMain.main_sha,
      group.prdMain && group.prdMain.mainSha,
      group.prdMain && group.prdMain.main_sha
    ]);

    var card = document.createElement("div");
    card.className = "env-row commit-drift-row";
    card.setAttribute("data-status", driftFound ? "drift" : "clean");

    var cardData = {
      provider: firstValueFromRows(group.rows, ["provider"]),
      repo: firstValueFromRows(group.rows, ["repo"]),
      branch: firstValueFromRows(group.rows, ["branch", "source_branch", "baseline_branch"]),
      group: group.key,
      groupLabel: group.label,
      title: group.label,
      status: driftFound ? "drift" : "clean",
      nprSha: nprSha,
      prdSha: prdSha,
      mainSha: mainSha,
      nprCommitUrl: pickCommitUrlForSide(group, "npr", nprSha),
      prdCommitUrl: pickCommitUrlForSide(group, "prd", prdSha),
      mainCommitUrl: pickCommitUrlForSide(group, "main", mainSha),
      nprPipelineUrl: pickPipelineUrlForSide(group, "npr"),
      prdPipelineUrl: pickPipelineUrlForSide(group, "prd"),
      responsibleUsers: collectResponsibleUsers(group.rows),
      jiraTickets: collectJiraTickets(group.rows),
      pullRequests: collectPullRequests(group.rows),
      explainText: collectExplainText(group.rows),
      compareUrl: firstValueFromRows(group.rows, ["compareUrl", "compare_url"]),
      summary: firstValueFromRows(group.rows, ["summary", "commit_summary"])
    };

    card.innerHTML = buildDriftCardHtml(cardData);
    card._terrabotJiraPayload = buildJiraTicketPayload(group, cardData);

    return card;
  }

  function buildJiraTicketPayload(group, data) {
    return {
      provider: data.provider || "",
      repo: data.repo || "",
      branch: data.branch || "",
      group: group.key || data.group || "",
      group_label: data.groupLabel || group.label || "",
      status: data.status || "",
      summary: data.summary || data.explainText || "",
      drift_description: data.summary || data.explainText || "",
      fix_instructions: data.explainText || "",
      npr_sha: data.nprSha || "",
      prd_sha: data.prdSha || "",
      main_sha: data.mainSha || "",
      npr_commit_url: data.nprCommitUrl || "",
      prd_commit_url: data.prdCommitUrl || "",
      main_commit_url: data.mainCommitUrl || "",
      npr_pipeline_url: data.nprPipelineUrl || "",
      prd_pipeline_url: data.prdPipelineUrl || "",
      compare_url: data.compareUrl || "",
      responsible_users: data.responsibleUsers || [],
      pull_requests: data.pullRequests || [],
      jira_tickets: data.jiraTickets || [],
      rows: group.rows || []
    };
  }

  function pickAdoUrl(group) {
    var rows = group.rows || [];
    var ordered = [];
    var i;

    for (i = 0; i < rows.length; i += 1) {
      if (normalizeStatus(rows[i].status) === "drift" || normalizeStatus(rows[i].status) === "error") {
        ordered.push(rows[i]);
      }
    }
    for (i = 0; i < rows.length; i += 1) {
      if (ordered.indexOf(rows[i]) === -1) {
        ordered.push(rows[i]);
      }
    }

    for (i = 0; i < ordered.length; i += 1) {
      var url = adoUrlForRow(ordered[i]);
      if (url) return url;
    }

    return "";
  }

  function pickPipelineUrlForSide(group, side) {
    var rows = group.rows || [];
    var i;
    var row;
    var type;
    var direct;

    for (i = 0; i < rows.length; i += 1) {
      row = rows[i] || {};
      type = row.comparison_type || row.comparisonType || "";

      if (side === "npr") {
        direct = firstValue([row.nprPipelineUrl, row.npr_pipeline_url, row.nprAdoRunUrl, row.npr_ado_run_url]);
        if (isAdoUrl(direct)) return direct;
        direct = deploymentUrl(row.npr_deployment || row.nprDeployment);
        if (direct) return direct;
        if (type === "npr_main") {
          direct = adoUrlForRow(row);
          if (direct) return direct;
        }
      }

      if (side === "prd") {
        direct = firstValue([row.prdPipelineUrl, row.prd_pipeline_url, row.prdAdoRunUrl, row.prd_ado_run_url]);
        if (isAdoUrl(direct)) return direct;
        direct = deploymentUrl(row.prd_deployment || row.prdDeployment);
        if (direct) return direct;
        if (type === "prd_main") {
          direct = adoUrlForRow(row);
          if (direct) return direct;
        }
      }
    }

    return "";
  }

  function pickCommitUrlForSide(group, side, sha) {
    var rows = group.rows || [];
    var i;
    var row;
    var direct;

    for (i = 0; i < rows.length; i += 1) {
      row = rows[i] || {};

      if (side === "npr") {
        direct = firstValue([row.nprCommitUrl, row.npr_commit_url, objectUrl(row.npr_commit || row.nprCommit)]);
      } else if (side === "prd") {
        direct = firstValue([row.prdCommitUrl, row.prd_commit_url, objectUrl(row.prd_commit || row.prdCommit)]);
      } else {
        direct = firstValue([
          row.mainCommitUrl,
          row.main_commit_url,
          row.main && row.main.commit_url,
          row.main && row.main.commitUrl,
          row.main && row.main.commit && row.main.commit.html_url,
          row.main && row.main.commit && row.main.commit.htmlUrl
        ]);
      }

      if (isGitHubCommitUrl(direct)) return direct;
    }

    for (i = 0; i < rows.length; i += 1) {
      direct = commitUrlFromResponsibleCommits(rows[i], sha);
      if (direct) return direct;
    }

    for (i = 0; i < rows.length; i += 1) {
      direct = githubCommitUrlFromRow(rows[i], sha);
      if (direct) return direct;
    }

    return "";
  }

  function objectUrl(value) {
    if (!value) return "";
    return value.html_url || value.htmlUrl || value.url || "";
  }

  function commitUrlFromResponsibleCommits(row, sha) {
    var commits = (row && (row.responsibleCommits || row.responsible_commits)) || [];
    var i;
    var commit;
    var commitSha;
    var url;

    for (i = 0; i < commits.length; i += 1) {
      commit = commits[i] || {};
      commitSha = commit.sha || commit.commitSha || commit.commit_sha || "";
      url = commit.html_url || commit.htmlUrl || commit.url || "";
      if (sha && commitSha && sameSha(sha, commitSha) && isGitHubCommitUrl(url)) return url;
    }

    return "";
  }

  function githubCommitUrlFromRow(row, sha) {
    var repoUrl = githubRepoUrlFromRow(row);
    if (!repoUrl || !sha) return "";
    return repoUrl + "/commit/" + encodeURIComponent(String(sha));
  }

  function githubRepoUrlFromRow(row) {
    var urls = [];
    var commits;
    var i;
    var match;

    if (!row) return "";
    urls.push(row.headCommitUrl, row.head_commit_url, row.commitUrl, row.commit_url, row.compareUrl, row.compare_url);
    if (row.main) urls.push(row.main.commit_url, row.main.commitUrl);

    commits = row.responsibleCommits || row.responsible_commits || [];
    for (i = 0; i < commits.length; i += 1) {
      urls.push(commits[i] && (commits[i].html_url || commits[i].htmlUrl || commits[i].url));
    }

    for (i = 0; i < urls.length; i += 1) {
      match = String(urls[i] || "").match(/^(https:\/\/github\.com\/[^\/]+\/[^\/]+)(?:\/|$)/i);
      if (match && match[1]) return match[1].replace(/\/$/, "");
    }

    return "";
  }

  function isGitHubCommitUrl(url) {
    return /^https:\/\/github\.com\/[^\/]+\/[^\/]+\/commit\//i.test(String(url || ""));
  }

  function adoUrlForRow(row) {
    if (!row) return "";

    var direct = firstValue([
      row.adoRunUrl,
      row.ado_run_url,
      row.adoPipelineUrl,
      row.ado_pipeline_url,
      row.pipelineUrl,
      row.pipeline_url,
      row.buildUrl,
      row.build_url
    ]);
    if (isAdoUrl(direct)) return direct;

    var type = row.comparison_type || row.comparisonType || "";
    var nprDeployment = row.npr_deployment || row.nprDeployment || {};
    var prdDeployment = row.prd_deployment || row.prdDeployment || {};

    if (type === "npr_main") return deploymentUrl(nprDeployment);
    if (type === "prd_main") return deploymentUrl(prdDeployment);

    if (type === "npr_prd") {
      var headSha = row.headSha || row.head_sha || "";
      var nprSha = row.nprSha || row.npr_sha || deploymentSha(nprDeployment);
      var prdSha = row.prdSha || row.prd_sha || deploymentSha(prdDeployment);

      if (headSha && nprSha && sameSha(headSha, nprSha)) return deploymentUrl(nprDeployment);
      if (headSha && prdSha && sameSha(headSha, prdSha)) return deploymentUrl(prdDeployment);

      if (deploymentTimestamp(nprDeployment) >= deploymentTimestamp(prdDeployment)) {
        return deploymentUrl(nprDeployment) || deploymentUrl(prdDeployment);
      }
      return deploymentUrl(prdDeployment) || deploymentUrl(nprDeployment);
    }

    return deploymentUrl(nprDeployment) || deploymentUrl(prdDeployment);
  }

  function deploymentUrl(deployment) {
    if (!deployment) return "";
    var url = deployment.url || deployment.web_url || deployment.webUrl || deployment.adoRunUrl || deployment.ado_run_url || "";
    return isAdoUrl(url) ? url : "";
  }

  function deploymentSha(deployment) {
    if (!deployment) return "";
    return deployment.sha || deployment.source_version || deployment.sourceVersion || "";
  }

  function deploymentTimestamp(deployment) {
    if (!deployment) return 0;
    var value = deployment.timestamp || deployment.finish_time || deployment.finishTime || deployment.start_time || deployment.startTime || deployment.queue_time || deployment.queueTime || "";
    if (typeof value === "number") return value;
    var date = new Date(value);
    return isNaN(date.getTime()) ? 0 : date.getTime();
  }

  function isAdoUrl(url) {
    if (!url) return false;
    var value = String(url).toLowerCase();
    return (value.indexOf("dev.azure.com") !== -1 || value.indexOf("visualstudio.com") !== -1 || value.indexOf("/_build/") !== -1 || value.indexOf("_build/results") !== -1) && value.indexOf("github.com/") === -1;
  }

  function sameSha(left, right) {
    if (!left || !right) return false;
    left = String(left).toLowerCase();
    right = String(right).toLowerCase();
    return left === right || left.indexOf(right) === 0 || right.indexOf(left) === 0;
  }

  function buildDriftCardHtml(data) {
    var jiraHtml = buildJiraHtml(data.jiraTickets, data.pullRequests);
    var userHtml = data.responsibleUsers.length
      ? '<div class="responsible-line"><strong>User responsible:</strong> ' + data.responsibleUsers.map(escapeHtml).join(", ") + '</div>'
      : "";
    var prHtml = buildPrHtml(data.pullRequests);
    var prBlock = prHtml
      ? '<div class="responsible-line"><strong>PR Number:</strong> ' + prHtml + '</div>'
      : "";
    var jiraBlock = jiraHtml
      ? '<div class="jira-status-line"><strong>JIRA Link:</strong> ' + jiraHtml + '</div>'
      : '<div class="jira-status-line"><strong>JIRA Link:</strong> Not found</div>';
    var explainBlock = data.explainText
      ? '<div class="drift-explain-panel" hidden><strong>Explain:</strong><br>' + escapeHtml(data.explainText) + '</div>'
      : "";
    var explainButton = data.explainText
      ? '<button class="small-action-btn" type="button" data-toggle-explain>Explain</button>'
      : "";
    var generalFixInstructions = data.status === "drift" ? buildGeneralFixInstructions(data) : "";
    var generalFixBlock = generalFixInstructions
      ? '<div class="fix-instruction"><strong>General drift fix instructions</strong>' + escapeHtml(generalFixInstructions) + '</div>'
      : "";
    var createJiraButton = data.status === "drift"
      ? '<button class="small-action-btn jira-create-btn" type="button" data-create-jira-ticket>Create Jira Ticket</button>'
      : "";
    return '' +
      '<div class="env-row-main">' +
        '<div class="env-row-titleline">' +
          '<div class="env-name">' + escapeHtml(data.title) + '</div>' +
          '<span class="status-chip ' + data.status + '">' + (data.status === "drift" ? "Drift Found" : "Clean") + '</span>' +
        '</div>' +
        '<div class="commit-strip">' +
          buildCommitCell("NPR", data.nprSha, data.nprCommitUrl, data.nprPipelineUrl) +
          buildCommitCell("PRD", data.prdSha, data.prdCommitUrl, data.prdPipelineUrl) +
          buildCommitCell("MAIN", data.mainSha, data.mainCommitUrl, "") +
          '<div class="env-stat drift-exists ' + (data.status === "drift" ? "drift" : "") + '"><strong>DRIFT FOUND</strong><span>' + (data.status === "drift" ? "YES" : "NO") + '</span></div>' +
        '</div>' +
        userHtml +
        prBlock +
        jiraBlock +
        generalFixBlock +
        explainBlock +
        '<div class="env-actions">' +
          explainButton +
          createJiraButton +
          buildLink(data.compareUrl, "Compare") +
        '</div>' +
      '</div>';
  }

  function buildGeneralFixInstructions(data) {
    var lines = [];
    lines.push("Review the NPR, PRD, and main commit IDs shown above and confirm which SHA should be the source of truth.");
    lines.push("Open the linked commit, PR, Jira links, and ADO pipeline run before making changes.");
    if (data.nprPipelineUrl || data.prdPipelineUrl) {
      lines.push("Rerun or promote the matching NPR/PRD Azure DevOps deployment pipeline so the environments point to the intended commit.");
    } else {
      lines.push("Find the matching NPR/PRD deployment pipeline and rerun or promote the intended commit.");
    }
    lines.push("Refresh this dashboard after the pipeline completes and verify drift is no longer shown.");
    return lines.join("\n");
  }

  function buildCommitCell(label, sha, commitUrl, pipelineUrl) {
    var commitLink = buildLink(commitUrl, "Open Commit");
    var pipelineLink = pipelineUrl ? buildLink(pipelineUrl, "Open Pipeline") : "";

    return '' +
      '<div class="env-stat commit-env-cell">' +
        '<strong>' + escapeHtml(label) + '</strong>' +
        '<span>' + escapeHtml(shortSha(sha) || "-") + '</span>' +
        '<div class="commit-cell-actions">' + commitLink + pipelineLink + '</div>' +
      '</div>';
  }

  function buildLink(url, label) {
    if (!url) return "";
    return '<a class="small-action-btn" href="' + escapeAttribute(url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(label) + '</a>';
  }

  function buildPrHtml(prs) {
    var seen = {};
    var links = [];

    for (var i = 0; i < prs.length; i += 1) {
      var pr = prs[i] || {};
      var number = pr.number || pr.id || "";
      var url = pr.url || pr.html_url || pr.htmlUrl || "";
      if (!number || seen[number]) continue;
      seen[number] = true;

      if (url) {
        links.push('<a class="pr-link-chip" href="' + escapeAttribute(url) + '" target="_blank" rel="noopener noreferrer">#' + escapeHtml(number) + '</a>');
      } else {
        links.push('<span class="pr-link-chip">#' + escapeHtml(number) + '</span>');
      }
    }

    return links.join(" ");
  }

  function buildJiraHtml(tickets, prs) {
    var allTickets = tickets.slice(0);

    for (var i = 0; i < prs.length; i += 1) {
      var prTickets = prs[i].jira_tickets || prs[i].jiraTickets || [];
      for (var j = 0; j < prTickets.length; j += 1) {
        allTickets.push(prTickets[j]);
      }
    }

    var seen = {};
    var links = [];

    for (var k = 0; k < allTickets.length; k += 1) {
      var ticket = allTickets[k] || {};
      var key = ticket.key || ticket.id || "";
      if (!key || seen[key]) continue;
      seen[key] = true;

      var url = ticket.url || ticket.web_url || "";
      if (url) {
        links.push('<a class="jira-ticket-chip" href="' + escapeAttribute(url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(key) + '</a>');
      } else {
        links.push('<span class="jira-ticket-chip unavailable">' + escapeHtml(key) + '</span>');
      }
    }

    return links.join(" ");
  }

  function groupHasDrift(group) {
    for (var i = 0; i < group.rows.length; i += 1) {
      if (normalizeStatus(group.rows[i].status) === "drift" || normalizeStatus(group.rows[i].status) === "error") {
        return true;
      }
    }
    return false;
  }

  function collectResponsibleUsers(rows) {
    var seen = {};
    var result = [];

    function addIdentity(value) {
      var clean = cleanUser(value);
      if (clean && !seen[clean]) {
        seen[clean] = true;
        result.push(clean);
      }
    }

    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i] || {};
      var users = row.responsibleUsers || row.responsible_users || [];
      var commits = row.responsibleCommits || row.responsible_commits || [];
      var j;

      for (j = 0; j < users.length; j += 1) {
        addIdentity(users[j]);
      }

      for (j = 0; j < commits.length; j += 1) {
        addIdentity({
          email: commits[j].author_email || commits[j].authorEmail || commits[j].committer_email || commits[j].committerEmail || "",
          login: commits[j].author_login || commits[j].authorLogin || commits[j].committer_login || commits[j].committerLogin || "",
          name: commits[j].author_name || commits[j].authorName || commits[j].committer_name || commits[j].committerName || ""
        });
      }
    }

    return result;
  }

  function cleanUser(user) {
    if (!user) return "";

    var candidates = [];
    if (typeof user === "string") {
      candidates.push(user);
    } else {
      candidates.push(user.login || "");
      candidates.push(user.user || "");
      candidates.push(user.username || "");
      candidates.push(user.email || "");
      candidates.push(user.name || "");
      candidates.push(user.displayName || "");
    }

    for (var i = 0; i < candidates.length; i += 1) {
      var clean = normalizeUserIdentity(candidates[i]);
      if (clean) return clean;
    }

    return "";
  }

  function normalizeUserIdentity(value) {
    var raw = String(value || "").trim();
    var match;

    if (!raw) return "";
    raw = raw.replace(/^GitHub App\\/i, "").replace(/^GitHub App\//i, "").trim();

    if (!raw || raw.toLowerCase() === "unknown") return "";
    if (/github app/i.test(raw)) return "";
    if (/microsoft\.visualstudio\.services\.tfs/i.test(raw)) return "";
    if (/ad157672-dafb-4cc1-82a8-0c9d5ddb0c63/i.test(raw)) return "";
    if (/^00000002-0000-8888-8000-000000000000@/i.test(raw)) return "";
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)) return "";
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}@[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)) return "";

    match = raw.match(/^\d+\+([^@]+)@users\.noreply\.github\.com$/i);
    if (match && match[1]) return match[1];

    match = raw.match(/^([^@]+)@users\.noreply\.github\.com$/i);
    if (match && match[1]) return match[1];

    return raw;
  }

  function collectJiraTickets(rows) {
    var result = [];
    var seen = {};

    for (var i = 0; i < rows.length; i += 1) {
      var tickets = rows[i].jiraTickets || rows[i].jira_tickets || [];
      for (var j = 0; j < tickets.length; j += 1) {
        var ticket = tickets[j] || {};
        var key = ticket.key || ticket.id || "";
        if (key && !seen[key]) {
          seen[key] = true;
          result.push(ticket);
        }
      }
    }

    return result;
  }

  function collectPullRequests(rows) {
    var result = [];
    var seen = {};

    function addPr(pr, fallbackIndex) {
      pr = pr || {};
      var key = pr.url || pr.html_url || pr.number || fallbackIndex;
      if (!key || seen[key]) return;
      seen[key] = true;
      result.push(pr);
    }

    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i] || {};
      var prs = row.pullRequests || row.pull_requests || row.prs || [];
      var commits = row.responsibleCommits || row.responsible_commits || [];
      var j;

      for (j = 0; j < prs.length; j += 1) {
        addPr(prs[j], String(i) + ":row:" + String(j));
      }

      for (j = 0; j < commits.length; j += 1) {
        var commitPrs = commits[j].pullRequests || commits[j].pull_requests || commits[j].prs || [];
        for (var k = 0; k < commitPrs.length; k += 1) {
          addPr(commitPrs[k], String(i) + ":commit:" + String(j) + ":" + String(k));
        }
      }
    }

    return result;
  }

  function collectExplainText(rows) {
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i] || {};
      if (row.fix_instructions) return row.fix_instructions;
      if (row.remediation) return row.remediation;
      if (row.summary) return row.summary;
      if (row.commit_summary) return row.commit_summary;
    }
    return "";
  }

  function firstValueFromRows(rows, keys) {
    for (var i = 0; i < rows.length; i += 1) {
      for (var j = 0; j < keys.length; j += 1) {
        if (rows[i] && rows[i][keys[j]]) return rows[i][keys[j]];
      }
    }
    return "";
  }

  function firstValue(values) {
    for (var i = 0; i < values.length; i += 1) {
      if (values[i]) return values[i];
    }
    return "";
  }

  function renderActivity(providers) {
    var list = document.getElementById("activityList");
    if (!list) return;

    list.innerHTML = "";

    var rows = [];
    if (providers.aws && providers.aws.environments) rows = rows.concat(filterAwsRows(providers.aws.environments));
    if (providers.azure && providers.azure.environments) rows = rows.concat(providers.azure.environments);

    if (!rows.length) {
      list.innerHTML = '<div class="empty-state">No recent drift activity.</div>';
      return;
    }

    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i] || {};
      var item = document.createElement("div");
      var status = normalizeStatus(row.status);

      item.className = "activity-item";
      item.innerHTML = '' +
        '<div class="activity-dot ' + status + '"></div>' +
        '<div>' +
          '<div class="activity-title">' + escapeHtml(row.name || row.group_label || "Drift check") + '</div>' +
          '<div class="activity-meta">' + escapeHtml(row.summary || row.commit_summary || "") + '</div>' +
        '</div>' +
        '<span class="status-chip ' + status + '">' + labelStatus(status) + '</span>';

      list.appendChild(item);
    }
  }

  function setFooterDates(updatedAt) {
    var text = "Last refreshed: " + formatDate(updatedAt);
    setStatusLine(text, "success");

    var activityUpdatedAt = document.getElementById("activityUpdatedAt");
    if (activityUpdatedAt) activityUpdatedAt.textContent = formatDate(updatedAt);
  }

  function calculateProviderStatus(groups) {
    var hasError = false;
    var hasDrift = false;
    var hasClean = false;

    for (var i = 0; i < groups.length; i += 1) {
      for (var j = 0; j < groups[i].rows.length; j += 1) {
        var status = normalizeStatus(groups[i].rows[j].status);
        if (status === "error") hasError = true;
        if (status === "drift") hasDrift = true;
        if (status === "clean") hasClean = true;
      }
    }

    if (hasError) return "error";
    if (hasDrift) return "drift";
    if (hasClean) return "clean";
    return "waiting";
  }

  function normalizeStatus(status) {
    var value = String(status || "waiting").toLowerCase().trim();
    if (value === "succeeded" || value === "success" || value === "aligned" || value === "ok") return "clean";
    if (value === "changed" || value === "mismatch" || value === "behind") return "drift";
    if (value === "failed" || value === "failure") return "error";
    if (value === "pending" || value === "running") return "waiting";
    if (value === "clean" || value === "drift" || value === "error" || value === "waiting") return value;
    return "unknown";
  }

  function labelStatus(status) {
    var normalized = normalizeStatus(status);
    if (normalized === "clean") return "Clean";
    if (normalized === "drift") return "Drift Found";
    if (normalized === "error") return "Error";
    if (normalized === "waiting") return "Waiting";
    return "Unknown";
  }

  function shortSha(value) {
    if (!value) return "-";
    return String(value).substring(0, 12);
  }

  function formatDate(value) {
    if (!value) return "Not checked yet";
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  }

  function setStatusLine(text, className) {
    var statusLine = document.getElementById("driftStatusLine");
    if (!statusLine) return;
    statusLine.textContent = text;
    statusLine.className = "drift-footnote " + (className || "");
  }

  function setText(id, value) {
    var element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
  }
}());
