/**
 * M&A Target Discovery Platform - Frontend Logic
 */

const API_BASE = '/api';
let currentRunId = null;
let pollInterval = null;

// DOM Elements
const criteriaInput = document.getElementById('criteria');
const useMockCheckbox = document.getElementById('useMock');
const runSearchBtn = document.getElementById('runSearch');
const statusDiv = document.getElementById('status');
const resultsContainer = document.getElementById('resultsContainer');
const resultsCount = document.getElementById('resultsCount');
const exportBtn = document.getElementById('exportBtn');
const evidenceModal = document.getElementById('evidenceModal');
const modalTitle = document.getElementById('modalTitle');
const modalBody = document.getElementById('modalBody');

// Event Listeners
runSearchBtn.addEventListener('click', startSearch);
exportBtn.addEventListener('click', exportResults);
evidenceModal.addEventListener('click', (e) => {
    if (e.target === evidenceModal) closeModal();
});

/**
 * Start a new search
 */
async function startSearch() {
    // Validate criteria JSON
    let criteria;
    try {
        criteria = JSON.parse(criteriaInput.value);
    } catch (e) {
        showStatus('Invalid JSON: ' + e.message, 'failed');
        return;
    }

    // Disable button
    runSearchBtn.disabled = true;
    runSearchBtn.innerHTML = '<span class="spinner"></span>Starting...';

    try {
        const response = await fetch(`${API_BASE}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                criteria: criteria,
                use_mock: useMockCheckbox.checked,
                limit: 50
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        currentRunId = data.run_id;
        showStatus('Search started...', 'running');

        // Start polling for status
        pollInterval = setInterval(checkStatus, 2000);

    } catch (e) {
        showStatus('Failed to start search: ' + e.message, 'failed');
        resetButton();
    }
}

/**
 * Check search status
 */
async function checkStatus() {
    if (!currentRunId) return;

    try {
        const response = await fetch(`${API_BASE}/status/${currentRunId}`);
        const data = await response.json();

        if (data.status === 'running') {
            showStatus(`Searching... Found ${data.total_found} candidates, scored ${data.total_scored}`, 'running');
        } else if (data.status === 'completed') {
            clearInterval(pollInterval);
            showStatus(`Completed! Found ${data.total_found} candidates.`, 'completed');
            await loadResults();
            resetButton();
        } else if (data.status === 'failed') {
            clearInterval(pollInterval);
            showStatus('Search failed: ' + (data.error_message || 'Unknown error'), 'failed');
            resetButton();
        }
    } catch (e) {
        console.error('Status check failed:', e);
    }
}

/**
 * Load and display results
 */
async function loadResults() {
    if (!currentRunId) return;

    try {
        const response = await fetch(`${API_BASE}/results/${currentRunId}`);
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            renderResults(data.results);
            resultsCount.textContent = `${data.total_results} results`;
            exportBtn.style.display = 'inline-block';
        } else {
            resultsContainer.innerHTML = '<div class="empty-state"><p>No results found matching your criteria</p></div>';
            resultsCount.textContent = '';
            exportBtn.style.display = 'none';
        }
    } catch (e) {
        resultsContainer.innerHTML = `<div class="empty-state"><p>Failed to load results: ${e.message}</p></div>`;
    }
}

/**
 * Render results table
 */
function renderResults(results) {
    const qualified = results.filter(r => !r.is_disqualified);
    const disqualified = results.filter(r => r.is_disqualified);

    let html = `
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Company</th>
                    <th>Score</th>
                    <th>Confidence</th>
                    <th>Business Model</th>
                    <th>Industries</th>
                    <th>Match Summary</th>
                    <th>Evidence</th>
                </tr>
            </thead>
            <tbody>
    `;

    // Qualified results
    for (const r of qualified) {
        const scoreClass = r.fit_score >= 70 ? 'high' : r.fit_score >= 40 ? 'medium' : 'low';
        html += `
            <tr>
                <td>#${r.rank}</td>
                <td>
                    <strong>${escapeHtml(r.name)}</strong>
                    ${r.website ? `<br><a href="${escapeHtml(r.website)}" target="_blank" style="font-size: 0.75rem; color: var(--primary);">${escapeHtml(r.domain || r.website)}</a>` : ''}
                </td>
                <td><span class="score ${scoreClass}">${r.fit_score.toFixed(1)}</span></td>
                <td>${(r.confidence * 100).toFixed(0)}%</td>
                <td>${escapeHtml(r.business_model || '-')}</td>
                <td>${r.industries.map(i => `<span class="tag">${escapeHtml(i)}</span>`).join('') || '-'}</td>
                <td style="max-width: 250px; font-size: 0.8125rem;">
                    ${r.match_summary.slice(0, 2).map(s => `<div>• ${escapeHtml(s)}</div>`).join('')}
                </td>
                <td>
                    <button class="evidence-btn" onclick='showEvidence(${JSON.stringify(r)})'>
                        View (${r.evidence.length})
                    </button>
                </td>
            </tr>
        `;
    }

    // Disqualified results (collapsed)
    if (disqualified.length > 0) {
        html += `
            <tr>
                <td colspan="8" style="background: var(--gray-100); font-weight: 500;">
                    Disqualified (${disqualified.length})
                </td>
            </tr>
        `;

        for (const r of disqualified) {
            html += `
                <tr style="opacity: 0.6;">
                    <td>#${r.rank}</td>
                    <td>
                        <strong>${escapeHtml(r.name)}</strong>
                        <span class="tag disqualified">Disqualified</span>
                    </td>
                    <td>-</td>
                    <td>-</td>
                    <td>${escapeHtml(r.business_model || '-')}</td>
                    <td>-</td>
                    <td style="font-size: 0.8125rem; color: var(--danger);">
                        ${r.disqualification_reasons.map(s => `<div>• ${escapeHtml(s)}</div>`).join('')}
                    </td>
                    <td>-</td>
                </tr>
            `;
        }
    }

    html += '</tbody></table>';
    resultsContainer.innerHTML = html;
}

/**
 * Show evidence modal
 */
function showEvidence(result) {
    modalTitle.textContent = `Evidence for ${result.name}`;

    let html = '';

    // Match summary
    if (result.match_summary && result.match_summary.length > 0) {
        html += '<h4 style="margin-bottom: 0.5rem;">Match Summary</h4>';
        html += '<ul style="margin-bottom: 1rem; padding-left: 1.5rem;">';
        for (const summary of result.match_summary) {
            html += `<li>${escapeHtml(summary)}</li>`;
        }
        html += '</ul>';
    }

    // Evidence items
    if (result.evidence && result.evidence.length > 0) {
        html += '<h4 style="margin-bottom: 0.5rem;">Supporting Evidence</h4>';
        for (const ev of result.evidence) {
            html += `
                <div class="evidence-item">
                    <div class="criterion">${escapeHtml(ev.criterion)}</div>
                    <div class="snippet">"${escapeHtml(ev.snippet)}"</div>
                    <div class="source">
                        Source: <a href="${escapeHtml(ev.source_url)}" target="_blank">${escapeHtml(ev.source_url)}</a>
                        <br>Confidence: ${(ev.confidence * 100).toFixed(0)}% | Method: ${escapeHtml(ev.extraction_method)}
                    </div>
                </div>
            `;
        }
    } else {
        html += '<p style="color: var(--gray-600);">No detailed evidence available</p>';
    }

    modalBody.innerHTML = html;
    evidenceModal.classList.add('open');
}

/**
 * Close evidence modal
 */
function closeModal() {
    evidenceModal.classList.remove('open');
}

/**
 * Export results as CSV
 */
function exportResults() {
    if (!currentRunId) return;
    window.location.href = `${API_BASE}/export/${currentRunId}`;
}

/**
 * Show status message
 */
function showStatus(message, type) {
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.style.display = 'block';
}

/**
 * Reset search button
 */
function resetButton() {
    runSearchBtn.disabled = false;
    runSearchBtn.innerHTML = 'Run Search';
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
