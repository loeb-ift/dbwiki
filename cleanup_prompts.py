import sqlite3
import os
import json
import argparse

def get_user_db_path(user_id: str) -> str:
    """Constructs the path to the user's database file."""
    db_dir = os.path.join(os.getcwd(), 'user_data')
    return os.path.join(db_dir, f'training_data_{user_id}.sqlite')

def cleanup_and_rebuild_prompts(user_id: str):
    """
    Deletes all existing prompts for a user and rebuilds them from the default JSON file.
    """
    db_path = get_user_db_path(user_id)
    if not os.path.exists(db_path):
        print(f"錯誤：找不到使用者 '{user_id}' 的資料庫檔案於 '{db_path}'。")
        return

    prompts_file_path = os.path.join(os.getcwd(), 'prompts', 'default_prompts.json')
    if not os.path.exists(prompts_file_path):
        print(f"錯誤：找不到預設提示詞檔案 '{prompts_file_path}'。")
        return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 1. Delete all existing prompts
            print(f"正在刪除使用者 '{user_id}' 的所有現有提示詞...")
            cursor.execute("DELETE FROM training_prompts;")
            print(f"成功刪除 {cursor.rowcount} 筆提示詞。")

            # 2. Re-initialize from the default prompts JSON file
            print("正在從 'prompts/default_prompts.json' 重新載入預設提示詞...")
            with open(prompts_file_path, 'r', encoding='utf-8') as f:
                default_prompts_content = json.load(f)

            inserted_count = 0
            for prompt_type, prompt_content in default_prompts_content.items():
                prompt_name = f"{prompt_type}_prompt"
                try:
                    cursor.execute(
                        "INSERT INTO training_prompts (prompt_name, prompt_content, prompt_type, is_global) VALUES (?, ?, ?, ?)",
                        (prompt_name, prompt_content, prompt_type, 1)
                    )
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    print(f"警告：嘗試插入重複的提示詞 '{prompt_name}'。跳過。")

            conn.commit()
            print(f"成功插入 {inserted_count} 筆新的預設提示詞。")
            print(f"使用者 '{user_id}' 的提示詞資料庫已成功清理並重建！")

    except Exception as e:
        print(f"執行過程中發生錯誤: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup and rebuild prompts for a specific user.")
    parser.add_argument("user_id", type=str, help="The ID of the user whose prompts need to be rebuilt.")
    args = parser.parse_args()
    
    cleanup_and_rebuild_prompts(args.user_id)