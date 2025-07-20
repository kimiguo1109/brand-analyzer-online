#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
品牌分析器 API后端
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import uuid

# 导入我们的分析器
from universal_brand_analyzer import UniversalBrandAnalyzer
# from convert_csv_to_json_v2 import TikTokDataConverter  # 不再需要

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 配置
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'analyzed_data'
ALLOWED_EXTENSIONS = {'json', 'csv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# 确保文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# 存储分析任务的全局字典
analysis_tasks = {}

# 任务清理配置
MAX_TASKS_IN_MEMORY = 50  # 最大保存的任务数量
TASK_TIMEOUT_HOURS = 24   # 任务超时时间（小时）

# 线程池配置 - 10个工作线程
MAX_WORKERS = 10
thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
print(f"🚀 Initialized thread pool with {MAX_WORKERS} workers for high-performance analysis")

# 应用关闭时清理线程池
import atexit

def cleanup_thread_pool():
    """应用关闭时清理线程池"""
    print("🔄 Shutting down thread pool...")
    thread_pool.shutdown(wait=True)
    print("✅ Thread pool shutdown complete")

atexit.register(cleanup_thread_pool)

def cleanup_old_tasks():
    """清理旧任务以防止内存泄漏"""
    current_time = datetime.now()
    tasks_to_remove = []
    
    for task_id, task_data in analysis_tasks.items():
        try:
            # 检查任务创建时间
            created_at_str = task_data.get('created_at')
            if created_at_str:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00').replace('+00:00', ''))
                age_hours = (current_time - created_at).total_seconds() / 3600
                
                # 清理超过24小时的任务
                if age_hours > TASK_TIMEOUT_HOURS:
                    tasks_to_remove.append(task_id)
                    print(f"Marking task {task_id} for cleanup (age: {age_hours:.1f} hours)")
            
        except Exception as e:
            print(f"Error checking task {task_id} age: {e}")
            # 如果无法解析时间，也标记为删除
            tasks_to_remove.append(task_id)
    
    # 如果任务数量超过限制，清理最旧的已完成任务
    if len(analysis_tasks) > MAX_TASKS_IN_MEMORY:
        completed_tasks = [(task_id, task_data) for task_id, task_data in analysis_tasks.items() 
                          if task_data.get('status') in ['completed', 'error']]
        
        # 按创建时间排序，删除最旧的
        completed_tasks.sort(key=lambda x: x[1].get('created_at', ''))
        excess_count = len(analysis_tasks) - MAX_TASKS_IN_MEMORY
        
        for i in range(min(excess_count, len(completed_tasks))):
            task_id = completed_tasks[i][0]
            if task_id not in tasks_to_remove:
                tasks_to_remove.append(task_id)
                print(f"Marking task {task_id} for cleanup (memory limit)")
    
    # 执行清理
    for task_id in tasks_to_remove:
        try:
            del analysis_tasks[task_id]
            print(f"Cleaned up task {task_id}")
        except KeyError:
            pass
    
    if tasks_to_remove:
        print(f"Cleaned up {len(tasks_to_remove)} old tasks. Remaining: {len(analysis_tasks)}")

def start_cleanup_thread():
    """启动清理线程"""
    def cleanup_worker():
        while True:
            try:
                cleanup_old_tasks()
                time.sleep(3600)  # 每小时清理一次
            except Exception as e:
                print(f"Error in cleanup thread: {e}")
                time.sleep(600)  # 出错时等待10分钟再试
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    print("Started task cleanup thread")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class WebAppHandler(logging.Handler):
    """自定义日志处理器，用于实时显示日志"""
    
    def __init__(self, task_id):
        super().__init__()
        self.task_id = task_id
        self.logs = []
    
    def emit(self, record):
        log_entry = self.format(record)
        self.logs.append({
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'level': record.levelname,
            'message': log_entry
        })
        
        # 更新任务状态
        if self.task_id in analysis_tasks:
            analysis_tasks[self.task_id]['logs'] = self.logs

# LoggingCSVConverter类已移除，现在使用直接CSV分析方法

def run_analysis(task_id, file_path, is_csv=False):
    """在线程池中运行分析任务 - 支持高并发处理"""
    try:
        # 确保任务存在于字典中
        if task_id not in analysis_tasks:
            print(f"Warning: Task {task_id} not found in analysis_tasks")
            return
            
        print(f"🚀 [Worker Thread] Starting analysis for task {task_id} (Pool capacity: {MAX_WORKERS})")
        start_time = time.time()
            
        # 更新任务状态
        analysis_tasks[task_id]['status'] = 'running'
        analysis_tasks[task_id]['progress'] = 'Starting analysis...'
        
        print(f"Starting analysis for task {task_id}, file: {file_path}, is_csv: {is_csv}")
        
        # 创建自定义logger（无论是否CSV都需要）
        custom_logger = logging.getLogger(f'analyzer_{task_id}')
        custom_logger.setLevel(logging.INFO)
        
        # 清除现有处理器
        custom_logger.handlers = []
        
        # 设置自定义日志处理器
        handler = WebAppHandler(task_id)
        handler.setFormatter(logging.Formatter('%(message)s'))
        custom_logger.addHandler(handler)
        
        # 创建分析器实例，传入自定义logger
        print(f"Creating analyzer for task {task_id}")
        analyzer = UniversalBrandAnalyzer(output_dir=RESULTS_FOLDER, custom_logger=custom_logger)
        
        # 如果是CSV文件，使用新的直接分析方法
        if is_csv:
            custom_logger.info('📂 CSV file detected, using direct analysis...')
            analysis_tasks[task_id]['progress'] = 'Starting direct CSV analysis...'
            
            # 检查CSV是否已经包含分析结果
            custom_logger.info('🔍 Checking if CSV already contains analysis results...')
            results = check_and_process_analyzed_csv(file_path, custom_logger)
            
            if not results:
                # 如果没有现成的分析结果，则进行新的分析
                print(f"Running direct CSV analysis for task {task_id}")
                analysis_tasks[task_id]['progress'] = 'Processing CSV data...'
                custom_logger.info('📊 CSV needs analysis, starting direct CSV analysis...')
                results = analyzer.analyze_creators_from_csv_direct(file_path)
        else:
            custom_logger.info('📄 JSON file detected, starting analysis...')
            analysis_tasks[task_id]['progress'] = 'JSON文件检测完成，开始分析...'
            
            # 运行分析
            print(f"Running JSON analysis for task {task_id}")
            analysis_tasks[task_id]['progress'] = '正在进行品牌分析...'
            results = analyzer.analyze_creators(file_path)
        
        print(f"Analysis completed for task {task_id}, results count: {len(results) if results else 0}")
        
        if results:
            # 保存结果
            custom_logger.info('💾 Saving analysis results...')
            analysis_tasks[task_id]['progress'] = '保存分析结果...'
            analyzer.save_results(results, file_path)
            
            # 生成结果文件路径
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 不使用时间戳，使用固定的文件名（与run_csv_analysis保持一致）
            brand_file = f"{base_name}_brand_related.csv"
            non_brand_file = f"{base_name}_non_brand.csv"
            
            # 生成合并后的结果文件
            merged_file = f"{base_name}_merged_results.csv"
            
            # 如果是CSV文件，执行合并逻辑
            if is_csv:
                # 如果CSV已经包含分析结果，直接复制为merged文件
                if os.path.exists(file_path) and file_path.endswith('.csv'):
                    # 检查是否已经是分析过的CSV
                    try:
                        import pandas as pd
                        df = pd.read_csv(file_path)
                        analysis_fields = ['account_type', 'brand', 'email']
                        has_analysis_fields = all(field in df.columns for field in analysis_fields)
                        
                        # 检查是否有有效数据
                        has_valid_data = False
                        if has_analysis_fields:
                            non_empty_account_types = df['account_type'].notna() & (df['account_type'] != '')
                            non_empty_brands = df['brand'].notna() & (df['brand'] != '')
                            valid_rows = non_empty_account_types.sum() + non_empty_brands.sum()
                            has_valid_data = valid_rows > len(df) * 0.1
                        
                        if has_analysis_fields and has_valid_data:
                            # 直接复制为merged文件
                            import shutil
                            merged_path = os.path.join(RESULTS_FOLDER, merged_file)
                            shutil.copy2(file_path, merged_path)
                            custom_logger.info('✅ CSV already contains analysis results, copied as merged file')
                            merge_success = True
                        else:
                            # 执行合并逻辑
                            custom_logger.info('🔗 Merging results with original data...')
                            analysis_tasks[task_id]['progress'] = 'Merging results...'
                            merge_success = merge_results_with_original(file_path, os.path.join(RESULTS_FOLDER, brand_file), merged_file, custom_logger)
                    except Exception as e:
                        custom_logger.error(f'❌ Error checking CSV format: {e}')
                        merge_success = False
                else:
                    merge_success = False
            else:
                # 对于JSON文件，不进行合并
                merge_success = False
            
            # 首先定义品牌相关账号：有extracted_brand_name或者被标记为品牌/矩阵账号
            brand_related_results = [r for r in results if 
                                   (r.extracted_brand_name and r.extracted_brand_name.strip()) or 
                                   r.is_brand or r.is_matrix_account]
            non_brand_results = [r for r in results if r not in brand_related_results]
            
            # 按照account_type统计总创作者中的各类型数量（互斥分类）
            total_creators = len(results)
            official_account_count = sum(1 for r in results if r.is_brand)
            matrix_account_count = sum(1 for r in results if r.is_matrix_account)
            # UGC创作者：在品牌相关中且标记为UGC的创作者
            ugc_creator_count = sum(1 for r in brand_related_results if r.is_ugc_creator)
            # 非品牌创作者：不在品牌相关列表中的所有创作者
            non_branded_creator_count = len(non_brand_results)
            
            # 品牌相关账号中的分类统计（用于Brand Related Breakdown）
            brand_in_related = sum(1 for r in brand_related_results if r.is_brand)
            matrix_in_related = sum(1 for r in brand_related_results if r.is_matrix_account)
            ugc_in_related = sum(1 for r in brand_related_results if r.is_ugc_creator)
            
            # 确保任务仍然存在于字典中（防止被清理）
            if task_id in analysis_tasks:
                # 更新任务状态
                analysis_tasks[task_id].update({
                    'status': 'completed',
                    'progress': '🎉 分析完成！',
                    'completed_at': datetime.now().isoformat(),
                    'results': {
                        'total_processed': total_creators,
                        'brand_related_count': len(brand_related_results),
                        'non_brand_count': total_creators - len(brand_related_results),
                        'official_account_count': official_account_count,
                        'matrix_account_count': matrix_account_count,
                        'ugc_creator_count': ugc_creator_count,
                        'non_branded_creator_count': non_branded_creator_count,
                        # 各类型在总创作者中的百分比
                        'official_account_percentage': round((official_account_count / total_creators) * 100) if total_creators > 0 else 0,
                        'matrix_account_percentage': round((matrix_account_count / total_creators) * 100) if total_creators > 0 else 0,
                        'ugc_creator_percentage': round((ugc_creator_count / total_creators) * 100) if total_creators > 0 else 0,
                        'non_branded_creator_percentage': round((non_branded_creator_count / total_creators) * 100) if total_creators > 0 else 0,
                        # Brand Related Breakdown - 在品牌相关账号中的百分比
                        'brand_in_related': brand_in_related,
                        'matrix_in_related': matrix_in_related,
                        'ugc_in_related': ugc_in_related,
                        'brand_in_related_percentage': round((brand_in_related / len(brand_related_results)) * 100) if len(brand_related_results) > 0 else 0,
                        'matrix_in_related_percentage': round((matrix_in_related / len(brand_related_results)) * 100) if len(brand_related_results) > 0 else 0,
                        'ugc_in_related_percentage': round((ugc_in_related / len(brand_related_results)) * 100) if len(brand_related_results) > 0 else 0,
                        'brand_file': brand_file,
                        'non_brand_file': non_brand_file,
                        'merged_file': merged_file if 'merge_success' in locals() and merge_success else None
                    }
                })
                custom_logger.info(f'✅ Analysis completed successfully! Processed {len(results)} creators')
                print(f"Task {task_id} completed successfully")
            else:
                print(f"Warning: Task {task_id} was removed from analysis_tasks during processing")
        else:
            if task_id in analysis_tasks:
                analysis_tasks[task_id]['status'] = 'error'
                analysis_tasks[task_id]['progress'] = '分析失败：没有成功分析任何创作者'
            custom_logger.error('❌ Analysis failed: No creators were successfully analyzed')
            print(f"Analysis failed for task {task_id}: No results")
            
    except Exception as e:
        error_msg = f'分析失败：{str(e)}'
        print(f"Exception in run_analysis for task {task_id}: {str(e)}")
        
        # 确保任务仍然存在
        if task_id in analysis_tasks:
            analysis_tasks[task_id]['status'] = 'error'
            analysis_tasks[task_id]['progress'] = error_msg
            analysis_tasks[task_id]['error_at'] = datetime.now().isoformat()
        
        # 也尝试记录到日志
        try:
            if 'custom_logger' in locals():
                custom_logger.error(f'❌ Analysis error: {str(e)}')
        except:
            pass
    
    finally:
        # 性能统计
        if 'start_time' in locals():
            execution_time = time.time() - start_time
            print(f"⏱️ [Worker Thread] Task {task_id} execution time: {execution_time:.2f}s")
            
            # 添加性能信息到任务数据中
            if task_id in analysis_tasks:
                analysis_tasks[task_id]['execution_time'] = execution_time
                analysis_tasks[task_id]['finished_at'] = datetime.now().isoformat()
        
        # 清理自定义logger
        try:
            if 'custom_logger' in locals():
                custom_logger.handlers = []
        except:
            pass
        
        print(f"🏁 [Worker Thread] Analysis thread for task {task_id} finished")

def run_csv_analysis(task_id, file_path):
    """在线程池中直接分析CSV文件 - 高性能并发处理"""
    try:
        # 确保任务存在于字典中
        if task_id not in analysis_tasks:
            print(f"Warning: Task {task_id} not found in analysis_tasks")
            return
            
        print(f"🚀 [CSV Worker] Starting CSV analysis for task {task_id} (Pool: {MAX_WORKERS} workers)")
        start_time = time.time()
            
        # 更新任务状态
        analysis_tasks[task_id]['status'] = 'running'
        analysis_tasks[task_id]['progress'] = 'Starting CSV analysis...'
        
        print(f"Starting CSV analysis for task {task_id}, file: {file_path}")
        
        # 创建自定义logger
        custom_logger = logging.getLogger(f'csv_analyzer_{task_id}')
        custom_logger.setLevel(logging.INFO)
        
        # 清除现有处理器
        custom_logger.handlers = []
        
        # 设置自定义日志处理器
        handler = WebAppHandler(task_id)
        handler.setFormatter(logging.Formatter('%(message)s'))
        custom_logger.addHandler(handler)
        
        custom_logger.info('📄 Starting CSV analysis...')
        analysis_tasks[task_id]['progress'] = 'CSV analysis started...'
        
        # 创建分析器实例，传入自定义logger
        print(f"Creating analyzer for task {task_id}")
        analyzer = UniversalBrandAnalyzer(output_dir=RESULTS_FOLDER, custom_logger=custom_logger)
        
        # 检查CSV是否已经包含分析结果
        custom_logger.info('🔍 Checking if CSV already contains analysis results...')
        results = check_and_process_analyzed_csv(file_path, custom_logger)
        
        if not results:
            # 如果没有现成的分析结果，则进行新的分析
            print(f"Running CSV analysis for task {task_id}")
            analysis_tasks[task_id]['progress'] = 'Processing CSV data...'
            custom_logger.info('📊 CSV needs analysis, starting direct CSV analysis...')
            results = analyzer.analyze_creators_from_csv_direct(file_path)
        
        print(f"CSV analysis completed for task {task_id}, results count: {len(results) if results else 0}")
        
        if results:
            # 保存结果
            custom_logger.info('💾 Saving analysis results...')
            analysis_tasks[task_id]['progress'] = 'Saving analysis results...'
            analyzer.save_results(results, file_path)
            
            # 生成结果文件路径
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # 不使用时间戳，使用固定的文件名
            brand_file = f"{base_name}_brand_related.csv"
            non_brand_file = f"{base_name}_non_brand.csv"
            
            # 生成合并后的结果文件
            merged_file = f"{base_name}_merged_results.csv"
            
            # 如果CSV已经包含分析结果，直接复制为merged文件
            if os.path.exists(file_path) and file_path.endswith('.csv'):
                # 检查是否已经是分析过的CSV
                try:
                    import pandas as pd
                    df = pd.read_csv(file_path)
                    analysis_fields = ['account_type', 'brand', 'email']
                    has_analysis_fields = all(field in df.columns for field in analysis_fields)
                    
                    # 检查是否有有效数据
                    has_valid_data = False
                    if has_analysis_fields:
                        non_empty_account_types = df['account_type'].notna() & (df['account_type'] != '')
                        non_empty_brands = df['brand'].notna() & (df['brand'] != '')
                        valid_rows = non_empty_account_types.sum() + non_empty_brands.sum()
                        has_valid_data = valid_rows > len(df) * 0.1
                    
                    if has_analysis_fields and has_valid_data:
                        # 直接复制为merged文件
                        import shutil
                        merged_path = os.path.join(RESULTS_FOLDER, merged_file)
                        shutil.copy2(file_path, merged_path)
                        custom_logger.info('✅ CSV already contains analysis results, copied as merged file')
                        merge_success = True
                    else:
                        # 执行合并逻辑
                        custom_logger.info('🔗 Merging results with original data...')
                        analysis_tasks[task_id]['progress'] = 'Merging results...'
                        merge_success = merge_results_with_original(file_path, os.path.join(RESULTS_FOLDER, brand_file), merged_file, custom_logger)
                except Exception as e:
                    custom_logger.error(f'❌ Error checking CSV format: {e}')
                    merge_success = False
            else:
                # 执行合并逻辑
                custom_logger.info('🔗 Merging results with original data...')
                analysis_tasks[task_id]['progress'] = 'Merging results...'
                merge_success = merge_results_with_original(file_path, os.path.join(RESULTS_FOLDER, brand_file), merged_file, custom_logger)
            
            # 首先定义品牌相关账号：有extracted_brand_name或者被标记为品牌/矩阵账号
            brand_related_results = [r for r in results if 
                                   (r.extracted_brand_name and r.extracted_brand_name.strip()) or 
                                   r.is_brand or r.is_matrix_account]
            non_brand_results = [r for r in results if r not in brand_related_results]
            
            # 按照account_type统计总创作者中的各类型数量（互斥分类）
            total_creators = len(results)
            official_account_count = sum(1 for r in results if r.is_brand)
            matrix_account_count = sum(1 for r in results if r.is_matrix_account)
            # UGC创作者：在品牌相关中且标记为UGC的创作者
            ugc_creator_count = sum(1 for r in brand_related_results if r.is_ugc_creator)
            # 非品牌创作者：不在品牌相关列表中的所有创作者
            non_branded_creator_count = len(non_brand_results)
            
            # 品牌相关账号中的分类统计（用于Brand Related Breakdown）
            brand_in_related = sum(1 for r in brand_related_results if r.is_brand)
            matrix_in_related = sum(1 for r in brand_related_results if r.is_matrix_account)
            ugc_in_related = sum(1 for r in brand_related_results if r.is_ugc_creator)
            
            # 更新任务状态为完成
            analysis_tasks[task_id]['status'] = 'completed'
            analysis_tasks[task_id]['progress'] = 'Analysis completed successfully!'
            analysis_tasks[task_id]['results'] = {
                'total_processed': total_creators,
                'brand_related_count': len(brand_related_results),
                'non_brand_count': total_creators - len(brand_related_results),
                'official_account_count': official_account_count,
                'matrix_account_count': matrix_account_count,
                'ugc_creator_count': ugc_creator_count,
                'non_branded_creator_count': non_branded_creator_count,
                # 各类型在总创作者中的百分比
                'official_account_percentage': round((official_account_count / total_creators) * 100) if total_creators > 0 else 0,
                'matrix_account_percentage': round((matrix_account_count / total_creators) * 100) if total_creators > 0 else 0,
                'ugc_creator_percentage': round((ugc_creator_count / total_creators) * 100) if total_creators > 0 else 0,
                'non_branded_creator_percentage': round((non_branded_creator_count / total_creators) * 100) if total_creators > 0 else 0,
                # Brand Related Breakdown - 在品牌相关账号中的百分比
                'brand_in_related': brand_in_related,
                'matrix_in_related': matrix_in_related,
                'ugc_in_related': ugc_in_related,
                'brand_in_related_percentage': round((brand_in_related / len(brand_related_results)) * 100) if len(brand_related_results) > 0 else 0,
                'matrix_in_related_percentage': round((matrix_in_related / len(brand_related_results)) * 100) if len(brand_related_results) > 0 else 0,
                'ugc_in_related_percentage': round((ugc_in_related / len(brand_related_results)) * 100) if len(brand_related_results) > 0 else 0,
                'brand_file': brand_file,
                'non_brand_file': non_brand_file,
                'merged_file': merged_file if merge_success else None
            }
            
            custom_logger.info(f'✅ Analysis completed! Total: {len(results)}, Brand Related: {len(brand_related_results)}, Non-Brand: {len(non_brand_results)}')
            
        else:
            analysis_tasks[task_id]['status'] = 'error'
            analysis_tasks[task_id]['progress'] = 'No results generated'
            custom_logger.error('❌ No results generated')
            
    except Exception as e:
        print(f"Error in run_csv_analysis for task {task_id}: {str(e)}")
        
        # 更新任务状态为错误
        error_msg = f"Analysis failed: {str(e)}"
        
        # 确保任务仍然存在
        if task_id in analysis_tasks:
            analysis_tasks[task_id]['status'] = 'error'
            analysis_tasks[task_id]['progress'] = error_msg
            analysis_tasks[task_id]['error_at'] = datetime.now().isoformat()
        
        # 也尝试记录到日志
        try:
            if 'custom_logger' in locals():
                custom_logger.error(f'❌ Analysis error: {str(e)}')
        except:
            pass
    
    finally:
        # 性能统计
        if 'start_time' in locals():
            execution_time = time.time() - start_time
            print(f"⏱️ [CSV Worker] Task {task_id} execution time: {execution_time:.2f}s")
            
            # 添加性能信息到任务数据中
            if task_id in analysis_tasks:
                analysis_tasks[task_id]['execution_time'] = execution_time
                analysis_tasks[task_id]['finished_at'] = datetime.now().isoformat()
        
        # 清理自定义logger
        try:
            if 'custom_logger' in locals():
                custom_logger.handlers = []
        except:
            pass
        
        print(f"🏁 [CSV Worker] CSV analysis thread for task {task_id} finished")

def check_and_process_analyzed_csv(csv_path, logger):
    """检查CSV是否已经包含分析结果，如果是则直接读取"""
    try:
        import pandas as pd
        from universal_brand_analyzer import CreatorAnalysis
        
        df = pd.read_csv(csv_path)
        
        # 检查是否包含分析结果字段
        analysis_fields = ['account_type', 'brand', 'email', 'recent_20_posts_views_avg', 
                          'recent_20_posts_like_avg', 'recent_20_posts_share_avg', 
                          'Posting Frequency', 'Stability Score']
        
        has_analysis_fields = all(field in df.columns for field in analysis_fields)
        
        # 检查字段是否有实际数据（不只是空值）
        has_valid_data = False
        if has_analysis_fields:
            # 检查是否有非空的分析结果
            non_empty_account_types = df['account_type'].notna() & (df['account_type'] != '')
            non_empty_brands = df['brand'].notna() & (df['brand'] != '')
            
            # 如果有至少10%的行有有效的account_type或brand数据，则认为已经分析过
            valid_rows = non_empty_account_types.sum() + non_empty_brands.sum()
            has_valid_data = valid_rows > len(df) * 0.1
        
        if has_analysis_fields and has_valid_data:
            logger.info('✅ CSV already contains analysis results, reading existing data...')
            
            results = []
            for _, row in df.iterrows():
                # 转换账户类型回布尔值
                account_type = str(row.get('account_type', 'ugc creator')).lower()
                is_brand = account_type == 'official account'
                is_matrix_account = account_type == 'matrix account'
                is_ugc_creator = account_type in ['ugc creator', 'non-branded creator']
                
                # 创建CreatorAnalysis对象
                analysis = CreatorAnalysis(
                    video_id=str(row.get('video_id', '')),
                    author_unique_id=str(row.get('user_unique_id', '')),
                    author_link=f"https://www.tiktok.com/@{row.get('user_unique_id', '')}",
                    signature=str(row.get('title', '')),  # 使用title作为signature
                    is_brand=is_brand,
                    is_matrix_account=is_matrix_account,
                    is_ugc_creator=is_ugc_creator,
                    extracted_brand_name=str(row.get('brand', '')),
                    brand_confidence=float(row.get('brand_confidence', 0)) if pd.notna(row.get('brand_confidence')) else 0.0,
                    analysis_details=str(row.get('analysis_details', '')),
                    author_followers_count=int(row.get('follower_count', 0)) if pd.notna(row.get('follower_count')) else 0,
                    author_followings_count=0,  # 不在原始CSV中
                    videoCount=0,  # 不在原始CSV中
                    author_avatar='',
                    create_times=str(row.get('date', '')),
                    email=str(row.get('email', '')),
                    recent_20_posts_views_avg=float(row.get('recent_20_posts_views_avg', 0)) if pd.notna(row.get('recent_20_posts_views_avg')) else 0.0,
                    recent_20_posts_like_avg=float(row.get('recent_20_posts_like_avg', 0)) if pd.notna(row.get('recent_20_posts_like_avg')) else 0.0,
                    recent_20_posts_share_avg=float(row.get('recent_20_posts_share_avg', 0)) if pd.notna(row.get('recent_20_posts_share_avg')) else 0.0,
                    posting_frequency=float(row.get('Posting Frequency', 0)) if pd.notna(row.get('Posting Frequency')) else 0.0,
                    stability_score=float(row.get('Stability Score', 0)) if pd.notna(row.get('Stability Score')) else 0.0
                )
                results.append(analysis)
            
            logger.info(f'📊 Read {len(results)} existing analysis results from CSV')
            return results
        else:
            if has_analysis_fields and not has_valid_data:
                logger.info('📋 CSV has analysis fields but no valid data, will perform new analysis')
            else:
                logger.info('❌ CSV does not contain analysis fields, will perform new analysis')
            return None
            
    except Exception as e:
        logger.error(f'❌ Error checking CSV: {e}')
        return None

def merge_results_with_original(original_csv_path, analysis_csv_path, output_filename, logger):
    """合并分析结果与原始数据"""
    try:
        import pandas as pd
        
        logger.info(f'📊 Loading original data from: {original_csv_path}')
        
        # 读取原始CSV文件
        original_df = pd.read_csv(original_csv_path)
        logger.info(f'📄 Original file contains {len(original_df)} rows')
        
        # 检查分析结果文件是否存在
        if not os.path.exists(analysis_csv_path):
            logger.error(f'❌ Analysis file not found: {analysis_csv_path}')
            return False
        
        # 读取分析数据文件
        analysis_df = pd.read_csv(analysis_csv_path)
        logger.info(f'📊 Analysis file contains {len(analysis_df)} rows')
        
        # 检查必需的列
        if 'video_id' not in original_df.columns:
            logger.error('❌ Original file missing video_id column')
            return False
        
        if 'video_id' not in analysis_df.columns:
            logger.error('❌ Analysis file missing video_id column')
            return False
        
        # 准备要合并的字段映射
        field_mapping = {
            'account_type': 'account_type',
            'brand': 'brand',
            'email': 'email', 
            'recent_20_posts_views_avg': 'recent_20_posts_views_avg',
            'recent_20_posts_like_avg': 'recent_20_posts_like_avg', 
            'recent_20_posts_share_avg': 'recent_20_posts_share_avg',
            'posting_frequency': 'Posting Frequency',
            'stability_score': 'Stability Score',
            'brand_confidence': 'brand_confidence',
            'analysis_details': 'analysis_details'
        }
        
        # 检查原始文件是否有这些字段，如果没有则创建
        for analysis_field, original_field in field_mapping.items():
            if original_field not in original_df.columns:
                logger.info(f'➕ Creating missing column: {original_field}')
                original_df[original_field] = ''
        
        # 执行合并
        logger.info('🔄 Merging data...')
        matched_count = 0
        updated_count = 0
        
        for index, row in original_df.iterrows():
            video_id = row['video_id']
            
            # 查找匹配的分析数据
            match = analysis_df[analysis_df['video_id'] == video_id]
            
            if not match.empty:
                matched_count += 1
                match_row = match.iloc[0]
                
                # 更新所有字段（强制更新）
                for analysis_field, original_field in field_mapping.items():
                    if analysis_field in analysis_df.columns and original_field in original_df.columns:
                        original_df.at[index, original_field] = match_row[analysis_field]
                        updated_count += 1
        
        logger.info(f'✅ Matched {matched_count} video IDs, updated {updated_count} field values')
        
        # 保存合并后的文件
        output_path = os.path.join(RESULTS_FOLDER, output_filename)
        logger.info(f'💾 Saving merged file to: {output_path}')
        original_df.to_csv(output_path, index=False)
        
        logger.info('🎉 Merge completed successfully!')
        return True
        
    except Exception as e:
        logger.error(f'❌ Merge failed: {str(e)}')
        return False

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'healthy', 'message': 'Brand Analyzer API is running'})

@app.route('/api/thread-pool-status', methods=['GET'])
def get_thread_pool_status():
    """获取线程池状态信息 - 监控分析性能"""
    # 统计正在运行的任务
    running_tasks = sum(1 for task in analysis_tasks.values() if task.get('status') == 'running')
    pending_tasks = sum(1 for task in analysis_tasks.values() if task.get('status') == 'pending')
    completed_tasks = sum(1 for task in analysis_tasks.values() if task.get('status') in ['completed', 'error'])
    
    # 检查有多少Future对象仍在运行
    active_futures = 0
    for task in analysis_tasks.values():
        future = task.get('future')
        if future and not future.done():
            active_futures += 1
    
    return jsonify({
        'thread_pool': {
            'max_workers': MAX_WORKERS,
            'active_futures': active_futures,
            'available_workers': MAX_WORKERS - active_futures
        },
        'tasks': {
            'total': len(analysis_tasks),
            'running': running_tasks,
            'pending': pending_tasks,
            'completed': completed_tasks
        },
        'performance': {
            'status': 'optimal' if active_futures < MAX_WORKERS else 'busy',
            'efficiency': f"{((MAX_WORKERS - active_futures) / MAX_WORKERS * 100):.1f}% available"
        }
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # 生成唯一的任务ID
        task_id = str(uuid.uuid4())
        
        # 保存上传的文件
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # 检测文件类型
        is_csv = file.filename.lower().endswith('.csv')
        file_type = 'CSV' if is_csv else 'JSON'
        
        # 初始化任务状态
        analysis_tasks[task_id] = {
            'status': 'pending',
            'progress': f'{file_type} file uploaded successfully, preparing to start analysis...',
            'file_path': file_path,
            'filename': file.filename,
            'file_type': file_type.lower(),
            'logs': [],
            'created_at': datetime.now().isoformat()
        }
        
        # 在线程池中运行分析任务 - 高效并发处理
        future = thread_pool.submit(run_analysis, task_id, file_path, is_csv)
        # 存储Future对象以便后续跟踪
        analysis_tasks[task_id]['future'] = future
        
        return jsonify({'task_id': task_id})
    
    return jsonify({'error': 'Unsupported file format, please upload JSON or CSV file'}), 400

@app.route('/api/status')
def get_status():
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({'error': 'Missing task_id parameter'}), 400
    
    print(f"Getting status for task {task_id}")
    print(f"Current tasks in memory: {list(analysis_tasks.keys())}")
    
    if task_id in analysis_tasks:
        task_data = analysis_tasks[task_id]
        print(f"Task {task_id} status: {task_data.get('status', 'unknown')}")
        
        # 添加调试信息
        debug_info = {
            'task_exists': True,
            'current_tasks_count': len(analysis_tasks),
            'task_created_at': task_data.get('created_at', 'unknown')
        }
        
        # 创建可JSON序列化的响应数据（排除Future对象）
        response_data = {k: v for k, v in task_data.items() if k != 'future'}
        response_data['debug'] = debug_info
        
        # 添加线程池状态信息
        future = task_data.get('future')
        if future:
            response_data['thread_status'] = {
                'is_running': not future.done(),
                'is_completed': future.done()
            }
        
        return jsonify(response_data)
    
    print(f"Task {task_id} not found in analysis_tasks")
    return jsonify({
        'error': 'Task not found', 
        'debug': {
            'task_exists': False,
            'current_tasks_count': len(analysis_tasks),
            'available_tasks': list(analysis_tasks.keys())[:5]  # 只显示前5个任务ID
        }
    }), 404

@app.route('/api/analyze-csv', methods=['POST'])
def analyze_csv():
    """直接分析指定的CSV文件"""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({'error': 'Missing file_path parameter'}), 400
        
        file_path = data['file_path']
        
        # 确保文件存在
        full_path = os.path.join(os.getcwd(), file_path)
        if not os.path.exists(full_path):
            return jsonify({'error': f'File not found: {file_path}'}), 404
        
        # 检查文件是否为CSV
        if not file_path.lower().endswith('.csv'):
            return jsonify({'error': 'Only CSV files are supported'}), 400
        
        # 生成唯一的任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        analysis_tasks[task_id] = {
            'status': 'pending',
            'progress': 'CSV file detected, starting analysis...',
            'file_path': full_path,
            'filename': os.path.basename(file_path),
            'file_type': 'csv',
            'logs': [],
            'created_at': datetime.now().isoformat()
        }
        
        # 在线程池中运行CSV分析任务 - 高效并发处理
        future = thread_pool.submit(run_csv_analysis, task_id, full_path)
        # 存储Future对象以便后续跟踪
        analysis_tasks[task_id]['future'] = future
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/api/download')
def download_file():
    task_id = request.args.get('task_id')
    file_type = request.args.get('file_type')
    
    if not task_id or not file_type:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    if task_id not in analysis_tasks:
        return jsonify({'error': 'Task not found'}), 404
    
    task = analysis_tasks[task_id]
    if task['status'] != 'completed':
        return jsonify({'error': 'Analysis not completed yet'}), 400
    
    if file_type == 'brand_related':
        filename = task['results']['brand_file']
    elif file_type == 'non_brand':
        filename = task['results']['non_brand_file']
    elif file_type == 'merged':
        filename = task['results'].get('merged_file')
        if not filename:
            return jsonify({'error': 'Merged file not available'}), 400
    else:
        return jsonify({'error': 'Invalid file type'}), 400
    
    file_path = os.path.join(RESULTS_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=filename)
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/logs')
def get_logs():
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({'error': 'Missing task_id parameter'}), 400
    
    print(f"Getting logs for task {task_id}")
    
    if task_id in analysis_tasks:
        logs = analysis_tasks[task_id].get('logs', [])
        print(f"Task {task_id} has {len(logs)} log entries")
        return jsonify({'logs': logs})
    
    print(f"Task {task_id} not found for logs")
    return jsonify({'error': 'Task not found'}), 404

if __name__ == '__main__':
    start_cleanup_thread() # 启动清理线程
    app.run(debug=True, host='0.0.0.0', port=5000) 