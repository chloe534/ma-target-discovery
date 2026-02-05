/**
 * M&A Target Discovery Platform - Frontend Logic
 */

const API_BASE = '/api';
let currentRunId = null;
let pollInterval = null;
let allResults = [];
let savedCompanies = JSON.parse(localStorage.getItem('savedCompanies') || '[]');

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
const regionFilter = document.getElementById('regionFilter');
const savedContainer = document.getElementById('savedContainer');
const savedRegionFilter = document.getElementById('savedRegionFilter');
const savedCountSpan = document.getElementById('savedCount');
const savedStats = document.getElementById('savedStats');

// Event Listeners
runSearchBtn.addEventListener('click', startSearch);
exportBtn.addEventListener('click', exportResults);
document.getElementById('exportSavedBtn').addEventListener('click', exportSavedCompanies);
document.getElementById('clearSavedBtn').addEventListener('click', clearSavedCompanies);
evidenceModal.addEventListener('click', (e) => {
    if (e.target === evidenceModal) closeModal();
});
regionFilter.addEventListener('change', filterResultsByRegion);
savedRegionFilter.addEventListener('change', renderSavedCompanies);

// Tab switching
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab + '-tab').classList.add('active');
        if (tab.dataset.tab === 'saved') {
            renderSavedCompanies();
        }
    });
});

// Initialize
updateSavedCount();

/**
 * Start a new search
 */
async function startSearch() {
    let criteria;
    try {
        criteria = JSON.parse(criteriaInput.value);
    } catch (e) {
        showStatus('Invalid JSON: ' + e.message, 'failed');
        return;
    }

    runSearchBtn.disabled = true;
    runSearchBtn.innerHTML = '<span class="spinner"></span>Starting...';

    try {
        const response = await fetch(`${API_BASE}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                criteria: criteria,
                use_mock: useMockCheckbox.checked,
                limit: 100
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        currentRunId = data.run_id;
        showStatus('Search started... This may take a few minutes.', 'running');

        pollInterval = setInterval(checkStatus, 3000);

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
            showStatus(`Searching... Found ${data.total_found} candidates, enriched ${data.total_scored}`, 'running');
        } else if (data.status === 'completed') {
            clearInterval(pollInterval);
            showStatus(`Completed! Found ${data.total_scored} companies.`, 'completed');
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
            allResults = data.results;
            populateRegionFilter(allResults);
            renderResults(allResults);
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
 * Extract region from company data
 */
function extractRegion(company) {
    // Try to extract from domain TLD or industries
    const domain = company.domain || '';
    const tldMap = {
        '.uk': 'United Kingdom',
        '.co.uk': 'United Kingdom',
        '.de': 'Germany',
        '.fr': 'France',
        '.ca': 'Canada',
        '.au': 'Australia',
        '.io': 'Global',
        '.com': 'United States',
        '.co': 'United States'
    };

    for (const [tld, region] of Object.entries(tldMap)) {
        if (domain.endsWith(tld)) {
            return region;
        }
    }

    return 'Unknown';
}

/**
 * Populate region filter dropdown
 */
function populateRegionFilter(results) {
    const regions = new Set(results.map(r => extractRegion(r)));
    regionFilter.innerHTML = '<option value="">All Regions</option>';
    Array.from(regions).sort().forEach(region => {
        regionFilter.innerHTML += `<option value="${escapeHtml(region)}">${escapeHtml(region)}</option>`;
    });
}

/**
 * Filter results by region
 */
function filterResultsByRegion() {
    const selectedRegion = regionFilter.value;
    if (!selectedRegion) {
        renderResults(allResults);
        resultsCount.textContent = `${allResults.length} results`;
    } else {
        const filtered = allResults.filter(r => extractRegion(r) === selectedRegion);
        renderResults(filtered);
        resultsCount.textContent = `${filtered.length} of ${allResults.length} results`;
    }
}

/**
 * Check if company is saved
 */
function isCompanySaved(domain) {
    return savedCompanies.some(c => c.domain === domain);
}

/**
 * Save a company
 */
function saveCompany(company) {
    if (!isCompanySaved(company.domain)) {
        const savedCompany = {
            ...company,
            region: extractRegion(company),
            savedAt: new Date().toISOString()
        };
        savedCompanies.push(savedCompany);
        localStorage.setItem('savedCompanies', JSON.stringify(savedCompanies));
        updateSavedCount();
        // Re-render to update button state
        filterResultsByRegion();
    }
}

/**
 * Remove a saved company
 */
function removeCompany(domain) {
    savedCompanies = savedCompanies.filter(c => c.domain !== domain);
    localStorage.setItem('savedCompanies', JSON.stringify(savedCompanies));
    updateSavedCount();
    renderSavedCompanies();
}

/**
 * Update saved count badge
 */
function updateSavedCount() {
    savedCountSpan.textContent = `(${savedCompanies.length})`;
}

/**
 * Clear all saved companies
 */
function clearSavedCompanies() {
    if (confirm('Are you sure you want to remove all saved companies?')) {
        savedCompanies = [];
        localStorage.setItem('savedCompanies', JSON.stringify(savedCompanies));
        updateSavedCount();
        renderSavedCompanies();
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
                    <th style="width: 50px;">Rank</th>
                    <th>Company</th>
                    <th style="width: 70px;">Score</th>
                    <th style="width: 70px;">Region</th>
                    <th>Business Model</th>
                    <th>Industries</th>
                    <th style="width: 200px;">Match Summary</th>
                    <th style="width: 80px;">Actions</th>
                </tr>
            </thead>
            <tbody>
    `;

    for (const r of qualified) {
        const scoreClass = r.fit_score >= 70 ? 'high' : r.fit_score >= 40 ? 'medium' : 'low';
        const region = extractRegion(r);
        const isSaved = isCompanySaved(r.domain);

        html += `
            <tr>
                <td>#${r.rank}</td>
                <td>
                    <strong>${escapeHtml(r.name)}</strong>
                    ${r.website ? `<br><a href="${escapeHtml(r.website)}" target="_blank" style="font-size: 0.75rem; color: var(--primary);">${escapeHtml(r.domain || r.website)}</a>` : ''}
                </td>
                <td><span class="score ${scoreClass}">${r.fit_score.toFixed(1)}</span></td>
                <td><span class="tag region">${escapeHtml(region)}</span></td>
                <td>${escapeHtml(r.business_model || '-')}</td>
                <td>${r.industries.slice(0, 3).map(i => `<span class="tag">${escapeHtml(i)}</span>`).join('') || '-'}</td>
                <td style="font-size: 0.75rem;">
                    ${r.match_summary.slice(0, 2).map(s => `<div>• ${escapeHtml(s)}</div>`).join('')}
                    ${r.evidence.length > 0 ? `<button class="evidence-btn" onclick='showEvidence(${JSON.stringify(r).replace(/'/g, "&#39;")})'>View evidence (${r.evidence.length})</button>` : ''}
                </td>
                <td>
                    <button class="btn btn-sm ${isSaved ? 'btn-secondary' : 'btn-save'}"
                            onclick='${isSaved ? '' : `saveCompany(${JSON.stringify(r).replace(/'/g, "&#39;")})`}'
                            ${isSaved ? 'disabled' : ''}>
                        ${isSaved ? 'Saved' : 'Save'}
                    </button>
                </td>
            </tr>
        `;
    }

    if (disqualified.length > 0) {
        html += `
            <tr>
                <td colspan="8" style="background: var(--gray-100); font-weight: 500;">
                    Disqualified (${disqualified.length})
                </td>
            </tr>
        `;

        for (const r of disqualified.slice(0, 10)) {
            html += `
                <tr style="opacity: 0.6;">
                    <td>#${r.rank}</td>
                    <td>
                        <strong>${escapeHtml(r.name)}</strong>
                        <span class="tag disqualified">Disqualified</span>
                    </td>
                    <td>-</td>
                    <td><span class="tag region">${escapeHtml(extractRegion(r))}</span></td>
                    <td>${escapeHtml(r.business_model || '-')}</td>
                    <td>-</td>
                    <td style="font-size: 0.75rem; color: var(--danger);">
                        ${r.disqualification_reasons.slice(0, 2).map(s => `<div>• ${escapeHtml(s)}</div>`).join('')}
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
 * Render saved companies organized by region
 */
function renderSavedCompanies() {
    const selectedRegion = savedRegionFilter.value;

    // Update region filter options
    const regions = [...new Set(savedCompanies.map(c => c.region || extractRegion(c)))].sort();
    savedRegionFilter.innerHTML = '<option value="">All Regions</option>';
    regions.forEach(region => {
        savedRegionFilter.innerHTML += `<option value="${escapeHtml(region)}" ${selectedRegion === region ? 'selected' : ''}>${escapeHtml(region)}</option>`;
    });

    // Filter companies
    let filteredCompanies = savedCompanies;
    if (selectedRegion) {
        filteredCompanies = savedCompanies.filter(c => (c.region || extractRegion(c)) === selectedRegion);
    }

    if (filteredCompanies.length === 0) {
        savedContainer.innerHTML = '<div class="empty-state"><p>No saved companies yet. Search for companies and click "Save" to add them here.</p></div>';
        savedStats.innerHTML = '';
        return;
    }

    // Group by region
    const byRegion = {};
    filteredCompanies.forEach(c => {
        const region = c.region || extractRegion(c);
        if (!byRegion[region]) byRegion[region] = [];
        byRegion[region].push(c);
    });

    // Render stats
    savedStats.innerHTML = `
        <div class="stat">
            <div class="stat-value">${filteredCompanies.length}</div>
            <div class="stat-label">Total Saved</div>
        </div>
        <div class="stat">
            <div class="stat-value">${Object.keys(byRegion).length}</div>
            <div class="stat-label">Regions</div>
        </div>
        <div class="stat">
            <div class="stat-value">${(filteredCompanies.reduce((sum, c) => sum + (c.fit_score || 0), 0) / filteredCompanies.length).toFixed(1)}</div>
            <div class="stat-label">Avg Score</div>
        </div>
    `;

    // Render grouped companies
    let html = '';
    Object.keys(byRegion).sort().forEach(region => {
        const companies = byRegion[region];
        html += `
            <div class="region-group">
                <div class="region-header">
                    <h3>${escapeHtml(region)} <span class="count">${companies.length}</span></h3>
                </div>
                <div class="region-companies">
        `;

        companies.sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0)).forEach(c => {
            html += `
                <div class="saved-company-card">
                    <div class="saved-company-info">
                        <h4>${escapeHtml(c.name)}</h4>
                        <p>
                            ${c.website ? `<a href="${escapeHtml(c.website)}" target="_blank">${escapeHtml(c.domain)}</a> • ` : ''}
                            Score: ${(c.fit_score || 0).toFixed(1)}
                            ${c.business_model ? ` • ${escapeHtml(c.business_model)}` : ''}
                        </p>
                    </div>
                    <div class="saved-company-actions">
                        <button class="btn btn-sm btn-secondary" onclick='showEvidence(${JSON.stringify(c).replace(/'/g, "&#39;")})'>Details</button>
                        <button class="btn-remove" onclick="removeCompany('${escapeHtml(c.domain)}')">Remove</button>
                    </div>
                </div>
            `;
        });

        html += '</div></div>';
    });

    savedContainer.innerHTML = html;
}

/**
 * Export saved companies as CSV
 */
function exportSavedCompanies() {
    if (savedCompanies.length === 0) {
        alert('No saved companies to export');
        return;
    }

    let csv = 'Name,Domain,Website,Score,Region,Business Model,Industries,Saved At\n';
    savedCompanies.forEach(c => {
        csv += `"${c.name}","${c.domain || ''}","${c.website || ''}","${(c.fit_score || 0).toFixed(1)}","${c.region || extractRegion(c)}","${c.business_model || ''}","${(c.industries || []).join('; ')}","${c.savedAt || ''}"\n`;
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'saved_companies.csv';
    a.click();
    URL.revokeObjectURL(url);
}

/**
 * Show evidence modal
 */
function showEvidence(result) {
    modalTitle.textContent = `Evidence for ${result.name}`;

    let html = '';

    if (result.match_summary && result.match_summary.length > 0) {
        html += '<h4 style="margin-bottom: 0.5rem;">Match Summary</h4>';
        html += '<ul style="margin-bottom: 1rem; padding-left: 1.5rem;">';
        for (const summary of result.match_summary) {
            html += `<li>${escapeHtml(summary)}</li>`;
        }
        html += '</ul>';
    }

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
