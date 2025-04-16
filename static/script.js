let currentResults = [];
let categories = {};
let currentGroupedPapers = null;

// ユーザー設定を管理するオブジェクト
const userSettings = {
    // 設定を初期化・ロードする
    init: function() {
        // 監視キーワード検索結果の日本語要約設定をロード
        this.watchKeywordJapaneseSummary = this.loadSetting('watchKeywordJapaneseSummary', true);
        
        // 設定画面の表示を初期化
        this.updateSettingsUI();
        
        console.log("ユーザー設定を読み込みました:", this.watchKeywordJapaneseSummary);
    },
    
    // 設定値を保存
    saveSetting: function(key, value) {
        localStorage.setItem(key, JSON.stringify(value));
    },
    
    // 設定値を読み込み
    loadSetting: function(key, defaultValue) {
        const savedValue = localStorage.getItem(key);
        return savedValue !== null ? JSON.parse(savedValue) : defaultValue;
    },
    
    // 監視キーワードの日本語要約設定を切り替え
    toggleWatchKeywordJapaneseSummary: function() {
        this.watchKeywordJapaneseSummary = !this.watchKeywordJapaneseSummary;
        this.saveSetting('watchKeywordJapaneseSummary', this.watchKeywordJapaneseSummary);
        
        // 既に表示されている論文を更新
        if (currentResults.length > 0) {
            displayResults(currentResults, null, this.watchKeywordJapaneseSummary);
        }
    },
    
    // 設定UIを更新
    updateSettingsUI: function() {
        const watchKeywordSummaryToggle = document.getElementById('watchKeywordJapaneseSummary');
        if (watchKeywordSummaryToggle) {
            watchKeywordSummaryToggle.checked = this.watchKeywordJapaneseSummary;
        }
    }
};

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // ユーザー設定を初期化
        userSettings.init();
        
        // 監視キーワード日本語要約設定のイベントリスナーを設定
        const watchKeywordSummaryToggle = document.getElementById('watchKeywordJapaneseSummary');
        if (watchKeywordSummaryToggle) {
            watchKeywordSummaryToggle.addEventListener('change', function() {
                userSettings.toggleWatchKeywordJapaneseSummary();
            });
        }
        
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
    const enableJapaneseSummary = document.getElementById('enableJapaneseSummary').checked; // 日本語要約のオン/オフ状態を取得
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
            url = `/api/search_by_date?query=${encodeURIComponent(query)}&from_date=${fromDate}&max_results=${maxResults}&use_japanese_summary=${enableJapaneseSummary}`;
        } else {
            // カテゴリーパラメータの構築
            const categoryParams = selectedCategories.map(cat => `categories=${encodeURIComponent(cat)}`).join('&');
            url = `/api/search?query=${encodeURIComponent(query)}&max_results=${maxResults}${categoryParams ? '&' + categoryParams : ''}&use_japanese_summary=${enableJapaneseSummary}`;
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

        displayResults(currentResults, null, enableJapaneseSummary);
        document.querySelector('.results-count').textContent = resultCountText;
        resultsSectionEl.classList.remove('d-none');

    } catch (error) {
        showError('検索中にエラーが発生しました: ' + error.message);
    } finally {
        loadingEl.classList.add('d-none');
    }
}

// 結果表示部分の実装
function displayResults(papers, groupedPapers = null, enableJapaneseSummary = true) {
    const resultsEl = document.getElementById('results');
    resultsEl.innerHTML = '';
    
    if ((!papers || papers.length === 0) && (!groupedPapers || Object.keys(groupedPapers).length === 0)) {
        resultsEl.innerHTML = '<div class="alert alert-info">検索結果が見つかりませんでした。</div>';
        return;
    }

    // グループ化されたデータがある場合（新着チェック時）
    if (groupedPapers && Object.keys(groupedPapers).length > 0) {
        // バックエンドから返されたグループ化データをそのまま表示
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
                                    ${keywordPapers.map(paper => createPaperCard(paper, enableJapaneseSummary)).join('')}
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

    // 通常の検索結果の表示（バックエンドから返された結果をそのまま表示）
    papers.forEach(paper => {
        const paperEl = document.createElement('div');
        paperEl.className = 'paper-card';
        paperEl.innerHTML = createPaperCard(paper, enableJapaneseSummary);
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

function createPaperCard(paper, enableJapaneseSummary = true) {
    // URLのフォールバック処理を追加
    const arxivUrl = paper.url || paper.pdf_url.replace('/pdf/', '/abs/');
    const pdfUrl = paper.pdf_url || arxivUrl.replace('/abs/', '/pdf/');
    
    return `
        <div class="paper-card">
            <h2 class="paper-title">${paper.title}</h2>
            ${enableJapaneseSummary && paper.title_ja ? `
            <h3 class="paper-title-ja">${paper.title_ja}</h3>
            ` : ''}
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
            ${enableJapaneseSummary && paper.summary_ja ? `
            <div class="paper-summary">
                <h3 class="h5 mb-3">日本語要約:</h3>
                <p>${paper.summary_ja}</p>
            </div>
            ` : ''}
            <div class="paper-links">
                <a href="${pdfUrl}" target="_blank" class="btn btn-sm btn-primary">
                    <i class="bi bi-file-earmark-pdf"></i> PDF
                </a>
                <a href="${arxivUrl}" target="_blank" class="btn btn-sm btn-secondary">
                    <i class="bi bi-link-45deg"></i> arXiv
                </a>
            </div>
        </div>
    `;
}

// ソート機能を実装
function sortResults(criterion) {
    if (!currentResults || currentResults.length === 0) return;
    
    // ソートの基準に応じて並び替え
    switch(criterion) {
        case 'date-desc':
            currentResults.sort((a, b) => new Date(b.published) - new Date(a.published));
            break;
        case 'date-asc':
            currentResults.sort((a, b) => new Date(a.published) - new Date(b.published));
            break;
        case 'title-asc':
            currentResults.sort((a, b) => a.title.localeCompare(b.title));
            break;
        case 'title-desc':
            currentResults.sort((a, b) => b.title.localeCompare(a.title));
            break;
    }
    
    // ソートされた結果を表示（フィルタリングなし）
    displayResults(currentResults, null, document.getElementById('enableJapaneseSummary').checked);
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
    
    // 監視キーワード用の日本語要約設定を使用
    const enableJapaneseSummary = userSettings.watchKeywordJapaneseSummary;

    try {
        // UI要素の初期化
        loadingEl.classList.remove('d-none');
        errorEl.classList.add('d-none');
        resultsSectionEl.classList.add('d-none');
        successEl.classList.add('d-none');
        resultsEl.innerHTML = '';

        const response = await fetch(`/api/new-papers?use_japanese_summary=${enableJapaneseSummary}`);
        const data = await response.json();

        if (data.status === 'error') {
            throw new Error(data.message || '新着論文の取得に失敗しました');
        }

        // 論文が存在するか確認
        const hasPapers = data.papers && Object.keys(data.papers).length > 0;

        // 新着論文がない場合
        if (!hasPapers) {
            showSuccess('新しい論文は見つかりませんでした');
            return;
        }

        // バックエンドの結果をそのまま表示
        if (data.grouped_papers && Object.keys(data.grouped_papers).length > 0) {
            // グループ化されたデータをそのまま表示
            currentGroupedPapers = data.grouped_papers;
            displayResults(null, currentGroupedPapers, enableJapaneseSummary);
            
            // ソート機能のために論文データをcurrentResultsに格納
            currentResults = [];
            Object.values(currentGroupedPapers).forEach(keywordGroups => {
                Object.values(keywordGroups).forEach(papers => {
                    currentResults = currentResults.concat(papers);
                });
            });
            
            // キーワードで絞り込まれた論文数をカウント
            let filteredCount = currentResults.length;
            document.querySelector('.results-count').textContent = `${filteredCount}件の論文が見つかりました`;
        } else if (data.papers && Object.keys(data.papers).length > 0) {
            // バックエンドから返された論文をそのまま表示
            const allPapers = [];
            Object.entries(data.papers).forEach(([keyword, paperList]) => {
                paperList.forEach(paper => {
                    paper.matched_keyword = keyword;
                    allPapers.push(paper);
                });
            });
            
            // currentResultsを更新
            currentResults = allPapers;
            
            displayResults(allPapers, null, enableJapaneseSummary);
            document.querySelector('.results-count').textContent = `${allPapers.length}件の論文が見つかりました`;
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