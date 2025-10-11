from flask import Blueprint, request, jsonify, session
import os
import uuid
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from werkzeug.utils import secure_filename

from app.core.helpers import get_dataset_tables
from app.models import get_user_db_connection
from app.vanna_wrapper import get_vanna_instance, configure_vanna_for_request
from app.utils.decorators import login_required

datasets_bp = Blueprint('datasets', __name__, url_prefix='/api/datasets')

@datasets_bp.route('', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def handle_datasets():
    user_id = session['username']
    if request.method == 'GET':
        with get_user_db_connection(user_id) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, dataset_name AS name, created_at FROM datasets ORDER BY created_at DESC")
            return jsonify({'status': 'success', 'datasets': [dict(row) for row in cursor.fetchall()]})
    
    elif request.method == 'POST':
        dataset_name = request.form.get('dataset_name')
        files = request.files.getlist('files')
        if not dataset_name or not files:
            return jsonify({'status': 'error', 'message': 'Dataset name and files are required.'}), 400
        
        db_path = os.path.join('user_data', 'datasets', f'{uuid.uuid4().hex}.sqlite')
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            for file in files:
                df = pd.read_csv(file.stream)
                table_name = os.path.splitext(secure_filename(file.filename))[0].replace('-', '_').replace(' ', '_')
                df.to_sql(table_name, engine, index=False, if_exists='replace')
            
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO datasets (dataset_name, db_path) VALUES (?, ?)", (dataset_name, db_path))
                new_id = cursor.lastrowid
                conn.commit()
            return jsonify({'status': 'success', 'dataset': {'id': new_id, 'dataset_name': dataset_name}}), 201
        except Exception as e:
            if os.path.exists(db_path): os.remove(db_path)
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'PUT':
        data = request.json
        dataset_id = data.get('dataset_id')
        new_name = data.get('new_name')
        
        if not dataset_id or not new_name:
            return jsonify({'status': 'error', 'message': 'Dataset ID and new name are required.'}), 400
        
        try:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM datasets WHERE id = ?", (dataset_id,))
                if not cursor.fetchone():
                    return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
                
                cursor.execute("UPDATE datasets SET dataset_name = ? WHERE id = ?", (new_name, dataset_id))
                conn.commit()
            
            return jsonify({'status': 'success', 'dataset': {'id': dataset_id, 'dataset_name': new_name}})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'DELETE':
        data = request.json
        dataset_id = data.get('dataset_id')
        
        if not dataset_id:
            return jsonify({'status': 'error', 'message': 'Dataset ID is required.'}), 400
        
        try:
            with get_user_db_connection(user_id) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
                
                db_path = row[0]
                
                cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
                conn.commit()
            
            if os.path.exists(db_path):
                os.remove(db_path)
            
            return jsonify({'status': 'success', 'dataset_id': dataset_id})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

@datasets_bp.route('/activate', methods=['POST'])
@login_required
def activate_dataset():
    user_id = session['username']
    dataset_id = request.get_json().get('dataset_id')
    if not dataset_id:
                    return jsonify({'status': 'error', 'message': '数据集ID是必需的，请先选择一个数据集。'}), 400
    
    try:
        # 使用统一的session键名
        session['active_dataset'] = str(dataset_id)
        vn = get_vanna_instance(user_id)
        vn = configure_vanna_for_request(vn, user_id, dataset_id)
        
        inspector = inspect(vn.engine)
        table_names = inspector.get_table_names()
        ddl_statements = []
        with vn.engine.connect() as connection:
            for name in table_names:
                ddl = connection.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}';")).scalar()
                if ddl: ddl_statements.append(ddl + ";")

        training_data = vn.get_training_data()
        is_trained = not training_data.empty if training_data is not None else False

        return jsonify({
            'status': 'success', 
            'message': f"Dataset activated.", 
            'table_names': table_names, 
            'ddl': ddl_statements,
            'is_trained': is_trained
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@datasets_bp.route('/<dataset_id>/tables', methods=['GET'])
@login_required
def get_tables_in_dataset_route(dataset_id):
    user_id = session['username']
    
    tables_info, error = get_dataset_tables(user_id, dataset_id)
    if error:
        return jsonify({'status': 'error', 'message': error}), 404 if error == "Dataset not found" else 500
    
    return jsonify({
        'status': 'success',
        'dataset_id': dataset_id,
        'table_names': tables_info['table_names'],
        'ddl_statements': tables_info['ddl_statements']
    })

@datasets_bp.route('/files', methods=['POST', 'DELETE'])
@login_required
def handle_dataset_files():
    user_id = session['username']
    dataset_id = request.args.get('dataset_id')
    
    if not dataset_id:
        return jsonify({'status': 'error', 'message': 'dataset_id is required.'}), 400
    
    with get_user_db_connection(user_id) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT db_path FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'status': 'error', 'message': 'Dataset not found.'}), 404
        
        db_path = row[0]
    
    if request.method == 'POST':
        files = request.files.getlist('files')
        if not files:
            return jsonify({'status': 'error', 'message': 'No files uploaded.'}), 400
        
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            added_tables = []
            
            for file in files:
                if not file.name.endswith('.csv'):
                    continue
                
                df = pd.read_csv(file.stream)
                table_name = os.path.splitext(secure_filename(file.filename))[0].replace('-', '_').replace(' ', '_')
                df.to_sql(table_name, engine, index=False, if_exists='replace')
                added_tables.append(table_name)
            
            tables_info, _ = get_dataset_tables(user_id, dataset_id)
            all_tables = tables_info['table_names']
            
            return jsonify({
                'status': 'success', 
                'message': f'Added {len(added_tables)} table(s) to dataset.',
                'added_tables': added_tables,
                'all_tables': all_tables
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    elif request.method == 'DELETE':
        data = request.json
        table_name = data.get('table_name')
        
        if not table_name:
            return jsonify({'status': 'error', 'message': 'table_name is required.'}), 400
        
        try:
            engine = create_engine(f'sqlite:///{db_path}')
            with engine.connect() as connection:
                inspector = inspect(engine)
                if table_name not in inspector.get_table_names():
                    return jsonify({'status': 'error', 'message': f'Table {table_name} not found.'}), 404
                
                connection.execute(text(f'DROP TABLE IF EXISTS {table_name}'))
                connection.commit()
            
            tables_info, _ = get_dataset_tables(user_id, dataset_id)
            all_tables = tables_info['table_names']
            
            return jsonify({
                'status': 'success', 
                'message': f'Table {table_name} deleted successfully.',
                'all_tables': all_tables
            })
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500