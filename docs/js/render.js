// docs/js/render.js
// AgentBridge Atlas — 前端渲染逻辑

let catalogData = null;
let currentItems = [];

async function loadCatalog() {
    try {
        const res = await fetch('data/catalog.json');
        if (!res.ok) throw new Error('Failed to load catalog');
        catalogData = await res.json();
        const assets = (catalogData.assets || []).map(a => ({ ...a, _type: 'asset' }));
        const discoveries = (catalogData.discoveries || []).map(d => ({ ...d, _type: 'discovery' }));
        currentItems = [...assets, ...discoveries];
        renderItems(currentItems);
    } catch (err) {
        document.getElementById('cardGrid').innerHTML = `<p style="color:#999;">⚠️ Unable to load catalog. Please try again later.</p>`;
        console.error(err);
    }
}

function renderItems(items) {
    const grid = document.getElementById('cardGrid');
    if (!items || items.length === 0) {
        grid.innerHTML = `<p style="color:#999;grid-column:1/-1;text-align:center;padding:2rem 0;">No items found.</p>`;
        return;
    }
    grid.innerHTML = items.map(item => {
        const isAsset = item._type === 'asset';
        const isDiscovery = item._type === 'discovery';
        let badge = '📄 Asset';
        let badgeClass = 'asset';
        let priceHtml = '';
        let domainHtml = '';
        let metaRight = '';

        if (isAsset) {
            badge = item.kind || 'Asset';
            badgeClass = 'asset';
            priceHtml = `<span class="price">${item.price || '?'} ${item.currency || 'USDC'}</span>`;
            if (item.domain && item.domain.length) {
                domainHtml = `<div class="domain-tags">${item.domain.slice(0,3).map(d => `<span>${d}</span>`).join('')}</div>`;
            }
            metaRight = priceHtml;
        } else if (isDiscovery) {
            badge = 'Discovery';
            badgeClass = 'discovery';
            const hasAsset = item.has_asset && item.asset_ids && item.asset_ids.length > 0;
            metaRight = hasAsset ? '📚 Has assets' : '🌐 Bridge available';
        }

        return `
            <div class="card" data-id="${item.id}" data-type="${item._type}" onclick="openDetail('${item.id}','${item._type}')">
                <div class="badge ${badgeClass}">${badge}</div>
                <h3>${item.name}</h3>
                <div class="description">${item.description || ''}</div>
                ${domainHtml}
                <div class="meta">
                    <span>${isAsset ? (item.format || '') : (item.intent || '')}</span>
                    <span>${metaRight}</span>
                </div>
            </div>
        `;
    }).join('');
}

document.getElementById('searchInput').addEventListener('input', function(e) {
    const q = e.target.value.trim().toLowerCase();
    if (!q) {
        renderItems(currentItems);
        return;
    }
    const filtered = currentItems.filter(item => {
        const name = (item.name || '').toLowerCase();
        const desc = (item.description || '').toLowerCase();
        const tags = (item.tags || []).join(' ').toLowerCase();
        const domain = (item.domain || []).join(' ').toLowerCase();
        const keywords = (item.keywords || []).join(' ').toLowerCase();
        const searchable = name + ' ' + desc + ' ' + tags + ' ' + domain + ' ' + keywords;
        return searchable.includes(q);
    });
    renderItems(filtered);
});

async function openDetail(id, type) {
    const modal = document.getElementById('detailModal');
    const body = document.getElementById('modalBody');
    const item = currentItems.find(i => i.id === id && i._type === type);
    if (!item) {
        body.innerHTML = '<p>Item not found.</p>';
        modal.classList.add('active');
        return;
    }

    const isAsset = type === 'asset';
    const isDiscovery = type === 'discovery';

    let html = `<h2>${item.name}</h2>`;
    html += `<p style="color:#555;">${item.description || ''}</p>`;

    if (isAsset) {
        html += `<div class="price" style="font-size:1.8rem;font-weight:700;margin:0.5rem 0;">${item.price || '?'} ${item.currency || 'USDC'}</div>`;
        html += `<p style="font-size:0.9rem;color:#666;">Payment: ${item.payment || 'x402'} &middot; Format: ${item.format || 'unknown'}</p>`;
        if (item.domain && item.domain.length) {
            html += `<p style="font-size:0.85rem;color:#777;">Domain: ${item.domain.join(', ')}</p>`;
        }
        if (item.tags && item.tags.length) {
            html += `<p style="font-size:0.85rem;color:#777;">Tags: ${item.tags.join(', ')}</p>`;
        }
        html += `<button class="btn-pay" onclick="purchaseAsset('${item.id}')">🔓 Pay & Get Content (${item.price} ${item.currency})</button>`;
    } else if (isDiscovery) {
        const hasAsset = item.has_asset && item.asset_ids && item.asset_ids.length > 0;
        if (hasAsset) {
            html += `<p style="color:#1a7a1a;">📚 This discovery has ${item.asset_ids.length} associated asset(s).</p>`;
            html += `<button class="btn-pay" onclick="viewAssetsForDiscovery('${item.id}')">View Associated Assets</button>`;
        } else {
            html += `<p style="color:#6a1a9a;">🌐 Bridge available — real-time data fetch.</p>`;
            html += `<p style="font-size:0.85rem;color:#777;">Intent: ${item.intent || ''}</p>`;
            html += `<button class="btn-pay" onclick="bridgeFetch('${item.id}')">🚀 Bridge Fetch</button>`;
        }
    }

    body.innerHTML = html;
    modal.classList.add('active');
}

document.getElementById('modalClose').addEventListener('click', function() {
    document.getElementById('detailModal').classList.remove('active');
});
document.getElementById('detailModal').addEventListener('click', function(e) {
    if (e.target === this) this.classList.remove('active');
});

async function purchaseAsset(assetId) {
    alert(`[Phase 4] x402 payment for: ${assetId}\nWill trigger GET /v1/assets/${assetId}/content → 402 → payment → delivery`);
}

async function viewAssetsForDiscovery(discoveryId) {
    alert(`[Phase 2] Will show assets for discovery: ${discoveryId}`);
}

async function bridgeFetch(discoveryId) {
    alert(`[Phase 4] Bridge fetch for: ${discoveryId}\nWill call /v1/bridge/fetch with x402 payment`);
}

loadCatalog();