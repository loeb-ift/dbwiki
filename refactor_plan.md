# Dynamic Prompt Generation Refactor Plan

## 1. Objective

To refactor the dynamic prompt generation logic in `app/blueprints/ask.py`. The current implementation relies on reading from filesystem logs (`ask_log/`), which is fragile and couples the logic too tightly with a temporary file-based data passing mechanism.

The goal is to make the process more robust, maintainable, and independent of the filesystem by using structured data directly within the application's memory.

## 2. Current Architecture & Problems

- **Data Flow**: `ask` function calls Vanna methods (`get_similar_question_sql`, etc.) -> Vanna methods write their results to individual log files in `ask_log/` -> `ask` function then calls `_get_all_ask_logs` to read and aggregate these same log files -> The aggregated string content is then injected into a prompt template via simple string replacement.
- **Problems**:
    - **Fragility**: Relies on file I/O, which can fail. Prone to race conditions in a multi-threaded environment.
    - **Low Cohesion**: The logic for generating context and consuming it is disconnected via the filesystem.
    - **Tight Coupling**: The `ask` function is tightly coupled to the specific file naming and content format of the logs created by `write_ask_log` and aggregated by `_get_all_ask_logs`.
    - **Inefficiency**: Writing to and reading from disk is less efficient than passing data in memory.
    - **Poor Readability**: String replacement on a large template is hard to read and maintain.

## 3. Proposed Refactoring

### 3.1. Core Idea

The `run_vanna_in_thread` function in `ask.py` already retrieves the necessary context as structured Python objects:
- `similar_qa` (a list of dictionaries)
- `related_ddl` (a list of strings)
- `related_docs` (a list of strings)

We will use these variables **directly** to build the final prompt, completely bypassing the `ask_log` filesystem dependency for this part of the logic.

### 3.2. Implementation Steps

1.  **Modify `app/blueprints/ask.py`**:
    - In `run_vanna_in_thread`, locate the section where `dynamic_prompt_content` is created (around line 139).
    - **Remove the call to `_get_all_ask_logs`**.
    - Create new helper functions (or inline logic) within `ask.py` to format the context variables into Markdown strings:
        - `format_similar_qa_as_markdown(similar_qa)`: This will take the list of QA dictionaries and return a Markdown table string.
        - `format_ddl_as_markdown(related_ddl)`: This will take the list of DDL strings and wrap them in a single ` ```sql ` code block.
        - `format_docs_as_markdown(related_docs)`: This will concatenate the list of documentation strings.
    - Use these formatted strings to populate the `ask_analysis_prompt_template`. An f-string is recommended for clarity.

    ```python
    # Example of the new logic in ask.py

    # ... after retrieving similar_qa, related_ddl, related_docs ...

    def format_similar_qa_as_markdown(qa_list):
        if not qa_list:
            return "無"
        header = "| 相似問題 | 相關 SQL 範例 |\n|---|---|\n"
        rows = [f"| {item.get('question', '')} | ```sql\n{item.get('sql', '')}\n``` |" for item in qa_list]
        return header + "\n".join(rows)

    def format_ddl_as_markdown(ddl_list):
        if not ddl_list:
            return "無"
        return f"```sql\n{''.join(ddl_list)}\n```"
    
    def format_docs_as_markdown(doc_list):
        if not doc_list:
            return "無"
        return "\n---\n".join(doc_list)

    ask_analysis_prompt_template = load_prompt_template('analysis')

    formatted_similar_qa = format_similar_qa_as_markdown(similar_qa)
    formatted_ddl = format_ddl_as_markdown(related_ddl)
    formatted_docs = format_docs_as_markdown(related_docs)

    dynamic_prompt_content = ask_analysis_prompt_template.replace(
        "[用戶提出的原始自然語言問題]", question
    ).replace(
        "[列出檢索到的相似問題和 SQL 範例]", formatted_similar_qa
    ).replace(
        "[列出檢索到的相關 DDL 語句]", formatted_ddl
    ).replace(
        "[列出檢索到的相關業務文件內容]", formatted_docs
    )

    # ... rest of the function ...
    ```

2.  **Deprecate `_get_all_ask_logs` in `app/core/helpers.py`**:
    - Since this function's primary consumer (`ask.py`) no longer needs it, it can be considered for removal.
    - For safety, we can first mark it with a `# DEPRECATED` comment. After verifying the new implementation works, it can be removed in a subsequent cleanup commit.
    - The `write_ask_log` and `_delete_all_ask_logs` functions should be kept, as they are still useful for general-purpose debugging and cleanup.

## 4. Benefits

- **Decoupling**: The prompt generation logic is no longer dependent on the filesystem logging implementation.
- **Robustness**: Eliminates potential I/O errors and race conditions.
- **Clarity**: The data flow is contained within a single function, making it much easier to understand and debug.
- **Maintainability**: Using helper functions and direct variable manipulation is cleaner than string replacement based on external file content.
