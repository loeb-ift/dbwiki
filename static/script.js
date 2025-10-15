// Global State
let activeDatasetId = null;
let activeTable = 'global';
let fullDdlMap = {};
let tableNames = [];
let currentQaData = [];
let current_page = 1;
const items_per_page = 10;
let total_pages = 1;
let selectedQaIds = new Set();

// --- Utility Functions ---
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// --- API Wrapper ---
async function apiFetch(url, options = {}) {
    try {
        options.headers = options.headers || {};
        if (!(options.body instanceof FormData) && !options.headers['Content-Type'] && options.body) {
            options.headers['Content-Type'] = 'application/json';
        }
        if (activeDatasetId !== null && activeDatasetId !== undefined) {
            options.headers['Dataset-Id'] = String(activeDatasetId);
        }
        
        const response = await fetch(url, options);
        if (!response.ok) {
            const errorText = await response.text();
            try {
                const errorJson = JSON.parse(errorText);
                throw new Error(errorJson.message || `HTTP Error ${response.status}`);
            } catch (e) {
                throw new Error(errorText || `HTTP Error ${response.status}`);
            }
        }
        return await response.json();
    } catch (error) {
        console.error(`API Fetch Error (${url}):`, error);
        alert(`API 呼叫失敗: ${error.message}`);
        throw error;
    }
}

// --- Core Functions ---
async function loadDatasets() {
    try {
        const result = await apiFetch('/api/datasets');
        const selector = document.getElementById('dataset-selector');
        if (!selector) return;

        selector.innerHTML = '<option value="">請選擇一個資料集...</option>';
        if (result.datasets && Array.isArray(result.datasets)) {
            result.datasets.forEach(ds => {
                const option = new Option(`${ds.name || ds.dataset_name} (${new Date(ds.created_at).toLocaleDateString()})`, ds.id);
                selector.add(option);
            });
        }
        
        selector.onchange = function() {
            const editBtn = document.getElementById('edit-dataset-btn');
            const deleteBtn = document.getElementById('delete-dataset-btn');
            if (editBtn) editBtn.disabled = !this.value;
            if (deleteBtn) deleteBtn.disabled = !this.value;
            activateDataset(this.value);
        };
    } catch (error) {
        console.error('加載資料集失敗:', error);
    }
}

async function activateDataset(datasetId) {
    const trainingSection = document.getElementById('training-section');
    const askSection = document.getElementById('ask-section');
    const promptsSection = document.getElementById('prompts-section');

    if (trainingSection) trainingSection.style.display = 'none';
    if (askSection) askSection.style.display = 'none';
    if (promptsSection) promptsSection.style.display = 'none';

    activeDatasetId = null;
    fullDdlMap = {};
    tableNames = [];
    currentQaData = [];
    current_page = 1;
    total_pages = 1;
    activeTable = 'global';
    selectedQaIds = new Set();
    
    if (!datasetId) {
        return;
    }
    
    try {
        const result = await apiFetch('/api/datasets/activate', {
            method: 'POST',
            body: JSON.stringify({ dataset_id: datasetId })
        });
        
        activeDatasetId = datasetId;
        tableNames = result.table_names || [];
        fullDdlMap = (result.ddl || []).reduce((map, ddl) => {
            const match = ddl.match(/CREATE\s+TABLE\s+["'\\]?(\w+)["'\\]?/i);
            if (match) map[match[1]] = ddl;
            return map;
        }, {});
        
        if (trainingSection) trainingSection.style.display = 'block';
        if (promptsSection) promptsSection.style.display = 'block';
        if (result.is_trained && askSection) {
            askSection.style.display = 'block';
        }
        
        await loadPrompts();
        populateTableSelector();
        await loadTrainingDataForTable('global');
        
        if (result.message) {
            console.log('資料集激活成功:', result.message);
        }
    } catch (error) {
        console.error('激活資料集失敗:', error);
        alert(`激活資料集失敗: ${error.message}`);
    }
}

function populateTableSelector() {
    const selector = document.getElementById('table-selector');
    if (!selector) return;

    selector.innerHTML = '';
    const globalOption = document.createElement('option');
    globalOption.value = 'global';
    globalOption.textContent = '全局/跨資料表';
    selector.appendChild(globalOption);
    
    if (Array.isArray(tableNames)) {
        tableNames.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            selector.appendChild(option);
        });
    }
    
    selector.value = 'global';
    activeTable = 'global';
}

async function loadTrainingDataForTable(tableName, page = 1) {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }
    if (!tableName) {
        alert('請選擇一個有效的資料表。');
        return;
    }
    
    activeTable = tableName;
    current_page = page;
    
    try {
        const ddlInput = document.getElementById('ddl-input');
        if (ddlInput) {
            if (tableName === 'global') {
                ddlInput.value = Object.values(fullDdlMap).join('\n\n');
            } else {
                ddlInput.value = fullDdlMap[tableName] || `/* 找不到資料表 "${tableName}" 的 DDL。 */`;
            }
        }
        
        const data = await apiFetch(`/api/training_data?table_name=${encodeURIComponent(tableName)}&page=${page}`);
        
        const docInput = document.getElementById('doc-input');
        if (docInput) docInput.value = data.documentation || '';
        
        currentQaData = Array.isArray(data.qa_pairs) ? data.qa_pairs : [];
        total_pages = data.pagination ? (data.pagination.total_pages || 1) : 1;
        
        renderQaTable();
        renderPaginationControls(data.pagination || { current_page: page, total_pages: total_pages });
        
        const docOutputSection = document.getElementById('documentation-output-section');
        const docOutput = document.getElementById('documentation-output');
        const serialOutput = document.getElementById('serial-number-analysis-output');

        if (tableName === 'global' && (data.dataset_analysis || data.serial_number_analysis)) {
            if (docOutput) docOutput.innerHTML = data.dataset_analysis ? marked.parse(data.dataset_analysis) : '<i>尚無結構分析。</i>';
            if (serialOutput) serialOutput.innerHTML = data.serial_number_analysis ? marked.parse(data.serial_number_analysis) : '<i>尚無流水號分析。</i>';
            if (docOutputSection) docOutputSection.style.display = 'block';
        } else if (tableName === 'global' && docOutputSection) {
            docOutputSection.style.display = 'none';
        }
    } catch (error) {
        console.error(`加載訓練數據失敗 (${tableName}):`, error);
        alert(`加載訓練數據失敗: ${error.message}`);
    }
}

function renderPaginationControls(pagination) {
    const controlsContainer = document.getElementById('qa-pagination-controls');
    if (!controlsContainer) return;
    controlsContainer.innerHTML = '';

    const batchOperationsDiv = document.createElement('div');
    batchOperationsDiv.className = 'batch-operations';
    
    const selectAllButton = document.createElement('button');
    selectAllButton.textContent = '全選';
    selectAllButton.id = 'select-all-btn';
    selectAllButton.onclick = selectAllQaRows;
    batchOperationsDiv.appendChild(selectAllButton);
    
    const batchDeleteButton = document.createElement('button');
    batchDeleteButton.textContent = '批次刪除';
    batchDeleteButton.id = 'batch-delete-button';
    batchDeleteButton.disabled = selectedQaIds.size === 0;
    batchDeleteButton.onclick = batchDeleteQaRows;
    batchOperationsDiv.appendChild(batchDeleteButton);
    
    controlsContainer.appendChild(batchOperationsDiv);

    if (!pagination || pagination.total_pages <= 1) return;

    const { current_page, total_pages } = pagination;
    const paginationNav = document.createElement('nav');
    
    const prevButton = document.createElement('button');
    prevButton.textContent = '« 上一頁';
    prevButton.disabled = current_page === 1;
    prevButton.onclick = () => loadTrainingDataForTable(activeTable, current_page - 1);
    paginationNav.appendChild(prevButton);

    const pageInfo = document.createElement('span');
    pageInfo.textContent = ` 第 ${current_page} / ${total_pages} 頁 `;
    pageInfo.className = 'page-info';
    paginationNav.appendChild(pageInfo);

    const nextButton = document.createElement('button');
    nextButton.textContent = '下一頁 »';
    nextButton.disabled = current_page === total_pages;
    nextButton.onclick = () => loadTrainingDataForTable(activeTable, current_page + 1);
    paginationNav.appendChild(nextButton);
    
    controlsContainer.appendChild(paginationNav);
}

async function saveDocumentation() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }
    
    try {
        const docInput = document.getElementById('doc-input');
        if (!docInput) return;
        const docContent = docInput.value;
        const result = await apiFetch('/api/save_documentation', {
            method: 'POST',
            body: JSON.stringify({ 
                documentation: docContent, 
                table_name: activeTable 
            })
        });
        alert(result.message || '儲存完成。');
    } catch (error) {
        console.error('儲存文檔失敗:', error);
    }
}

function renderQaTable() {
    const tableBody = document.getElementById('qa-table-body');
    if (!tableBody) return;
    tableBody.innerHTML = '';
    
    if (!Array.isArray(currentQaData) || currentQaData.length === 0) {
        const row = tableBody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 4;
        cell.textContent = '沒有可用的問答配對。';
        cell.style.textAlign = 'center';
        return;
    }
    
    currentQaData.forEach((item) => {
        const row = tableBody.insertRow();
        row.dataset.id = item.id || '';
        
        const checkboxCell = row.insertCell();
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'qa-checkbox';
        checkbox.checked = selectedQaIds.has(item.id);
        checkbox.onchange = function() {
            if (this.checked) {
                selectedQaIds.add(item.id);
            } else {
                selectedQaIds.delete(item.id);
            }
            updateBatchDeleteButton();
        };
        checkboxCell.appendChild(checkbox);
        
        const questionCell = row.insertCell();
        const questionTextarea = document.createElement('textarea');
        questionTextarea.value = item.question || '';
        questionCell.appendChild(questionTextarea);
        
        const sqlCell = row.insertCell();
        const sqlPre = document.createElement('pre');
        sqlPre.contentEditable = 'true';
        sqlPre.textContent = item.sql || '';
        sqlCell.appendChild(sqlPre);
        
        const actionCell = row.insertCell();
        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = '刪除';
        deleteBtn.onclick = () => deleteSingleQaRow(item.id, row);
        actionCell.appendChild(deleteBtn);
    });
    
    updateBatchDeleteButton();
}

async function deleteSingleQaRow(qaId, rowElement) {
    if (!qaId) {
        rowElement.remove();
        return;
    }
    if (confirm('確定要刪除此問答配對嗎？')) {
        try {
            await apiFetch('/api/delete_qa_pair', {
                method: 'POST',
                body: JSON.stringify({ id: qaId })
            });
            rowElement.remove();
            selectedQaIds.delete(qaId);
            updateBatchDeleteButton();
            // Optionally, reload data to ensure consistency
            await loadTrainingDataForTable(activeTable, current_page);
        } catch (error) {
            console.error('刪除問答配對失敗:', error);
        }
    }
}

function addQaPairRow(qa_pair = {}) {
    const { id = '', question = '', sql = '' } = qa_pair;
    const tableBody = document.getElementById('qa-table-body');
    if (!tableBody) return;

    const row = tableBody.insertRow(0);
    row.dataset.id = id;
    
    const checkboxCell = row.insertCell();
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'qa-checkbox';
    checkbox.disabled = !id;
    if (id) {
        checkbox.onchange = function() {
            if (this.checked) selectedQaIds.add(id);
            else selectedQaIds.delete(id);
            updateBatchDeleteButton();
        };
    }
    checkboxCell.appendChild(checkbox);

    const questionCell = row.insertCell();
    const questionTextarea = document.createElement('textarea');
    questionTextarea.value = question;
    if (!question) questionTextarea.placeholder = '輸入新問題...';
    questionCell.appendChild(questionTextarea);

    const sqlCell = row.insertCell();
    const sqlPre = document.createElement('pre');
    sqlPre.contentEditable = 'true';
    sqlPre.textContent = sql;
    if (!sql) sqlPre.placeholder = '輸入對應的 SQL...';
    sqlCell.appendChild(sqlPre);

    const actionCell = row.insertCell();
    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = '刪除';
    deleteBtn.onclick = () => deleteSingleQaRow(id, row);
    actionCell.appendChild(deleteBtn);

    if (!question && !sql) {
        questionTextarea.focus();
    }
}

async function saveAllQaModifications() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }
    
    const tableBody = document.getElementById('qa-table-body');
    if (!tableBody) return;

    let successCount = 0, errorCount = 0;
    const promises = [];

    for (const row of tableBody.rows) {
        const id = row.dataset.id;
        const question = row.cells[1]?.querySelector('textarea')?.value.trim() || '';
        const sql = row.cells[2]?.querySelector('pre')?.innerText.trim() || '';
        
        if (!question || !sql) continue;
        
        const promise = apiFetch('/api/add_qa_question', {
            method: 'POST',
            body: JSON.stringify({ 
                id: id || null, // Send id for update
                question: question, 
                sql: sql, 
                table_name: activeTable 
            })
        }).then(() => successCount++).catch(e => {
            console.error(`保存QA失败 (${question.substring(0, 20)}...):`, e);
            errorCount++;
        });
        promises.push(promise);
    }
    
    try {
        await Promise.all(promises);
        alert(`儲存完成: ${successCount} 成功, ${errorCount} 失敗。`);
        await loadTrainingDataForTable(activeTable, current_page);
    } catch (error) {
        console.error('保存QA修改時發生未知錯誤:', error);
    }
}

// --- Batch Operations Functions --- 
function selectAllQaRows() {
    const tableBody = document.getElementById('qa-table-body');
    if (!tableBody) return;

    const checkboxes = tableBody.querySelectorAll('input.qa-checkbox:not(:disabled)');
    const isAllSelected = checkboxes.length > 0 && Array.from(checkboxes).every(cb => cb.checked);
    
    checkboxes.forEach(checkbox => {
        const row = checkbox.closest('tr');
        const id = row.dataset.id;
        if (!id) return;

        checkbox.checked = !isAllSelected;
        if (checkbox.checked) {
            selectedQaIds.add(id);
        } else {
            selectedQaIds.delete(id);
        }
    });
    
    updateBatchDeleteButton();
}

function updateBatchDeleteButton() {
    const batchDeleteButton = document.getElementById('batch-delete-button');
    if (batchDeleteButton) {
        batchDeleteButton.disabled = selectedQaIds.size === 0;
    }
}

async function batchDeleteQaRows() {
    if (selectedQaIds.size === 0) {
        alert('請先選擇要刪除的項目。');
        return;
    }
    
    if (confirm(`確定要刪除選中的 ${selectedQaIds.size} 個問答配對嗎？`)) {
        try {
            await apiFetch('/api/batch_delete_qa', {
                method: 'POST',
                body: JSON.stringify({ ids: Array.from(selectedQaIds) })
            });
            
            selectedQaIds.clear();
            alert('批次刪除成功。');
            
            // Reload data for the current page
            await loadTrainingDataForTable(activeTable, current_page);
        } catch (error) {
            console.error('批次刪除失敗:', error);
        }
    }
}

function uploadQaFile() {
    const fileInput = document.getElementById('qa-file-input');
    const file = fileInput.files[0];
    if (!file) {
        alert('請先選擇一個 .sql 檔案。');
        return;
    }

    const progressContainer = document.getElementById('qa-upload-progress-container');
    const progressBar = document.getElementById('qa-upload-progress-bar');
    const percentageText = document.getElementById('qa-upload-percentage');
    const logContainer = document.getElementById('qa-gen-log-container');
    const logOutput = document.getElementById('qa-gen-log');
    const trainingLogContainer = document.getElementById('training-log-container');

    if (progressContainer) progressContainer.style.display = 'block';
    if (progressBar) progressBar.style.width = '0%';
    if (percentageText) percentageText.textContent = '0%';
    if (logContainer) logContainer.style.display = 'block';
    if (trainingLogContainer) trainingLogContainer.style.display = 'none'; // Hide other log
    if (logOutput) logOutput.textContent = '開始上傳並生成問答配對...\n';

    const formData = new FormData();
    formData.append('sql_file', file);

    fetch('/api/generate_qa_from_sql', {
        method: 'POST',
        headers: {
            'Dataset-Id': activeDatasetId
        },
        body: formData
    })
    .then(response => {
        if (!response.body) {
            throw new Error('伺服器回應無效。');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        function push() {
            reader.read().then(({ done, value }) => {
                if (done) {
                    if (logOutput) logOutput.textContent += '所有問答已生成完畢。\n';
                    loadTrainingDataForTable(activeTable, 1); // Refresh the table
                    return;
                }
                const chunk = decoder.decode(value, { stream: true });
                chunk.split('\n\n').forEach(event => {
                    if (!event.startsWith('data: ')) return;
                    try {
                        const data = JSON.parse(event.substring(6));
                        if (logOutput) logOutput.textContent += `${data.message}\n`;
                        if (progressBar && data.percentage) {
                            progressBar.style.width = `${data.percentage}%`;
                        }
                        if (percentageText && data.percentage) {
                            percentageText.textContent = `${data.percentage}%`;
                        }
                        if (data.status === 'progress' && data.qa_pair) {
                            addQaPairRow(data.qa_pair);
                        }
                    } catch (e) {
                        console.warn('解析生成日誌失敗:', e, 'Chunk:', event);
                    }
                });
                push();
            });
        }
        push();
    })
    .catch(error => {
        console.error('上傳 SQL 檔案失敗:', error);
        if (logOutput) logOutput.textContent += `錯誤: ${error.message}\n`;
        alert(`上傳失敗: ${error.message}`);
    });
}

// This function is now triggered by uploadQaFile, so we can keep its logic
// but it's not directly called by an event anymore.
function handleQaFileUpload(event) {
    uploadQaFile();
}

// --- Training Functions ---
async function trainModel() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }

    const trainBtn = document.getElementById('train-model-btn');
    const logContainer = document.getElementById('training-log-container');
    const logOutput = document.getElementById('training-log');
    const progressBar = document.getElementById('training-progress-bar');
    const progressText = document.getElementById('training-percentage');
    const qaLogContainer = document.getElementById('qa-gen-log-container');

    if (!trainBtn || !logContainer || !logOutput || !progressBar || !progressText) return;

    trainBtn.disabled = true;
    trainBtn.textContent = '訓練中...';
    logContainer.style.display = 'block';
    if (qaLogContainer) qaLogContainer.style.display = 'none'; // Hide other log
    logOutput.textContent = '';
    progressBar.style.width = '0%';
    progressText.textContent = '0%';

    const addLog = (message) => {
        logOutput.textContent += message + '\n';
        logOutput.scrollTop = logOutput.scrollHeight;
    };

    const updateProgress = throttle((percentage, message) => {
        const roundedPercentage = Math.round(percentage);
        progressBar.style.width = `${roundedPercentage}%`;
        progressText.textContent = `${roundedPercentage}%`;
        if (message) addLog(`[${roundedPercentage}%] ${message}`);
    }, 250);

    try {
        // Step 1: Clear old training data
        addLog('正在清除舊的訓練資料...');
        const clearResponse = await fetch('/api/clear_training_data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Dataset-Id': activeDatasetId
            }
        });

        if (!clearResponse.ok) {
            const errorData = await clearResponse.json();
            throw new Error(errorData.message || '清除舊資料失敗');
        }
        addLog('舊資料清除完畢，開始新的訓練...');

        // Step 2: Start new training and process the stream
        const trainResponse = await fetch('/api/train', {
            method: 'POST',
            headers: { 'Dataset-Id': activeDatasetId }
        });

        if (!trainResponse.ok) {
             const errorData = await trainResponse.json();
             throw new Error(errorData.message || '啟動訓練失敗');
        }
        if (!trainResponse.body) throw new Error('訓練響應無效');

        const reader = trainResponse.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                updateProgress(100, '訓練流程已完成。');
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            chunk.split('\n\n').forEach(event => {
                if (event.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(event.substring(6));
                        if (data.type === 'error') {
                            throw new Error(data.message);
                        }
                        if (data.percentage !== undefined && data.message) {
                            updateProgress(data.percentage, data.message);
                        }
                    } catch (jsonError) {
                        // This might catch the error thrown above, so log it and rethrow
                        console.warn('處理訓練日誌時發生錯誤:', jsonError, 'Chunk:', event);
                        // Don't rethrow here as it might be a simple parsing error of a chunk
                    }
                }
            });
        }

        alert('模型訓練成功！');
        const askSection = document.getElementById('ask-section');
        if (askSection) askSection.style.display = 'block';

    } catch (error) {
        const errorMessage = '訓練失敗：' + error.message;
        alert(errorMessage);
        addLog(`❌ ${errorMessage}`);
    } finally {
        trainBtn.disabled = false;
        trainBtn.textContent = '重新訓練整個模型';
    }
}

// --- Modal Functions ---
function openNewDatasetModal() {
    const modal = document.getElementById('new-dataset-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    const form = document.getElementById('new-dataset-form');
    if (form) form.reset();
}

function closeNewDatasetModal() {
    const modal = document.getElementById('new-dataset-modal');
    if (modal) modal.style.display = 'none';
}

async function handleNewDatasetSubmit(event) {
    event.preventDefault();
    
    const form = document.getElementById('new-dataset-form');
    if (!form) return;
    const formData = new FormData(form);
    const submitBtn = form.querySelector('button[type="submit"]');
    
    if (!formData.get('dataset_name')?.trim()) {
        alert('請輸入資料集名稱');
        return;
    }
    if (document.getElementById('new-dataset-files').files.length === 0) {
        alert('請至少選擇一個 CSV 檔案');
        return;
    }
    
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = '上傳中...';
    }
    
    try {
        await apiFetch('/api/datasets', { method: 'POST', body: formData });
        alert('資料集創建成功！');
        closeNewDatasetModal();
        await loadDatasets();
    } catch (error) {
        console.error('創建新資料集失敗:', error);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '上傳並創建';
        }
    }
}

function openEditDatasetModal() {
    const modal = document.getElementById('edit-dataset-modal');
    const selector = document.getElementById('dataset-selector');
    if (!modal || !selector || !selector.value) return;

    const selectedOption = selector.options[selector.selectedIndex];
    const datasetName = selectedOption.text.split(' (')[0];
    
    const idField = document.getElementById('edit-dataset-id');
    const nameField = document.getElementById('edit-dataset-name');

    if (idField) idField.value = selector.value;
    if (nameField) nameField.value = datasetName;
    
    modal.style.display = 'flex';
}

function closeEditDatasetModal() {
    const modal = document.getElementById('edit-dataset-modal');
if (modal) modal.style.display = 'none';
}

async function handleEditDatasetSubmit(event) {
    event.preventDefault();
    const form = document.getElementById('edit-dataset-form');
    if (!form) return;

    const datasetId = document.getElementById('edit-dataset-id')?.value;
    const datasetName = document.getElementById('edit-dataset-name')?.value.trim();
    const submitBtn = form.querySelector('button[type="submit"]');

    if (!datasetName) {
        alert('請輸入資料集名稱');
        return;
    }
    if (!datasetId) return;

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = '儲存中...';
    }

    try {
        await apiFetch(`/api/datasets`, {
            method: 'PUT',
            body: JSON.stringify({ dataset_id: datasetId, new_name: datasetName })
        });
        alert('資料集更新成功！');
        closeEditDatasetModal();
        await loadDatasets();
        const selector = document.getElementById('dataset-selector');
        if (selector) {
            selector.value = datasetId;
            selector.dispatchEvent(new Event('change'));
        }
    } catch (error) {
        console.error('更新資料集失敗:', error);
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '儲存修改';
        }
    }
}

async function deleteDataset() {
    const selector = document.getElementById('dataset-selector');
    if (!selector || !selector.value) return;

    const datasetId = selector.value;
    const datasetName = selector.options[selector.selectedIndex].text.split(' (')[0];
    
    if (!confirm(`確定要刪除資料集 "${datasetName}" 嗎？此操作無法撤銷！`)) return;
    
    try {
        await apiFetch(`/api/datasets`, {
            method: 'DELETE',
            body: JSON.stringify({ dataset_id: datasetId })
        });
        alert('資料集刪除成功！');
        await loadDatasets();
        selector.value = '';
        selector.dispatchEvent(new Event('change'));
    } catch (error) {
        console.error('刪除資料集失敗:', error);
    }
}

// --- Ask and Execute Functions ---
let lastGeneratedSql = '';

async function ask() {
    const questionInput = document.getElementById('question-input');
    if (!questionInput || !questionInput.value.trim()) {
        alert('請輸入問題。');
        return;
    }
    const question = questionInput.value.trim();

    const askBtn = document.getElementById('ask-button');
    const thinkingContainer = document.getElementById('thinking-container');
    const thinkingOutput = document.getElementById('thinking-output');
    const sqlContainer = document.getElementById('sql-container');
    const resultContainer = document.getElementById('result-container');
    const chartContainer = document.getElementById('chart-container');
    const analysisContainer = document.getElementById('analysis-container');
    const followupContainer = document.getElementById('followup-container');
    const statusContainer = document.getElementById('ask-status-container');
    const sqlErrorContainer = document.getElementById('sql-error-container');
 
     // Reset UI
     if (askBtn) {
         askBtn.disabled = true;
         askBtn.textContent = '思考中...';
     }
    if (statusContainer) statusContainer.textContent = '正在初始化請求...';
    if (thinkingContainer) thinkingContainer.style.display = 'none'; // Hide old thinking container
    if (analysisContainer) analysisContainer.style.display = 'block'; // Show new analysis container
    
    const originalQuestionDisplay = document.getElementById('original-question-display');
    if (originalQuestionDisplay) {
        originalQuestionDisplay.textContent = question;
    }
    const analysisOutput = document.getElementById('analysis-output');
    if (analysisOutput) {
        analysisOutput.innerHTML = '';
    }
 
     // Hide all result containers initially
     [resultContainer, chartContainer, analysisContainer, followupContainer, sqlErrorContainer].forEach(el => {
         if (el) {
             el.innerHTML = '';
             el.style.display = 'none';
         }
     });
    if(sqlContainer) {
        sqlContainer.style.display = 'none';
        sqlContainer.innerHTML = '<pre id="sql-output"></pre>';
    }
    lastGeneratedSql = '';

    try {
        const response = await fetch('/api/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Dataset-Id': activeDatasetId
            },
            body: JSON.stringify({ question: question })
        });

        if (!response.body) throw new Error('The response from the server is invalid.');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            chunk.split('\n\n').forEach(event => {
                if (!event.startsWith('data: ')) return;
                try {
                    const data = JSON.parse(event.substring(6));
                    handleStreamedData(data);
                } catch (e) {
                    console.warn('Failed to parse stream data chunk:', e);
                }
            });
        }
    } catch (error) {
        console.error('An error occurred during the ask process:', error);
        if (thinkingOutput) thinkingOutput.innerHTML += `<div style="color: red;">❌ 錯誤: ${error.message}</div>`;
        alert(`提問失敗: ${error.message}`);
    } finally {
        if (askBtn) {
            askBtn.disabled = false;
            askBtn.textContent = '提出問題';
        }
       if (statusContainer) statusContainer.textContent = '流程處理完成。';
       
       const chartContainer = document.getElementById('chart-container');
       if (chartContainer && chartContainer.style.display === 'none') {
           const chartOutput = document.getElementById('chart-output');
           if(chartOutput) {
               chartOutput.innerHTML = '<p><i>沒有可用的圖表數據。</i></p>';
           }
           chartContainer.style.display = 'block';
       }
   }
}

function handleStreamedData(data) {
    const type = data.type;
    const content = data.content;
    const thinkingOutput = document.getElementById('thinking-output');

    if (type === 'retrieved_context') {
        if (!thinkingOutput) return;
        let html = `<h4>檢索到相關內容 (${data.subtype}):</h4>`;
        if (data.subtype === 'qa' && Array.isArray(content)) {
            html += '<ul>';
            content.forEach(item => {
                html += `<li><b>Q:</b> ${item.question}<br><b>SQL:</b> <pre>${item.sql}</pre></li>`;
            });
            html += '</ul>';
        } else if (data.subtype === 'ddl' && Array.isArray(content)) {
            html += `<pre>${content.join('\n\n')}</pre>`;
        } else if (data.subtype === 'documentation' && Array.isArray(content)) {
            html += `<div>${content.join('<hr>')}</div>`;
        }
        thinkingOutput.innerHTML += html;
    } else if (type === 'info') {
        const statusContainer = document.getElementById('ask-status-container');
        if (statusContainer) statusContainer.textContent = content;
        if (thinkingOutput) thinkingOutput.innerHTML += `<p><i>${content}</i></p>`;
    } else if (type === 'sql_chunk') {
        const sqlContainer = document.getElementById('sql-container');
        const sqlOutput = document.getElementById('sql-output');
        if (sqlContainer && sqlOutput) {
            if (!sqlContainer.querySelector('h3')) {
                const title = document.createElement('h3');
                title.textContent = '思考可能的SQL語法';
                sqlContainer.prepend(title);
            }
            sqlContainer.style.display = 'block';
            sqlOutput.textContent += content;
        }
    } else if (type === 'sql') {
        const sqlContainer = document.getElementById('sql-container');
        const sqlOutput = document.getElementById('sql-output');
        if (sqlContainer && sqlOutput) {
            if (!sqlContainer.querySelector('h3')) {
                const title = document.createElement('h3');
                title.textContent = '思考可能的SQL語法';
                sqlContainer.prepend(title);
            }
            lastGeneratedSql = content;
            sqlOutput.textContent = content; // Set the final SQL
            sqlContainer.style.display = 'block';
        }
    } else if (type === 'df') {
        const resultContainer = document.getElementById('result-container');
        if (resultContainer) {
            try {
                const df = JSON.parse(content);
                renderResultTable(df.data, df.columns);
                resultContainer.style.display = 'block';
            } catch (e) {
                resultContainer.textContent = "無法解析查詢結果。";
                resultContainer.style.display = 'block';
            }
        }
    } else if (type === 'chart') {
        const chartContainer = document.getElementById('chart-container');
        const chartOutput = document.getElementById('chart-output');
        if (chartContainer && chartOutput) {
            if (content) {
                try {
                    const plotly_json = (new Function(`return ${content}`))();
                    Plotly.newPlot(chartOutput, plotly_json.data, plotly_json.layout);
                } catch (e) {
                    console.error("無法渲染 Plotly 圖表:", e);
                    chartOutput.innerHTML = '<p><i>渲染圖表時發生錯誤。</i></p>';
                }
            } else {
                chartOutput.innerHTML = '<p><i>沒有可用的圖表數據。</i></p>';
            }
            chartContainer.style.display = 'block';
        }
    } else if (type === 'explanation') {
        const analysisContainer = document.getElementById('analysis-container');
        const analysisOutput = document.getElementById('analysis-output');
        if (analysisContainer && analysisOutput && window.marked) {
            analysisOutput.innerHTML = marked.parse(content);
            analysisContainer.style.display = 'block';
        }
    } else if (type === 'followup_questions' && content && content.length > 0) {
        const followupContainer = document.getElementById('followup-container');
        const followupOutput = document.getElementById('followup-output');
        if (followupContainer && followupOutput) {
            followupOutput.innerHTML = '';
            content.forEach(q => {
                const btn = document.createElement('button');
                btn.textContent = q;
                btn.onclick = () => {
                    const questionInput = document.getElementById('question-input');
                    if (questionInput) questionInput.value = q;
                    ask();
                };
                followupOutput.appendChild(btn);
            });
            followupContainer.style.display = 'block';
        }
    } else if (type === 'sql_error') {
        const sqlContainer = document.getElementById('sql-container');
        const sqlOutput = document.getElementById('sql-output');
        if (sqlContainer && sqlOutput && data.sql) {
            sqlOutput.textContent = data.sql;
            sqlContainer.style.display = 'block';
        }

        const errorContainer = document.getElementById('sql-error-container');
        const errorSqlOutput = document.getElementById('sql-error-output');
        const errorDetailsOutput = document.getElementById('sql-error-details');
        if (errorContainer && errorSqlOutput && errorDetailsOutput) {
            errorSqlOutput.textContent = data.sql;
            errorDetailsOutput.textContent = data.error;
            errorContainer.style.display = 'block';
        }
    } else if (type === 'error') {
        throw new Error(data.message);
    }
}

function renderResultTable(data, columns) {
    const container = document.getElementById('result-output');
    if (!container) return;
    container.innerHTML = '';
    if (!data || data.length === 0) {
        container.textContent = '（查詢結果為空）';
        return;
    }

    const table = document.createElement('table');
    const thead = table.createTHead();
    const tbody = table.createTBody();
    
    const headerRow = thead.insertRow();
    columns.forEach(key => {
        const th = document.createElement('th');
        th.textContent = key;
        headerRow.appendChild(th);
    });

    data.forEach(rowData => {
        const row = tbody.insertRow();
        rowData.forEach(value => {
            const cell = row.insertCell();
            cell.textContent = value;
        });
    });
    container.appendChild(table);
}

// --- Prompt Management Functions ---
async function loadPrompts() {
    if (!activeDatasetId) return;
    try {
        const response = await apiFetch('/api/prompts');
        renderPromptsTable(response.prompts || []);
    } catch (error) {
        console.error('加载提示词失败:', error);
    }
}

function renderPromptsTable(prompts) {
    const tableBody = document.getElementById('prompts-table-body');
    if (!tableBody) return;
    tableBody.innerHTML = '';
    
    if (!Array.isArray(prompts) || prompts.length === 0) {
        const row = tableBody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 4;
        cell.textContent = '沒有可用的提示詞。';
        cell.style.textAlign = 'center';
        return;
    }

    prompts.forEach((prompt) => {
        const row = tableBody.insertRow();
        row.dataset.id = prompt.id;
        
        row.insertCell().textContent = prompt.prompt_name;
        row.insertCell().textContent = prompt.prompt_description || '';
        row.insertCell().textContent = prompt.is_global ? '是' : '否';

        const actionCell = row.insertCell();
        const editBtn = document.createElement('button');
        editBtn.textContent = '編輯';
        editBtn.onclick = () => editPrompt(prompt);
        actionCell.appendChild(editBtn);
        
        const resetBtn = document.createElement('button');
        resetBtn.textContent = '重置默認';
        resetBtn.onclick = () => resetPromptToDefault(prompt.id, prompt.prompt_name);
        actionCell.appendChild(resetBtn);
        
        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = '刪除';
        deleteBtn.onclick = () => deletePrompt(prompt.id, prompt.prompt_name);
        actionCell.appendChild(deleteBtn);
    });
}

function openPromptModal() {
    const modal = document.getElementById('prompt-modal');
    if (!modal) return;
    const modalTitle = document.getElementById('prompt-modal-title');
    const form = document.getElementById('prompt-form');
    
    if (modalTitle) modalTitle.textContent = '新增提示詞';
    if (form) form.reset();
    const promptIdInput = document.getElementById('prompt-id');
    if (promptIdInput) promptIdInput.value = '';
    
    modal.style.display = 'flex';
}

function closePromptModal() {
    const modal = document.getElementById('prompt-modal');
    if (modal) modal.style.display = 'none';
}

function editPrompt(prompt) {
    const modal = document.getElementById('prompt-modal');
    if (!modal) return;
    
    const modalTitle = document.getElementById('prompt-modal-title');
    if (modalTitle) modalTitle.textContent = '編輯提示詞';
    
    const idInput = document.getElementById('prompt-id');
    const nameInput = document.getElementById('prompt-name');
    const contentInput = document.getElementById('prompt-content');
    const descInput = document.getElementById('prompt-description');

    if (idInput) idInput.value = prompt.id;
    if (nameInput) nameInput.value = prompt.prompt_name;
    if (contentInput) contentInput.value = prompt.prompt_content;
    if (descInput) descInput.value = prompt.prompt_description || '';
    
    modal.style.display = 'flex';
}

async function savePrompt(event) {
    event.preventDefault();
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    const id = document.getElementById('prompt-id')?.value;
    const name = document.getElementById('prompt-name')?.value.trim();
    const content = document.getElementById('prompt-content')?.value;
    const description = document.getElementById('prompt-description')?.value;

    if (!name || !content) {
        alert('提示詞名稱和內容為必填項。');
        return;
    }
    
    try {
        const response = await apiFetch('/api/save_prompt', {
            method: 'POST',
            body: JSON.stringify({
                id: id || null,
                prompt_name: name,
                prompt_content: content,
                prompt_description: description
            })
        });
        
        alert(response.message || '提示詞儲存成功');
        closePromptModal();
        await loadPrompts();
    } catch (error) {
        console.error('儲存提示詞失敗:', error);
    }
}

async function deletePrompt(promptId, promptName) {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    if (!confirm(`確定要刪除提示詞 "${promptName}" 嗎？`)) return;
    
    try {
        const response = await apiFetch('/api/delete_prompt', {
            method: 'POST',
            body: JSON.stringify({ id: promptId })
        });
        alert(response.message || '提示詞刪除成功');
        await loadPrompts();
    } catch (error) {
        console.error('刪除提示詞失敗:', error);
    }
}

async function resetPromptToDefault(promptId, promptName) {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    if (!confirm(`確定要將提示詞 "${promptName}" 重置為默認值嗎？`)) return;
    
    try {
        const response = await apiFetch(`/api/reset_prompt_to_default/${encodeURIComponent(promptName)}`, {
            method: 'POST',
            body: JSON.stringify({ id: promptId })
        });
        alert(response.message || '提示詞已重置為默認值');
        await loadPrompts();
    } catch (error) {
        console.error('重置提示詞失敗:', error);
    }
}

// --- Event Listeners and Initialization ---
function setupEventListeners() {
    document.getElementById('new-dataset-btn')?.addEventListener('click', openNewDatasetModal);
    document.getElementById('edit-dataset-btn')?.addEventListener('click', openEditDatasetModal);
    document.getElementById('delete-dataset-btn')?.addEventListener('click', deleteDataset);
    document.getElementById('new-dataset-form')?.addEventListener('submit', handleNewDatasetSubmit);
    document.getElementById('edit-dataset-form')?.addEventListener('submit', handleEditDatasetSubmit);
    document.querySelector('#new-dataset-modal .close-btn')?.addEventListener('click', closeNewDatasetModal);
    document.querySelector('#edit-dataset-modal .close-btn')?.addEventListener('click', closeEditDatasetModal);

    document.getElementById('table-selector')?.addEventListener('change', (e) => {
        if (activeDatasetId) loadTrainingDataForTable(e.target.value);
    });
    document.getElementById('save-doc-btn')?.addEventListener('click', saveDocumentation);
    document.getElementById('add-qa-btn')?.addEventListener('click', () => addQaPairRow());
    document.getElementById('save-qa-btn')?.addEventListener('click', saveAllQaModifications);
    document.getElementById('train-model-btn')?.addEventListener('click', trainModel);
    
    document.getElementById('add-prompt-btn')?.addEventListener('click', openPromptModal);
    document.getElementById('prompt-form')?.addEventListener('submit', savePrompt);
    document.querySelector('#prompt-modal .close-btn')?.addEventListener('click', closePromptModal);

    document.getElementById('ask-button')?.addEventListener('click', ask);
    document.getElementById('question-input')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            ask();
        }
    });

    window.addEventListener('click', (event) => {
        if (event.target === document.getElementById('new-dataset-modal')) closeNewDatasetModal();
        if (event.target === document.getElementById('edit-dataset-modal')) closeEditDatasetModal();
        if (event.target === document.getElementById('prompt-modal')) closePromptModal();
    });
}

function init() {
    setupEventListeners();
    loadDatasets();
}

// --- Global Exports ---
async function analyzeSchema() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }

    const docOutput = document.getElementById('documentation-output');
    const serialOutput = document.getElementById('serial-number-analysis-output');
    const analyzeBtn = document.getElementById('analyze-schema-btn');
    const docSection = document.getElementById('documentation-output-section');

    // Clear previous results and show the section
    if(docOutput) docOutput.innerHTML = '<p><i>正在初始化分析...</i></p>';
    if(serialOutput) serialOutput.innerHTML = '';
    if(docSection) docSection.style.display = 'block';
    
    if(analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = '分析中...';
    }

    try {
        const response = await fetch('/api/analyze_schema', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Dataset-Id': activeDatasetId },
            body: JSON.stringify({ streaming: true })
        });

        if (!response.body) throw new Error('The response from the server is invalid.');

        // Clear the initial message
        if(docOutput) docOutput.innerHTML = '';

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const events = chunk.split('\n\n');

            for (const event of events) {
                if (!event.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(event.substring(6));
                    
                    if (data.type === 'info') {
                        const p = document.createElement('p');
                        p.innerHTML = `<i>${data.message}</i>`;
                        if(docOutput) docOutput.appendChild(p);
                    } else if (data.type === 'analysis_result') {
                        if(docOutput && window.marked) docOutput.innerHTML = marked.parse(data.content);
                    } else if (data.type === 'serial_number_analysis_result') {
                        if(serialOutput && window.marked) serialOutput.innerHTML = marked.parse(data.content);
                    } else if (data.type === 'end_of_stream') {
                        if(serialOutput && !serialOutput.innerHTML) {
                            serialOutput.innerHTML = '<p>未找到或無法分析流水號規則。</p>';
                        }
                    } else if (data.type === 'error') {
                        throw new Error(data.message);
                    }
                } catch (e) {
                    console.warn('Failed to parse stream data chunk:', e);
                }
            }
        }
    } catch (error) {
        console.error('分析資料庫結構失敗:', error);
        if(docOutput) docOutput.innerHTML += `<p style="color: red;">分析失敗: ${error.message}</p>`;
    } finally {
        if(analyzeBtn) {
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = '自動分析資料庫結構';
        }
    }
}

// Export functions that are called from HTML onclick attributes
window.analyzeSchema = analyzeSchema;
window.handleNewDatasetSubmit = handleNewDatasetSubmit;
window.handleEditDatasetSubmit = handleEditDatasetSubmit;
window.openNewDatasetModal = openNewDatasetModal;
window.closeNewDatasetModal = closeNewDatasetModal;
window.openEditDatasetModal = openEditDatasetModal;
window.closeEditDatasetModal = closeEditDatasetModal;
window.deleteDataset = deleteDataset;
window.loadTrainingDataForTable = loadTrainingDataForTable;
window.saveDocumentation = saveDocumentation;
window.addQaPairRow = addQaPairRow;
window.saveAllQaModifications = saveAllQaModifications;
window.trainModel = trainModel;
window.ask = ask;
window.openPromptModal = openPromptModal;
window.closePromptModal = closePromptModal;
window.savePrompt = savePrompt;
window.editPrompt = editPrompt;
window.deletePrompt = deletePrompt;
window.resetPromptToDefault = resetPromptToDefault;
window.selectAllQaRows = selectAllQaRows;
window.batchDeleteQaRows = batchDeleteQaRows;
window.uploadQaFile = uploadQaFile;

// --- DOM Ready ---
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
