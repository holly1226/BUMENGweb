"""
文学作品语义搜索模块
使用 Qwen Embedding + BallTree 实现快速语义检索
"""

import json
import pickle
import numpy as np
import asyncio
from pathlib import Path
from typing import List, Dict, Tuple
from sklearn.neighbors import BallTree
from ai_handler import get_qwen_embedding_async

class LiteratureSearchEngine:
    """文学作品语义搜索引擎"""
    
    def __init__(self, storage_dir: str = "backend/storage"):
        self.storage_dir = Path(storage_dir)
        
        # 数据存储
        self.literature_works = []  # literature_mentor.json
        self.literature_embeddings = []
        self.literature_tree = None
        
        self.highpoints = {}  # highpoints.json
        self.highpoint_texts = []  # 展平后的文本
        self.highpoint_embeddings = []
        self.highpoint_tree = None
        self.highpoint_mapping = []  # 记录每个embedding对应的类别和key
        
        # 缓存文件路径
        self.cache_dir = self.storage_dir / "embeddings_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.literature_cache = self.cache_dir / "literature_embeddings.pkl"
        self.highpoint_cache = self.cache_dir / "highpoint_embeddings.pkl"
    
    async def initialize(self, force_rebuild: bool = False):
        """
        初始化搜索引擎
        Args:
            force_rebuild: 是否强制重建索引(忽略缓存)
        """
        print("🔧 [Search Engine] 正在初始化语义搜索引擎...")
        
        # 加载原始数据
        await self._load_raw_data()
        
        # 构建或加载索引
        if force_rebuild or not self._cache_exists():
            print("📊 [Search Engine] 开始构建向量索引...")
            await self._build_indices()
            self._save_cache()
        else:
            print("📦 [Search Engine] 从缓存加载向量索引...")
            self._load_cache()
        
        print("✅ [Search Engine] 搜索引擎就绪!")
        print(f"   - 文学作品库: {len(self.literature_works)} 部作品")
        print(f"   - 角色高光库: {len(self.highpoint_texts)} 个高光时刻")
    
    async def _load_raw_data(self):
        """加载原始JSON数据"""
        # 1. 加载文学作品
        literature_path = self.storage_dir / "literature_mentor.json"
        with open(literature_path, "r", encoding="utf-8") as f:
            self.literature_works = json.load(f)
        
        # 2. 加载高光时刻
        highpoint_path = self.storage_dir / "highpoints.json"
        with open(highpoint_path, "r", encoding="utf-8") as f:
            self.highpoints = json.load(f)
        
        # 3. 展平高光时刻数据
        self.highpoint_texts = []
        self.highpoint_mapping = []
        for category, moments in self.highpoints.items():
            for moment_key, moment_desc in moments.items():
                self.highpoint_texts.append(f"{moment_key}: {moment_desc}")
                self.highpoint_mapping.append({
                    "category": category,
                    "key": moment_key,
                    "description": moment_desc
                })
    
    async def _build_indices(self):
        """构建向量索引"""
        print("🔄 [Search Engine] 生成文学作品embedding...")
        
        # 1. 为文学作品生成embedding
        self.literature_embeddings = []
        for i, work in enumerate(self.literature_works):
            # 组合标题、作者、描述作为检索文本
            text = f"{work['title']} {work['author']} {work['desc']}"
            emb = await get_qwen_embedding_async(text, dimensions=512)
            self.literature_embeddings.append(emb)
            
            if (i + 1) % 100 == 0:
                print(f"   进度: {i+1}/{len(self.literature_works)}")
                await asyncio.sleep(0.1)  # 避免请求过快
        
        # 构建BallTree
        self.literature_tree = BallTree(
            np.array(self.literature_embeddings), 
            metric='euclidean'
        )
        print(f"✅ [Search Engine] 文学作品索引完成!")
        
        # 2. 为高光时刻生成embedding
        print("🔄 [Search Engine] 生成高光时刻embedding...")
        self.highpoint_embeddings = []
        for i, text in enumerate(self.highpoint_texts):
            emb = await get_qwen_embedding_async(text, dimensions=512)
            self.highpoint_embeddings.append(emb)
            
            if (i + 1) % 100 == 0:
                print(f"   进度: {i+1}/{len(self.highpoint_texts)}")
                await asyncio.sleep(0.1)
        
        # 构建BallTree
        self.highpoint_tree = BallTree(
            np.array(self.highpoint_embeddings),
            metric='euclidean'
        )
        print(f"✅ [Search Engine] 高光时刻索引完成!")
    
    def _cache_exists(self) -> bool:
        """检查缓存是否存在"""
        return (self.literature_cache.exists() and 
                self.highpoint_cache.exists())
    
    def _save_cache(self):
        """保存缓存"""
        print("💾 [Search Engine] 保存向量缓存...")
        
        # 保存文学作品缓存
        with open(self.literature_cache, "wb") as f:
            pickle.dump({
                "embeddings": self.literature_embeddings,
                "tree": self.literature_tree
            }, f)
        
        # 保存高光时刻缓存
        with open(self.highpoint_cache, "wb") as f:
            pickle.dump({
                "embeddings": self.highpoint_embeddings,
                "tree": self.highpoint_tree,
                "mapping": self.highpoint_mapping
            }, f)
        
        print("✅ [Search Engine] 缓存已保存")
    
    def _load_cache(self):
        """加载缓存"""
        # 加载文学作品缓存
        with open(self.literature_cache, "rb") as f:
            data = pickle.load(f)
            self.literature_embeddings = data["embeddings"]
            self.literature_tree = data["tree"]
        
        # 加载高光时刻缓存
        with open(self.highpoint_cache, "rb") as f:
            data = pickle.load(f)
            self.highpoint_embeddings = data["embeddings"]
            self.highpoint_tree = data["tree"]
            self.highpoint_mapping = data["mapping"]
    
    async def search_literature(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict]:
        """
        搜索相似的文学作品
        Args:
            query: 查询文本(如玩家的世界观建议)
            top_k: 返回前k个结果
        Returns:
            List[Dict]: 相似作品列表
        """
        if self.literature_tree is None:
            raise RuntimeError("搜索引擎未初始化,请先调用 initialize()")
        
        # 生成查询向量
        query_emb = await get_qwen_embedding_async(query, dimensions=512)
        
        # 检索最近邻
        distances, indices = self.literature_tree.query([query_emb], k=top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            work = self.literature_works[idx].copy()
            # 计算相似度分数(距离越小越相似)
            work['similarity_score'] = float(1 / (1 + distances[0][i]))
            work['distance'] = float(distances[0][i])
            results.append(work)
        
        return results
    
    async def search_highpoints(
        self,
        query: str,
        top_k: int = 3
    ) -> List[Dict]:
        """
        搜索相似的高光时刻
        Args:
            query: 查询文本(如玩家的角色偏好)
            top_k: 返回前k个结果
        Returns:
            List[Dict]: 相似高光时刻列表
        """
        if self.highpoint_tree is None:
            raise RuntimeError("搜索引擎未初始化,请先调用 initialize()")
        
        # 生成查询向量
        query_emb = await get_qwen_embedding_async(query, dimensions=512)
        
        # 检索最近邻
        distances, indices = self.highpoint_tree.query([query_emb], k=top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            moment = self.highpoint_mapping[idx].copy()
            moment['similarity_score'] = float(1 / (1 + distances[0][i]))
            moment['distance'] = float(distances[0][i])
            results.append(moment)
        
        return results
    
    async def search_for_game_init(
        self,
        suggestions: List[str],
        role_prefs: Dict[str, str],
        literature_top_k: int = 5,
        highpoint_top_k: int = 3
    ) -> Dict:
        """
        游戏初始化时的综合搜索
        Args:
            suggestions: 所有玩家的世界观建议列表
            role_prefs: 玩家角色偏好字典 {player_name: preference}
            literature_top_k: 文学作品返回数量
            highpoint_top_k: 每个玩家返回的高光时刻数量
        Returns:
            Dict: 包含文学作品推荐和角色高光推荐
        """
        print("🔍 [Search Engine] 开始综合检索...")
        
        # 1. 合并所有玩家建议,检索文学作品
        combined_suggestions = " ".join(suggestions)
        literature_results = await self.search_literature(
            combined_suggestions, 
            top_k=literature_top_k
        )
        
        print(f"📚 [Search Engine] 找到 {len(literature_results)} 部相似作品:")
        for work in literature_results:
            print(f"   - 《{work['title']}》{work['author']} (相似度: {work['similarity_score']:.3f})")
        
        # 2. 为每个玩家检索角色高光
        player_highpoints = {}
        for player_name, pref in role_prefs.items():
            if pref:  # 只有当玩家有偏好时才检索
                highpoints = await self.search_highpoints(pref, top_k=highpoint_top_k)
                player_highpoints[player_name] = highpoints
                
                print(f"✨ [Search Engine] 为玩家 {player_name} 找到高光时刻:")
                for hp in highpoints:
                    print(f"   - [{hp['category']}] {hp['key']}")
        
        return {
            "literature_recommendations": literature_results,
            "player_highpoints": player_highpoints
        }
    
    def format_for_prompt(self, search_results: Dict) -> str:
        """
        将搜索结果格式化为AI Prompt的输入
        Args:
            search_results: search_for_game_init 的返回结果
        Returns:
            str: 格式化的文本
        """
        lines = []
        
        # 1. 文学作品推荐
        lines.append("【参考文学作品】")
        for work in search_results["literature_recommendations"]:
            lines.append(f"- 《{work['title']}》({work['author']})")
            lines.append(f"  特点: {work['desc']}")
        
        lines.append("\n【玩家角色高光时刻设计参考】")
        # 2. 玩家高光时刻
        for player_name, highpoints in search_results["player_highpoints"].items():
            lines.append(f"\n玩家 {player_name} 的期望高光:")
            for hp in highpoints:
                lines.append(f"  - [{hp['category']}] {hp['key']}: {hp['description']}")
        
        return "\n".join(lines)


# 全局单例
_search_engine = None

async def get_search_engine() -> LiteratureSearchEngine:
    """获取全局搜索引擎实例(单例模式)"""
    global _search_engine
    if _search_engine is None:
        _search_engine = LiteratureSearchEngine()
        await _search_engine.initialize()
    return _search_engine


# 测试代码
async def test_search():
    """测试搜索功能"""
    engine = await get_search_engine()
    
    # 测试1: 搜索文学作品
    print("\n" + "="*60)
    print("测试1: 搜索推理悬疑类作品")
    results = await engine.search_literature("孤岛密室杀人悬疑推理", top_k=3)
    for work in results:
        print(f"- 《{work['title']}》 相似度: {work['similarity_score']:.3f}")
    
    # 测试2: 搜索高光时刻
    print("\n" + "="*60)
    print("测试2: 搜索权谋反转高光")
    highpoints = await engine.search_highpoints("我想在关键时刻揭露阴谋翻盘", top_k=3)
    for hp in highpoints:
        print(f"- [{hp['category']}] {hp['key']}: {hp['description']}")
    
    # 测试3: 游戏初始化综合搜索
    print("\n" + "="*60)
    print("测试3: 游戏初始化综合搜索")
    game_results = await engine.search_for_game_init(
        suggestions=["蒸汽朋克世界", "魔法学院", "悬疑推理"],
        role_prefs={
            "玩家A": "我想要智斗反转",
            "玩家B": "我想要团队配合"
        }
    )
    
    print("\n格式化后的Prompt参考:")
    print(engine.format_for_prompt(game_results))


if __name__ == "__main__":
    asyncio.run(test_search())
