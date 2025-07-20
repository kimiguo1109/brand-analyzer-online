#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用品牌创作者分析器
支持动态数据源和通用品牌判断条件
"""

import os
import sys
import json
import csv
import time
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from google import genai
from google.genai import types
import statistics
import re
import random
import glob

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API配置
GEMINI_API_KEY = 'AIzaSyB8GkbKtlc9OfyHE2c_wasXpCatYRC11IY'
RAPIDAPI_KEY = '34ba1ae26fmsha15de959b0b5d6ep11e6e6jsn64ad77705138'

# 大型科技公司列表（需要更严格的判断）
MAJOR_TECH_COMPANIES = {
    'apple', 'microsoft', 'google', 'amazon', 'facebook', 'meta', 'samsung', 
    'sony', 'intel', 'nvidia', 'ibm', 'oracle', 'adobe', 'salesforce', 
    'netflix', 'uber', 'twitter', 'linkedin', 'snapchat', 'tiktok', 'instagram'
}

@dataclass
class CreatorAnalysis:
    """创作者分析结果"""
    video_id: str
    author_unique_id: str
    author_link: str
    signature: str
    is_brand: bool
    is_matrix_account: bool
    is_ugc_creator: bool
    extracted_brand_name: str
    brand_confidence: float
    analysis_details: str
    author_followers_count: int
    author_followings_count: int
    videoCount: int
    author_avatar: str
    create_times: str
    
    # 新增字段
    email: str = ""
    recent_20_posts_views_avg: float = 0.0
    recent_20_posts_like_avg: float = 0.0
    recent_20_posts_share_avg: float = 0.0
    posting_frequency: float = 0.0
    stability_score: float = 0.0
    brands_in_videos: List[str] = None
    
    def __post_init__(self):
        if self.brands_in_videos is None:
            self.brands_in_videos = []

@dataclass
class VideoData:
    """视频数据结构"""
    video_id: str
    title: str
    play_count: int
    digg_count: int
    share_count: int
    create_time: int

@dataclass
class AnalysisProgress:
    """分析进度跟踪"""
    total_creators: int
    completed_creators: int
    failed_creators: int
    current_batch: int
    errors: List[str]
    
    def __post_init__(self):
        self.errors = []

class UniversalBrandAnalyzer:
    """通用品牌分析器"""
    
    def __init__(self, output_dir: str = "analyzed_data", custom_logger=None):
        self.output_dir = output_dir
        self.results_dir = os.path.join(output_dir, "results")
        self.cache_dir = os.path.join(output_dir, "cache")
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.logger = custom_logger or logger
        self.logger.info(f"Universal Brand Analyzer initialized, output dir: {output_dir}")
        
        # 配置Gemini API - 使用新的Client方式
        try:
            self.client = genai.Client(api_key=GEMINI_API_KEY)
            self.logger.info("Gemini client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini client: {e}")
            self.client = None
        
        # 防ban机制配置
        self.api_call_count = 0
        self.last_api_call_time = 0
        self.rate_limit_delay = 1  # 基础延迟1秒
        self.max_api_calls_per_minute = 50  # 每分钟最多50次API调用
        
        # 进度跟踪
        self.progress = None
        self.report_file = None
        
        # 缓存相关
        self.cache_file = None
        self.analyzed_users = set()  # 已分析的用户ID
        self.realtime_csv_file = None  # 实时保存的CSV文件
        
    def init_progress_tracking(self, total_creators: int):
        """初始化进度跟踪"""
        self.progress = AnalysisProgress(
            total_creators=total_creators,
            completed_creators=0,
            failed_creators=0,
            current_batch=1,
            errors=[]
        )
        
        # 创建报告文件 (不使用时间戳，确保只有一个报告文件)
        self.report_file = os.path.join(self.results_dir, f"analysis_report.txt")
        
        with open(self.report_file, 'w', encoding='utf-8') as f:
            f.write(f"品牌分析报告\n")
            f.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总创作者数: {total_creators}\n")
            f.write(f"{'='*50}\n\n")
            
    def update_progress(self, creator_id: str, success: bool = True, error_msg: str = None):
        """更新进度"""
        if not self.progress:
            return
            
        if success:
            self.progress.completed_creators += 1
        else:
            self.progress.failed_creators += 1
            if error_msg:
                self.progress.errors.append(f"{creator_id}: {error_msg}")
        
        # 记录进度日志
        progress_pct = (self.progress.completed_creators / self.progress.total_creators) * 100
        self.logger.info(f"分析进度: {self.progress.completed_creators}/{self.progress.total_creators} "
                        f"({progress_pct:.1f}%) - 成功: {self.progress.completed_creators}, "
                        f"失败: {self.progress.failed_creators}")
        
        # 更新报告文件
        if self.report_file:
            with open(self.report_file, 'a', encoding='utf-8') as f:
                status = "成功" if success else "失败"
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {creator_id}: {status}\n")
                if error_msg:
                    f.write(f"  错误: {error_msg}\n")
                    
    def finalize_report(self):
        """完成报告"""
        if not self.report_file or not self.progress:
            return
            
        with open(self.report_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*50}\n")
            f.write(f"分析完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总创作者数: {self.progress.total_creators}\n")
            f.write(f"成功分析: {self.progress.completed_creators}\n")
            f.write(f"失败数量: {self.progress.failed_creators}\n")
            f.write(f"成功率: {(self.progress.completed_creators/self.progress.total_creators)*100:.1f}%\n")
            
            if self.progress.errors:
                f.write(f"\n错误详情:\n")
                for error in self.progress.errors:
                    f.write(f"  - {error}\n")
                    
        self.logger.info(f"分析报告已保存: {self.report_file}")
                    
    def wait_for_rate_limit(self):
        """防ban机制：控制API调用频率"""
        current_time = time.time()
        
        # 检查是否需要等待
        if current_time - self.last_api_call_time < self.rate_limit_delay:
            wait_time = self.rate_limit_delay - (current_time - self.last_api_call_time)
            time.sleep(wait_time)
            
        # 更新API调用计数
        self.api_call_count += 1
        self.last_api_call_time = time.time()
        
        # 如果API调用过于频繁，增加延迟
        if self.api_call_count % self.max_api_calls_per_minute == 0:
            self.logger.info(f"已调用API {self.api_call_count} 次，休息5秒防止被ban")
            time.sleep(5)
            # 随机延迟避免固定模式
            time.sleep(random.uniform(0.5, 2.0))
            
        # 每100次调用后增加基础延迟
        if self.api_call_count % 100 == 0:
            self.rate_limit_delay = min(self.rate_limit_delay * 1.2, 3.0)
            self.logger.info(f"调整API调用延迟为: {self.rate_limit_delay:.1f}秒")
    
    def convert_timestamp_to_date(self, timestamp) -> str:
        """将Unix时间戳转换为年月日格式"""
        try:
            if timestamp and str(timestamp).isdigit():
                dt = datetime.fromtimestamp(int(timestamp))
                return dt.strftime('%Y-%m-%d')
            return ""
        except (ValueError, OSError) as e:
            self.logger.warning(f"时间戳转换失败: {timestamp}, 错误: {e}")
            return ""
    
    def get_tiktok_user_posts(self, unique_id: str, count: int = 20) -> List[VideoData]:
        """获取TikTok用户的最近视频数据"""
        url = f"https://tiktok-scraper7.p.rapidapi.com/user/posts"
        
        params = {
            'unique_id': unique_id,
            'count': count,
            'cursor': 0
        }
        
        headers = {
            'x-rapidapi-host': 'tiktok-scraper7.p.rapidapi.com',
            'x-rapidapi-key': RAPIDAPI_KEY
        }
        
        # 添加重连机制，最多重试5次
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=15)
                self.logger.debug(f"TikTok API请求 {unique_id}: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('code') == 0 and data.get('data') and data['data'].get('videos'):
                        videos = data['data']['videos']
                        video_data = []
                        
                        for video in videos:
                            video_data.append(VideoData(
                                video_id=video.get('video_id', ''),
                                title=video.get('title', ''),
                                play_count=video.get('play_count', 0),
                                digg_count=video.get('digg_count', 0),
                                share_count=video.get('share_count', 0),
                                create_time=video.get('create_time', 0)
                            ))
                        
                        self.logger.info(f"获取到用户 {unique_id} 的 {len(video_data)} 个视频数据")
                        return video_data
                    else:
                        self.logger.warning(f"TikTok API返回错误: {data.get('msg', 'Unknown error')}")
                        # 如果是API响应错误，尝试重连
                        if attempt < max_retries - 1:
                            self.logger.info(f"TikTok API请求失败，正在重试... (尝试 {attempt + 2}/{max_retries})")
                            time.sleep(1)  # 等待1秒后重试
                            continue
                        return []
                else:
                    self.logger.warning(f"TikTok API请求失败: {response.status_code}")
                    # 如果是HTTP错误，尝试重连
                    if attempt < max_retries - 1:
                        self.logger.info(f"TikTok API请求失败，正在重试... (尝试 {attempt + 2}/{max_retries})")
                        time.sleep(1)  # 等待1秒后重试
                        continue
                    return []
                    
            except Exception as e:
                self.logger.error(f"获取用户 {unique_id} 视频数据失败: {str(e)}")
                if attempt < max_retries - 1:
                    self.logger.info(f"TikTok API请求异常，正在重试... (尝试 {attempt + 2}/{max_retries})")
                    time.sleep(1)  # 等待1秒后重试
                    continue
                return []
        
        # 如果所有重试都失败了
        self.logger.error(f"TikTok API请求失败，已重试 {max_retries} 次")
        return []
    
    def calculate_video_metrics(self, videos: List[VideoData]) -> Dict:
        """计算视频指标"""
        if not videos:
            return {
                'avg_views': 0,
                'avg_likes': 0,
                'avg_shares': 0,
                'posting_frequency': 0,
                'stability_score': 0
            }
        
        # 计算平均值
        avg_views = sum(v.play_count for v in videos) / len(videos)
        avg_likes = sum(v.digg_count for v in videos) / len(videos)
        avg_shares = sum(v.share_count for v in videos) / len(videos)
        
        # 计算发布频率 (每天发布视频数)
        if len(videos) > 1:
            # 获取时间范围
            timestamps = [v.create_time for v in videos if v.create_time > 0]
            if len(timestamps) >= 2:
                timestamps.sort()
                time_span_days = (timestamps[-1] - timestamps[0]) / (24 * 3600)
                posting_frequency = len(videos) / max(time_span_days, 1) if time_span_days > 0 else 0
            else:
                posting_frequency = 0
        else:
            posting_frequency = 0
        
        # 计算稳定性分数 (基于观看次数的变异系数)
        if len(videos) > 1:
            view_counts = [v.play_count for v in videos]
            if any(count > 0 for count in view_counts):
                mean_views = statistics.mean(view_counts)
                if mean_views > 0:
                    std_views = statistics.stdev(view_counts)
                    # 变异系数越小，稳定性越高，所以用1减去变异系数
                    cv = std_views / mean_views
                    stability_score = max(0, 1 - cv)
                else:
                    stability_score = 0
            else:
                stability_score = 0
        else:
            stability_score = 0
        
        return {
            'avg_views': avg_views,
            'avg_likes': avg_likes,
            'avg_shares': avg_shares,
            'posting_frequency': posting_frequency,
            'stability_score': min(1.0, stability_score)  # 限制在0-1之间
        }
    
    def extract_email_from_signature(self, signature: str) -> str:
        """从签名中提取邮箱"""
        if not signature:
            return ""
        
        # 邮箱正则表达式
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, signature)
        
        if matches:
            return matches[0]
        return ""
    
    def filter_brand_name(self, brand_name: str, account_type: str) -> str:
        """过滤和清理brand name"""
        if not brand_name or not brand_name.strip():
            return ""
        
        # 对于official account和matrix account，直接返回品牌名
        if account_type in ['official account', 'matrix account']:
            return brand_name.strip()
        
        # 对于ugc creator，需要过滤掉明显不是brand name的内容
        if account_type == 'ugc creator':
            # 分割多个品牌名称
            brands = [b.strip() for b in brand_name.split(',')]
            filtered_brands = []
            
            for brand in brands:
                if not brand:
                    continue
                
                # 首先检查是否是已知品牌
                known_brands = ['nike', 'adidas', 'apple', 'samsung', 'google', 'microsoft', 'chanel', 'dior', 'gucci', 'prada', 'versace', 'sephora', 'ulta', 'lululemon', 'nordstrom', 'zara', 'forever21', 'uniqlo', 'target', 'walmart', 'amazon', 'shein', 'asos', 'boohoo', 'revolve', 'fenty', 'glossier', 'cerave', 'neutrogena', 'olay', 'clinique', 'lancome', 'nars', 'benefit', 'tarte', 'mac', 'maybelline', 'revlon', 'covergirl', 'loreal', 'nyx', 'morphe', 'kylie', 'rare beauty', 'drunk elephant', 'the ordinary', 'la roche posay', 'estee lauder', 'tom ford', 'charlotte tilbury', 'urban decay', 'too faced', 'smashbox', 'bobbi brown', 'essence', 'milani', 'elf', 'colourpop', 'anastasia', 'coach', 'michael kors', 'kate spade', 'marc jacobs', 'tory burch', 'rebecca minkoff', 'cartier', 'tiffany', 'bulgari', 'rolex', 'omega', 'casio', 'fossil', 'daniel wellington', 'anthropologie', 'free people', 'reformation', 'everlane', 'ganni', 'staud', 'jacquemus', 'bottega veneta', 'saint laurent', 'balenciaga', 'givenchy', 'celine', 'hermes', 'louis vuitton', 'scentbird', 'perfumacy', 'cave']
                
                # 如果是已知品牌，直接保留
                if (brand.lower() in known_brands or 
                    brand.lower().replace(' ', '').replace('-', '') in known_brands):
                    filtered_brands.append(brand)
                    continue
                
                # 对于非已知品牌，应用过滤条件
                invalid_indicators = [
                    # 人名特征
                    len(brand) < 3,  # 太短
                    brand.lower() in ['andrea', 'josh', 'leam', 'tiktok', 'tiktokm', 'instagram', 'facebook', 'twitter', 'youtube', 'snapchat', 'whatsapp', 'linkedin', 'pinterest', 'reddit', 'discord'],  # 常见人名/平台名
                    brand.endswith('__'),  # 用户名格式
                    brand.startswith('@'),  # 用户名格式
                    brand.lower() in ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once'],  # 常见词汇
                    # 检查是否只包含数字和特殊字符
                    not re.search(r'[a-zA-Z]', brand),  # 必须包含字母
                    # 检查是否包含过多特殊字符
                    len(re.findall(r'[_\-\.@#]', brand)) > len(brand) * 0.3,  # 特殊字符不能超过30%
                    # 检查是否是明显的非品牌词汇
                    brand.lower() in ['none', 'null', 'empty', 'unknown', 'undefined', 'n/a', 'na', 'test', 'example', 'sample', 'demo'],  # 无效词汇
                    # 检查是否包含明显的人名模式（仅对非已知品牌）
                    re.match(r'^[A-Z][a-z]+$', brand) and len(brand) <= 6 and brand.lower() in ['john', 'mike', 'sarah', 'anna', 'david', 'emma', 'james', 'lisa', 'robert', 'maria', 'andrea', 'josh', 'leam', 'alex', 'kate', 'tom', 'jane', 'bob', 'amy', 'peter'],  # 常见人名
                    # 检查是否是数字序列
                    brand.isdigit(),  # 纯数字
                    # 检查是否是随机字符串
                    len(set(brand.lower())) < 3,  # 字符多样性太低
                ]
                
                if not any(invalid_indicators):
                    # 进一步检查是否是有效的品牌名
                    if len(brand) >= 3 and brand.replace(' ', '').replace('-', '').replace('.', '').isalnum():
                        # 检查是否符合品牌名称特征
                        if ((len(brand) >= 4 and brand.istitle() and ' ' not in brand) or  # 单词首字母大写品牌
                            (len(brand.split()) <= 3 and all(word.istitle() for word in brand.split()))):  # 多词品牌名
                            filtered_brands.append(brand)
            
            if filtered_brands:
                return ', '.join(filtered_brands)
            else:
                return ""
        
        return brand_name.strip()
    
    def get_account_type(self, analysis_result: Dict) -> str:
        """根据分析结果获取账户类型"""
        brand_name = analysis_result.get('brand_name', '')
        
        if analysis_result.get('is_brand', False):
            return 'official account'
        elif analysis_result.get('is_matrix_account', False):
            return 'matrix account'
        elif analysis_result.get('is_ugc_creator', False):
            # 检查是否有品牌名称
            if brand_name and brand_name.strip():
                return 'ugc creator'
            else:
                return 'non-branded creator'
        else:
            # 默认情况，检查是否有品牌名称
            if brand_name and brand_name.strip():
                return 'ugc creator'
            else:
                return 'non-branded creator'
    
    def extract_business_name_from_signature(self, signature: str) -> str:
        """从签名中提取商店/企业名称"""
        if not signature:
            return ""
        
        # 增强的商店名称模式
        patterns = [
            # 完整商店格式：Name + 商店类型 (完整匹配)
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:barber\s+shop|barbershop|salon|restaurant|cafe|clinic|store|shop|spa|gym|fitness|studio|boutique|market|bakery|pharmacy|hotel|motel))',
            # 大写格式：NAME BARBERSHOP, NAME RESTAURANT 等
            r'([A-Z][A-Z\s]+?\s+(?:BARBERSHOP|BARBER\s+SHOP|SALON|RESTAURANT|CAFE|CLINIC|STORE|SHOP|SPA|GYM|FITNESS|STUDIO|BOUTIQUE|MARKET|BAKERY|PHARMACY|HOTEL|MOTEL))',
            # 特定格式：Bob's Barber Shop, Maria's Salon
            r'([A-Z][a-z]+(?:\'s)?\s+(?:barber\s+shop|barbershop|salon|restaurant|cafe|clinic|store|shop|spa|gym|fitness|studio|boutique|market|bakery|pharmacy|hotel|motel))',
            # 多词格式：Bob's Barber Shop, Maria's Beauty Salon
            r'([A-Z][a-z]+(?:\'s)?\s+[A-Z][a-z]+\s+(?:barber\s+shop|barbershop|salon|restaurant|cafe|clinic|store|shop|spa|gym|fitness|studio|boutique|market|bakery|pharmacy|hotel|motel))',
            # 位置信息：Location: Bob Barber Shop, Visit us at: Maria's Salon
            r'location:\s*([^,\n]+)',
            r'visit\s+us\s+at\s*:\s*([^,\n]+)',
            # 地址格式：Address: 商店名
            r'address:\s*([^,\n]+)',
            # 联系方式后的商店名：Call us at 商店名
            r'(?:call\s+us\s+at|phone|contact):\s*([^,\n]+)',
            # 营业时间指示的商店名：Open at 商店名
            r'(?:open\s+at|find\s+us\s+at|visit\s+us):\s*([^,\n]+)',
            # 服务描述：Professional at 商店名
            r'(?:professional\s+at|working\s+at|employed\s+at):\s*([^,\n]+)',
            # 特定地区格式：CUKURBE BARBERSHOP sentul
            r'([A-Z][A-Z\s]+?\s+(?:BARBERSHOP|BARBER\s+SHOP|SALON|RESTAURANT|CAFE|CLINIC|STORE|SHOP|SPA|GYM|FITNESS|STUDIO|BOUTIQUE|MARKET|BAKERY|PHARMACY|HOTEL|MOTEL))\s+[a-z]+',
            # 简单格式：Name Barber, Name Salon (不带Shop)
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:barber|salon|restaurant|cafe|clinic|store|shop|spa|gym|fitness|studio|boutique|market|bakery|pharmacy|hotel|motel)(?:\s|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, signature, re.IGNORECASE)
            if match:
                business_name = match.group(1).strip()
                
                # 清理常见的无关词汇和标点符号
                business_name = re.sub(r'location:?\s*', '', business_name, flags=re.IGNORECASE)
                business_name = re.sub(r'visit\s+us\s+at\s*:?\s*', '', business_name, flags=re.IGNORECASE)
                business_name = re.sub(r'address:?\s*', '', business_name, flags=re.IGNORECASE)
                business_name = re.sub(r'(?:call\s+us\s+at|phone|contact):?\s*', '', business_name, flags=re.IGNORECASE)
                business_name = re.sub(r'(?:open\s+at|find\s+us\s+at):?\s*', '', business_name, flags=re.IGNORECASE)
                business_name = re.sub(r'(?:professional\s+at|working\s+at|employed\s+at):?\s*', '', business_name, flags=re.IGNORECASE)
                business_name = re.sub(r'[^\w\s\'&-]', '', business_name)  # 保留基本标点符号
                business_name = business_name.strip()
                
                # 确保名称不为空且有意义
                if len(business_name) > 2 and not business_name.lower() in ['the', 'and', 'or', 'at', 'in', 'on', 'with', 'for', 'by']:
                    # 如果是全大写，转换为标题格式
                    if business_name.isupper():
                        return business_name.title()
                    else:
                        return business_name
        
        # 如果没有找到明确的商店模式，尝试提取可能的品牌名称
        # 查找可能的品牌提及
        brand_patterns = [
            r'(?:brand|company|business):\s*([^,\n]+)',
            r'(?:owner\s+of|founder\s+of|ceo\s+of):\s*([^,\n]+)',
            r'(?:representing|working\s+for|employed\s+by):\s*([^,\n]+)',
            r'(@[a-zA-Z0-9_]+)',  # 社交媒体句柄
        ]
        
        for pattern in brand_patterns:
            match = re.search(pattern, signature, re.IGNORECASE)
            if match:
                brand_name = match.group(1).strip()
                # 清理@符号
                brand_name = re.sub(r'@', '', brand_name)
                brand_name = re.sub(r'[^\w\s\'&-]', '', brand_name)
                brand_name = brand_name.strip()
                
                if len(brand_name) > 2 and not brand_name.lower() in ['the', 'and', 'or', 'at', 'in', 'on', 'with', 'for', 'by']:
                    return brand_name.title()
        
        return ""
    
    def analyze_creator_brands_from_videos(self, videos: List[VideoData]) -> List[str]:
        """从视频标题中分析品牌信息"""
        brands = set()
        
        for video in videos:
            title = video.title.lower()
            
            # 查找品牌标签和提及
            brand_patterns = [
                r'@(\w+)',  # @brand mentions
                r'#(\w+)partner',  # #brandpartner
                r'#(\w+)ambassador',  # #brandambassador
                r'#(\w+)ad',  # #brandad
                r'#ad\s+(\w+)',  # #ad brand
                r'sponsored\s+by\s+(\w+)',  # sponsored by brand
            ]
            
            for pattern in brand_patterns:
                matches = re.findall(pattern, title)
                for match in matches:
                    if len(match) > 2:  # 过滤掉太短的匹配
                        brands.add(match.capitalize())
        
        return list(brands)
    
    def get_tiktok_user_info(self, unique_id: str) -> Dict:
        """获取TikTok用户信息"""
        if not unique_id or unique_id == 'None':
            return self._default_user_info()
            
        url = "https://tiktok-scraper7.p.rapidapi.com/user/info"
        querystring = {"unique_id": unique_id}
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "tiktok-scraper7.p.rapidapi.com"
        }
        
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0 and 'data' in data:
                    user_data = data['data'].get('user', {})
                    stats_data = data['data'].get('stats', {})
                    return {
                        'signature': user_data.get('signature', ''),
                        'followerCount': stats_data.get('followerCount', 0),
                        'followingCount': stats_data.get('followingCount', 0),
                        'videoCount': stats_data.get('videoCount', 0),
                        'avatar': user_data.get('avatarThumb', ''),
                        'author_followers_count': stats_data.get('followerCount', 0),
                        'author_followings_count': stats_data.get('followingCount', 0),
                        'author_avatar': user_data.get('avatarThumb', '')
                    }
                else:
                    self.logger.warning(f"TikTok API 返回错误代码: {data.get('code', 'unknown')} for {unique_id}")
            else:
                self.logger.warning(f"TikTok API请求失败: {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"获取TikTok用户信息时出错 {unique_id}: {e}")
            
        return self._default_user_info()
    
    def _default_user_info(self) -> Dict:
        """返回默认用户信息"""
        return {
            'signature': '',
            'followerCount': 0,
            'followingCount': 0,
            'videoCount': 0,
            'avatar': '',
            'author_followers_count': 0,
            'author_followings_count': 0,
            'author_avatar': ''
        }
    
    def is_official_account(self, unique_id: str, nickname: str, signature: str) -> bool:
        """检查是否为官方账号"""
        official_indicators = [
            'official', 'verified', '@company.com', '@brand.com', 
            'team', 'support', 'headquarters', 'corporate'
        ]
        
        combined_text = f"{unique_id} {nickname} {signature}".lower()
        return any(indicator in combined_text for indicator in official_indicators)
    
    def analyze_creator_with_gemini(self, signature: str, nickname: str, unique_id: str, context: str = "", user_info: Dict = None) -> Dict:
        """使用Gemini API分析创作者类型"""
        
        is_official = self.is_official_account(unique_id, nickname, signature)
        
        prompt = f"""Analyze the following TikTok creator profile and classify them into ONE of these three categories:

Creator Username: {unique_id}
Display Name: {nickname}
Bio/Signature: {signature}
Is Official Account: {is_official}
Content Context: {context}

CLASSIFICATION CATEGORIES:

1. OFFICIAL_BRAND: Official brand/company accounts or primary promotional accounts
   - Username contains the brand/product name (e.g., @appname, @brandname, @productname)
   - Bio directly promotes their own product/service with app store links, download calls
   - Clear company branding and product ownership
   - Primary account representing the brand/product
   - **BRAND.CATEGORY FORMAT**: Usernames like @brand.beauty, @brand.official, @brand.store indicate official accounts
   - **DOMAIN-LIKE FORMAT**: Usernames ending in .id, .app, .store, .shop, .ca, .com, .co, .uk, .us often indicate official accounts
   - **REGIONAL BRAND FORMAT**: Brand names with regional/geographic identifiers (e.g., @garniermenid, @dovemenarabia, @kahfeveryday.my)
   - **PRODUCT LINE FORMAT**: Brand names with product line identifiers (e.g., @brandmen, @brandwomen, @brandkids)
   - **KNOWN BRAND NAMES**: Any username containing established brand names (luxury, tech, beauty brands)
   - **AFFILIATE PROGRAMS**: Accounts offering affiliate commissions are often official brand accounts
   - **IMPORTANT**: For major brands (Nike, Apple, Google, etc.), if the username exactly matches the brand name, it should be classified as OFFICIAL_BRAND
   - **LUXURY/BEAUTY BRANDS**: Chanel, Dior, Gucci, Prada, Versace, Louis Vuitton, Hermès, Cartier, Tiffany, Bulgari, etc.
   - **FRAGRANCE/COSMETICS**: Sephora, Ulta, L'Oréal, Maybelline, CoverGirl, Revlon, MAC, Urban Decay, etc.
   - **REGIONAL VARIANTS**: Garnier (garniermenid), Dove (dovemenarabia), Kahf (kahfeveryday.my), etc.
   - Examples: @getnoteai, @ainotebook_app, @quizard.ai, @notabilityapp, @nike, @apple, @google, @chanel.beauty, @cave.id, @perfumacy.ca, @prada, @x.ssenz, @garniermenid, @dovemenarabia, @kahfeveryday.my

2. MATRIX_ACCOUNT: Creator profiles with clear connection to a specific brand/business but NOT the main official account
   - Profile has obvious brand links, descriptions, partnerships with ONE specific brand
   - Bio mentions working for/with a specific company or brand
   - Clear affiliation or employment with a particular brand shown in profile
   - Consistent promotion of a single brand across content
   - **BUSINESS REPRESENTATIVES**: Accounts representing specific local businesses, shops, or services
     * Barber shop employees/owners: "Bob Barber Shop Location: new Cairo", "CUKURBE BARBERSHOP sentul"
     * Restaurant staff: "Manager at Pizza Palace", "Chef at Mario's Kitchen"
     * Salon workers: "Stylist at Beauty Lounge", "Nails by Sarah Salon"
     * Shop owners: "Owner of Tech Store", "Fashion Boutique NYC"
   - **IMPORTANT**: Only use this if the account is clearly NOT the main official account
   - Examples: "Apple employee", "Brand ambassador for Nike", "Working at Tesla", regional brand accounts, local business representatives

3. UGC_CREATOR: Only creators with clear brand partnership signals OR regular users
   - Look for these SPECIFIC SIGNALS of brand partnerships:
     * Brand mentions/tags in content or bio
     * Use of #ad, #sponsored, #partner tags
     * Disclosure of partnerships or sponsorships
     * Bio links to brand/store (Shopify, LTK, etc.)
     * Discount codes or affiliate links mentioned
     * Call-to-actions encouraging purchases ("Use my code X")
     * Consistent posting about same brand/products with commercial intent
   - Examples: @brandnat with #tldvpartner, creators with discount codes, affiliate marketers
   - **CRITICAL**: Only assign brand name if clear partnership signals exist
   - **NO BRAND NAME** for: product reviewers, general content creators, personal accounts
   - **NEVER** assign random words, people names, or generic terms as brand names

CRITICAL CLASSIFICATION RULES:
1. If the USERNAME exactly matches a major brand name (nike, apple, google, etc.) → OFFICIAL_BRAND
2. If the USERNAME contains a product/brand name AND the bio promotes that same product → OFFICIAL_BRAND
3. **OFFICIAL ACCOUNT PRIORITY SIGNALS**: These patterns strongly indicate OFFICIAL_BRAND:
   - Username format: @brand.category (e.g., @chanel.beauty, @nike.store, @apple.official)
   - Username format: @brand.domain (e.g., @cave.id, @brand.app, @company.shop)
   - Username format: @brand.country (e.g., @perfumacy.ca, @brand.com, @store.uk)
   - Known luxury/beauty brands: Chanel, Dior, Gucci, Louis Vuitton, etc.
   - Affiliate program mentions: "Join Our Affiliate", "Get Commission"
   - Professional product promotion without location/contact info
4. If profile clearly shows connection to ONE specific brand (but not official account) → MATRIX_ACCOUNT  
5. **BUSINESS REPRESENTATIVES**: If bio contains business location/contact info or represents a specific local business → MATRIX_ACCOUNT
   - Look for: business addresses, phone numbers, "Location:", shop names, service descriptions
   - Examples: "Bob Barber Shop Location: new Cairo", "CUKURBE BARBERSHOP sentul", "Pizza Palace - Call 123-456"
6. For UGC_CREATOR: ONLY assign brand name if clear partnership signals exist (tags, codes, sponsorship disclosure)
7. Content creators who just review/mention products WITHOUT partnership signals should be UGC_CREATOR with NO brand name
8. **STRICT BRAND NAME POLICY**: UGC_CREATOR brand names must be legitimate brands, not random words, people names, or generic terms
9. For major tech companies (Apple, Google, etc.), be strict about "official" indicators for OFFICIAL_BRAND
10. For smaller apps/products, if username = product name → OFFICIAL_BRAND
11. **PERSONAL vs BUSINESS**: Personal creators doing their profession (individual barbers, chefs, etc.) = UGC_CREATOR; Business representatives = MATRIX_ACCOUNT
12. **PRECEDENCE**: OFFICIAL_BRAND signals override MATRIX_ACCOUNT classification
13. Only ONE category should be True, others must be False

Please respond with EXACTLY 6 values separated by pipes (|):

1. OFFICIAL_BRAND [True/False]
2. MATRIX_ACCOUNT [True/False] 
3. UGC_CREATOR [True/False]
4. Brand Name [Specific brand name or "None"] - Extract the specific brand/business name:
   - For OFFICIAL_BRAND: Use the main brand name (e.g., "Nike", "Apple", "GetNote AI")
   - For MATRIX_ACCOUNT: Extract business name from bio (e.g., "Bob Barber Shop", "CUKURBE BARBERSHOP", "Pizza Palace")
   - For UGC_CREATOR: Only if clear partnership signals exist (tags, codes, sponsorship disclosure)
5. Confidence Score [0.0-1.0] - How confident are you in this classification?
6. Analysis Details [Brief explanation] - Explain your classification reasoning and any partnership signals found

Examples:
- True|False|False|GetNote AI|0.95|Username contains brand name 'getnoteai' and bio promotes GetNote AI app
- True|False|False|Nike|0.95|Username exactly matches major brand 'nike' - this is the official Nike account
- True|False|False|Chanel|0.95|Username 'chanel.beauty' follows brand.category format - official Chanel beauty account
- True|False|False|Cave|0.90|Username 'cave.id' follows brand.domain format with affiliate program - official Cave account
- True|False|False|Perfumacy|0.90|Username 'perfumacy.ca' follows brand.country format - official Perfumacy Canada account
- False|True|False|tldv.io|0.85|Bio shows clear partnership with tldv.io through #tldvpartner tag
- False|True|False|Bob Barber Shop|0.90|Bio mentions 'Bob Barber Shop Location: new Cairo' - represents specific local business
- False|True|False|CUKURBE BARBERSHOP|0.85|Bio mentions 'CUKURBE BARBERSHOP sentul' - business representative account
- False|False|True|Nike|0.80|Profile shows #nikeambassador and discount codes for Nike products
- False|False|True|None|0.90|General tech reviewer with no clear brand partnership signals or sponsorship disclosure
- False|False|True|None|0.85|Individual barber/chef/professional without representing specific business
- False|False|True|None|0.85|Perfume reviewer selling samples but no specific brand partnership signals

Format: True|False|False|BrandName|0.9|Brief explanation"""

        # 添加重试机制
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 添加防ban机制
                self.wait_for_rate_limit()
                
                # 使用新的Gemini Client API
                if not self.client:
                    raise Exception("Gemini client not initialized")
                
                try:
                    response = self.client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[prompt]
                    )
                except Exception as e:
                    self.logger.error(f"Gemini API error: {e}")
                    raise e
                
                if response.text:
                    parts = [p.strip() for p in response.text.split('|')]
                    if len(parts) == 6:
                        is_brand = parts[0].lower() == 'true'
                        is_matrix = parts[1].lower() == 'true'
                        is_ugc = parts[2].lower() == 'true'
                        brand_name = parts[3] if parts[3].lower() != 'none' else ''
                        
                        # 安全地转换置信度分数
                        try:
                            confidence = float(str(parts[4]))
                        except (ValueError, AttributeError):
                            confidence = 0.0
                        
                        # 验证分类的互斥性
                        classifications = [is_brand, is_matrix, is_ugc]
                        if sum(classifications) != 1:
                            self.logger.warning(f"Invalid classification for {unique_id}: multiple/no categories selected, defaulting to UGC")
                            is_brand, is_matrix, is_ugc = False, False, True
                            brand_name = ''
                        
                        return {
                            'is_brand': is_brand,
                            'is_matrix_account': is_matrix,
                            'is_ugc_creator': is_ugc,
                            'brand_name': brand_name,
                            'brand_confidence': confidence,
                            'analysis_details': parts[5]
                        }
                    else:
                        self.logger.warning(f"Unexpected Gemini response format: {response.text}")
                        return self._default_analysis()
                else:
                    self.logger.warning("Empty response from Gemini")
                    return self._default_analysis()
                    
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                self.logger.error(f"Gemini API error for {unique_id} (attempt {retry_count}/{max_retries}): {error_msg}")
                
                # 记录错误到报告文件
                if self.report_file:
                    with open(self.report_file, 'a', encoding='utf-8') as f:
                        f.write(f"  Gemini API错误 (尝试 {retry_count}/{max_retries}): {error_msg}\n")
                
                # 检查是否是地区限制错误
                if "User location is not supported" in error_msg or "FAILED_PRECONDITION" in error_msg:
                    if retry_count < max_retries:
                        self.logger.info(f"地区限制错误，等待5秒后重试 (尝试 {retry_count + 1}/{max_retries})")
                        time.sleep(5)
                        continue
                    else:
                        self.logger.warning(f"Gemini API location restriction after {max_retries} retries for {unique_id}, switching to rule-based analysis")
                        return self.analyze_creator_with_rules(signature, nickname, unique_id, context, user_info)
                
                # SSL错误处理
                if "SSL" in error_msg or "EOF" in error_msg:
                    if retry_count < max_retries:
                        # 指数退避：越是重试次数多，等待时间越长
                        wait_time = (2 ** retry_count) + random.uniform(0.5, 2.0)
                        self.logger.info(f"SSL错误，等待{wait_time:.1f}秒后重试 (尝试 {retry_count + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        self.logger.warning(f"SSL error after {max_retries} retries for {unique_id}, switching to rule-based analysis")
                        return self.analyze_creator_with_rules(signature, nickname, unique_id, context, user_info)
                
                # 其他错误
                if retry_count < max_retries:
                    # 指数退避
                    wait_time = (2 ** retry_count) + random.uniform(0.5, 2.0)
                    self.logger.info(f"API错误，等待{wait_time:.1f}秒后重试 (尝试 {retry_count + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.warning(f"Gemini API general error after {max_retries} retries for {unique_id}, using rule-based fallback")
                    return self.analyze_creator_with_rules(signature, nickname, unique_id, context, user_info)
        
        # 如果所有重试都失败了，使用基于规则的分析
        return self.analyze_creator_with_rules(signature, nickname, unique_id, context, user_info)
    
    def analyze_creator_with_rules(self, signature: str, nickname: str, unique_id: str, context: str = "", user_info: Dict = None) -> Dict:
        """基于规则的创作者分析（Gemini API备用方案）"""
        
        # 基础数据清理
        signature = signature.lower() if signature else ""
        nickname = nickname.lower() if nickname else ""
        unique_id = unique_id.lower() if unique_id else ""
        
        # 知名品牌官方账号列表
        official_brands = {
            'nike': 'Nike',
            'adidas': 'Adidas',
            'apple': 'Apple',
            'google': 'Google',
            'microsoft': 'Microsoft',
            'samsung': 'Samsung',
            'sony': 'Sony',
            'amazon': 'Amazon',
            'facebook': 'Facebook',
            'instagram': 'Instagram',
            'twitter': 'Twitter',
            'youtube': 'YouTube',
            'spotify': 'Spotify',
            'netflix': 'Netflix',
            'uber': 'Uber',
            'tesla': 'Tesla',
            'starbucks': 'Starbucks',
            'mcdonald': 'McDonald\'s',
            'cocacola': 'Coca-Cola',
            'pepsi': 'Pepsi',
            'chanel': 'Chanel',
            'dior': 'Dior',
            'gucci': 'Gucci',
            'louis': 'Louis Vuitton',
            'louisvuitton': 'Louis Vuitton',
            'prada': 'Prada',
            'versace': 'Versace',
            'armani': 'Armani',
            'cave': 'Cave',
            'sephora': 'Sephora',
            'ulta': 'Ulta',
            'xssenz': 'X.SSENZ',
            'x.ssenz': 'X.SSENZ',
            'garnier': 'Garnier',
            'garniermenid': 'Garnier',
            'dove': 'Dove',
            'dovemenarabia': 'Dove',
            'kahf': 'Kahf',
            'kahfeveryday': 'Kahf',
            'loreal': 'L\'Oréal',
            'maybelline': 'Maybelline',
            'covergirl': 'CoverGirl',
            'revlon': 'Revlon',
            'mac': 'MAC',
            'urbandecay': 'Urban Decay',
            'hermes': 'Hermès',
            'cartier': 'Cartier',
            'tiffany': 'Tiffany',
            'bulgari': 'Bulgari',
            'perfumacy': 'Perfumacy',
            'scentbird': 'Scentbird'
        }
        
        # 检查是否为知名品牌官方账号
        for brand_key, brand_name in official_brands.items():
            if brand_key in unique_id:
                return {
                    'is_brand': True,
                    'is_matrix_account': False,
                    'is_ugc_creator': False,
                    'brand_name': brand_name,
                    'brand_confidence': 0.95,
                    'analysis_details': f'Rule-based: Official {brand_name} account - recognized brand username'
                }
        
        # 增强地区品牌识别
        regional_brand_patterns = {
            'garniermenid': ('Garnier', 'Garnier Men Indonesia'),
            'garniermen': ('Garnier', 'Garnier Men'),
            'dovemenarabia': ('Dove', 'Dove Men Arabia'),
            'dovemen': ('Dove', 'Dove Men'),
            'kahfeveryday': ('Kahf', 'Kahf Malaysia'),
            'kahfmy': ('Kahf', 'Kahf Malaysia'),
            'xssenz': ('X.SSENZ', 'X.SSENZ fragrance brand'),
            'x.ssenz': ('X.SSENZ', 'X.SSENZ fragrance brand')
        }
        
        for pattern, (brand_name, description) in regional_brand_patterns.items():
            if pattern in unique_id:
                return {
                    'is_brand': True,
                    'is_matrix_account': False,
                    'is_ugc_creator': False,
                    'brand_name': brand_name,
                    'brand_confidence': 0.90,
                    'analysis_details': f'Rule-based: Official {brand_name} account - {description} regional format'
                }
        
        # 检查brand.category或brand.domain格式
        if '.' in unique_id:
            parts = unique_id.split('.')
            if len(parts) == 2:
                brand_part, category_part = parts
                # 检查是否是官方账号格式
                official_suffixes = ['beauty', 'official', 'store', 'shop', 'app', 'id', 'co', 'com', 'global', 'world', 'usa', 'uk', 'ca', 'us', 'de', 'fr', 'au', 'in']
                if category_part in official_suffixes:
                    # 提取品牌名称
                    brand_name = brand_part.replace('_', ' ').title()
                    return {
                        'is_brand': True,
                        'is_matrix_account': False,
                        'is_ugc_creator': False,
                        'brand_name': brand_name,
                        'brand_confidence': 0.90,
                        'analysis_details': f'Rule-based: Official {brand_name} account - brand.category format ({unique_id})'
                    }
        
        # 矩阵账号检测 - 主要看bio中的品牌关联
        matrix_indicators = []
        
        # 检查是否为Costco相关账号
        if 'costco' in unique_id or 'costco' in signature:
            # 检查是否有明确的非官方信号
            non_official_signals = [
                'not affiliated', 'not associated', 'independent', 'personal',
                'email me for collabs', 'collaboration', 'partner', 'guide'
            ]
            
            # 检查是否有明确的官方信号
            official_signals = ['official', 'corporate', 'headquarters', 'company']
            
            # 如果有明确的官方信号，则为官方账号
            if any(signal in signature for signal in official_signals) and 'costco' in unique_id:
                return {
                    'is_brand': True,
                    'is_matrix_account': False,
                    'is_ugc_creator': False,
                    'brand_name': 'Costco',
                    'brand_confidence': 0.90,
                    'analysis_details': 'Rule-based: Official Costco account - username contains Costco with official indicators'
                }
            # 如果有非官方信号或者是guide类型，则为矩阵账号
            elif any(signal in signature for signal in non_official_signals) or 'guide' in unique_id:
                return {
                    'is_brand': False,
                    'is_matrix_account': True,
                    'is_ugc_creator': False,
                    'brand_name': 'Costco',
                    'brand_confidence': 0.85,
                    'analysis_details': 'Rule-based: Costco matrix account - related to Costco but not official (guide/non-affiliated)'
                }
            elif 'costco' in unique_id:
                return {
                    'is_brand': True,
                    'is_matrix_account': False,
                    'is_ugc_creator': False,
                    'brand_name': 'Costco',
                    'brand_confidence': 0.90,
                    'analysis_details': 'Rule-based: Official Costco account - username contains Costco'
                }
        
        # 检查其他品牌相关关键词
        brand_keywords = [
            'official', 'brand', 'company', 'studio', 'tech', 'software',
            'download', 'available', 'store', 'get', 'try', 'use', 'platform'
        ]
        
        # 官方账号联盟计划关键词
        affiliate_keywords = [
            'join our affiliate', 'get commission', 'affiliate program',
            'become an affiliate', 'earn commission', 'partnership program'
        ]
        
        # 商店代表关键词
        business_keywords = [
            'shop', 'store', 'salon', 'barber', 'restaurant', 'cafe', 'clinic',
            'location:', 'address:', 'call', 'phone', 'number', 'contact',
            'visit us', 'find us', 'open', 'hours', 'service', 'booking'
        ]
        
        # UGC/合作关键词
        partnership_keywords = [
            '#ad', '#sponsored', '#partner', '#promo', '#collaboration',
            'ambassador', 'discount', 'code', 'affiliate', 'link',
            'promo', 'sale', 'shop', 'buy', 'purchase', 'collab'
        ]
        
        # 官方品牌账号检测
        brand_indicators = 0
        potential_brand_name = ""
        
        # 检查用户名是否包含品牌特征
        brand_username_patterns = ['app', 'official', 'ai', 'tech', 'studio', 'brand']
        if any(keyword in unique_id for keyword in brand_username_patterns):
            brand_indicators += 2
            # 尝试提取品牌名称
            for word in unique_id.split('_'):
                if len(word) > 3 and word not in ['app', 'official', 'ai', 'the']:
                    potential_brand_name = word.title()
                    break
        
        # 检查bio中的品牌推广信息
        if any(keyword in signature for keyword in brand_keywords):
            brand_indicators += 1
            
        # 检查是否有下载链接或商店链接
        if any(term in signature for term in ['download', 'app store', 'google play', 'available now']):
            brand_indicators += 2
            
        # 检查合作伙伴关系信号
        partnership_signals = sum(1 for keyword in partnership_keywords if keyword in signature)
        
        # 检查商店代表信号
        business_signals = sum(1 for keyword in business_keywords if keyword in signature)
        
        # 检查联盟计划信号
        affiliate_signals = sum(1 for keyword in affiliate_keywords if keyword in signature)
        
        # 官方账号判断
        is_official = self.is_official_account(unique_id, nickname, signature)
        
        # 分类逻辑
        if brand_indicators >= 3 or (is_official and brand_indicators >= 1) or affiliate_signals >= 1:
            # 官方品牌账号
            if not potential_brand_name:
                potential_brand_name = unique_id.replace('_', ' ').title()
            
            # 生成分析详情
            reasons = []
            if brand_indicators >= 3:
                reasons.append(f'{brand_indicators} brand indicators')
            if is_official and brand_indicators >= 1:
                reasons.append('official account signals')
            if affiliate_signals >= 1:
                reasons.append('affiliate program mentioned')
            
            return {
                'is_brand': True,
                'is_matrix_account': False,
                'is_ugc_creator': False,
                'brand_name': potential_brand_name,
                'brand_confidence': 0.9 if affiliate_signals >= 1 else 0.8,
                'analysis_details': f'Rule-based: Official brand account - {", ".join(reasons)}'
            }
            
        elif business_signals >= 2:
            # 商店代表账号（矩阵账号）
            # 尝试从signature中提取商店名称
            business_name = self.extract_business_name_from_signature(signature)
            if not business_name:
                business_name = unique_id.replace('_', ' ').title()
            
            return {
                'is_brand': False,
                'is_matrix_account': True,
                'is_ugc_creator': False,
                'brand_name': business_name,
                'brand_confidence': 0.8,
                'analysis_details': f'Rule-based: Business representative account - {business_signals} business indicators found'
            }
            
        elif partnership_signals >= 2:
            # UGC创作者（有明确合作信号）
            return {
                'is_brand': False,
                'is_matrix_account': False,
                'is_ugc_creator': True,
                'brand_name': '',  # 规则分析不提取合作品牌名
                'brand_confidence': 0.7,
                'analysis_details': f'Rule-based: UGC creator with partnership signals ({partnership_signals} indicators found)'
            }
            
        elif brand_indicators >= 1:
            # 可能的矩阵账号
            return {
                'is_brand': False,
                'is_matrix_account': True,
                'is_ugc_creator': False,
                'brand_name': potential_brand_name if potential_brand_name else '',
                'brand_confidence': 0.6,
                'analysis_details': f'Rule-based: Potential matrix account - some brand connections detected'
            }
            
        else:
            # 普通创作者
            return {
                'is_brand': False,
                'is_matrix_account': False,
                'is_ugc_creator': True,
                'brand_name': '',
                'brand_confidence': 0.9,
                'analysis_details': 'Rule-based: Regular creator - no significant brand indicators found'
            }
    
    def _default_analysis(self) -> Dict:
        """默认分析结果"""
        return {
            'is_brand': False,
            'is_matrix_account': False,
            'is_ugc_creator': True,
            'brand_name': '',
            'brand_confidence': 0.0,
            'analysis_details': 'Analysis failed - defaulted to UGC creator'
        }
    
    def choose_best_brand_representative(self, brand_name: str, candidate_info: Dict) -> bool:
        """
        智能选择最佳品牌代表
        
        Args:
            brand_name: 品牌名称
            candidate_info: 候选者信息 (现在包含is_brand和is_matrix字段)
            
        Returns:
            是否应该选择当前候选者作为品牌代表
        """
        if brand_name.lower() not in self.brand_candidates:
            # 第一个候选者，直接接受
            self.brand_candidates[brand_name.lower()] = candidate_info
            return True
        
        current_best = self.brand_candidates[brand_name.lower()]
        
        # 比较标准（按优先级排序）:
        # 1. 官方品牌账号优先于矩阵账号
        # 2. 官方认证状态
        # 3. 置信度分数
        # 4. 粉丝数量
        # 5. 用户名中包含品牌名称
        
        current_is_brand = current_best.get('is_brand', False)
        current_is_matrix = current_best.get('is_matrix', False)
        new_is_brand = candidate_info.get('is_brand', False)
        new_is_matrix = candidate_info.get('is_matrix', False)
        
        # 优先级: Official Brand > Matrix Account
        if new_is_brand and current_is_matrix:
            self.brand_candidates[brand_name.lower()] = candidate_info
            self.logger.info(f"品牌 '{brand_name}': 选择官方品牌账号 {candidate_info['unique_id']} 替换矩阵账号 {current_best['unique_id']}")
            return True
        
        if current_is_brand and new_is_matrix:
            self.logger.info(f"品牌 '{brand_name}': 保持官方品牌账号 {current_best['unique_id']}，拒绝矩阵账号 {candidate_info['unique_id']}")
            return False
        
        # 如果类型相同，继续其他比较
        current_is_official = current_best.get('is_official', False)
        new_is_official = candidate_info.get('is_official', False)
        
        # 如果新候选者是官方认证而当前不是，选择新的
        if new_is_official and not current_is_official:
            self.brand_candidates[brand_name.lower()] = candidate_info
            self.logger.info(f"品牌 '{brand_name}': 选择新的官方认证账号 {candidate_info['unique_id']} 替换 {current_best['unique_id']}")
            return True
        
        # 如果当前是官方认证而新的不是，保持当前
        if current_is_official and not new_is_official:
            self.logger.info(f"品牌 '{brand_name}': 保持现有官方认证账号 {current_best['unique_id']}，拒绝 {candidate_info['unique_id']}")
            return False
        
        # 如果官方认证状态相同，比较置信度
        current_confidence = current_best.get('confidence', 0.0)
        new_confidence = candidate_info.get('confidence', 0.0)
        
        if new_confidence > current_confidence + 0.1:  # 显著更高的置信度
            self.brand_candidates[brand_name.lower()] = candidate_info
            self.logger.info(f"品牌 '{brand_name}': 选择高置信度账号 {candidate_info['unique_id']} (置信度: {new_confidence:.2f}) 替换 {current_best['unique_id']} (置信度: {current_confidence:.2f})")
            return True
        
        # 如果置信度接近，比较粉丝数量
        if abs(new_confidence - current_confidence) <= 0.1:
            current_followers = current_best.get('followers', 0)
            new_followers = candidate_info.get('followers', 0)
            
            if new_followers > current_followers * 1.5:  # 新候选者粉丝数显著更多
                self.brand_candidates[brand_name.lower()] = candidate_info
                self.logger.info(f"品牌 '{brand_name}': 选择高粉丝账号 {candidate_info['unique_id']} ({new_followers:,} 粉丝) 替换 {current_best['unique_id']} ({current_followers:,} 粉丝)")
                return True
        
        # 检查用户名中是否包含品牌名
        current_has_brand_in_name = brand_name.lower() in current_best['unique_id'].lower()
        new_has_brand_in_name = brand_name.lower() in candidate_info['unique_id'].lower()
        
        if new_has_brand_in_name and not current_has_brand_in_name:
            self.brand_candidates[brand_name.lower()] = candidate_info
            self.logger.info(f"品牌 '{brand_name}': 选择用户名包含品牌的账号 {candidate_info['unique_id']} 替换 {current_best['unique_id']}")
            return True
        
        # 默认保持当前选择
        self.logger.info(f"品牌 '{brand_name}': 保持现有代表 {current_best['unique_id']}，拒绝 {candidate_info['unique_id']}")
        return False
    
    def detect_data_format(self, data: List[Dict]) -> str:
        """检测数据格式类型"""
        if not data:
            return "unknown"
        
        sample = data[0]
        
        # 检查是否为嵌套格式（如creator_list.json）
        if 'basic_info' in sample and isinstance(sample['basic_info'], dict):
            return "nested"
        
        # 检查是否为平面格式（如shoe_list.json的扁平化版本）
        if 'author_unique_id' in sample:
            return "flat"
        
        return "unknown"
    
    def extract_creator_info(self, item: Dict, data_format: str) -> Optional[Dict]:
        """根据数据格式提取创作者信息"""
        try:
            if data_format == "nested":
                # 嵌套格式 (如 creator_list.json)
                basic_info = item.get('basic_info', {})
                author_unique_id = basic_info.get('author_unique_id', '').strip()
                
                if not author_unique_id or author_unique_id == 'None':
                    return None
                    
                return {
                    'video_id': item.get('video_id', ''),
                    'author_unique_id': author_unique_id,
                    'author_nickname': basic_info.get('author_nickname', ''),
                    'create_time': basic_info.get('create_time', ''),
                    'signature': item.get('description', ''),  # 可能在外层
                    'title': item.get('title', ''),
                    'basic_info': basic_info
                }
            
            elif data_format == "flat":
                # 扁平格式
                author_unique_id = item.get('author_unique_id', '').strip()
                
                if not author_unique_id or author_unique_id == 'None':
                    return None
                    
                return {
                    'video_id': item.get('video_id', ''),
                    'author_unique_id': author_unique_id,
                    'author_nickname': item.get('author_nickname', ''),
                    'create_time': item.get('create_time', ''),
                    'signature': item.get('signature', ''),
                    'title': item.get('title', ''),
                    'basic_info': item  # 整个item作为basic_info
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"提取创作者信息时出错: {e}")
            return None
    
    def process_creator_batch(self, creators_batch: List[Dict]) -> List[CreatorAnalysis]:
        """处理一批创作者"""
        results = []
        
        for creator in creators_batch:
            try:
                # 从嵌套结构中提取信息
                basic_info = creator.get('basic_info', {})
                author_unique_id = basic_info.get('author_unique_id', '').strip()
                author_nickname = basic_info.get('author_nickname', '').strip()
                create_time = basic_info.get('create_time', '')
                
                if not author_unique_id:
                    self.logger.warning(f"跳过空的 author_unique_id: {creator.get('video_id', 'unknown')}")
                    continue
                
                # 转换时间戳为年月日格式（从JSON获取）
                create_times = self.convert_timestamp_to_date(str(create_time))
                
                # 获取TikTok用户信息（API获取signature, followers, etc.）
                self.logger.info(f"获取用户信息: {author_unique_id}")
                user_info = self.get_tiktok_user_info(author_unique_id)
                
                # 获取用户最近20个视频数据
                videos = self.get_tiktok_user_posts(author_unique_id, 20)
                time.sleep(0.5)  # API调用间隔
                
                # 计算视频指标
                metrics = self.calculate_video_metrics(videos)
                
                # 从API获取signature，从JSON获取author_avatar（如果有的话）
                signature = user_info.get('signature', '') or f"Creator: {author_nickname}"
                
                # 优先从JSON获取avatar，否则从API获取
                json_avatar = basic_info.get('author_avatar', '') or basic_info.get('thumbnail_url', '')
                api_avatar = user_info.get('author_avatar', '')
                author_avatar = json_avatar or api_avatar
                
                # 构建内容上下文
                title = creator.get('title', '')
                description = creator.get('signature', '') or creator.get('description', '')
                context = f"Title: {title}\nDescription: {description}".strip()
                
                # 使用Gemini API分析
                self.logger.info(f"分析创作者: {author_unique_id} ({author_nickname})")
                analysis_result = self.analyze_creator_with_gemini(
                    signature, author_nickname, author_unique_id, context, user_info
                )
                
                # 从视频中分析品牌信息
                video_brands = self.analyze_creator_brands_from_videos(videos)
                
                # 提取邮箱
                email = self.extract_email_from_signature(signature)
                
                # 根据账户类型确定品牌名称
                if analysis_result.get('is_brand', False) or analysis_result.get('is_matrix_account', False):
                    # 官方或矩阵账户：使用唯一的品牌名称
                    brand_name = analysis_result.get('brand_name', '')
                else:
                    # 创作者账户：使用从视频中提取的所有品牌名称
                    if video_brands:
                        brand_name = ', '.join(video_brands)
                    else:
                        brand_name = analysis_result.get('brand_name', '')
                
                # 如果没有从视频中提取到品牌，则使用原始分析结果
                if not brand_name.strip():
                    brand_name = analysis_result.get('brand_name', '')
                
                # 获取账户类型并过滤brand name
                account_type = self.get_account_type(analysis_result)
                filtered_brand_name = self.filter_brand_name(brand_name, account_type)
                
                # 创建分析结果
                analysis = CreatorAnalysis(
                    video_id=str(creator.get('video_id', '')),
                    author_unique_id=author_unique_id,
                    author_link=f"https://www.tiktok.com/@{author_unique_id}",
                    signature=signature.replace('\n', ' ').replace('\r', ' '),  # 清理换行符
                    is_brand=analysis_result['is_brand'],
                    is_matrix_account=analysis_result['is_matrix_account'], # 新增字段，默认为False
                    is_ugc_creator=analysis_result['is_ugc_creator'], # 新增字段，默认为False
                    extracted_brand_name=filtered_brand_name,  # 使用过滤后的brand name
                    brand_confidence=analysis_result.get('brand_confidence', 0.0),
                    analysis_details=analysis_result['analysis_details'],
                    author_followers_count=user_info.get('author_followers_count', 0),
                    author_followings_count=user_info.get('author_followings_count', 0),
                    videoCount=user_info.get('videoCount', 0),
                    author_avatar=author_avatar,  # 使用优化后的avatar获取逻辑
                    create_times=create_times,
                    # 新增字段
                    email=email,
                    recent_20_posts_views_avg=metrics['avg_views'],
                    recent_20_posts_like_avg=metrics['avg_likes'],
                    recent_20_posts_share_avg=metrics['avg_shares'],
                    posting_frequency=metrics['posting_frequency'],
                    stability_score=metrics['stability_score']
                )
                
                results.append(analysis)
                
                # 实时保存结果到CSV
                self.save_result_to_realtime_csv(analysis)
                
                # 更新缓存
                self.analyzed_users.add(author_unique_id)
                self.save_analyzed_cache()
                
                # 更新进度
                self.update_progress(author_unique_id, success=True)
                
                self.logger.info(f"✅ 已完成并保存: {author_unique_id} ({len(results)} 个结果)")
                
                # 添加延迟避免API限制
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"处理创作者时出错: {e}")
                # 更新进度（失败情况）
                creator_id = creator.get('basic_info', {}).get('author_unique_id', 'unknown')
                self.update_progress(creator_id, success=False, error_msg=str(e))
                continue
                
        return results
    
    def analyze_creators(self, input_file: str) -> List[CreatorAnalysis]:
        """分析创作者列表"""
        self.logger.info(f"开始分析创作者，输入文件: {input_file}")
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                creators_data = json.load(f)
        except FileNotFoundError:
            self.logger.error(f"输入文件 {input_file} 不存在")
            return []
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {e}")
            return []
        
        self.logger.info(f"加载了 {len(creators_data)} 个数据项")
        
        # 检测数据格式
        data_format = self.detect_data_format(creators_data)
        self.logger.info(f"检测到数据格式: {data_format}")
        
        # 提取唯一的创作者信息
        unique_creators = {}
        for item in creators_data:
            creator_info = self.extract_creator_info(item, data_format)
            if creator_info:
                unique_id = creator_info['author_unique_id']
                if unique_id not in unique_creators:
                    unique_creators[unique_id] = creator_info
        
        creators_list = list(unique_creators.values())
        self.logger.info(f"去重后有 {len(creators_list)} 个唯一创作者")
        
        # 分批处理
        batch_size = 35  # 每批处理35个创作者
        all_results = []
        
        # 使用ThreadPoolExecutor进行并发处理
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for i in range(0, len(creators_list), batch_size):
                batch = creators_list[i:i + batch_size]
                future = executor.submit(self.process_creator_batch, batch)
                futures.append(future)
                
                # 批次间添加延迟
                if i + batch_size < len(creators_list):
                    time.sleep(1)
            
            # 收集结果
            for future in as_completed(futures):
                try:
                    batch_results = future.result()
                    all_results.extend(batch_results)
                    self.logger.info(f"完成批处理，当前总结果数: {len(all_results)}")
                except Exception as e:
                    self.logger.error(f"批处理失败: {e}")
        
        self.logger.info(f"分析完成，总共处理了 {len(all_results)} 个创作者")
        return all_results
    
    def process_single_creator_from_csv(self, creator_data: dict) -> CreatorAnalysis:
        """处理单个创作者的CSV数据 - 用于并发处理"""
        try:
            user_id = str(creator_data.get('user_unique_id', '')).strip()
            video_id = str(creator_data.get('video_id', '')).strip()
            user_nickname = str(creator_data.get('user_nickname', '')).strip()
            title = str(creator_data.get('title', '')).strip()
            date = str(creator_data.get('date', '')).strip()
            
            self.logger.info(f"🔄 [线程] 正在分析创作者: {user_id} ({user_nickname})")
            
            # 获取TikTok用户信息
            user_info = self.get_tiktok_user_info(user_id)
            
            # 获取用户最近20个视频数据
            videos = self.get_tiktok_user_posts(user_id, 20)
            time.sleep(0.1)  # 减少API调用间隔，因为是并发的
            
            # 计算视频指标
            metrics = self.calculate_video_metrics(videos)
            
            # 获取signature
            signature = user_info.get('signature', '') or f"Creator: {user_nickname}"
            
            # 使用Gemini API分析
            context = f"Title: {title}\nDate: {date}"
            analysis_result = self.analyze_creator_with_gemini(
                signature, user_nickname, user_id, context, user_info
            )
            
            # 从视频中分析品牌信息
            video_brands = self.analyze_creator_brands_from_videos(videos)
            
            # 提取邮箱
            email = self.extract_email_from_signature(signature)
            
            # 确定品牌名称
            if analysis_result.get('is_brand', False) or analysis_result.get('is_matrix_account', False):
                brand_name = analysis_result.get('brand_name', '')
            else:
                if video_brands:
                    brand_name = ', '.join(video_brands)
                else:
                    brand_name = analysis_result.get('brand_name', '')
            
            # 获取账户类型并过滤brand name
            account_type = self.get_account_type(analysis_result)
            filtered_brand_name = self.filter_brand_name(brand_name, account_type)
            
            # 创建分析结果
            analysis = CreatorAnalysis(
                video_id=video_id,
                author_unique_id=user_id,
                author_link=f"https://www.tiktok.com/@{user_id}",
                signature=signature.replace('\n', ' ').replace('\r', ' '),
                is_brand=analysis_result['is_brand'],
                is_matrix_account=analysis_result['is_matrix_account'],
                is_ugc_creator=analysis_result['is_ugc_creator'],
                extracted_brand_name=filtered_brand_name,
                brand_confidence=analysis_result.get('brand_confidence', 0.0),
                analysis_details=analysis_result['analysis_details'],
                author_followers_count=user_info.get('author_followers_count', 0),
                author_followings_count=user_info.get('author_followings_count', 0),
                videoCount=user_info.get('videoCount', 0),
                author_avatar=user_info.get('author_avatar', ''),
                create_times=date,
                email=email,
                recent_20_posts_views_avg=metrics['avg_views'],
                recent_20_posts_like_avg=metrics['avg_likes'],
                recent_20_posts_share_avg=metrics['avg_shares'],
                posting_frequency=metrics['posting_frequency'],
                stability_score=metrics['stability_score']
            )
            
            # 线程安全的实时保存结果到CSV
            self.save_result_to_realtime_csv(analysis)
            
            # 更新缓存
            self.analyzed_users.add(user_id)
            self.save_analyzed_cache()
            
            # 更新进度
            self.update_progress(user_id, success=True)
            
            return analysis
            
        except Exception as e:
            user_id = creator_data.get('user_unique_id', 'unknown')
            self.logger.error(f"❌ [线程] 处理创作者 {user_id} 时出错: {e}")
            self.update_progress(user_id, success=False, error_msg=str(e))
            return None

    def analyze_creators_from_csv_direct(self, input_csv_file: str) -> List[CreatorAnalysis]:
        """直接从CSV文件分析创作者，不进行JSON转换"""
        self.logger.info(f"开始直接分析CSV文件: {input_csv_file}")
        
        try:
            import pandas as pd
            
            # 读取CSV文件
            df = pd.read_csv(input_csv_file)
            self.logger.info(f"CSV文件包含 {len(df)} 行数据")
            
            # 检查必要的列
            required_columns = ['user_unique_id', 'video_id']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                self.logger.error(f"CSV文件缺少必要列: {missing_columns}")
                return []
            
            # 提取唯一的创作者
            unique_creators = df.drop_duplicates(subset=['user_unique_id'])
            self.logger.info(f"发现 {len(unique_creators)} 个唯一创作者")
            
            # 初始化缓存和实时保存
            self.init_cache_and_realtime_save(input_csv_file)
            
            # 过滤掉已分析的创作者
            creators_to_analyze = []
            for _, row in unique_creators.iterrows():
                user_id = str(row['user_unique_id']).strip()
                if user_id and user_id not in self.analyzed_users:
                    creators_to_analyze.append(row)
            
            if not creators_to_analyze:
                self.logger.info("所有创作者都已分析完成！")
                return []
            
            self.logger.info(f"需要分析 {len(creators_to_analyze)} 个创作者")
            
            # 初始化进度跟踪
            self.init_progress_tracking(len(creators_to_analyze))
            
            # 🚀 使用线程池并发分析创作者 - 10个工作线程
            all_results = []
            self.logger.info(f"🚀 启动10个工作线程并发分析 {len(creators_to_analyze)} 个创作者")
            
            # 将pandas行转换为字典列表
            creators_list = [row.to_dict() for _, row in creators_to_analyze.iterrows()] if hasattr(creators_to_analyze, 'iterrows') else list(creators_to_analyze)
            
            # 使用ThreadPoolExecutor进行并发处理
            with ThreadPoolExecutor(max_workers=10) as executor:
                # 提交所有任务
                future_to_creator = {
                    executor.submit(self.process_single_creator_from_csv, creator_data): creator_data 
                    for creator_data in creators_list
                }
                
                # 收集结果
                for future in as_completed(future_to_creator):
                    creator_data = future_to_creator[future]
                    try:
                        result = future.result()
                        if result:
                            all_results.append(result)
                            # 线程安全的进度更新
                            user_id = creator_data.get('user_unique_id', 'unknown')
                            self.logger.info(f"✅ [并发完成] {user_id} (总进度: {len(all_results)}/{len(creators_list)})")
                    except Exception as e:
                        user_id = creator_data.get('user_unique_id', 'unknown')
                        self.logger.error(f"❌ [并发处理失败] {user_id}: {e}")
                        self.update_progress(user_id, success=False, error_msg=str(e))
            
            # 完成报告
            self.finalize_report()
            
            # 显示进度摘要
            self.show_progress_summary()
            
            self.logger.info(f"直接CSV分析完成，总共处理了 {len(all_results)} 个创作者")
            return all_results
            
        except Exception as e:
            self.logger.error(f"直接CSV分析失败: {e}")
            return []
    
    def analyze_creators_from_csv(self, input_csv_file: str) -> List[CreatorAnalysis]:
        """从CSV文件分析创作者列表"""
        self.logger.info(f"开始从CSV文件分析创作者: {input_csv_file}")
        
        creators_data = []
        
        try:
            with open(input_csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 提取user_unique_id（可能的字段名）
                    user_id = (row.get('user_unique_id') or 
                              row.get('author_unique_id') or 
                              row.get('unique_id') or 
                              row.get('username') or 
                              row.get('user_id'))
                    
                    if user_id:
                        # 创建基本的创作者信息结构
                        creator_info = {
                            'video_id': row.get('video_id', ''),
                            'basic_info': {
                                'author_unique_id': user_id.strip(),
                                'author_nickname': row.get('author_nickname', ''),
                                'create_time': row.get('create_time', '')
                            },
                            'title': row.get('title', ''),
                            'description': row.get('description', ''),
                            'signature': row.get('signature', '')
                        }
                        creators_data.append(creator_info)
                        
        except Exception as e:
            self.logger.error(f"读取CSV文件失败: {e}")
            return []
        
        self.logger.info(f"从CSV文件加载了 {len(creators_data)} 个数据项")
        
        # 提取唯一的创作者信息
        unique_creators = {}
        for item in creators_data:
            creator_info = self.extract_creator_info(item, "nested")
            if creator_info:
                unique_id = creator_info['author_unique_id']
                if unique_id not in unique_creators:
                    unique_creators[unique_id] = creator_info
        
        creators_list = list(unique_creators.values())
        self.logger.info(f"去重后有 {len(creators_list)} 个唯一创作者")
        
        # 初始化缓存和实时保存
        self.init_cache_and_realtime_save(input_csv_file)
        
        # 过滤掉已分析的创作者
        creators_list = self.filter_unanalyzed_creators(creators_list)
        
        if not creators_list:
            self.logger.info("所有创作者都已分析完成！")
            return []
        
        # 初始化进度跟踪
        self.init_progress_tracking(len(creators_list))
        
        # 分批处理
        batch_size = 35  # 每批处理35个创作者
        all_results = []
        
        # 使用ThreadPoolExecutor进行并发处理
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for i in range(0, len(creators_list), batch_size):
                batch = creators_list[i:i + batch_size]
                future = executor.submit(self.process_creator_batch, batch)
                futures.append(future)
                
                # 批次间添加延迟
                if i + batch_size < len(creators_list):
                    time.sleep(1)
            
            # 收集结果
            for future in as_completed(futures):
                try:
                    batch_results = future.result()
                    all_results.extend(batch_results)
                    self.logger.info(f"完成批处理，当前总结果数: {len(all_results)}")
                except Exception as e:
                    self.logger.error(f"批处理失败: {e}")
        
        # 完成报告
        self.finalize_report()
        
        # 显示进度摘要
        self.show_progress_summary()
        
        self.logger.info(f"分析完成，总共处理了 {len(all_results)} 个创作者")
        self.logger.info(f"实时结果已保存到: {self.realtime_csv_file}")
        
        return all_results
    
    def save_results(self, results: List[CreatorAnalysis], input_filename: str):
        """保存结果到两个CSV文件：品牌相关 和 非品牌"""
        self.logger.info(f"开始保存结果，总共 {len(results)} 个创作者")
        
        # 重新定义品牌相关：有extracted_brand_name或者被标记为品牌/矩阵账号
        brand_related = [r for r in results if 
                        (r.extracted_brand_name and r.extracted_brand_name.strip()) or 
                        r.is_brand or r.is_matrix_account]
        non_brand = [r for r in results if r not in brand_related]
        
        # 在品牌相关账号中按三种类型分类统计
        official_brands = [r for r in brand_related if r.is_brand]
        matrix_accounts = [r for r in brand_related if r.is_matrix_account]
        ugc_in_brand = [r for r in brand_related if r.is_ugc_creator]
        
        self.logger.info(f"品牌相关账号: {len(brand_related)} (官方品牌: {len(official_brands)}, 矩阵账号: {len(matrix_accounts)}, UGC创作者: {len(ugc_in_brand)})")
        self.logger.info(f"非品牌账号: {len(non_brand)}")
        
        # 根据输入文件名生成输出文件名 (不使用时间戳)
        base_name = os.path.splitext(os.path.basename(input_filename))[0]
        
        brand_file = os.path.join(self.output_dir, f"{base_name}_brand_related.csv")
        non_brand_file = os.path.join(self.output_dir, f"{base_name}_non_brand.csv")
        
        # CSV字段 (按新的顺序)
        fieldnames = [
            'video_id', 'author_unique_id', 'author_link', 'signature',
            'account_type', 'brand', 'email', 'recent_20_posts_views_avg',
            'recent_20_posts_like_avg', 'recent_20_posts_share_avg', 'posting_frequency',
            'stability_score', 'brand_confidence', 'analysis_details',
            'author_followers_count', 'author_followings_count', 'videoCount',
            'author_avatar', 'create_times'
        ]
        
        def write_csv(file_path: str, creators: List[CreatorAnalysis]):
            """写入CSV文件的辅助函数"""
            with open(file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                
                for creator in creators:
                    # 获取账户类型
                    account_type = self.get_account_type({
                        'is_brand': creator.is_brand,
                        'is_matrix_account': creator.is_matrix_account,
                        'is_ugc_creator': creator.is_ugc_creator,
                        'brand_name': creator.extracted_brand_name
                    })
                    
                    # 过滤brand name
                    filtered_brand = self.filter_brand_name(creator.extracted_brand_name, account_type)
                    
                    writer.writerow({
                        'video_id': creator.video_id,
                        'author_unique_id': creator.author_unique_id,
                        'author_link': creator.author_link,
                        'signature': creator.signature,
                        'account_type': account_type,
                        'brand': filtered_brand,
                        'email': creator.email,
                        'recent_20_posts_views_avg': creator.recent_20_posts_views_avg,
                        'recent_20_posts_like_avg': creator.recent_20_posts_like_avg,
                        'recent_20_posts_share_avg': creator.recent_20_posts_share_avg,
                        'posting_frequency': creator.posting_frequency,
                        'stability_score': creator.stability_score,
                        'brand_confidence': creator.brand_confidence,
                        'analysis_details': creator.analysis_details,
                        'author_followers_count': creator.author_followers_count,
                        'author_followings_count': creator.author_followings_count,
                        'videoCount': creator.videoCount,
                        'author_avatar': creator.author_avatar,
                        'create_times': creator.create_times
                    })
        
        # 保存两个主要分类文件
        write_csv(brand_file, brand_related)
        write_csv(non_brand_file, non_brand)
        
        self.logger.info(f"品牌相关结果已保存到 {brand_file} ({len(brand_related)} 个)")
        self.logger.info(f"非品牌结果已保存到 {non_brand_file} ({len(non_brand)} 个)")
        
        # 输出品牌相关账号的详细分类统计
        if len(brand_related) > 0:
            brand_pct = (len(official_brands) / len(brand_related)) * 100
            matrix_pct = (len(matrix_accounts) / len(brand_related)) * 100
            ugc_pct = (len(ugc_in_brand) / len(brand_related)) * 100
            
            self.logger.info(f"\n=== brand_related_list 三种类型统计 ===")
            self.logger.info(f"品牌相关账号总数: {len(brand_related)}")
            self.logger.info(f"官方品牌账号 (is_brand): {len(official_brands)} ({brand_pct:.1f}%)")
            self.logger.info(f"矩阵账号 (is_matrix_account): {len(matrix_accounts)} ({matrix_pct:.1f}%)")
            self.logger.info(f"UGC创作者 (is_ugc_creator): {len(ugc_in_brand)} ({ugc_pct:.1f}%)")
            
            # 品牌分布统计
            brand_distribution = {}
            for result in brand_related:
                if result.extracted_brand_name:
                    brand = result.extracted_brand_name
                    if brand not in brand_distribution:
                        brand_distribution[brand] = {'brand': 0, 'matrix': 0, 'ugc': 0}
                    
                    if result.is_brand:
                        brand_distribution[brand]['brand'] += 1
                    elif result.is_matrix_account:
                        brand_distribution[brand]['matrix'] += 1
                    else:  # is_ugc_creator
                        brand_distribution[brand]['ugc'] += 1
            
            if brand_distribution:
                self.logger.info(f"\n=== 品牌分布详情 (在brand_related_list中) ===")
                for brand, counts in sorted(brand_distribution.items()):
                    total_brand = counts['brand'] + counts['matrix'] + counts['ugc']
                    self.logger.info(f"- {brand}: {total_brand} 个账号 (官方: {counts['brand']}, 矩阵: {counts['matrix']}, UGC: {counts['ugc']})")
        else:
            self.logger.info(f"\n=== brand_related_list 三种类型统计 ===")
            self.logger.info(f"没有发现品牌相关账号")
            
        # 总体分类统计（包含所有类型）
        total = len(results)
        if total > 0:
            brand_related_pct = (len(brand_related) / total) * 100
            non_brand_pct = (len(non_brand) / total) * 100
            
            self.logger.info(f"\n=== 总体创作者分类统计 ===")
            self.logger.info(f"品牌相关创作者: {len(brand_related)} ({brand_related_pct:.1f}%)")
            self.logger.info(f"非品牌创作者: {len(non_brand)} ({non_brand_pct:.1f}%)")

    def init_cache_and_realtime_save(self, input_filename: str):
        """初始化缓存和实时保存"""
        base_name = os.path.splitext(os.path.basename(input_filename))[0]
        
        # 缓存文件
        self.cache_file = os.path.join(self.cache_dir, f"{base_name}_analyzed_cache.json")
        
        # 实时保存的CSV文件 (不使用时间戳，确保只有一个文件)
        self.realtime_csv_file = os.path.join(self.results_dir, f"{base_name}.csv")
        
        # 加载已分析的用户缓存
        self.load_analyzed_cache()
        
        # 初始化实时CSV文件
        self.init_realtime_csv()
        
    def load_analyzed_cache(self):
        """加载已分析的用户缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.analyzed_users = set(cache_data.get('analyzed_users', []))
                    self.logger.info(f"加载缓存: {len(self.analyzed_users)} 个已分析用户")
            except Exception as e:
                self.logger.error(f"加载缓存失败: {e}")
                self.analyzed_users = set()
        else:
            self.analyzed_users = set()
            
    def save_analyzed_cache(self):
        """保存已分析的用户缓存"""
        try:
            cache_data = {
                'analyzed_users': list(self.analyzed_users),
                'last_update': datetime.now().isoformat()
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存缓存失败: {e}")
            
    def init_realtime_csv(self):
        """初始化实时CSV文件"""
        try:
            # 检查文件是否已存在
            if os.path.exists(self.realtime_csv_file):
                self.logger.info(f"检测到已存在的CSV文件: {self.realtime_csv_file}")
                
                # 检查文件是否有效（包含header）
                try:
                    with open(self.realtime_csv_file, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        header = next(reader, None)
                        if header and len(header) > 0:
                            self.logger.info(f"使用已存在的CSV文件，继续追加数据")
                            return
                except Exception as e:
                    self.logger.warning(f"读取现有CSV文件失败: {e}，重新创建文件")
            
            # 创建新的CSV文件或重新创建损坏的文件
            with open(self.realtime_csv_file, 'w', encoding='utf-8', newline='') as f:
                fieldnames = [
                    'video_id', 'author_unique_id', 'author_link', 'signature',
                    'account_type', 'brand', 'email', 'recent_20_posts_views_avg',
                    'recent_20_posts_like_avg', 'recent_20_posts_share_avg', 'posting_frequency',
                    'stability_score', 'brand_confidence', 'analysis_details',
                    'author_followers_count', 'author_followings_count', 'videoCount',
                    'author_avatar', 'create_times'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
            self.logger.info(f"初始化实时CSV文件: {self.realtime_csv_file}")
        except Exception as e:
            self.logger.error(f"初始化实时CSV失败: {e}")
            
    def save_result_to_realtime_csv(self, result: CreatorAnalysis):
        """实时保存单个分析结果到CSV"""
        try:
            with open(self.realtime_csv_file, 'a', encoding='utf-8', newline='') as f:
                fieldnames = [
                    'video_id', 'author_unique_id', 'author_link', 'signature',
                    'account_type', 'brand', 'email', 'recent_20_posts_views_avg',
                    'recent_20_posts_like_avg', 'recent_20_posts_share_avg', 'posting_frequency',
                    'stability_score', 'brand_confidence', 'analysis_details',
                    'author_followers_count', 'author_followings_count', 'videoCount',
                    'author_avatar', 'create_times'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                # 获取账户类型
                account_type = self.get_account_type({
                    'is_brand': result.is_brand,
                    'is_matrix_account': result.is_matrix_account,
                    'is_ugc_creator': result.is_ugc_creator,
                    'brand_name': result.extracted_brand_name
                })
                
                # 过滤brand name
                filtered_brand = self.filter_brand_name(result.extracted_brand_name, account_type)
                
                row = {
                    'video_id': result.video_id,
                    'author_unique_id': result.author_unique_id,
                    'author_link': result.author_link,
                    'signature': result.signature,
                    'account_type': account_type,
                    'brand': filtered_brand,
                    'email': result.email,
                    'recent_20_posts_views_avg': result.recent_20_posts_views_avg,
                    'recent_20_posts_like_avg': result.recent_20_posts_like_avg,
                    'recent_20_posts_share_avg': result.recent_20_posts_share_avg,
                    'posting_frequency': result.posting_frequency,
                    'stability_score': result.stability_score,
                    'brand_confidence': result.brand_confidence,
                    'analysis_details': result.analysis_details,
                    'author_followers_count': result.author_followers_count,
                    'author_followings_count': result.author_followings_count,
                    'videoCount': result.videoCount,
                    'author_avatar': result.author_avatar,
                    'create_times': result.create_times
                }
                writer.writerow(row)
                
                # 立即刷新到磁盘
                f.flush()
                
        except Exception as e:
            self.logger.error(f"实时保存CSV失败: {e}")
            
    def filter_unanalyzed_creators(self, creators_list: List[Dict]) -> List[Dict]:
        """过滤出未分析的创作者"""
        unanalyzed = []
        for creator in creators_list:
            user_id = creator.get('basic_info', {}).get('author_unique_id', '')
            if user_id and user_id not in self.analyzed_users:
                unanalyzed.append(creator)
        
        skipped_count = len(creators_list) - len(unanalyzed)
        if skipped_count > 0:
            self.logger.info(f"跳过 {skipped_count} 个已分析的创作者，剩余 {len(unanalyzed)} 个待分析")
        
        return unanalyzed
    
    def clear_cache(self, input_filename: str = None):
        """清除缓存，重新开始分析"""
        if input_filename:
            base_name = os.path.splitext(os.path.basename(input_filename))[0]
            cache_file = os.path.join(self.cache_dir, f"{base_name}_analyzed_cache.json")
            if os.path.exists(cache_file):
                os.remove(cache_file)
                self.logger.info(f"已清除缓存文件: {cache_file}")
        else:
            # 清除所有缓存
            cache_files = [f for f in os.listdir(self.cache_dir) if f.endswith('_analyzed_cache.json')]
            for cache_file in cache_files:
                os.remove(os.path.join(self.cache_dir, cache_file))
                self.logger.info(f"已清除缓存文件: {cache_file}")
        
        self.analyzed_users = set()
        
    def get_cache_status(self, input_filename: str = None):
        """获取缓存状态"""
        if input_filename:
            base_name = os.path.splitext(os.path.basename(input_filename))[0]
            cache_file = os.path.join(self.cache_dir, f"{base_name}_analyzed_cache.json")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                        analyzed_count = len(cache_data.get('analyzed_users', []))
                        last_update = cache_data.get('last_update', 'Unknown')
                        return {
                            'analyzed_count': analyzed_count,
                            'last_update': last_update,
                            'cache_file': cache_file
                        }
                except Exception as e:
                    self.logger.error(f"读取缓存状态失败: {e}")
        return None
        
    def load_realtime_results(self, input_filename: str = None):
        """加载实时保存的结果"""
        if not input_filename:
            # 查找任意实时结果文件
            import glob
            pattern = os.path.join(self.results_dir, "*.csv")
            files = glob.glob(pattern)
            
            if not files:
                self.logger.warning("未找到实时结果文件")
                return []
                
            # 使用最新的文件
            latest_file = max(files, key=os.path.getctime)
        else:
            base_name = os.path.splitext(os.path.basename(input_filename))[0]
            latest_file = os.path.join(self.results_dir, f"{base_name}.csv")
            
        if not os.path.exists(latest_file):
            self.logger.warning(f"实时结果文件不存在: {latest_file}")
            return []
            
        self.logger.info(f"加载实时结果: {latest_file}")
        
        results = []
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 转换account_type回布尔值
                    account_type = row.get('account_type', 'ugc creator')
                    is_brand = account_type == 'official account'
                    is_matrix_account = account_type == 'matrix account'
                    is_ugc_creator = account_type == 'ugc creator'
                    
                    # 转换数据类型
                    result = CreatorAnalysis(
                        video_id=row['video_id'],
                        author_unique_id=row['author_unique_id'],
                        author_link=row['author_link'],
                        signature=row['signature'],
                        is_brand=is_brand,
                        is_matrix_account=is_matrix_account,
                        is_ugc_creator=is_ugc_creator,
                        extracted_brand_name=row.get('brand', ''),
                        brand_confidence=float(row.get('brand_confidence', 0)) if row.get('brand_confidence') else 0.0,
                        analysis_details=row.get('analysis_details', ''),
                        author_followers_count=int(row.get('author_followers_count', 0)) if row.get('author_followers_count') else 0,
                        author_followings_count=int(row.get('author_followings_count', 0)) if row.get('author_followings_count') else 0,
                        videoCount=int(row.get('videoCount', 0)) if row.get('videoCount') else 0,
                        author_avatar=row.get('author_avatar', ''),
                        create_times=row.get('create_times', ''),
                        email=row.get('email', ''),
                        recent_20_posts_views_avg=float(row.get('recent_20_posts_views_avg', 0)) if row.get('recent_20_posts_views_avg') else 0.0,
                        recent_20_posts_like_avg=float(row.get('recent_20_posts_like_avg', 0)) if row.get('recent_20_posts_like_avg') else 0.0,
                        recent_20_posts_share_avg=float(row.get('recent_20_posts_share_avg', 0)) if row.get('recent_20_posts_share_avg') else 0.0,
                        posting_frequency=float(row.get('posting_frequency', 0)) if row.get('posting_frequency') else 0.0,
                        stability_score=float(row.get('stability_score', 0)) if row.get('stability_score') else 0.0
                    )
                    results.append(result)
                    
            self.logger.info(f"已加载 {len(results)} 个实时结果")
            return results
            
        except Exception as e:
            self.logger.error(f"加载实时结果失败: {e}")
            return []
            
    def show_progress_summary(self):
        """显示进度摘要"""
        if self.progress:
            total = self.progress.total_creators
            completed = self.progress.completed_creators
            failed = self.progress.failed_creators
            percentage = (completed / total) * 100 if total > 0 else 0
            
            print(f"\n{'='*50}")
            print(f"分析进度摘要:")
            print(f"总创作者数: {total}")
            print(f"已完成: {completed} ({percentage:.1f}%)")
            print(f"失败: {failed}")
            print(f"剩余: {total - completed - failed}")
            print(f"{'='*50}")
            
            if self.realtime_csv_file:
                print(f"实时结果文件: {self.realtime_csv_file}")
            if self.cache_file:
                print(f"缓存文件: {self.cache_file}")
            if self.report_file:
                print(f"报告文件: {self.report_file}")
            print(f"{'='*50}\n")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='通用品牌创作者分析器')
    parser.add_argument('input_file', help='输入JSON或CSV文件路径')
    parser.add_argument('--output-dir', default='analyzed_data', help='输出目录 (默认: analyzed_data)')
    parser.add_argument('--batch-size', type=int, default=35, help='批处理大小 (默认: 35)')
    parser.add_argument('--max-workers', type=int, default=7, help='最大并发数 (默认: 7)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        logger.error(f"输入文件不存在: {args.input_file}")
        sys.exit(1)
    
    start_time = time.time()
    
    analyzer = UniversalBrandAnalyzer(output_dir=args.output_dir)
    
    # 根据文件类型选择分析方法
    file_extension = os.path.splitext(args.input_file)[1].lower()
    
    if file_extension == '.csv':
        logger.info("检测到CSV文件，使用CSV分析方法")
        results = analyzer.analyze_creators_from_csv(args.input_file)
    else:
        logger.info("检测到JSON文件，使用JSON分析方法")
        results = analyzer.analyze_creators(args.input_file)
    
    if results:
        # 保存结果
        analyzer.save_results(results, args.input_file)
        
        # 输出统计信息
        brand_count = sum(1 for r in results if r.is_brand)
        matrix_count = sum(1 for r in results if r.is_matrix_account)
        ugc_count = sum(1 for r in results if r.is_ugc_creator)
        
        # 重新定义品牌相关：有extracted_brand_name或者被标记为品牌/矩阵账号
        brand_related_results = [r for r in results if 
                               (r.extracted_brand_name and r.extracted_brand_name.strip()) or 
                               r.is_brand or r.is_matrix_account]
        non_brand_results = [r for r in results if r not in brand_related_results]
        
        # 在品牌相关账号中的三种类型统计
        brand_in_related = sum(1 for r in brand_related_results if r.is_brand)
        matrix_in_related = sum(1 for r in brand_related_results if r.is_matrix_account)
        ugc_in_related = sum(1 for r in brand_related_results if r.is_ugc_creator)
        
        brand_related_count = len(brand_related_results)
        total_count = len(results)
        
        elapsed_time = time.time() - start_time
        
        logger.info(f"\n=== 分析完成 ===")
        logger.info(f"输入文件: {args.input_file}")
        logger.info(f"总创作者数: {total_count}")
        logger.info(f"品牌相关账号: {brand_related_count} ({(brand_related_count/total_count)*100:.1f}%)" if total_count > 0 else "品牌相关账号: 0")
        logger.info(f"非品牌账号: {len(non_brand_results)} ({(len(non_brand_results)/total_count)*100:.1f}%)" if total_count > 0 else "非品牌账号: 0")
        
        # brand_related_list中的三种类型占比
        if brand_related_count > 0:
            brand_in_related_pct = (brand_in_related / brand_related_count) * 100
            matrix_in_related_pct = (matrix_in_related / brand_related_count) * 100
            ugc_in_related_pct = (ugc_in_related / brand_related_count) * 100
            
            logger.info(f"\n=== brand_related_list中三种类型占比 ===")
            logger.info(f"官方品牌账号: {brand_in_related} ({brand_in_related_pct:.1f}%)")
            logger.info(f"矩阵账号: {matrix_in_related} ({matrix_in_related_pct:.1f}%)")
            logger.info(f"UGC创作者: {ugc_in_related} ({ugc_in_related_pct:.1f}%)")
        
        # 所有数据中的三分类统计（参考用）
        if total_count > 0:
            brand_total_pct = (brand_count / total_count) * 100
            matrix_total_pct = (matrix_count / total_count) * 100
            ugc_total_pct = (ugc_count / total_count) * 100
            
            logger.info(f"\n=== 全量数据三分类统计 (参考) ===")
            logger.info(f"官方品牌账号 (is_brand): {brand_count} ({brand_total_pct:.1f}%)")
            logger.info(f"矩阵账号 (is_matrix_account): {matrix_count} ({matrix_total_pct:.1f}%)")
            logger.info(f"UGC创作者 (is_ugc_creator): {ugc_count} ({ugc_total_pct:.1f}%)")
        
        logger.info(f"处理用时: {elapsed_time:.1f} 秒")
        
        # 输出已识别的品牌列表
        brand_list = set()
        for result in brand_related_results:
            if result.extracted_brand_name:
                brand_list.add(result.extracted_brand_name)
        
        if brand_list:
            logger.info(f"\n已识别的品牌: {sorted(brand_list)}")
            
        # 详细品牌分布统计
        brand_distribution = {}
        for result in brand_related_results:
            if result.extracted_brand_name:
                brand = result.extracted_brand_name
                if brand not in brand_distribution:
                    brand_distribution[brand] = {'brand': 0, 'matrix': 0, 'ugc': 0}
                
                if result.is_brand:
                    brand_distribution[brand]['brand'] += 1
                elif result.is_matrix_account:
                    brand_distribution[brand]['matrix'] += 1
                else:  # is_ugc_creator
                    brand_distribution[brand]['ugc'] += 1
        
        if brand_distribution:
            logger.info(f"\n=== 详细品牌分布 (brand_related_list) ===")
            for brand, counts in sorted(brand_distribution.items()):
                total_brand = counts['brand'] + counts['matrix'] + counts['ugc']
                logger.info(f"- {brand}: {total_brand} 个账号 (官方: {counts['brand']}, 矩阵: {counts['matrix']}, UGC: {counts['ugc']})")
    else:
        logger.error("没有成功分析任何创作者")

if __name__ == "__main__":
    main() 