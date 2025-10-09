// Global State
let activeDatasetId = null;
let activeTable = 'global';
let fullDdlMap = {};
let tableNames = [];
let currentQaData = [];

// --- API Wrapper ---
async function apiFetch(url, options = {}) {
    try {
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
                const option = new Option(`${ds.dataset_name} (${new Date(ds.created_at).toLocaleDateString()})`, ds.id);
                selector.add(option);
            });
        }
    } catch (error) {
        console.error('加載資料集失敗:', error);
    }
}

async function activateDataset(datasetId) {
    document.getElementById('training-section').style.display = 'none';
    document.getElementById('ask-section').style.display = 'none';
    activeDatasetId = null;
    fullDdlMap = {};
    tableNames = [];
    currentQaData = [];
    activeTable = 'global';
    
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
        
        if (result.is_trained) {
            document.getElementById('ask-section').style.display = 'block';
        }
        
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
    if (!activeDatasetId || !tableName) return;
    
    activeTable = tableName;
    
    try {
        const ddlInput = document.getElementById('ddl-input');
        if (tableName === 'global') {
            ddlInput.value = Object.values(fullDdlMap).join('\n\n');
        } else {
            ddlInput.value = fullDdlMap[tableName] || `/* 找不到資料表 "${tableName}" 的 DDL。 */`;
        }
        
        const data = await apiFetch(`/api/training_data?table_name=${encodeURIComponent(tableName)}&page=${page}`);
        document.getElementById('doc-input').value = data.documentation || '';
        currentQaData = Array.isArray(data.qa_pairs) ? data.qa_pairs : [];
        
        renderQaTable();
        renderPaginationControls(data.pagination);

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

    if (!pagination || pagination.total_pages <= 1) {
        return;
    }

    const { current_page, total_pages } = pagination;

    const prevButton = document.createElement('button');
    prevButton.textContent = '« 上一頁';
    prevButton.disabled = current_page === 1;
    prevButton.onclick = () => loadTrainingDataForTable(activeTable, current_page - 1);
    controlsContainer.appendChild(prevButton);

    const pageInfo = document.createElement('span');
    pageInfo.textContent = ` 第 ${current_page} / ${total_pages} 頁 `;
    pageInfo.style.margin = '0 1em';
    controlsContainer.appendChild(pageInfo);

    const nextButton = document.createElement('button');
    nextButton.textContent = '下一頁 »';
    nextButton.disabled = current_page === total_pages;
    nextButton.onclick = () => loadTrainingDataForTable(activeTable, current_page + 1);
    controlsContainer.appendChild(nextButton);
}

async function saveDocumentation() {
    if (!activeDatasetId || !activeTable) return;
    
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
    
    if (Array.isArray(currentQaData)) {
        currentQaData.forEach((item, index) => {
            const row = tableBody.insertRow();
            row.dataset.id = item.id || '';
            
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
                const rowIndex = Array.from(tableBody.rows).indexOf(row);
                if (rowIndex !== -1) {
                    currentQaData.splice(rowIndex, 1);
                }
            };
            actionCell.appendChild(deleteBtn);
        });
    }
}

function addQaPairRow(question = '', sql = '') {
    const tableBody = document.getElementById('qa-table-body');
    const row = tableBody.insertRow();
    row.dataset.id = '';

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
    if (!activeDatasetId || !activeTable) return;
    
    const tableBody = document.getElementById('qa-table-body');
    let successCount = 0, errorCount = 0;
    
    try {
        for (const row of tableBody.rows) {
            const id = row.dataset.id;
            const question = row.cells[0]?.querySelector('textarea')?.value.trim() || '';
            const sql = row.cells[1]?.querySelector('pre')?.innerText.trim() || '';
            
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

async function trainModel() {
    if (!activeDatasetId) {
        alert('請先選擇一個資料集');
        return;
    }
    
    const trainBtn = document.getElementById('train-model-btn');
    const logContainer = document.getElementById('training-log-container');
    const logOutput = document.getElementById('training-log');
    
    trainBtn.disabled = true;
    trainBtn.textContent = '訓練中...';
    logContainer.style.display = 'block';
    logOutput.textContent = '準備開始訓練...\n';
    
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
            const question = row.cells[0]?.querySelector('textarea')?.value.trim();
            const sql = row.cells[1]?.querySelector('pre')?.innerText.trim();
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
            body: formData
        });

        if (!response.body) {
            throw new Error('訓練響應無效');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { value, done } = await reader.read();
            
            if (done) {
                addLog('✅ 訓練流程已完成。');
                break;
            }
            
            try {
                const chunk = decoder.decode(value, { stream: true });
                chunk.split('\n\n').forEach(event => {
                    if (event.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(event.substring(6));
                            if(data.message) {
                                addLog(`[${Math.round(data.percentage)}%] ${data.message}`);
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
        
        alert('模型訓練成功！');
        document.getElementById('ask-section').style.display = 'block';
        analyzeSchema(); // Automatically trigger schema analysis after successful training
        
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

// --- Event Listeners ---
function setupEventListeners() {
    const datasetSelector = document.getElementById('dataset-selector');
    if (datasetSelector) {
        datasetSelector.addEventListener('change', (e) => activateDataset(e.target.value));
    }
    
    const tableSelector = document.getElementById('table-selector');
    if (tableSelector) {
        tableSelector.addEventListener('change', (e) => loadTrainingDataForTable(e.target.value));
    }
    
    const newDatasetForm = document.getElementById('new-dataset-form');
    if (newDatasetForm) {
        newDatasetForm.addEventListener('submit', handleNewDatasetSubmit);
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
    
    logContainer.style.display = 'block';
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

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                addLog('✅ 所有問答配對已生成完畢。');
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            const events = chunk.split('\n\n');

            for (const event of events) {
                if (event.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(event.substring(6));
                        if (data.status === 'progress' && data.qa_pair) {
                            addQaPairRow(data.qa_pair.question, data.qa_pair.sql);
                        } else {
                            addLog(data.message || JSON.stringify(data));
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
    }
}

// --- Documentation Generation ---
async function generateAndDisplayDocumentation() {
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
