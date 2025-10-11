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

// --- API Wrapper ---
async function apiFetch(url, options = {}) {
    try {
        // 确保options.headers存在并添加Dataset-Id头
        options.headers = options.headers || {};
        if (!options.headers['Content-Type'] && options.body) {
            options.headers['Content-Type'] = 'application/json';
        }
        // 总是添加Dataset-Id头，即使为null，服务器可以据此判断状态
        options.headers['Dataset-Id'] = activeDatasetId;
        
        const response = await fetch(url, options);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || `HTTP Error ${response.status}`);
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
        selector.innerHTML = '<option value="">請選擇一個資料集...</option>';
        if (result.datasets && Array.isArray(result.datasets)) {
            result.datasets.forEach(ds => {
                const option = new Option(`${ds.name || ds.dataset_name} (${new Date(ds.created_at).toLocaleDateString()})`, ds.id);
                selector.add(option);
            });
        }
        // 监听数据集选择变化，启用/禁用编辑和删除按钮
        selector.onchange = function() {
            const editBtn = document.getElementById('edit-dataset-btn');
            const deleteBtn = document.getElementById('delete-dataset-btn');
            if (this.value) {
                editBtn.disabled = false;
                deleteBtn.disabled = false;
                activateDataset(this.value);
            } else {
                editBtn.disabled = true;
                deleteBtn.disabled = true;
                activateDataset(null);
            }
        };
    } catch (error) {
        console.error('加載資料集失敗:', error);
    }
}

async function activateDataset(datasetId) {
    document.getElementById('training-section').style.display = 'none';
    document.getElementById('ask-section').style.display = 'none';
    document.getElementById('prompts-section').style.display = 'none';
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dataset_id: datasetId })
        });
        
        activeDatasetId = datasetId;
        tableNames = result.table_names || [];
        fullDdlMap = (result.ddl || []).reduce((map, ddl) => {
            const match = ddl.match(/CREATE\s+TABLE\s+["'\\]?(\w+)["'\\]?/i);
            if (match) map[match[1]] = ddl;
            return map;
        }, {});
        
        document.getElementById('training-section').style.display = 'block';
        document.getElementById('prompts-section').style.display = 'block';
        
        if (result.is_trained) {
            document.getElementById('ask-section').style.display = 'block';
        }
        
        // 加载提示词列表
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
    // 首先检查是否有活跃的数据集
    if (!activeDatasetId) {
        console.error('No active dataset selected when trying to load training data');
        alert('請先選擇一個資料集。');
        return;
    }
    
    // 然后检查表名是否有效
    if (!tableName) {
        alert('請選擇一個有效的資料表。');
        return;
    }
    
    activeTable = tableName;
    current_page = page;
    
    try {
        const ddlInput = document.getElementById('ddl-input');
        if (tableName === 'global') {
            ddlInput.value = Object.values(fullDdlMap).join('\n\n');
        } else {
            ddlInput.value = fullDdlMap[tableName] || `/* 找不到資料表 "${tableName}" 的 DDL。 */`;
        }
        
        // 安全检查：在API调用前再次验证activeDatasetId
        if (!activeDatasetId) {
            console.error('Dataset deselected while preparing API request');
            alert('請先選擇一個資料集。');
            return;
        }
        
        const data = await apiFetch(`/api/training_data?table_name=${encodeURIComponent(tableName)}&page=${page}`);
        document.getElementById('doc-input').value = data.documentation || '';
        currentQaData = Array.isArray(data.qa_pairs) ? data.qa_pairs : [];
        
        // 如果API返回分页信息，使用API的分页数据
        if (data.pagination) {
            total_pages = data.pagination.total_pages || 1;
        } else {
            // 否则本地计算分页
            total_pages = Math.ceil(currentQaData.length / items_per_page);
        }
        
        renderQaTable();
        renderPaginationControls(data.pagination || { current_page: page, total_pages: total_pages });
        
        // Load and display dataset analysis if available
        if (tableName === 'global' && data.dataset_analysis) {
            document.getElementById('documentation-output').textContent = data.dataset_analysis;
            document.getElementById('documentation-output-section').style.display = 'block';
        } else if (tableName === 'global') {
            // If no global analysis, hide the section
            document.getElementById('documentation-output-section').style.display = 'none';
        }
    } catch (error) {
        console.error(`加載訓練數據失敗 (${tableName}):`, error);
        alert(`加載訓練數據失敗: ${error.message}`);
    }
}

async function generateDocumentationFromAnalysis() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }

    const docSection = document.getElementById('documentation-output-section');
    const docOutput = document.getElementById('documentation-output');
    
    docSection.style.display = 'block';
    docOutput.textContent = '正在加載資料庫結構分析...';

    try {
        const result = await apiFetch('/api/generate_documentation_from_analysis', { method: 'POST' });

        if (result.status === 'success' && result.documentation) {
            docOutput.textContent = result.documentation;
        } else {
            throw new Error(result.message || '未找到已儲存的分析文件。');
        }
    } catch (error) {
        console.error('加載資料庫分析文件失敗:', error);
        docOutput.textContent = `加載失敗: ${error.message}`;
    }
}

function renderPaginationControls(pagination) {
    const controlsContainer = document.getElementById('qa-pagination-controls');
    if (!controlsContainer) return;
    controlsContainer.innerHTML = '';

    // 添加全选和批次删除按钮
    const batchOperationsDiv = document.createElement('div');
    batchOperationsDiv.style.marginBottom = '10px';
    batchOperationsDiv.style.display = 'flex';
    batchOperationsDiv.style.gap = '10px';
    
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
    
    // 添加删除所有按钮
    const deleteAllButton = document.createElement('button');
    deleteAllButton.textContent = '刪除所有';
    deleteAllButton.id = 'delete-all-button';
    deleteAllButton.onclick = async () => {
        await deleteAllQaPairs();
    };
    batchOperationsDiv.appendChild(deleteAllButton);
    
    controlsContainer.appendChild(batchOperationsDiv);

    if (!pagination || pagination.total_pages <= 1) {
        return;
    }

    const { current_page, total_pages } = pagination;

    const prevButton = document.createElement('button');
    prevButton.textContent = '« 上一頁';
    prevButton.disabled = current_page === 1;
    prevButton.id = 'prev-page-btn';
    prevButton.onclick = () => loadTrainingDataForTable(activeTable, current_page - 1);
    controlsContainer.appendChild(prevButton);

    const pageInfo = document.createElement('span');
    pageInfo.textContent = ` 第 ${current_page} / ${total_pages} 頁 `;
    pageInfo.style.margin = '0 1em';
    pageInfo.id = 'page-info';
    controlsContainer.appendChild(pageInfo);

    const nextButton = document.createElement('button');
    nextButton.textContent = '下一頁 »';
    nextButton.disabled = current_page === total_pages;
    nextButton.id = 'next-page-btn';
    nextButton.onclick = () => loadTrainingDataForTable(activeTable, current_page + 1);
    controlsContainer.appendChild(nextButton);
}

async function saveDocumentation() {
    if (!activeDatasetId || !activeTable) {
        if (!activeDatasetId) {
            alert('請先選擇一個資料集。');
        }
        return;
    }
    
    try {
        const docContent = document.getElementById('doc-input').value;
        const result = await apiFetch('/api/save_documentation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                documentation: docContent, 
                table_name: activeTable 
            })
        });
        
        alert(result.message || '儲存完成。');
    } catch (error) {
        console.error('儲存文檔失敗:', error);
        alert(`儲存文檔失敗: ${error.message}`);
    }
}

function renderQaTable() {
    const tableBody = document.getElementById('qa-table-body');
    tableBody.innerHTML = '';
    
    if (!Array.isArray(currentQaData) || currentQaData.length === 0) {
        return;
    }
    
    // 后端已经处理了分页，直接使用 currentQaData
    currentQaData.forEach((item, index) => {
        const row = tableBody.insertRow();
        row.dataset.id = item.id || '';
        // The originalIndex should be based on the current page and index
        row.dataset.originalIndex = (current_page - 1) * items_per_page + index;
        
        // 添加复选框单元格
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
        deleteBtn.onclick = () => {
            row.remove();
            const originalIndex = parseInt(row.dataset.originalIndex);
            if (!isNaN(originalIndex)) {
                currentQaData.splice(originalIndex, 1);
                selectedQaIds.delete(item.id);
                updateBatchDeleteButton();
                // 如果删除后当前页没有数据且不是第一页，则返回上一页
                if (paginatedData.length === 1 && current_page > 1) {
                    current_page--;
                }
                renderQaTable();
            }
        };
        actionCell.appendChild(deleteBtn);
    });
    
    // 更新批次删除按钮状态
    updateBatchDeleteButton();
}

function addQaPairRow(question = '', sql = '') {
    const tableBody = document.getElementById('qa-table-body');
    const row = tableBody.insertRow();
    row.dataset.id = '';
    
    // 添加复选框单元格
    const checkboxCell = row.insertCell();
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'qa-checkbox';
    checkbox.disabled = true; // 新添加的行默认不能选中
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
    deleteBtn.onclick = () => {
        row.remove();
    };
    actionCell.appendChild(deleteBtn);

    if (!question && !sql) {
        questionTextarea.focus();
    }
}

async function saveAllQaModifications() {
    if (!activeDatasetId || !activeTable) {
        if (!activeDatasetId) {
            alert('請先選擇一個資料集。');
        }
        return;
    }
    
    const tableBody = document.getElementById('qa-table-body');
    let successCount = 0, errorCount = 0;
    
    try {
        for (const row of tableBody.rows) {
            const id = row.dataset.id;
            const question = row.cells[1]?.querySelector('textarea')?.value.trim() || '';
            const sql = row.cells[2]?.querySelector('pre')?.innerText.trim() || '';
            
            if (!question || !sql) continue;
            
            try {
                if (id) {
                    // Update endpoint is not implemented in this version
                } else {
                    await apiFetch('/api/add_qa_question', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            question: question, 
                            sql: sql, 
                            table_name: activeTable 
                        })
                    });
                }
                successCount++;
            } catch (e) {
                console.error(`保存QA失败 (${question.substring(0, 20)}...):`, e);
                errorCount++;
            }
        }
        
        alert(`儲存完成: ${successCount} 成功, ${errorCount} 失敗。`);
        await loadTrainingDataForTable(activeTable);
    } catch (error) {
        console.error('保存QA修改失敗:', error);
        alert(`保存QA修改失敗: ${error.message}`);
    }
}

// --- Batch Operations Functions --- 
function selectAllQaRows() {
    const tableBody = document.getElementById('qa-table-body');
    const checkboxes = tableBody.querySelectorAll('input[type="checkbox"]');
    const isAllSelected = Array.from(checkboxes).every(checkbox => checkbox.checked);
    
    selectedQaIds.clear();
    checkboxes.forEach(checkbox => {
        checkbox.checked = !isAllSelected;
        if (!isAllSelected && checkbox.disabled === false) {
            const row = checkbox.closest('tr');
            const id = row.dataset.id;
            if (id) {
                selectedQaIds.add(id);
            }
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

function batchDeleteQaRows() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    if (selectedQaIds.size === 0) {
        alert('請先選擇要刪除的行');
        return;
    }
    
    if (confirm(`確定要刪除選中的 ${selectedQaIds.size} 行問答配對嗎？`)) {
        // 先保存当前页面数据
        const tableBody = document.getElementById('qa-table-body');
        const currentPageData = [];
        
        for (const row of tableBody.rows) {
            const id = row.dataset.id;
            const originalIndex = parseInt(row.dataset.originalIndex);
            if (!isNaN(originalIndex)) {
                currentPageData.push({ id, originalIndex });
            }
        }
        
        // 根据选中的ID删除数据
        currentPageData.forEach(item => {
            if (selectedQaIds.has(item.id)) {
                currentQaData.splice(item.originalIndex, 1);
            }
        });
        
        selectedQaIds.clear();
        total_pages = Math.ceil(currentQaData.length / items_per_page);
        
        // 如果当前页没有数据了，返回上一页
        if (currentQaData.length === 0) {
            current_page = 1;
        } else if (current_page > total_pages) {
            current_page = total_pages;
        }
        
        renderQaTable();
        renderPaginationControls({ current_page: current_page, total_pages: total_pages });
        updateBatchDeleteButton();
    }
}

async function deleteAllQaPairs() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    if (currentQaData.length === 0) {
        alert('此資料集沒有可刪除的問答配對');
        return;
    }
    
    if (confirm(`確定要刪除整個資料集的所有問答配對嗎？此操作將永久刪除所有數據且無法撤銷！`)) {
        try {
            // 调用API删除整个数据集的所有问答配对
            await apiFetch('/api/delete_all_qa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    table_name: activeTable
                })
            });
            
            // 更新前端状态
            currentQaData = [];
            selectedQaIds.clear();
            current_page = 1;
            total_pages = 1;
            
            // 重新渲染表格和分页控件
            renderQaTable();
            renderPaginationControls({ current_page: current_page, total_pages: total_pages });
            updateBatchDeleteButton();
            
            alert('整個資料集的所有問答配對已成功刪除');
        } catch (error) {
            console.error('刪除所有問答配對失敗:', error);
            alert(`刪除失敗: ${error.message}`);
        }
    }
}

// --- File Upload Progress --- 
function setupFileUploadProgress() {
    // 为generateQaFromSqlFile函数添加进度更新
    const originalGenerateQaFromSqlFile = window.generateQaFromSqlFile;
    window.generateQaFromSqlFile = async function(file) {
        const progressContainer = document.getElementById('qa-upload-progress-container');
        const progressBar = document.getElementById('qa-upload-progress-bar');
        const progressPercentage = document.getElementById('qa-upload-percentage');
        
        if (progressContainer && progressBar && progressPercentage) {
            progressContainer.style.display = 'block';
            progressBar.style.width = '0%';
            progressPercentage.textContent = '0%';
            
            try {
                // 使用原始函数
                await originalGenerateQaFromSqlFile(file);
            } finally {
                // 模拟进度完成
                progressBar.style.width = '100%';
                progressPercentage.textContent = '100%';
                
                // 延迟后隐藏进度条
                setTimeout(() => {
                    progressContainer.style.display = 'none';
                }, 1000);
            }
        }
    };
}

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
    
    trainBtn.disabled = true;
    trainBtn.textContent = '訓練中...';
    logContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressText.textContent = '0%';
    
    function addLog(message) {
        logOutput.textContent += message + '\n';
        logOutput.scrollTop = logOutput.scrollHeight;
    }
    
    try {
        const ddl = document.getElementById('ddl-input').value;
        const doc = document.getElementById('doc-input').value;
        
        const qaTableBody = document.getElementById('qa-table-body');
        const qaPairs = [];
        for (const row of qaTableBody.rows) {
            const question = row.cells[1]?.querySelector('textarea')?.value.trim();
            const sql = row.cells[2]?.querySelector('pre')?.innerText.trim();
            if (question && sql) {
                qaPairs.push({ question, sql });
            }
        }

        const formData = new FormData();
        formData.append('ddl', ddl);
        formData.append('doc', doc);
        formData.append('qa_pairs', JSON.stringify(qaPairs));

        const response = await fetch('/api/train', { 
            method: 'POST',
            body: formData,
            // 添加这个头部可以防止浏览器在某些情况下自动刷新
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.body) {
            throw new Error('訓練響應無效');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        // 用于跟踪问答配对的训练进度
        let qaProcessed = 0;
        const totalQaPairs = qaPairs.length;
        
        // 用于限制UI更新频率的计数器
        let updateCounter = 0;
        
        while (true) {
            const { value, done } = await reader.read();
            
            if (done) {
                addLog('✅ 訓練流程已完成。');
                progressBar.style.width = '100%';
                progressText.textContent = '100%';
                break;
            }
            
            try {
                const chunk = decoder.decode(value, { stream: true });
                chunk.split('\n\n').forEach(event => {
                    if (event.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(event.substring(6));
                            if(data.message) {
                                // 特殊处理问答配对训练的进度
                                if (data.message.includes('問答配對') && totalQaPairs > 0) {
                                    // 仅当进度百分比变化明显时才更新UI，减少页面跳动
                                    if (Math.abs(progressBar.style.width.replace('%', '') - Math.round(data.percentage)) > 5 || updateCounter % 3 === 0) {
                                        progressBar.style.width = `${Math.round(data.percentage)}%`;
                                        progressText.textContent = `${Math.round(data.percentage)}%`;
                                    }
                                 
                                    // 详细的训练日志只在完成一定数量的问答对后才显示
                                    if (data.message.includes('訓練完成') || data.message.includes('正在訓練問答配對...') && updateCounter % 5 === 0) {
                                        addLog(`[${Math.round(data.percentage)}%] ${data.message}`);
                                    }
                                } else {
                                    // 对于其他阶段，正常更新UI
                                    addLog(`[${Math.round(data.percentage)}%] ${data.message}`);
                                    progressBar.style.width = `${Math.round(data.percentage)}%`;
                                    progressText.textContent = `${Math.round(data.percentage)}%`;
                                }
                                
                                updateCounter++;
                            }
                        } catch (jsonError) {
                            console.warn('解析訓練日誌失敗:', jsonError);
                        }
                    }
                });
            } catch (decodeError) {
                console.warn('解析訓練日誌數據失敗:', decodeError);
            }
        }
        
        // 训练完成后的处理 - 只在全部完成后执行一次UI更新
        alert('模型訓練成功！');
        document.getElementById('ask-section').style.display = 'block';
        
        // 先执行schema分析，再加载数据
        await analyzeSchema();
        
        // 训练完成后，使用当前页面的页码重新加载数据，防止分页重置
        // 增加延迟时间，确保分析完成后再加载数据
        setTimeout(() => {
            loadTrainingDataForTable(activeTable, current_page);
        }, 800);
        
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
    if (modal) {
        modal.style.display = 'flex';
        const form = document.getElementById('new-dataset-form');
        if (form) {
            form.reset();
        }
    }
}

function closeNewDatasetModal() {
    const modal = document.getElementById('new-dataset-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function handleNewDatasetSubmit(event) {
    event.preventDefault();
    
    const form = document.getElementById('new-dataset-form');
    const formData = new FormData(form);
    const submitBtn = document.getElementById('new-dataset-submit-btn');
    
    const datasetName = formData.get('dataset_name');
    if (!datasetName || !datasetName.trim()) {
        alert('請輸入資料集名稱');
        return;
    }
    
    const files = document.getElementById('new-dataset-files').files;
    if (files.length === 0) {
        alert('請至少選擇一個 CSV 檔案');
        return;
    }
    
    for (const file of files) {
        if (!file.name.endsWith('.csv')) {
            alert(`只支援 CSV 檔案: ${file.name}`);
            return;
        }
    }
    
    submitBtn.disabled = true;
    submitBtn.textContent = '上傳中...';
    
    try {
        await apiFetch('/api/datasets', { 
            method: 'POST', 
            body: formData 
        });
        
        alert('資料集創建成功！');
        closeNewDatasetModal();
        await loadDatasets();
    } catch (error) {
        console.error('創建新資料集失敗:', error);
        alert(`創建新資料集失敗: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '上傳並創建';
    }
}

// 打开编辑数据集模态框
function openEditDatasetModal() {
    const modal = document.getElementById('edit-dataset-modal');
    const selector = document.getElementById('dataset-selector');
    const selectedOption = selector.options[selector.selectedIndex];
    const datasetName = selectedOption.text.split(' (')[0]; // 获取数据集名称，去除日期部分
    const datasetId = selector.value;
    
    document.getElementById('edit-dataset-id').value = datasetId;
    document.getElementById('edit-dataset-name').value = datasetName;
    modal.style.display = 'flex';
    
    // 加载当前数据集中的CSV文件列表
    loadDatasetFiles(datasetId);
    
    // 设置添加文件按钮的点击事件
    document.getElementById('add-file-btn').onclick = async function() {
        await handleAddDatasetFile(datasetId);
    };
}

// 关闭编辑数据集模态框
function closeEditDatasetModal() {
    const modal = document.getElementById('edit-dataset-modal');
    modal.style.display = 'none';
    
    // 清空文件列表
    document.getElementById('current-files-list').innerHTML = '';
}

// 加载数据集中的文件列表
async function loadDatasetFiles(datasetId) {
    const filesListContainer = document.getElementById('current-files-list');
    filesListContainer.innerHTML = '<p>正在加载文件列表...</p>';
    
    try {
        const response = await apiFetch(`/api/datasets/${datasetId}/tables`);
        const tables = response.table_names || [];
        
        if (tables.length === 0) {
            filesListContainer.innerHTML = '<p>資料集中沒有任何文件。</p>';
        } else {
            filesListContainer.innerHTML = '';
            tables.forEach(tableName => {
                const fileItem = document.createElement('div');
                fileItem.style.display = 'flex';
                fileItem.style.justifyContent = 'space-between';
                fileItem.style.alignItems = 'center';
                fileItem.style.padding = '5px 0';
                fileItem.style.borderBottom = '1px solid #eee';
                
                const fileNameSpan = document.createElement('span');
                fileNameSpan.textContent = tableName + '.csv';
                
                const deleteBtn = document.createElement('button');
                deleteBtn.textContent = '移除';
                deleteBtn.style.padding = '3px 8px';
                deleteBtn.style.fontSize = '0.8em';
                deleteBtn.style.backgroundColor = '#dc3545';
                deleteBtn.onclick = async function() {
                    await handleRemoveDatasetFile(datasetId, tableName);
                };
                
                fileItem.appendChild(fileNameSpan);
                fileItem.appendChild(deleteBtn);
                filesListContainer.appendChild(fileItem);
            });
        }
    } catch (error) {
        console.error('加載資料集文件列表失敗:', error);
        filesListContainer.innerHTML = `<p style="color: red;">加載文件列表失敗: ${error.message}</p>`;
    }
}

// 添加文件到数据集
async function handleAddDatasetFile(datasetId) {
    const fileInput = document.getElementById('edit-dataset-files');
    const files = fileInput.files;
    
    if (files.length === 0) {
        alert('請先選擇要添加的 CSV 檔案');
        return;
    }
    
    const file = files[0];
    if (!file.name.endsWith('.csv')) {
        alert('只支援 CSV 檔案');
        return;
    }
    
    const addBtn = document.getElementById('add-file-btn');
    const originalText = addBtn.textContent;
    addBtn.disabled = true;
    addBtn.textContent = '添加中...';
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        await apiFetch('/api/datasets/files', {
            method: 'POST',
            headers: {
                'X-Dataset-Id': datasetId
            },
            body: formData
        });
        
        alert(`文件 "${file.name}" 添加成功！`);
        
        // 清空文件输入并重新加载文件列表
        fileInput.value = '';
        await loadDatasetFiles(datasetId);
        
        // 重新加载数据集列表，以便更新相关信息
        await loadDatasets();
        
        // 重新选择当前数据集
        const selector = document.getElementById('dataset-selector');
        selector.value = datasetId;
        selector.dispatchEvent(new Event('change'));
    } catch (error) {
        console.error('添加文件失敗:', error);
        alert(`添加文件失敗: ${error.message}`);
    } finally {
        addBtn.disabled = false;
        addBtn.textContent = originalText;
    }
}

// 从数据集移除文件
async function handleRemoveDatasetFile(datasetId, tableName) {
    if (!confirm(`確定要從資料集中移除 "${tableName}.csv" 嗎？`)) {
        return;
    }
    
    try {
        await apiFetch('/api/datasets/files', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                dataset_id: datasetId,
                table_name: tableName
            })
        });
        
        alert(`文件 "${tableName}.csv" 移除成功！`);
        
        // 重新加载文件列表
        await loadDatasetFiles(datasetId);
        
        // 重新加载数据集列表，以便更新相关信息
        await loadDatasets();
        
        // 重新选择当前数据集
        const selector = document.getElementById('dataset-selector');
        selector.value = datasetId;
        selector.dispatchEvent(new Event('change'));
    } catch (error) {
        console.error('移除文件失敗:', error);
        alert(`移除文件失敗: ${error.message}`);
    }
}

// 处理编辑数据集表单提交
async function handleEditDatasetSubmit(event) {
    event.preventDefault();
    
    const datasetId = document.getElementById('edit-dataset-id').value;
    const datasetName = document.getElementById('edit-dataset-name').value.trim();
    const submitBtn = document.getElementById('edit-dataset-submit-btn');
    
    if (!datasetName) {
        alert('請輸入資料集名稱');
        return;
    }
    
    submitBtn.disabled = true;
    submitBtn.textContent = '儲存中...';
    
    try {
        await apiFetch(`/api/datasets`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dataset_id: datasetId, new_name: datasetName })
        });
        
        alert('資料集更新成功！');
        closeEditDatasetModal();
        await loadDatasets();
        // 重新选择修改后的数据集
        const selector = document.getElementById('dataset-selector');
        selector.value = datasetId;
        selector.dispatchEvent(new Event('change'));
    } catch (error) {
        console.error('更新資料集失敗:', error);
        alert(`更新資料集失敗: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '儲存修改';
    }
}

// 删除数据集
async function deleteDataset() {
    const selector = document.getElementById('dataset-selector');
    const datasetId = selector.value;
    const selectedOption = selector.options[selector.selectedIndex];
    const datasetName = selectedOption.text.split(' (')[0];
    
    if (!confirm(`確定要刪除資料集 "${datasetName}" 嗎？此操作無法撤銷！`)) {
        return;
    }
    
    try {
        await apiFetch(`/api/datasets`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dataset_id: datasetId })
        });
        
        alert('資料集刪除成功！');
        await loadDatasets();
        selector.value = '';
        selector.dispatchEvent(new Event('change'));
    } catch (error) {
        console.error('刪除資料集失敗:', error);
        alert(`刪除資料集失敗: ${error.message}`);
    }
}
function setupEventListeners() {
    // 标签页切换
    const datasetTab = document.getElementById('dataset-tab');
    if (datasetTab) {
        datasetTab.addEventListener('click', () => {
            document.getElementById('dataset-section').style.display = 'block';
            document.getElementById('training-section').style.display = 'none';
            document.getElementById('ask-section').style.display = 'none';
            document.getElementById('prompts-section').style.display = 'none';
            document.getElementById('documentation-output-section').style.display = 'none';
        });
    }

    const trainingTab = document.getElementById('training-tab');
    if (trainingTab) {
        trainingTab.addEventListener('click', () => {
            document.getElementById('dataset-section').style.display = 'none';
            document.getElementById('training-section').style.display = 'block';
            document.getElementById('ask-section').style.display = 'none';
            document.getElementById('prompts-section').style.display = 'none';
            document.getElementById('documentation-output-section').style.display = 'none';
        });
    }

    const askTab = document.getElementById('ask-tab');
    if (askTab) {
        askTab.addEventListener('click', () => {
            document.getElementById('dataset-section').style.display = 'none';
            document.getElementById('training-section').style.display = 'none';
            document.getElementById('ask-section').style.display = 'block';
            document.getElementById('prompts-section').style.display = 'none';
            document.getElementById('documentation-output-section').style.display = 'none';
        });
    }

    const promptsTab = document.getElementById('prompts-tab');
    if (promptsTab) {
        promptsTab.addEventListener('click', () => {
            document.getElementById('dataset-section').style.display = 'none';
            document.getElementById('training-section').style.display = 'none';
            document.getElementById('ask-section').style.display = 'none';
            document.getElementById('prompts-section').style.display = 'block';
            document.getElementById('documentation-output-section').style.display = 'none';
            if (activeDatasetId) {
                loadPrompts();
            }
        });
    }

    const documentationTab = document.getElementById('documentation-tab');
    if (documentationTab) {
        documentationTab.addEventListener('click', () => {
            document.getElementById('dataset-section').style.display = 'none';
            document.getElementById('training-section').style.display = 'none';
            document.getElementById('ask-section').style.display = 'none';
            document.getElementById('prompts-section').style.display = 'none';
            document.getElementById('documentation-output-section').style.display = 'block';
        });
    }

    // 新增提示词按钮
    const addPromptBtn = document.getElementById('add-prompt-btn');
    if (addPromptBtn) {
        addPromptBtn.addEventListener('click', openPromptModal);
    }

    // 关闭提示词模态框按钮
    const closePromptModalBtn = document.getElementById('close-prompt-modal');
    if (closePromptModalBtn) {
        closePromptModalBtn.addEventListener('click', closePromptModal);
    }

    // 关闭数据集模态框按钮
    const closeDatasetModalBtn = document.getElementById('close-dataset-modal');
    if (closeDatasetModalBtn) {
        closeDatasetModalBtn.addEventListener('click', closeNewDatasetModal);
    }
    
    // 模态框外部点击关闭
    window.addEventListener('click', (event) => {
        if (event.target === document.getElementById('prompt-modal')) {
            closePromptModal();
        }
        if (event.target === document.getElementById('dataset-modal')) {
            closeNewDatasetModal();
        }
    });

    // 数据集选择器变化
    // 注意：这里不再需要添加事件监听器，因为我们在loadDatasets函数中已经添加了
    
    // 数据表选择器变化
    const tableSelector = document.getElementById('table-selector');
    if (tableSelector) {
        tableSelector.addEventListener('change', (e) => {
            if (!activeDatasetId) {
                alert('請先選擇一個資料集。');
                tableSelector.value = 'global'; // 恢复到默认值
                return;
            }
            loadTrainingDataForTable(e.target.value);
        });
    }
    
    // 新增数据集表单提交
    const newDatasetForm = document.getElementById('new-dataset-form');
    if (newDatasetForm) {
        newDatasetForm.addEventListener('submit', handleNewDatasetSubmit);
    }
    
    // 编辑数据集表单提交
    const editDatasetForm = document.getElementById('edit-dataset-form');
    if (editDatasetForm) {
        editDatasetForm.addEventListener('submit', handleEditDatasetSubmit);
    }
    
    window.addEventListener('load', loadDatasets);
}

function init() {
    setupEventListeners();
    loadDatasets();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// --- Ask and Execute Functions ---
let lastGeneratedSql = '';

async function ask() {
    const questionInput = document.getElementById('question-input');
    const question = questionInput.value.trim();
    if (!question) {
        alert('請輸入問題。');
        return;
    }

    const askBtn = document.getElementById('ask-button');
    const thinkingContainer = document.getElementById('thinking-container');
    const thinkingOutput = document.getElementById('thinking-output');
    const analysisContainer = document.getElementById('analysis-container');
    const analysisOutput = document.getElementById('analysis-output');
    const sqlContainer = document.getElementById('sql-container');
    const sqlOutput = document.getElementById('sql-output');
    const resultContainer = document.getElementById('result-container');
    const resultOutput = document.getElementById('result-output');

    askBtn.disabled = true;
    askBtn.textContent = '思考中...';
    thinkingContainer.style.display = 'block';
    thinkingOutput.innerHTML = '';
    analysisContainer.style.display = 'none';
    analysisOutput.innerHTML = '';
    sqlContainer.style.display = 'none';
    resultContainer.style.display = 'none';
    sqlOutput.textContent = '';
    resultOutput.textContent = '';
    lastGeneratedSql = '';

    try {
        const response = await fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question })
        });

        if (!response.body) {
            throw new Error('The response from the server is invalid.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            const events = chunk.split('\n\n');

            for (const event of events) {
                if (event.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(event.substring(6));
                        if (data.type === 'thinking_step') {
                            const stepElement = document.createElement('div');
                            stepElement.style.marginBottom = '10px';
                            
                            const stepTitle = document.createElement('strong');
                            stepTitle.textContent = data.step;
                            stepElement.appendChild(stepTitle);

                            if (data.details) {
                                const detailsPre = document.createElement('pre');
                                detailsPre.style.marginTop = '5px';
                                detailsPre.style.paddingLeft = '15px';
                                detailsPre.style.borderLeft = '2px solid #555';
                                detailsPre.textContent = typeof data.details === 'object' ? JSON.stringify(data.details, null, 2) : data.details;
                                stepElement.appendChild(detailsPre);
                            }
                            
                            thinkingOutput.appendChild(stepElement);
                            thinkingOutput.scrollTop = thinkingOutput.scrollHeight;
                        } else if (data.type === 'result') {
                            if (data.sql) {
                                lastGeneratedSql = data.sql;
                                sqlOutput.textContent = lastGeneratedSql;
                                sqlContainer.style.display = 'block';
                            }
                            if (data.df_json) {
                                try {
                                    const df = JSON.parse(data.df_json);
                                    renderResultTable(df);
                                    resultContainer.style.display = 'block';
                                } catch (e) {
                                    resultOutput.textContent = "無法解析查詢結果。";
                                    resultContainer.style.display = 'block';
                                }
                            }
                            if (data.analysis_result) {
                                analysisOutput.innerHTML = marked.parse(data.analysis_result);
                                analysisContainer.style.display = 'block';
                            }
                        } else if (data.type === 'error') {
                            throw new Error(data.message);
                        }
                    } catch (e) {
                        console.warn('Failed to parse stream data chunk:', e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('An error occurred during the ask process:', error);
        const errorElement = document.createElement('div');
        errorElement.style.color = 'red';
        errorElement.textContent = `❌ 錯誤: ${error.message}`;
        thinkingOutput.appendChild(errorElement);
        alert(`提問失敗: ${error.message}`);
    } finally {
        askBtn.disabled = false;
        askBtn.textContent = '提出問題';
    }
}

function renderResultTable(data) {
    const container = document.getElementById('result-output');
    container.innerHTML = '';
    if (!data || data.length === 0) {
        container.textContent = '（查詢結果為空）';
        return;
    }

    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const tbody = document.createElement('tbody');
    
    const headerRow = document.createElement('tr');
    Object.keys(data[0]).forEach(key => {
        const th = document.createElement('th');
        th.textContent = key;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);

    data.forEach(rowData => {
        const row = document.createElement('tr');
        Object.values(rowData).forEach(value => {
            const td = document.createElement('td');
            td.textContent = value;
            row.appendChild(td);
        });
        tbody.appendChild(row);
    });

    table.appendChild(thead);
    table.appendChild(tbody);
    container.appendChild(table);
}

// --- Generate QA from SQL File ---
async function handleQaFileUpload(event) {
    const fileInput = event.target;
    const file = fileInput.files[0];
    if (!file) return;

    if (file.name.toLowerCase().endsWith('.sql')) {
        await generateQaFromSqlFile(file);
    } else {
        alert('不支援的檔案類型。請上傳 .sql 檔案。');
    }
    fileInput.value = '';
}

async function generateQaFromSqlFile(file) {
    const formData = new FormData();
    formData.append('sql_file', file);

    const logContainer = document.getElementById('qa-gen-log-container');
    const logOutput = document.getElementById('qa-gen-log');
    const progressContainer = document.getElementById('qa-upload-progress-container');
    const progressBar = document.getElementById('qa-upload-progress-bar');
    const progressPercentage = document.getElementById('qa-upload-percentage');
    
    logContainer.style.display = 'block';
    if (progressContainer && progressBar && progressPercentage) {
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressPercentage.textContent = '0%';
    }
    logOutput.textContent = '準備從 SQL 檔案生成問答配對...\n';

    function addLog(message) {
        logOutput.textContent += message + '\n';
        logOutput.scrollTop = logOutput.scrollHeight;
    }

    try {
        const response = await fetch('/api/generate_qa_from_sql', {
            method: 'POST',
            body: formData
        });

        if (!response.body) throw new Error('The response from the server is invalid.');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let processedQueries = 0;
        let totalQueries = 0;

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                addLog('✅ 所有問答配對已生成完畢。');
                if (progressContainer && progressBar && progressPercentage) {
                    progressBar.style.width = '100%';
                    progressPercentage.textContent = '100%';
                }
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            const events = chunk.split('\n\n');

            for (const event of events) {
                if (event.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(event.substring(6));
                        if (data.status === 'starting') {
                            totalQueries = data.total;
                            addLog(`找到 ${totalQueries} 個 SQL 查詢語句。`);
                        } else if (data.status === 'progress' && data.qa_pair) {
                            processedQueries++;
                            addQaPairRow(data.qa_pair.question, data.qa_pair.sql);
                            
                            // 更新进度条
                            if (totalQueries > 0 && progressContainer && progressBar && progressPercentage) {
                                const percentage = Math.round((processedQueries / totalQueries) * 100);
                                progressBar.style.width = `${percentage}%`;
                                progressPercentage.textContent = `${percentage}%`;
                            }
                        } else if (data.message) {
                            addLog(data.message);
                        }
                    } catch (e) {
                        console.warn('Failed to parse stream data chunk:', e);
                    }
                }
            }
        }
        alert('問答配對生成完成！請記得點擊 "儲存所有修改" 來保存新產生的配對。');

    } catch (error) {
        console.error('An error occurred during QA generation from SQL file:', error);
        addLog(`❌ 錯誤: ${error.message}`);
        alert(`從 SQL 檔案生成問答配對失敗: ${error.message}`);
    } finally {
        // 延迟后隐藏进度条
        if (progressContainer) {
            setTimeout(() => {
                progressContainer.style.display = 'none';
            }, 1000);
        }
    }
}

// --- Documentation Generation ---
async function generateAndDisplayDocumentation() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }

    const ddl = document.getElementById('ddl-input').value;
    if (!ddl) {
        console.warn("No DDL content found to generate documentation.");
        return;
    }

    const docSection = document.getElementById('documentation-output-section');
    const docOutput = document.getElementById('documentation-output');
    
    docSection.style.display = 'block';
    docOutput.textContent = '正在生成資料庫結構分析...';

    try {
        const result = await apiFetch('/api/generate_documentation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ddl: ddl })
        });

        if (result.status === 'success') {
            docOutput.textContent = result.documentation;
        } else {
            throw new Error(result.message || '生成失敗');
        }
    } catch (error) {
        console.error('生成資料庫文件失敗:', error);
        docOutput.textContent = `生成失敗: ${error.message}`;
    }
}

function addQaPairRow(question = '', sql = '') {
    // 将新的问答对添加到当前页的开头
    const newItem = { question, sql };
    const currentStartIndex = (current_page - 1) * items_per_page;
    currentQaData.splice(currentStartIndex, 0, newItem);
    
    // 如果添加新行后当前页超过了每页的数量限制，需要重新计算分页
    total_pages = Math.ceil(currentQaData.length / items_per_page);
    
    renderQaTable();
    renderPaginationControls({ current_page: current_page, total_pages: total_pages });
    
    // 自动选中新添加的行
    setTimeout(() => {
        const tableBody = document.getElementById('qa-table-body');
        if (tableBody.rows.length > 0) {
            const firstRow = tableBody.rows[0];
            const questionTextarea = firstRow.cells[1]?.querySelector('textarea');
            if (questionTextarea) {
                questionTextarea.focus();
            }
        }
    }, 100);
}

// --- File Upload Handlers ---
function handleDocFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        const docInput = document.getElementById('doc-input');
        docInput.value += (docInput.value ? '\n\n' : '') + e.target.result;
    };
    reader.readAsText(file);
    event.target.value = '';
}

// --- Schema Analysis ---
async function analyzeSchema() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集。');
        return;
    }

    const outputDiv = document.getElementById('schema-analysis-output');
    const analyzeBtn = document.getElementById('analyze-schema-btn');
    
    outputDiv.innerHTML = '<p>正在分析資料庫結構，請稍候...</p>';
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = '分析中...';

    try {
        const result = await apiFetch('/api/analyze_schema', { method: 'POST' });
        
        if (result.status === 'success' && result.analysis) {
            outputDiv.innerHTML = `<pre style="white-space: pre-wrap; background-color: #f8f8f8; padding: 1em; border-radius: 4px;">${result.analysis}</pre>`;
        } else {
            outputDiv.innerHTML = `<p>分析完成，但未找到任何可分析的資料。原因：${result.message || '未知'}</p>`;
        }
    } catch (error) {
        outputDiv.innerHTML = `<p style="color: red;">分析失敗: ${error.message}</p>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = '自動分析資料庫結構';
    }
}

function appendToInput(elementId, textToAppend) {
    const textarea = document.getElementById(elementId);
    textarea.value += (textarea.value ? '\n\n' : '') + textToAppend;
    textarea.scrollTop = textarea.scrollHeight;
}

function toggleVisibility(elementId) {
    const element = document.getElementById(elementId);
    if (element.style.display === 'none') {
        element.style.display = 'table';
    } else {
        element.style.display = 'none';
    }
}

// --- Prompt Management Functions ---

// 加载所有提示词
async function loadPrompts() {
    if (!activeDatasetId) return;
    
    try {
        const response = await apiFetch('/api/prompts');
        const prompts = response.prompts || [];
        renderPromptsTable(prompts);
    } catch (error) {
        console.error('加载提示词失败:', error);
        alert(`加载提示词失败: ${error.message}`);
    }
}

// 渲染提示词表格
function renderPromptsTable(prompts) {
    const tableBody = document.getElementById('prompts-table-body');
    tableBody.innerHTML = '';
    
    // 添加类型映射，将存储的值转换为更有意义的中文描述
    const promptTypeMap = {
        'analysis': '分析型（用於分析用戶問題和生成SQL）',
        'documentation': '文檔型（用於生成數據庫文檔）',
        'qa_generation': 'QA生成型（用於從SQL生成問答配對）',
        'other': '其他類型',
        '用於分析用戶問題和生成SQL的提示詞': '分析型（用於分析用戶問題和生成SQL）',
        '用於從SQL生成問答配對的提示詞': 'QA生成型（用於從SQL生成問答配對）',
        '用於生成數據庫文檔的提示詞': '文檔型（用於生成數據庫文檔）',
        '默認提示詞': '默認提示詞'
    };
    
    if (Array.isArray(prompts)) {
        prompts.forEach((prompt) => {
            const row = tableBody.insertRow();
            row.dataset.id = prompt.id;
            
            const nameCell = row.insertCell();
            nameCell.textContent = prompt.prompt_name;
            
            const typeCell = row.insertCell();
            // 使用映射后的类型描述
            typeCell.textContent = promptTypeMap[prompt.prompt_type] || prompt.prompt_type;
            
            const isGlobalCell = row.insertCell();
            isGlobalCell.textContent = prompt.is_global ? '是' : '否';
            
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
}

// 打开提示词模态框
function openPromptModal() {
    const modal = document.getElementById('prompt-modal');
    const modalTitle = document.getElementById('prompt-modal-title');
    const form = document.getElementById('prompt-form');
    
    modalTitle.textContent = '新增提示詞';
    form.reset();
    document.getElementById('prompt-id').value = '';
    modal.style.display = 'flex';
}

// 关闭提示词模态框
function closePromptModal() {
    const modal = document.getElementById('prompt-modal');
    modal.style.display = 'none';
}

// 编辑提示词
function editPrompt(prompt) {
    const modal = document.getElementById('prompt-modal');
    const modalTitle = document.getElementById('prompt-modal-title');
    
    modalTitle.textContent = '編輯提示詞';
    document.getElementById('prompt-id').value = prompt.id;
    document.getElementById('prompt-name').value = prompt.prompt_name;
    document.getElementById('prompt-type').value = prompt.prompt_type;
    document.getElementById('prompt-is-global').checked = prompt.is_global;
    document.getElementById('prompt-content').value = prompt.prompt_content;
    
    modal.style.display = 'flex';
}

// 保存提示词
async function savePrompt(event) {
    event.preventDefault();
    
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    const id = document.getElementById('prompt-id').value;
    const name = document.getElementById('prompt-name').value.trim();
    const type = document.getElementById('prompt-type').value;
    const isGlobal = document.getElementById('prompt-is-global').checked;
    const content = document.getElementById('prompt-content').value;
    
    if (!name) {
        alert('請輸入提示詞名稱');
        return;
    }
    
    if (!content) {
        alert('請輸入提示詞內容');
        return;
    }
    
    try {
        const response = await apiFetch('/api/save_prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: id || null,
                prompt_name: name,
                prompt_type: type,
                is_global: isGlobal,
                prompt_content: content
            })
        });
        
        alert(response.message || '提示詞儲存成功');
        closePromptModal();
        await loadPrompts();
    } catch (error) {
        console.error('儲存提示詞失敗:', error);
        alert(`儲存提示詞失敗: ${error.message}`);
    }
}

// 删除提示词
async function deletePrompt(promptId, promptName) {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    if (!confirm(`確定要刪除提示詞 "${promptName}" 嗎？`)) {
        return;
    }
    
    try {
        const response = await apiFetch('/api/delete_prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: promptId })
        });
        
        alert(response.message || '提示詞刪除成功');
        await loadPrompts();
    } catch (error) {
        console.error('刪除提示詞失敗:', error);
        alert(`刪除提示詞失敗: ${error.message}`);
    }
}

// 重置提示词为默认值
async function resetPromptToDefault(promptId, promptName) {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    if (!confirm(`確定要將提示詞 "${promptName}" 重置為默認值嗎？`)) {
        return;
    }
    
    try {
        const response = await apiFetch(`/api/reset_prompt_to_default/${encodeURIComponent(promptName)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: promptId })
        });
        
        alert(response.message || '提示詞已重置為默認值');
        await loadPrompts();
    } catch (error) {
        console.error('重置提示詞失敗:', error);
        alert(`重置提示詞失敗: ${error.message}`);
    }
}

// 添加提示词表单提交事件监听器
function setupPromptEventListeners() {
    const promptForm = document.getElementById('prompt-form');
    if (promptForm) {
        promptForm.addEventListener('submit', savePrompt);
    }
}

// 修改初始化函数，添加提示词相关事件监听器和上传进度条
function init() {
    setupEventListeners();
    setupPromptEventListeners();
    setupFileUploadProgress();
    loadDatasets();
}
