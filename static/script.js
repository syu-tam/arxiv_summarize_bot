let currentResults = [];
let categories = {};

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // カテゴリー情報の取得
        const response = await fetch('/api/categories');
        const data = await response.json();
        if (data.status === 'success') {
            categories = data.categories;
            renderCategoryFilters();
        }

        // 監視中のキーワード一覧を取得
        await loadWatchedKeywords();
    } catch (error) {
        console.error('初期化エラー:', error);
    }
});

function renderCategoryFilters() {
    const container = document.getElementById('categoryFilters');
    
    Object.entries(categories).forEach(([mainCat, info]) => {
        const categoryGroup = document.createElement('div');
        categoryGroup.className = 'col-md-6 category-group';
        
        categoryGroup.innerHTML = `
            <div class="category-title">${info.name}</div>
            <div class="subcategory-list">
                ${Object.entries(info.subcategories).map(([id, name]) => `
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" value="${id}" id="${id}">
                        <label class="form-check-label" for="${id}">
                            ${name}
                        </label>
                    </div>
                `).join('')}
            </div>
        `;
        
        container.appendChild(categoryGroup);
    });
}

function getSelectedCategories() {
    const checkboxes = document.querySelectorAll('#categoryFilters input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

async function searchPapers() {
    const query = document.getElementById('searchQuery').value.trim();
    const maxResults = document.getElementById('maxResults').value;
    const selectedCategories = getSelectedCategories();
    const loadingEl = document.getElementById('loading');
    const errorEl = document.getElementById('error');
    const resultsEl = document.getElementById('results');
    const resultsSectionEl = document.getElementById('results-section');

    if (!query && selectedCategories.length === 0) {
        showError('検索キーワードまたはカテゴリーを選択してください');
        return;
    }

    // UIの初期化
    loadingEl.classList.remove('d-none');
    errorEl.classList.add('d-none');
    resultsSectionEl.classList.add('d-none');
    resultsEl.innerHTML = '';

    try {
        // カテゴリーパラメータの構築
        const categoryParams = selectedCategories.map(cat => `categories=${encodeURIComponent(cat)}`).join('&');
        const url = `/api/search?query=${encodeURIComponent(query)}&max_results=${maxResults}${categoryParams ? '&' + categoryParams : ''}`;
        
        const response = await fetch(url);
        const data = await response.json();

        if (data.status === 'error') {
            throw new Error(data.message || '検索に失敗しました');
        }

        currentResults = data.papers || [];

        displayResults(currentResults);
        document.querySelector('.results-count').textContent = 
            `${currentResults.length}件の論文が見つかりました${selectedCategories.length > 0 ? ` (${selectedCategories.length}個のカテゴリーでフィルター中)` : ''}`;
        resultsSectionEl.classList.remove('d-none');

    } catch (error) {
        showError('検索中にエラーが発生しました: ' + error.message);
    } finally {
        loadingEl.classList.add('d-none');
    }
}

// 結果表示部分の実装
function displayResults(papers) {
    const resultsEl = document.getElementById('results');
    resultsEl.innerHTML = '';
    
    if (!papers || papers.length === 0) {
        resultsEl.innerHTML = '<div class="alert alert-info">検索結果が見つかりませんでした。</div>';
        return;
    }

    papers.forEach(paper => {
        const paperEl = document.createElement('div');
        paperEl.className = 'paper-card';
        paperEl.innerHTML = `
            <h2 class="paper-title">${paper.title}</h2>
            <div class="paper-meta">
                <div class="meta-item">
                    <i class="bi bi-people"></i>
                    ${paper.authors.join(', ')}
                </div>
                <div class="meta-item">
                    <i class="bi bi-tag"></i>
                    ${paper.primary_category}
                </div>
                <div class="meta-item">
                    <i class="bi bi-calendar"></i>
                    ${new Date(paper.published).toLocaleDateString('ja-JP')}
                </div>
            </div>
            <div class="paper-summary">
                <h3 class="h5 mb-3">日本語要約:</h3>
                <p>${paper.summary_ja}</p>
            </div>
            <div class="paper-link">
                <a href="${paper.pdf_url}" class="btn btn-outline-primary" target="_blank">
                    <i class="bi bi-file-pdf"></i>
                    PDFを開く
                </a>
            </div>
        `;
        resultsEl.appendChild(paperEl);
    });
}

function sortResults(criterion) {
    if (!currentResults.length) return;

    switch (criterion) {
        case 'date':
            currentResults.sort((a, b) => new Date(b.published) - new Date(a.published));
            break;
        case 'title':
            currentResults.sort((a, b) => a.title.localeCompare(b.title));
            break;
    }

    displayResults(currentResults);
}

function showError(message) {
    const errorEl = document.getElementById('error');
    errorEl.textContent = message;
    errorEl.classList.remove('d-none');
}

function showSuccess(message) {
    const successEl = document.getElementById('success');
    successEl.textContent = message;
    successEl.classList.remove('d-none');
    setTimeout(() => {
        successEl.classList.add('d-none');
    }, 3000);
}

async function loadWatchedKeywords() {
    try {
        const response = await fetch('/api/watch');
        const data = await response.json();
        if (data.status === 'success') {
            renderWatchedKeywords(data.watched_keywords);
        }
    } catch (error) {
        console.error('監視キーワードの取得に失敗:', error);
    }
}

function renderWatchedKeywords(watchedKeywords) {
    const container = document.getElementById('watchedKeywords');
    if (watchedKeywords.keywords.length === 0) {
        container.innerHTML = '<div class="text-muted">監視中のキーワードはありません</div>';
        return;
    }

    const badges = watchedKeywords.keywords.map(keyword => `
        <span class="badge bg-light text-dark me-2 mb-2 p-2">
            ${keyword}
            <button class="btn btn-link btn-sm text-danger p-0 ms-2" 
                    onclick="removeWatchKeyword('${keyword}')" 
                    style="font-size: 0.8rem;">
                <i class="bi bi-x"></i>
            </button>
        </span>
    `).join('');

    container.innerHTML = badges;
}

async function addWatchKeyword() {
    const keywordInput = document.getElementById('newKeyword');
    const keyword = keywordInput.value.trim();
    if (!keyword) return;

    try {
        const selectedCategories = getSelectedCategories();
        const response = await fetch(`/api/watch?keyword=${encodeURIComponent(keyword)}${
            selectedCategories.map(cat => `&categories=${encodeURIComponent(cat)}`).join('')
        }`, {
            method: 'POST'
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            keywordInput.value = '';
            await loadWatchedKeywords();
            showSuccess(data.message);
        }
    } catch (error) {
        showError('キーワードの追加に失敗しました');
    }
}

async function removeWatchKeyword(keyword) {
    try {
        const response = await fetch(`/api/watch/${encodeURIComponent(keyword)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            await loadWatchedKeywords();
            showSuccess(data.message);
        }
    } catch (error) {
        showError('キーワードの削除に失敗しました');
    }
}

async function checkNewPapers() {
    const loadingEl = document.getElementById('loading');
    const errorEl = document.getElementById('error');
    const resultsSectionEl = document.getElementById('results-section');
    const resultsEl = document.getElementById('results');
    const successEl = document.getElementById('success');

    try {
        // UI要素の初期化
        loadingEl.classList.remove('d-none');
        errorEl.classList.add('d-none');
        resultsSectionEl.classList.add('d-none');
        successEl.classList.add('d-none');
        resultsEl.innerHTML = '';

        const response = await fetch('/api/new-papers');
        const data = await response.json();

        if (data.status === 'error') {
            throw new Error(data.message || '新着論文の取得に失敗しました');
        }

        // 新着論文がない場合
        if (!data.papers || data.papers.length === 0) {
            showSuccess('新しい論文は見つかりませんでした');
            return;
        }

        // 新着論文がある場合
        displayResults(data.papers);
        document.querySelector('.results-count').textContent = 
            `${data.papers.length}件の新着論文が見つかりました`;
        resultsSectionEl.classList.remove('d-none');

    } catch (error) {
        showError('新着論文の確認に失敗しました: ' + error.message);
    } finally {
        loadingEl.classList.add('d-none');
    }
}

async function saveEmailConfig() {
    const config = {
        smtp_server: document.getElementById('smtpServer').value,
        smtp_port: parseInt(document.getElementById('smtpPort').value),
        username: document.getElementById('username').value,
        password: document.getElementById('password').value,
        from_email: document.getElementById('fromEmail').value,
        to_emails: document.getElementById('toEmails').value.split(',').map(email => email.trim())
    };

    try {
        const response = await fetch('/api/email-config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });

        const data = await response.json();
        if (data.status === 'success') {
            // モーダルを閉じる
            const modal = bootstrap.Modal.getInstance(document.getElementById('emailConfigModal'));
            modal.hide();
            showSuccess(data.message);
        } else {
            showError(data.message);
        }
    } catch (error) {
        showError('メール設定の保存に失敗しました');
    }
}

// Enterキーでの検索を有効化
document.getElementById('searchQuery').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        searchPapers();
    }
});