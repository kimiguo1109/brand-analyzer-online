# 通用品牌创作者分析器 (Universal Brand Creator Analyzer)

这是一个通用的品牌创作者分析工具，能够动态处理不同格式的TikTok创作者数据，并使用Gemini AI进行品牌判断分析。

## 功能特点

- 🚀 **动态数据源支持**: 自动检测并适配不同的JSON数据格式
- 🤖 **AI智能分析**: 使用Gemini API进行准确的品牌代表判断
- 📊 **详细统计**: 生成品牌分布统计和分析报告
- 💾 **灵活输出**: 自动生成带时间戳的CSV文件到指定目录
- ⚡ **高效处理**: 支持并发处理和批量分析
- 🔄 **品牌唯一性**: 确保每个品牌只分配给一个创作者

## 安装依赖

```bash
pip install requests google-generativeai
```

## 使用方法

### 基本用法

```bash
python universal_brand_analyzer.py <input_file.json>
```

### 高级用法

```bash
python universal_brand_analyzer.py creator_list.json \
    --output-dir analyzed_data \
    --batch-size 50 \
    --max-workers 10
```

### 参数说明

- `input_file`: 必需，输入的JSON文件路径
- `--output-dir`: 可选，输出目录 (默认: analyzed_data)
- `--batch-size`: 可选，批处理大小 (默认: 35)
- `--max-workers`: 可选，最大并发数 (默认: 7)

## 支持的数据格式

### 嵌套格式 (Nested Format)
适用于 `creator_list.json` 等文件：
```json
[
    {
        "video_id": "7123456789",
        "basic_info": {
            "author_unique_id": "username",
            "author_nickname": "Display Name",
            "create_time": "1234567890"
        },
        "title": "Video Title",
        "description": "Video Description"
    }
]
```

### 扁平格式 (Flat Format)
适用于简化的JSON文件：
```json
[
    {
        "video_id": "7123456789",
        "author_unique_id": "username",
        "author_nickname": "Display Name",
        "create_time": "1234567890",
        "title": "Video Title",
        "signature": "Bio/Description"
    }
]
```

## 输出文件

脚本会在指定的输出目录中生成以下文件：

- `<input_name>_brand_creators_<timestamp>.csv` - 品牌创作者列表
- `<input_name>_non_brand_creators_<timestamp>.csv` - 非品牌创作者列表

### CSV字段说明

| 字段名 | 描述 |
|--------|------|
| video_id | 视频ID |
| author_unique_id | 创作者唯一ID |
| author_link | TikTok主页链接 |
| signature | 创作者简介 |
| is_brand_representative | 是否为品牌代表 |
| extracted_brand_name | 提取的品牌名称 |
| analysis_details | 分析详情 |
| author_followers_count | 粉丝数量 |
| author_followings_count | 关注数量 |
| videoCount | 视频数量 |
| author_avatar | 头像URL |
| create_times | 创建时间 |

## 分析规则

### 品牌代表判断标准

1. **官方品牌代表识别**:
   - 明确的品牌雇员身份声明
   - 账号名称直接表明品牌关联
   - 使用第一人称代表品牌发声
   - 有官方邮箱域名或认证标识

2. **非品牌代表识别**:
   - 个人使用体验分享
   - 产品推荐或评测
   - 联盟营销/带货
   - 粉丝自发分享品牌产品

3. **大型科技公司特殊规则**:
   - 必须有明确的官方身份证明
   - 仅提及品牌名不等于官方代表
   - 独立创作者推广不算品牌代表

### 品牌唯一性
- 每个品牌名称只能分配给一个创作者
- 如果检测到重复品牌，后续创作者将被标记为非品牌代表

## 示例运行

### 分析鞋类相关创作者
```bash
python universal_brand_analyzer.py shoe_list.json
```

### 分析笔记应用相关创作者
```bash
python universal_brand_analyzer.py creator_list.json --output-dir results/note_taking
```

## 输出示例

```
2024-07-09 06:30:15,123 - INFO - Universal Brand Analyzer initialized, output dir: analyzed_data
2024-07-09 06:30:15,124 - INFO - 开始分析创作者，输入文件: shoe_list.json
2024-07-09 06:30:15,125 - INFO - 加载了 24079 个数据项
2024-07-09 06:30:15,126 - INFO - 检测到数据格式: nested
2024-07-09 06:30:15,127 - INFO - 去重后有 754 个唯一创作者

...分析过程...

=== 分析完成 ===
输入文件: shoe_list.json
总创作者数: 754
品牌创作者数: 12
品牌创作者比例: 1.59%
处理用时: 850.2 秒

已识别的品牌: ['ANTA', 'ASICS', 'Decathlon', 'Nike', 'Puma', 'Under Armour']

品牌分布:
- ANTA: 2 个创作者
- ASICS: 1 个创作者
- Decathlon: 3 个创作者
- Nike: 2 个创作者
- Puma: 2 个创作者
- Under Armour: 2 个创作者
```

## 注意事项

1. **API限制**: 脚本使用了外部API (Gemini, TikTok)，请注意API调用限制
2. **处理时间**: 大量数据处理可能需要较长时间，建议合理设置批处理大小
3. **网络连接**: 需要稳定的网络连接来调用外部API
4. **文件大小**: 确保有足够的磁盘空间存储输出文件

## 故障排除

### 常见问题

1. **API配额超限**: 
   - 调整批处理大小和并发数
   - 增加延迟时间

2. **网络连接错误**:
   - 检查网络连接
   - 确认API密钥有效

3. **文件格式不支持**:
   - 检查JSON文件格式
   - 确认包含必需字段

### 日志级别调整

```python
logging.basicConfig(level=logging.DEBUG)  # 详细调试信息
logging.basicConfig(level=logging.WARNING)  # 只显示警告和错误
```

## 开发者信息

- **版本**: 1.0.0
- **作者**: Kimi Guo
- **更新时间**: 2025-07-11