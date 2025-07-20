# TikTok 创作者品牌分析工具

这是一个基于 Create React App 和 Vercel Functions 的品牌分析工具，用于分析 TikTok 创作者的品牌关联度。

## 功能特性

- 📊 **智能分类**: 自动将创作者分为官方品牌账户、矩阵账户和 UGC 创作者
- 🎯 **品牌识别**: 智能提取和识别创作者与品牌的关联
- 📈 **统计分析**: 提供详细的统计数据和分布信息
- 📄 **结果导出**: 支持下载分析结果为 CSV 格式
- 🚀 **实时处理**: 文件上传后实时显示处理进度

## 技术架构

### 前端
- **框架**: Create React App (React 18)
- **样式**: Tailwind CSS 3.3
- **图标**: Lucide React
- **构建工具**: React Scripts 5.0

### 后端
- **API**: Vercel Functions (Node.js)
- **文件处理**: Formidable
- **数据分析**: 模拟处理（可扩展为实际 Python 脚本）

## 项目结构

```
brand-analyzer-dashboard/
├── src/
│   ├── components/
│   │   └── BrandAnalyzerDashboard.js    # 主组件
│   ├── App.js                           # 应用入口
│   ├── index.js                         # React 入口
│   └── index.css                        # 全局样式
├── api/
│   ├── upload.js                        # 文件上传处理
│   ├── status.js                        # 任务状态查询
│   ├── download.js                      # 文件下载
│   ├── logs.js                          # 日志查询
│   └── health.js                        # 健康检查
├── public/
│   └── index.html                       # HTML 模板
├── package.json                         # 项目配置
├── vercel.json                          # Vercel 部署配置
└── tailwind.config.js                   # Tailwind 配置
```

## 开发环境设置

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd brand-analyzer-dashboard
   ```

2. **安装依赖**
   ```bash
   npm install
   ```

3. **启动开发服务器**
   ```bash
   npm start
   ```

4. **访问应用**
   打开 [http://localhost:3000](http://localhost:3000)

## 部署

### Vercel 部署（推荐）

1. **安装 Vercel CLI**
   ```bash
   npm install -g vercel
   ```

2. **部署到 Vercel**
   ```bash
   vercel --prod
   ```

3. **配置域名**
   - 在 Vercel Dashboard 中配置自定义域名
   - 更新 `vercel.json` 中的 rewrites 配置

### 本地构建

```bash
npm run build
```

## API 接口

### 基础路径
- 开发环境: `http://localhost:3000/api`
- 生产环境: `https://your-domain.vercel.app/api`

### 接口列表

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/upload` | POST | 文件上传和处理 |
| `/api/status?task_id=xxx` | GET | 获取任务状态 |
| `/api/download?task_id=xxx&file_type=xxx` | GET | 下载结果文件 |
| `/api/logs?task_id=xxx` | GET | 获取处理日志 |

## 使用说明

1. **准备数据**: 准备 JSON 格式的创作者数据文件（如 note_taking_list.json）
2. **上传文件**: 选择 JSON 格式的创作者数据文件
3. **等待处理**: 系统将自动调用 Python 分析脚本进行智能分析
4. **实时监控**: 查看处理进度和实时日志输出
5. **查看结果**: 处理完成后查看详细统计数据和分类结果
6. **下载结果**: 下载品牌相关和非品牌数据的 CSV 文件

### 后端处理流程
系统会自动调用以下命令进行分析：
```bash
python universal_brand_analyzer.py uploaded_file.json --output-dir analyzed_data --batch-size 35 --max-workers 7
```

## 数据格式

### 输入格式 (JSON)
```json
[
  {
    "author_unique_id": "creator1",
    "author_follower_count": 100000,
    "signature": "AI工具推荐",
    "video_description": "各种AI工具测评..."
  },
  {
    "author_unique_id": "creator2", 
    "author_follower_count": 50000,
    "signature": "官方账号",
    "video_description": "品牌官方内容..."
  }
]
```

### 输出格式 (CSV)
```csv
video_id,author_unique_id,author_link,signature,is_brand,is_matrix_account,is_ugc_creator,brand_name,analysis_details,author_followers_count,author_followings_count,videoCount,author_avatar,create_times
1,creator1,https://...,AI工具推荐,false,false,true,AI工具,分析详情...,100000,500,100,avatar.jpg,2024-01-01
2,creator2,https://...,官方账号,true,false,false,某品牌,分析详情...,50000,200,50,avatar2.jpg,2024-01-01
```

## 配置

### 环境变量
项目支持以下环境变量配置：
- `REACT_APP_API_URL`: API 基础地址（可选）

### Vercel 配置
`vercel.json` 文件包含：
- Functions 配置（超时时间、内存等）
- CORS 头部设置
- URL 重写规则

## 扩展开发

### 添加新的分析逻辑
1. 修改 `api/upload.js` 中的 `processFile` 函数
2. 添加新的统计字段到结果对象
3. 更新前端显示组件

### 集成真实 Python 分析器
1. 安装 Python 环境到 Vercel Functions
2. 修改 `api/upload.js` 调用 Python 脚本
3. 配置必要的依赖和环境

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request 来改进项目。

## 支持

如有问题，请联系开发团队或创建 Issue。 