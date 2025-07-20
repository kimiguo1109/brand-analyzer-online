import { GoogleGenerativeAI } from '@google/generative-ai';
import fetch from 'node-fetch';

// API配置
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || 'AIzaSyB8GkbKtlc9OfyHE2c_wasXpCatYRC11IY';
const RAPIDAPI_KEY = process.env.RAPIDAPI_KEY || '34ba1ae26fmsha15de959b0b5d6ep11e6e6jsn64ad77705138';

// 初始化Gemini
const genAI = new GoogleGenerativeAI(GEMINI_API_KEY);

// 大型科技公司列表
const MAJOR_TECH_COMPANIES = new Set([
    'apple', 'microsoft', 'google', 'amazon', 'facebook', 'meta', 'samsung', 
    'sony', 'intel', 'nvidia', 'ibm', 'oracle', 'adobe', 'salesforce', 
    'netflix', 'uber', 'twitter', 'linkedin', 'snapchat', 'tiktok', 'instagram'
]);

class BrandAnalyzer {
    constructor() {
        this.model = genAI.getGenerativeModel({ model: "gemini-2.0-flash-exp" });
        this.apiCallCount = 0;
        this.lastApiCallTime = 0;
        this.rateLimitDelay = 2000; // 2秒延迟，平衡效率和稳定性
        this.maxApiCallsPerMinute = 20; // 合理的限制，依赖重试处理429
        this.retryCount = 0;
        this.maxRetries = 3;
    }

    // 优化的频率控制 - 平衡效率和稳定性
    async waitForRateLimit() {
        const currentTime = Date.now();
        
        // 基础间隔控制
        if (currentTime - this.lastApiCallTime < this.rateLimitDelay) {
            const waitTime = this.rateLimitDelay - (currentTime - this.lastApiCallTime);
            console.log(`⏳ API间隔等待 ${Math.round(waitTime/1000)} 秒...`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
        }
        
        this.apiCallCount++;
        this.lastApiCallTime = Date.now();
        
        // 每20次调用短暂休息，避免突发请求
        if (this.apiCallCount % this.maxApiCallsPerMinute === 0) {
            console.log(`⏸️ 已调用API ${this.apiCallCount} 次，短暂休息5秒`);
            await new Promise(resolve => setTimeout(resolve, 5000));
        }
        
        console.log(`📊 API调用计数: ${this.apiCallCount}`);
    }

    // 带重试的API调用
    async callGeminiWithRetry(prompt, uniqueId, retryCount = 0) {
        try {
            await this.waitForRateLimit();
            
            const result = await this.model.generateContent(prompt);
            const response = await result.response;
            return response.text();
            
        } catch (error) {
            console.error(`Gemini API error for ${uniqueId} (attempt ${retryCount + 1}/${this.maxRetries}):`, error.message);
            
            // 如果是配额错误且还有重试次数，等待更长时间后重试
            if (error.message.includes('429') || error.message.includes('quota') || error.message.includes('Too Many Requests')) {
                if (retryCount < this.maxRetries - 1) {
                    const backoffDelay = Math.min(30000 * Math.pow(2, retryCount), 120000); // 指数退避，最多2分钟
                    console.log(`⏰ 配额限制，等待 ${backoffDelay/1000} 秒后重试...`);
                    await new Promise(resolve => setTimeout(resolve, backoffDelay));
                    return this.callGeminiWithRetry(prompt, uniqueId, retryCount + 1);
                } else {
                    console.error(`❌ ${uniqueId} 达到最大重试次数，跳过此创作者`);
                    return null;
                }
            } else {
                throw error; // 非配额错误直接抛出
            }
        }
    }

    // 获取TikTok用户信息
    async getTikTokUserInfo(uniqueId) {
        if (!uniqueId || uniqueId === 'None') {
            return this.getDefaultUserInfo();
        }

        const url = `https://tiktok-scraper7.p.rapidapi.com/user/info?unique_id=${encodeURIComponent(uniqueId)}`;
        
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'x-rapidapi-key': RAPIDAPI_KEY,
                    'x-rapidapi-host': 'tiktok-scraper7.p.rapidapi.com'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.code === 0 && data.data) {
                    const userData = data.data.user || {};
                    const statsData = data.data.stats || {};
                    
                    return {
                        signature: userData.signature || '',
                        followerCount: statsData.followerCount || 0,
                        followingCount: statsData.followingCount || 0,
                        videoCount: statsData.videoCount || 0,
                        avatar: userData.avatarThumb || '',
                        author_followers_count: statsData.followerCount || 0,
                        author_followings_count: statsData.followingCount || 0,
                        author_avatar: userData.avatarThumb || ''
                    };
                }
            }
        } catch (error) {
            console.warn(`获取TikTok用户信息失败 ${uniqueId}:`, error.message);
        }
        
        return this.getDefaultUserInfo();
    }

    // 获取TikTok用户最近视频
    async getTikTokUserPosts(uniqueId, count = 20) {
        const url = `https://tiktok-scraper7.p.rapidapi.com/user/posts?unique_id=${encodeURIComponent(uniqueId)}&count=${count}&cursor=0`;

        const maxRetries = 3;
        for (let attempt = 0; attempt < maxRetries; attempt++) {
            try {
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'x-rapidapi-key': RAPIDAPI_KEY,
                        'x-rapidapi-host': 'tiktok-scraper7.p.rapidapi.com'
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (data.code === 0 && data.data && data.data.videos) {
                        const videos = data.data.videos;
                        const videoData = videos.map(video => ({
                            video_id: video.video_id || '',
                            title: video.title || '',
                            play_count: video.play_count || 0,
                            digg_count: video.digg_count || 0,
                            share_count: video.share_count || 0,
                            create_time: video.create_time || 0
                        }));
                        
                        console.log(`获取到用户 ${uniqueId} 的 ${videoData.length} 个视频数据`);
                        return videoData;
                    } else {
                        console.warn(`TikTok API返回错误: ${data.msg || 'Unknown error'}`);
                        if (attempt < maxRetries - 1) {
                            console.log(`TikTok API请求失败，正在重试... (尝试 ${attempt + 2}/${maxRetries})`);
                            await new Promise(resolve => setTimeout(resolve, 1000));
                            continue;
                        }
                        return [];
                    }
                } else {
                    console.warn(`TikTok API请求失败: ${response.status}`);
                    if (attempt < maxRetries - 1) {
                        console.log(`TikTok API请求失败，正在重试... (尝试 ${attempt + 2}/${maxRetries})`);
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        continue;
                    }
                    return [];
                }
                    
            } catch (error) {
                console.error(`获取用户 ${uniqueId} 视频数据失败: ${error.message}`);
                if (attempt < maxRetries - 1) {
                    console.log(`TikTok API请求异常，正在重试... (尝试 ${attempt + 2}/${maxRetries})`);
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }
                return [];
            }
        }
        
        // 如果所有重试都失败了
        console.error(`TikTok API请求失败，已重试 ${maxRetries} 次`);
        return [];
    }

    // 计算视频指标
    calculateVideoMetrics(videos) {
        if (!videos || videos.length === 0) {
            return {
                avg_views: 0,
                avg_likes: 0,
                avg_shares: 0,
                posting_frequency: 0,
                stability_score: 0
            };
        }

        // 计算平均值
        const avgViews = videos.reduce((sum, v) => sum + (v.play_count || 0), 0) / videos.length;
        const avgLikes = videos.reduce((sum, v) => sum + (v.digg_count || 0), 0) / videos.length;
        const avgShares = videos.reduce((sum, v) => sum + (v.share_count || 0), 0) / videos.length;

        // 计算发布频率
        let postingFrequency = 0;
        if (videos.length > 1) {
            const timestamps = videos
                .map(v => v.create_time)
                .filter(t => t > 0)
                .sort((a, b) => a - b);
            
            if (timestamps.length >= 2) {
                const timeSpanDays = (timestamps[timestamps.length - 1] - timestamps[0]) / (24 * 3600);
                postingFrequency = timeSpanDays > 0 ? videos.length / Math.max(timeSpanDays, 1) : 0;
            }
        }

        // 计算稳定性分数
        let stabilityScore = 0;
        if (videos.length > 1) {
            const viewCounts = videos.map(v => v.play_count || 0);
            const validCounts = viewCounts.filter(count => count > 0);
            
            if (validCounts.length > 1) {
                const mean = validCounts.reduce((sum, count) => sum + count, 0) / validCounts.length;
                if (mean > 0) {
                    const variance = validCounts.reduce((sum, count) => sum + Math.pow(count - mean, 2), 0) / validCounts.length;
                    const std = Math.sqrt(variance);
                    const cv = std / mean;
                    stabilityScore = Math.max(0, Math.min(1, 1 - cv));
                }
            }
        }

        return {
            avg_views: avgViews,
            avg_likes: avgLikes,
            avg_shares: avgShares,
            posting_frequency: postingFrequency,
            stability_score: stabilityScore
        };
    }

    // 使用Gemini分析创作者类型
    async analyzeCreatorWithGemini(signature, nickname, uniqueId, context = "", userInfo = {}) {
        const isOfficial = this.isOfficialAccount(uniqueId, nickname, signature);
        
        const prompt = `Analyze the following TikTok creator profile and classify them into ONE of these three categories:

Creator Username: ${uniqueId}
Display Name: ${nickname}
Bio/Signature: ${signature}
Is Official Account: ${isOfficial}
Content Context: ${context}

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

Format: True|False|False|BrandName|0.9|Brief explanation`;

        const maxRetries = 3;
        let retryCount = 0;
        
        while (retryCount < maxRetries) {
            try {
                const text = await this.callGeminiWithRetry(prompt, uniqueId, retryCount);
                
                if (!text) {
                    // API调用失败，使用规则备用方案
                    console.log(`⚠️ ${uniqueId} API调用失败，使用规则备用分析`);
                    return this.analyzeCreatorWithRules(signature, nickname, uniqueId, context, userInfo);
                }
                
                if (text) {
                    const parts = text.split('|').map(p => p.trim());
                    if (parts.length === 6) {
                        const isBrand = parts[0].toLowerCase() === 'true';
                        const isMatrix = parts[1].toLowerCase() === 'true';
                        const isUgc = parts[2].toLowerCase() === 'true';
                        const brandName = parts[3] !== 'None' ? parts[3] : '';
                        const confidence = parseFloat(parts[4]) || 0.0;
                        
                        // 验证分类的互斥性
                        const classifications = [isBrand, isMatrix, isUgc];
                        if (classifications.filter(Boolean).length !== 1) {
                            console.warn(`Invalid classification for ${uniqueId}: multiple/no categories selected, defaulting to UGC`);
                            return {
                                is_brand: false,
                                is_matrix_account: false,
                                is_ugc_creator: true,
                                brand_name: '',
                                brand_confidence: 0.0,
                                analysis_details: 'Invalid classification - defaulted to UGC creator'
                            };
                        }
                        
                        return {
                            is_brand: isBrand,
                            is_matrix_account: isMatrix,
                            is_ugc_creator: isUgc,
                            brand_name: brandName,
                            brand_confidence: confidence,
                            analysis_details: parts[5]
                        };
                    }
                }
                
                console.warn(`Unexpected Gemini response format: ${text}`);
                return this.getDefaultAnalysis();
                
            } catch (error) {
                retryCount++;
                console.error(`Gemini API error for ${uniqueId} (attempt ${retryCount}/${maxRetries}):`, error.message);
                
                if (retryCount < maxRetries) {
                    const waitTime = Math.pow(2, retryCount) * 1000 + Math.random() * 1000;
                    console.log(`等待${waitTime/1000}秒后重试...`);
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                    continue;
                } else {
                    console.warn(`Gemini API failed after ${maxRetries} retries for ${uniqueId}, using rule-based analysis`);
                    return this.analyzeCreatorWithRules(signature, nickname, uniqueId, context, userInfo);
                }
            }
        }
        
        return this.analyzeCreatorWithRules(signature, nickname, uniqueId, context, userInfo);
    }

    // 基于规则的分析（备用方案）
    analyzeCreatorWithRules(signature, nickname, uniqueId, context = "", userInfo = {}) {
        const lowerUniqueId = uniqueId.toLowerCase();
        const lowerSignature = (signature || '').toLowerCase();
        const lowerNickname = (nickname || '').toLowerCase();
        
        // 知名品牌检测
        const officialBrands = {
            'nike': 'Nike', 'adidas': 'Adidas', 'apple': 'Apple', 'google': 'Google',
            'microsoft': 'Microsoft', 'samsung': 'Samsung', 'sony': 'Sony', 'amazon': 'Amazon',
            'chanel': 'Chanel', 'dior': 'Dior', 'gucci': 'Gucci', 'prada': 'Prada',
            'cave': 'Cave', 'sephora': 'Sephora', 'ulta': 'Ulta'
        };
        
        for (const [brandKey, brandName] of Object.entries(officialBrands)) {
            if (lowerUniqueId.includes(brandKey)) {
                return {
                    is_brand: true,
                    is_matrix_account: false,
                    is_ugc_creator: false,
                    brand_name: brandName,
                    brand_confidence: 0.95,
                    analysis_details: `Rule-based: Official ${brandName} account - recognized brand username`
                };
            }
        }
        
        // 品牌格式检测
        if (lowerUniqueId.includes('.')) {
            const parts = lowerUniqueId.split('.');
            if (parts.length === 2) {
                const [brandPart, categoryPart] = parts;
                const officialSuffixes = ['beauty', 'official', 'store', 'shop', 'app', 'id', 'co', 'com'];
                if (officialSuffixes.includes(categoryPart)) {
                    const brandName = brandPart.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    return {
                        is_brand: true,
                        is_matrix_account: false,
                        is_ugc_creator: false,
                        brand_name: brandName,
                        brand_confidence: 0.90,
                        analysis_details: `Rule-based: Official ${brandName} account - brand.category format`
                    };
                }
            }
        }
        
        // 商业关键词检测
        const businessKeywords = ['shop', 'store', 'salon', 'barber', 'restaurant', 'location', 'address'];
        const businessCount = businessKeywords.filter(keyword => lowerSignature.includes(keyword)).length;
        
        if (businessCount >= 2) {
            return {
                is_brand: false,
                is_matrix_account: true,
                is_ugc_creator: false,
                brand_name: uniqueId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                brand_confidence: 0.8,
                analysis_details: `Rule-based: Business representative account - ${businessCount} business indicators found`
            };
        }
        
        // 默认为UGC创作者
        return {
            is_brand: false,
            is_matrix_account: false,
            is_ugc_creator: true,
            brand_name: '',
            brand_confidence: 0.9,
            analysis_details: 'Rule-based: Regular creator - no significant brand indicators found'
        };
    }

    // 检查是否为官方账号
    isOfficialAccount(uniqueId, nickname, signature) {
        const officialIndicators = ['official', 'verified', '@company.com', '@brand.com', 'team', 'support', 'headquarters', 'corporate'];
        const combinedText = `${uniqueId} ${nickname} ${signature}`.toLowerCase();
        return officialIndicators.some(indicator => combinedText.includes(indicator));
    }

    // 提取邮箱
    extractEmailFromSignature(signature) {
        if (!signature) return '';
        const emailPattern = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/;
        const match = signature.match(emailPattern);
        return match ? match[0] : '';
    }

    // 获取账户类型
    getAccountType(analysisResult) {
        if (analysisResult.is_brand) {
            return 'official account';
        } else if (analysisResult.is_matrix_account) {
            return 'matrix account';
        } else if (analysisResult.is_ugc_creator) {
            return analysisResult.brand_name && analysisResult.brand_name.trim() ? 'ugc creator' : 'non-branded creator';
        } else {
            return 'non-branded creator';
        }
    }

    // 过滤品牌名称
    filterBrandName(brandName, accountType, analysisDetails = '') {
        if (!brandName || !brandName.trim()) {
            return '';
        }

        // 如果AI分析明确说没有品牌合作，则过滤掉品牌名称
        const noPartnershipIndicators = [
            'no indication of a brand partnership',
            'no clear brand partnership',
            'no significant brand indicators',
            'no brand partnership signals',
            'no sponsorship disclosure',
            'regular creator',
            'personal account'
        ];

        if (noPartnershipIndicators.some(indicator => 
            analysisDetails.toLowerCase().includes(indicator))) {
            return '';
        }

        // 官方账户和矩阵账户直接返回
        if (accountType === 'official account' || accountType === 'matrix account') {
            return brandName.trim();
        }

        // 已知无效品牌名称列表
        const invalidBrandNames = [
            'sabrina', 'fall', 'taylor', 'jeneralgrievous', 'sweet', 'hobipower', 
            'gloria', 'leah', 'flyanaboss', 'andrea', 'josh', 'leam', 'megan',
            'calvin896155', 'alessio', 'jerseyjanetp', 'chet', 'old', 'stop',
            'metro', 'prices', 'iszuh', 'samhealinghabits', 'none', 'null', 'test'
        ];

        // UGC创作者需要更严格的过滤
        if (accountType === 'ugc creator') {
            // 分割多个品牌名称并过滤
            const brands = brandName.split(',').map(b => b.trim()).filter(b => {
                const lowerBrand = b.toLowerCase();
                
                const invalidIndicators = [
                    b.length < 3,
                    invalidBrandNames.includes(lowerBrand),
                    /^[0-9]+$/.test(b),
                    !/[a-zA-Z]/.test(b),
                    // 检查是否是明显的人名
                    /^[A-Z][a-z]+$/.test(b) && b.length <= 8 && invalidBrandNames.includes(lowerBrand)
                ];

                return !invalidIndicators.some(Boolean);
            });

            // 只保留已知的真实品牌
            const knownBrands = [
                'nike', 'adidas', 'apple', 'samsung', 'google', 'microsoft', 'chanel', 
                'dior', 'gucci', 'prada', 'versace', 'sephora', 'ulta', 'lululemon', 
                'nordstrom', 'zara', 'uniqlo', 'target', 'walmart', 'amazon', 'shein',
                'old spice', 'oldspice', 'nivea', 'dove', 'costco', 'bissell', 'snickers',
                'peacock', 'netflix', 'uber', 'tesla', 'starbucks', 'mcdonald', 'sony',
                'microsoft', 'cerave', 'neutrogena', 'softsoap', 'listerine', 'kraft',
                'culturelle', 'serovital', 'north face', 'mackenzie'
            ];

            const validBrands = brands.filter(brand => {
                const lowerBrand = brand.toLowerCase();
                return knownBrands.some(known => 
                    lowerBrand.includes(known) || known.includes(lowerBrand)
                );
            });

            return validBrands.length > 0 ? validBrands.join(', ') : '';
        }

        return brandName.trim();
    }

    // 默认用户信息
    getDefaultUserInfo() {
        return {
            signature: '',
            followerCount: 0,
            followingCount: 0,
            videoCount: 0,
            avatar: '',
            author_followers_count: 0,
            author_followings_count: 0,
            author_avatar: ''
        };
    }

    // 默认分析结果
    getDefaultAnalysis() {
        return {
            is_brand: false,
            is_matrix_account: false,
            is_ugc_creator: true,
            brand_name: '',
            brand_confidence: 0.0,
            analysis_details: 'Analysis failed - defaulted to UGC creator'
        };
    }

    // 转换时间戳
    convertTimestampToDate(timestamp) {
        try {
            if (timestamp && !isNaN(timestamp)) {
                const date = new Date(parseInt(timestamp) * 1000);
                return date.toISOString().split('T')[0];
            }
        } catch (error) {
            console.warn(`时间戳转换失败: ${timestamp}`, error);
        }
        return '';
    }

    // 主要分析方法
    async analyzeCreator(creatorData) {
        const { 
            author_unique_id: uniqueId, 
            author_nickname: nickname = '', 
            title = '', 
            create_time = '',
            signature: inputSignature = ''
        } = creatorData;

        if (!uniqueId || uniqueId === 'None') {
            throw new Error('Invalid creator data: missing author_unique_id');
        }

        console.log(`🔍 分析创作者: ${uniqueId} (${nickname})`);

        // 获取TikTok用户信息
        const userInfo = await this.getTikTokUserInfo(uniqueId);
        
        // 获取用户最近视频
        const videos = await this.getTikTokUserPosts(uniqueId, 20);
        await new Promise(resolve => setTimeout(resolve, 100)); // API间隔
        
        // 计算视频指标
        const metrics = this.calculateVideoMetrics(videos);
        
        // 使用API获取的signature，如果没有则使用输入的signature
        const signature = userInfo.signature || inputSignature || `Creator: ${nickname}`;
        
        // 构建上下文
        const context = `Title: ${title}\nCreate Time: ${create_time}`.trim();
        
        // 使用Gemini分析
        console.log(`🤖 使用Gemini分析: ${uniqueId}`);
        const analysisResult = await this.analyzeCreatorWithGemini(
            signature, nickname, uniqueId, context, userInfo
        );
        
        // 提取邮箱
        const email = this.extractEmailFromSignature(signature);
        
        // 获取账户类型
        const accountType = this.getAccountType(analysisResult);
        
        // 过滤品牌名称（传入分析详情）
        const filteredBrandName = this.filterBrandName(
            analysisResult.brand_name, 
            accountType, 
            analysisResult.analysis_details
        );
        
        // 返回完整分析结果
        const result = {
            video_id: creatorData.video_id || this.generateVideoId(),
            author_unique_id: uniqueId,
            author_link: `https://www.tiktok.com/@${uniqueId}`,
            signature: signature.replace(/\n/g, ' ').replace(/\r/g, ' '),
            account_type: accountType,
            brand: filteredBrandName,
            email: email,
            recent_20_posts_views_avg: metrics.avg_views,
            recent_20_posts_like_avg: metrics.avg_likes,
            recent_20_posts_share_avg: metrics.avg_shares,
            posting_frequency: metrics.posting_frequency,
            stability_score: metrics.stability_score,
            brand_confidence: analysisResult.brand_confidence,
            analysis_details: analysisResult.analysis_details,
            author_followers_count: userInfo.author_followers_count,
            author_followings_count: userInfo.author_followings_count,
            videoCount: userInfo.videoCount,
            author_avatar: userInfo.author_avatar,
            create_times: this.convertTimestampToDate(create_time),
            is_brand: analysisResult.is_brand,
            is_matrix_account: analysisResult.is_matrix_account,
            is_ugc_creator: analysisResult.is_ugc_creator
        };

        console.log(`✅ 完成分析: ${uniqueId} - ${accountType} - ${filteredBrandName || 'No Brand'}`);
        return result;
    }

    // 批量分析创作者
    async analyzeCreators(creators, progressCallback = null) {
        const results = [];
        const batchSize = 5; // 优化的批处理大小，提高并发效率
        
        console.log(`🚀 开始批量分析 ${creators.length} 个创作者`);
        
        try {
            for (let i = 0; i < creators.length; i += batchSize) {
                const batch = creators.slice(i, i + batchSize);
                const batchNum = Math.floor(i / batchSize) + 1;
                const totalBatches = Math.ceil(creators.length / batchSize);
                
                console.log(`📦 处理批次 ${batchNum}/${totalBatches} (${batch.length} 个创作者)`);
                
                try {
                    // 并发处理批次内的创作者
                    const batchPromises = batch.map(async (creator) => {
                        try {
                            // 转换数据格式为analyzeCreator期望的格式
                            const creatorData = {
                                author_unique_id: creator.unique_id,
                                author_nickname: creator.display_name || creator.unique_id,
                                title: creator.title || '',
                                create_time: creator.create_time || '',
                                signature: creator.signature || ''
                            };
                            
                            const result = await this.analyzeCreator(creatorData);
                            return result;
                        } catch (error) {
                            console.error(`❌ 分析创作者失败 ${creator.unique_id}:`, error.message);
                            return null; // 失败的分析返回null
                        }
                    });
                    
                    const batchResults = await Promise.all(batchPromises);
                    const validResults = batchResults.filter(r => r !== null);
                    results.push(...validResults);
                    
                    // 更新进度
                    const progress = Math.floor(((i + batch.length) / creators.length) * 100);
                    const message = `处理批次 ${batchNum}/${totalBatches}，成功: ${validResults.length}/${batch.length}`;
                    
                    if (progressCallback) {
                        try {
                            progressCallback(progress, message);
                        } catch (callbackError) {
                            console.error('进度回调函数错误:', callbackError);
                        }
                    }
                    
                    console.log(`📊 批次 ${batchNum} 完成，成功: ${validResults.length}/${batch.length}`);
                    
                } catch (batchError) {
                    console.error(`❌ 批次 ${batchNum} 处理失败:`, batchError);
                    // 批次失败时，尝试逐个处理该批次中的创作者
                    for (const creator of batch) {
                        try {
                            const creatorData = {
                                author_unique_id: creator.unique_id,
                                author_nickname: creator.display_name || creator.unique_id,
                                title: creator.title || '',
                                create_time: creator.create_time || '',
                                signature: creator.signature || ''
                            };
                            const result = await this.analyzeCreator(creatorData);
                            if (result) results.push(result);
                        } catch (error) {
                            console.error(`❌ 单个创作者分析失败 ${creator.unique_id}:`, error.message);
                        }
                    }
                }
                
                // 批次间短暂延迟
                if (i + batchSize < creators.length) {
                    console.log('⏳ 批次间隔...');
                    await new Promise(resolve => setTimeout(resolve, 1500)); // 减少到1.5秒
                }
            }
        } catch (criticalError) {
            console.error('❌ 批量分析过程中发生严重错误:', criticalError);
            // 即使发生严重错误，也返回已处理的结果
        }
        
        // 统计和分类结果
        const brandRelated = results.filter(r => {
            if (r.account_type === 'official account' || r.account_type === 'matrix account') {
                return true;
            }
            if (r.account_type === 'ugc creator' && r.brand && r.brand.trim()) {
                // 检查分析详情是否明确说没有品牌合作
                const analysisDetails = (r.analysis_details || '').toLowerCase();
                const noPartnership = [
                    'no indication of a brand partnership',
                    'no clear brand partnership',
                    'no significant brand indicators'
                ].some(indicator => analysisDetails.includes(indicator));
                return !noPartnership;
            }
            return false;
        });
        
        const nonBrand = results.filter(r => !brandRelated.includes(r));
        
        // 分类统计
        const officialCount = results.filter(r => r.account_type === 'official account').length;
        const matrixCount = results.filter(r => r.account_type === 'matrix account').length;
        const ugcCount = results.filter(r => r.account_type === 'ugc creator').length;
        const nonBrandedCount = results.filter(r => r.account_type === 'non-branded creator').length;
        
        // 品牌分布统计
        const brandDistribution = {};
        brandRelated.forEach(r => {
            if (r.brand && r.brand.trim()) {
                const brand = r.brand.trim();
                if (!brandDistribution[brand]) {
                    brandDistribution[brand] = { official: 0, matrix: 0, ugc: 0, total: 0 };
                }
                if (r.account_type === 'official account') {
                    brandDistribution[brand].official++;
                } else if (r.account_type === 'matrix account') {
                    brandDistribution[brand].matrix++;
                } else {
                    brandDistribution[brand].ugc++;
                }
                brandDistribution[brand].total++;
            }
        });
        
        const analysisResults = {
            total_processed: results.length,
            brand_related_count: brandRelated.length,
            non_brand_count: nonBrand.length,
            
            // 详细分类统计
            official_brand_count: officialCount,
            matrix_account_count: matrixCount,
            ugc_creator_count: ugcCount,
            non_branded_creator_count: nonBrandedCount,
            
            // 品牌分布
            brand_distribution: brandDistribution,
            unique_brands_count: Object.keys(brandDistribution).length,
            
            // 数据数组
            brand_related_data: brandRelated,
            non_brand_data: nonBrand,
            all_data: results
        };
        
        console.log(`✅ 批量分析完成: 处理了 ${results.length}/${creators.length} 个创作者`);
        console.log(`📊 品牌相关: ${brandRelated.length}, 非品牌: ${nonBrand.length}`);
        
        return analysisResults;
    }

    // 生成视频ID
    generateVideoId() {
        return '7' + Math.floor(Math.random() * 900000000000000000 + 100000000000000000).toString();
    }
}

export default BrandAnalyzer; 