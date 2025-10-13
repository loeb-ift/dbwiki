import sqlite3
import os
import json

def get_user_db_path(user_id: str) -> str:
    """Constructs the path to the user's database file."""
    db_dir = os.path.join(os.getcwd(), 'user_data')
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def update_prompt_in_db(user_id: str, prompt_type: str, new_content: str):
    """
    Connects to a user's database and updates a specific prompt.
    """
    db_path = get_user_db_path(user_id)
    if not os.path.exists(db_path):
        print(f"錯誤：找不到使用者 '{user_id}' 的資料庫檔案於 '{db_path}'。")
        return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id FROM training_prompts WHERE prompt_type = ?", (prompt_type,)
            )
            prompt_exists = cursor.fetchone()

            if prompt_exists:
                print(f"正在更新使用者 '{user_id}' 的現有提示詞 '{prompt_type}'...")
                cursor.execute(
                    "UPDATE training_prompts SET prompt_content = ? WHERE prompt_type = ?",
                    (new_content, prompt_type)
                )
            else:
                print(f"在資料庫中找不到提示詞 '{prompt_type}'。將為使用者 '{user_id}' 新增一筆...")
                prompt_name = f"{prompt_type}_prompt"
                cursor.execute(
                    "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                    (prompt_name, new_content, prompt_type, 1) # Insert as global
                )

            conn.commit()
            print(f"成功更新使用者 '{user_id}' 的提示詞 '{prompt_type}'。")

    except sqlite3.Error as e:
        print(f"使用者 '{user_id}' 的資料庫操作失敗: {e}")

def update_all_users(prompt_type: str, new_content: str):
    """Iterates through all user databases and updates a specific prompt."""
    db_dir = os.path.join(os.getcwd(), 'user_data')
    if not os.path.isdir(db_dir):
        print(f"錯誤：找不到使用者資料目錄 '{db_dir}'。")
        return

    print(f"開始為所有使用者更新 '{prompt_type}' 提示詞...")
    updated_count = 0
    for filename in os.listdir(db_dir):
        if filename.startswith('training_data_') and filename.endswith('.sqlite'):
            user_id = filename.replace('training_data_', '').replace('.sqlite', '')
            print(f"\n--- 正在處理使用者: {user_id} ---")
            update_prompt_in_db(user_id, prompt_type, new_content)
            updated_count += 1
    
    if updated_count == 0:
        print("在 'user_data' 目錄中沒有找到任何使用者資料庫。")
    else:
        print(f"\n所有 {updated_count} 位使用者的提示詞更新完畢。")

if __name__ == "__main__":
    
    # Load the new prompt content from the JSON file
    try:
        prompts_file_path = os.path.join(os.getcwd(), 'prompts', 'default_prompts.json')
        with open(prompts_file_path, 'r', encoding='utf-8') as f:
            all_prompts = json.load(f)
        
        analysis_prompt_content = all_prompts.get("analysis")

        if not analysis_prompt_content:
            print("錯誤：在 'default_prompts.json' 中找不到 'analysis' 提示詞。")
        else:
            # Update the 'analysis' prompt for all users
            update_all_users("analysis", analysis_prompt_content)

    except FileNotFoundError:
        print(f"錯誤：找不到提示詞設定檔 '{prompts_file_path}'。")
    except json.JSONDecodeError:
        print(f"錯誤：無法解析 JSON 檔案 '{prompts_file_path}'。")
    except Exception as e:
        print(f"執行期間發生未知錯誤: {e}")