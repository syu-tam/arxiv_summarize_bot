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
    const fromDate = document.getElementById('fromDate').value; // 日付フィールドから値を取得
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
        // 検索URLの構築
        let url = '';
        
        // 日付指定がある場合は日付検索APIを使用
        if (fromDate) {
            url = `/api/search_by_date?query=${encodeURIComponent(query)}&from_date=${fromDate}&max_results=${maxResults}`;
        } else {
            // カテゴリーパラメータの構築
            const categoryParams = selectedCategories.map(cat => `categories=${encodeURIComponent(cat)}`).join('&');
            url = `/api/search?query=${encodeURIComponent(query)}&max_results=${maxResults}${categoryParams ? '&' + categoryParams : ''}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();

        if (data.status === 'error') {
            throw new Error(data.message || '検索に失敗しました');
        }

        currentResults = data.papers || [];

        // 日付指定検索の場合、結果数の表示を拡張
        let resultCountText = `${currentResults.length}件の論文が見つかりました`;
        if (selectedCategories.length > 0) {
            resultCountText += ` (${selectedCategories.length}個のカテゴリーでフィルター中)`;
        }
        if (fromDate) {
            resultCountText += ` (${fromDate}以降の論文)`;
        }

        displayResults(currentResults);
        document.querySelector('.results-count').textContent = resultCountText;
        resultsSectionEl.classList.remove('d-none');

    } catch (error) {
        showError('検索中にエラーが発生しました: ' + error.message);
    } finally {
        loadingEl.classList.add('d-none');
    }
}

// 結果表示部分の実装
function displayResults(papers, groupedPapers = null) {
    const resultsEl = document.getElementById('results');
    resultsEl.innerHTML = '';
    
    if ((!papers || papers.length === 0) && (!groupedPapers || Object.keys(groupedPapers).length === 0)) {
        resultsEl.innerHTML = '<div class="alert alert-info">検索結果が見つかりませんでした。</div>';
        return;
    }

    // グループ化されたデータがある場合（新着チェック時）
    if (groupedPapers && Object.keys(groupedPapers).length > 0) {
        Object.entries(groupedPapers).forEach(([date, keywordGroups], dateIndex) => {
            const dateSection = document.createElement('div');
            dateSection.className = 'date-section';
            
            // 日付を日本語フォーマットに変換
            const jpDate = new Date(date).toLocaleDateString('ja-JP', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
            
            // 日付ヘッダー部分
            dateSection.innerHTML = `
                <div class="date-header" onclick="toggleDateSection(${dateIndex})">
                    <h2 class="h3">${jpDate}</h2>
                    <i class="bi bi-chevron-down toggle-icon"></i>
                </div>
                <div class="date-content" id="date-content-${dateIndex}">
                    ${Object.entries(keywordGroups).map(([keyword, keywordPapers], keywordIndex) => `
                        <div class="keyword-section">
                            <div class="keyword-header" onclick="toggleKeywordSection(${dateIndex}, ${keywordIndex})">
                                <h3 class="h4">キーワード: ${keyword} (${keywordPapers.length}件)</h3>
                                <i class="bi bi-chevron-down toggle-icon"></i>
                            </div>
                            <div class="keyword-content" id="keyword-content-${dateIndex}-${keywordIndex}">
                                <div class="papers-group">
                                    ${keywordPapers.map(paper => createPaperCard(paper)).join('')}
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
            
            resultsEl.appendChild(dateSection);
            
            // 最初の日付セクションのみ開く
            if (dateIndex === 0) {
                const content = dateSection.querySelector('.date-content');
                const header = dateSection.querySelector('.date-header');
                content.classList.add('active');
                header.classList.add('active');
                
                // 最初のキーワードセクションも開く
                const firstKeywordContent = content.querySelector('.keyword-content');
                const firstKeywordHeader = content.querySelector('.keyword-header');
                if (firstKeywordContent && firstKeywordHeader) {
                    firstKeywordContent.classList.add('active');
                    firstKeywordHeader.classList.add('active');
                }
            }
        });
        return;
    }

    // 通常の検索結果の表示（従来の表示方法）
    papers.forEach(paper => {
        const paperEl = document.createElement('div');
        paperEl.className = 'paper-card';
        paperEl.innerHTML = createPaperCard(paper);
        resultsEl.appendChild(paperEl);
    });
}

// 日付セクションの開閉を制御する関数
function toggleDateSection(index) {
    const content = document.getElementById(`date-content-${index}`);
    const header = content.previousElementSibling;
    content.classList.toggle('active');
    header.classList.toggle('active');
}

// キーワードセクションの開閉を制御する関数
function toggleKeywordSection(dateIndex, keywordIndex) {
    const content = document.getElementById(`keyword-content-${dateIndex}-${keywordIndex}`);
    const header = content.previousElementSibling;
    content.classList.toggle('active');
    header.classList.toggle('active');
}

function createPaperCard(paper) {
    return `
        <div class="paper-card">
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
        </div>
    `;
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

        // 監視キーワードに一致する論文を表示
        if (data.grouped_papers && Object.keys(data.grouped_papers).length > 0) {
            displayResults(null, data.grouped_papers);
            
            // キーワードで絞り込まれた論文数をカウント
            let filteredCount = 0;
            Object.values(data.grouped_papers).forEach(keywordGroups => {
                Object.values(keywordGroups).forEach(papers => {
                    filteredCount += papers.length;
                });
            });
            
            // 全体の論文数と表示されている論文数を表示
            let resultCountText = `${data.papers.length}件の新着論文が見つかりました`;
            if (filteredCount < data.papers.length) {
                resultCountText += `（そのうち${filteredCount}件が監視キーワードに一致し表示されています）`;
            }
            document.querySelector('.results-count').textContent = resultCountText;
        } else {
            // 監視キーワードに一致する論文がない場合は、全ての論文をそのまま表示
            displayResults(data.papers);
            document.querySelector('.results-count').textContent = 
                `${data.papers.length}件の新着論文が見つかりました`;
        }
        
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