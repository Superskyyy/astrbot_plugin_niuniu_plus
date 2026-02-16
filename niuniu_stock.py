# -*- coding: utf-8 -*-
"""
牛牛股市系统 - 妖牛股

设计理念：
- 只有一只股票：妖牛股
- 所有游戏事件都会影响股价
- 记录最近事件，让股市有故事感
"""

import os
import json
import math
import random
import time
from typing import Dict, Any, Tuple, List
from collections import deque

# 数据文件路径（和其他数据存在一起，避免重装丢失）
STOCK_DATA_FILE = 'data/niuniu_stock.json'

# 股票配置
STOCK_CONFIG = {
    "name": "妖牛股",
    "emoji": "🐂",
    "base_price": 100.0,
    "min_price": 0.01,
    "max_price": 999999.99,
    # 不同事件的波动范围
    "volatility": {
        "dajiao": (0.005, 0.02),    # 打胶：0.5%-2%
        "compare": (0.01, 0.05),     # 比划：1%-5%
        "item": (0.02, 0.08),        # 道具：2%-8%
        "chaos": (0.02, 0.08),       # 混沌事件：2%-8%
        "global": (0.05, 0.15),      # 全局：5%-15%
    },
}

# 事件描述模板 - 大量搞怪文案（每类至少20条）
EVENT_TEMPLATES = {
    "dajiao": {
        "up": [
            "📈 {nickname} 打胶增长 {change}cm，华尔街震惊！",
            "📈 {nickname} 勤劳打胶，巴菲特点赞",
            "📈 {nickname} 的手速带动了股价",
            "📈 {nickname} 打出了新高度，股民狂喜",
            "📈 {nickname} 一发入魂！妖牛股应声上涨",
            "📈 打胶打出GDP，{nickname} 功不可没",
            "📈 {nickname} 的牛牛带动经济复苏",
            "📈 专家称{nickname}打胶有利于股市健康",
            "📈 {nickname} 打胶的姿势很标准，股价认可",
            "📈 热搜：{nickname} 打胶引发牛市",
            "📈 {nickname} 打得好！散户跟风买入",
            "📈 {nickname} 的努力被市场看见了",
            "📈 「打胶兴邦」—— {nickname}",
            "📈 {nickname} 成为今日最佳打胶选手",
            "📈 {nickname} 打胶，妖牛股：我涨！",
            "📈 {nickname} 的打胶频率与股价高度正相关",
            "📈 机构研报：{nickname} 打胶是重大利好",
            "📈 {nickname} 打胶打出了投资价值",
            "📈 {nickname} 被评为「股市发动机」",
            "📈 「只要{nickname}在打胶，牛市就有希望」",
            "📈 {nickname} 的打胶技术获得市场高度认可",
            "📈 {nickname} 打胶，北向资金疯狂涌入",
            "📈 {nickname} 用实际行动证明打胶能救市",
            "📈 「打胶一小步，股价一大步」—— {nickname}",
            "📈 {nickname} 的牛牛成为市场风向标",
        ],
        "down": [
            "📉 {nickname} 打胶缩水 {change}cm，股民心凉",
            "📉 {nickname} 打胶翻车，散户割肉",
            "📉 {nickname} 的失误让股市蒙羞",
            "📉 {nickname} 打了个寂寞，股价应声下跌",
            "📉 {nickname} 手滑了？妖牛股暴跌！",
            "📉 {nickname} 打胶用力过猛，市场不买账",
            "📉 打胶也能亏钱？{nickname} 做到了",
            "📉 {nickname} 的操作看哭了股民",
            "📉 {nickname} 被列入打胶黑名单",
            "📉 {nickname} 打胶打出了熊市",
            "📉 分析师：{nickname} 的打胶姿势不对",
            "📉 {nickname} 打胶？股市：告辞！",
            "📉 {nickname} 的牛牛让市场失去信心",
            "📉 {nickname} 打胶引发踩踏事故",
            "📉 紧急避险！{nickname} 打胶了！",
            "📉 {nickname} 的打胶频率与股价负相关",
            "📉 机构研报：{nickname} 打胶是重大利空",
            "📉 {nickname} 打胶打出了恐慌情绪",
            "📉 {nickname} 被评为「股市绞肉机」",
            "📉 「只要{nickname}在打胶，熊市就有希望」",
            "📉 {nickname} 的打胶技术遭到市场唾弃",
            "📉 {nickname} 打胶，北向资金疯狂出逃",
            "📉 {nickname} 用实际行动证明打胶能砸盘",
            "📉 「打胶一小步，股价跌十步」—— {nickname}",
            "📉 {nickname} 的牛牛成为市场反向指标",
        ],
    },
    "compare": {
        "up": [
            "📈 {nickname} 比划大胜！股民开香槟",
            "📈 {nickname} 碾压对手，妖牛股狂飙",
            "📈 一场精彩比划，股价直冲云霄",
            "📈 {nickname} 的牛牛太强了，股市沸腾",
            "📈 {nickname} 赢得漂亮！机构疯狂买入",
            "📈 {nickname} 用实力证明了牛牛的价值",
            "📈 {nickname} 的胜利提振了市场信心",
            "📈 史诗级对决！{nickname} 获胜，股价新高",
            "📈 {nickname} 一战成名，股票涨停！",
            "📈 {nickname} 的牛牛震慑全场，股价应声上涨",
            "📈 「这就是实力」—— {nickname}",
            "📈 {nickname} 比划获胜，韭菜们乐开花",
            "📈 {nickname} 用牛牛捍卫了股价！",
            "📈 {nickname} 获胜！分析师上调评级",
            "📈 {nickname} 的硬度征服了市场",
            "📈 {nickname} 比划赢了，赢麻了！",
            "📈 「比划王者」{nickname} 带飞股价",
            "📈 {nickname} 的胜利让空头瑟瑟发抖",
            "📈 {nickname} 赢得毫无悬念，股价涨得理所当然",
            "📈 {nickname} 的牛牛就是市场的定海神针",
            "📈 {nickname} 获胜！游资：买买买！",
            "📈 {nickname} 用牛牛创造了新的历史",
            "📈 「{nickname} 赢了，我们都赢了」—— 股民",
            "📈 {nickname} 的胜利是对股市最好的激励",
            "📈 {nickname} 一骑绝尘，股价跟着绝尘",
        ],
        "down": [
            "📉 {nickname} 比划惨败，股市一片绿",
            "📉 {nickname} 被对手碾压，股民哭晕",
            "📉 惨烈比划！{nickname} 落败，股价跳水",
            "📉 {nickname} 的牛牛不争气，股市崩盘",
            "📉 {nickname} 输得太惨，机构清仓跑路",
            "📉 {nickname} 的失败打击了市场信心",
            "📉 「菜就多练」—— 市场对{nickname}的评价",
            "📉 {nickname} 被暴打，股价被暴打",
            "📉 {nickname} 的牛牛丢人了，股价跟着丢",
            "📉 {nickname} 惨遭碾压，散户：润了润了",
            "📉 {nickname} 输麻了，妖牛股也输麻了",
            "📉 {nickname} 的比划表演令人失望",
            "📉 {nickname} 被教做人，股价被教做股",
            "📉 {nickname} 的硬度不够硬，股价不够挺",
            "📉 {nickname} 输了，股民的心也碎了",
            "📉 {nickname} 比划输了，输傻了！",
            "📉 「比划青铜」{nickname} 拖累股价",
            "📉 {nickname} 的失败让多头绝望",
            "📉 {nickname} 输得毫无悬念，股价跌得理所当然",
            "📉 {nickname} 的牛牛就是市场的定时炸弹",
            "📉 {nickname} 落败！游资：跑跑跑！",
            "📉 {nickname} 用牛牛创造了新的耻辱",
            "📉 「{nickname} 输了，我们都输了」—— 股民",
            "📉 {nickname} 的失败是对股市最大的打击",
            "📉 {nickname} 一败涂地，股价跟着涂地",
        ],
    },
    "item": {
        "up": [
            "📈 {nickname} 使用道具血赚！股市疯狂",
            "📈 道具效果逆天！{nickname} 带飞股价",
            "📈 {nickname} 的操作秀翻全场，股价起飞",
            "📈 {nickname} 用道具创造奇迹！",
            "📈 {nickname} 的道具选择很明智，股市认可",
            "📈 「科技改变命运」—— {nickname}",
            "📈 {nickname} 氪金成功，股价跟着成功",
            "📈 道具在手，{nickname} 说涨就涨",
            "📈 {nickname} 的道具让市场刮目相看",
            "📈 {nickname} 用道具征服了妖牛股",
            "📈 {nickname} 的神操作引发跟风买入",
            "📈 道具玩得好，{nickname} 带动股价跑",
            "📈 {nickname} 的道具带来了财富效应",
            "📈 {nickname} 道具开挂，股价跟着开挂",
            "📈 {nickname} 被评为「道具之王」，股价点赞",
            "📈 {nickname} 的道具技术登峰造极",
            "📈 「充钱使我变强」—— {nickname} 的成功秘诀",
            "📈 {nickname} 用道具打开了财富之门",
            "📈 道具商城感谢{nickname}的鼎力支持",
            "📈 {nickname} 的道具操作堪称教科书",
            "📈 {nickname} 用道具改写了股市走向",
            "📈 「道具就是生产力」—— {nickname}",
            "📈 {nickname} 的道具让对手瑟瑟发抖",
            "📈 {nickname} 靠道具逆天改命",
            "📈 {nickname} 的氪金实力令人敬畏",
        ],
        "down": [
            "📉 {nickname} 道具翻车！股民心态崩了",
            "📉 道具反噬！{nickname} 拖累股市",
            "📉 {nickname} 的操作堪称灾难，股价暴跌",
            "📉 {nickname} 用道具搞砸了一切",
            "📉 「这钱花得不值」—— {nickname}",
            "📉 {nickname} 的道具成了股市毒药",
            "📉 {nickname} 氪金失败，股价跟着失败",
            "📉 道具在手，{nickname} 说跌就跌",
            "📉 {nickname} 的道具让市场失望透顶",
            "📉 {nickname} 用道具毁灭了希望",
            "📉 {nickname} 的骚操作引发恐慌抛售",
            "📉 道具玩脱了，{nickname} 害惨股民",
            "📉 {nickname} 的道具带来了绝望",
            "📉 {nickname} 道具翻车，股价原地爆炸",
            "📉 {nickname} 被评为「道具毒瘤」",
            "📉 {nickname} 的道具技术一塌糊涂",
            "📉 「充钱使我变弱」—— {nickname} 的惨痛教训",
            "📉 {nickname} 用道具打开了地狱之门",
            "📉 道具商城：{nickname} 是我们的反面教材",
            "📉 {nickname} 的道具操作堪称灾难片",
            "📉 {nickname} 用道具改写了股市悲剧",
            "📉 「道具就是毁灭力」—— {nickname}",
            "📉 {nickname} 的道具让所有人瑟瑟发抖",
            "📉 {nickname} 靠道具加速毁灭",
            "📉 {nickname} 的氪金实力令人窒息",
        ],
    },
    "chaos": {
        "up": [
            "🌀 混沌风暴来袭！妖牛股居然涨了？",
            "🌀 {nickname} 触发混沌，股市反而狂飙",
            "🌀 混沌能量注入，股价疯涨！",
            "🌀 混沌之中蕴含机遇！股价暴涨",
            "🌀 {nickname} 的混沌成了财富密码",
            "🌀 「乱世出妖股」—— 今日行情",
            "🌀 混沌风暴过境，留下一地涨幅",
            "🌀 {nickname} 在混沌中找到了财富",
            "🌀 混沌？股价：我偏要涨！",
            "🌀 {nickname} 触发的混沌很对味",
            "🌀 混沌风暴竟是利好？神奇！",
            "🌀 {nickname} 的混沌能量被市场吸收",
            "🌀 「混沌即机遇」—— 妖牛股如是说",
            "🌀 风暴中心的{nickname}，意外带来牛市",
            "🌀 混沌之力注入妖牛股，起飞！",
            "🌀 {nickname} 驾驭混沌，征服股市",
            "🌀 「我命由我不由天」—— 混沌中的{nickname}",
            "🌀 混沌？不过是{nickname}的垫脚石",
            "🌀 {nickname} 在混沌中杀出一条血路",
            "🌀 混沌风暴成了{nickname}的助推器",
            "🌀 「混沌是最好的机会」—— {nickname}",
            "🌀 {nickname} 用混沌重塑了市场信心",
            "🌀 混沌过后，{nickname} 笑到最后",
            "🌀 {nickname} 在风暴眼中找到了财富密码",
            "🌀 「感谢混沌」—— {nickname}",
        ],
        "down": [
            "🌀 混沌风暴肆虐！股价惨遭毒手",
            "🌀 {nickname} 引发混沌，股市地震！",
            "🌀 混沌吞噬一切，妖牛股暴跌",
            "🌀 混沌带来的只有毁灭！",
            "🌀 {nickname} 的混沌成了股市噩梦",
            "🌀 「大乱必有大跌」—— 今日行情",
            "🌀 混沌风暴过境，留下一片废墟",
            "🌀 {nickname} 在混沌中毁灭了财富",
            "🌀 混沌来临！股价：我先死为敬",
            "🌀 {nickname} 触发的混沌太猛了",
            "🌀 混沌风暴就是利空，没得商量",
            "🌀 {nickname} 的混沌能量太邪恶了",
            "🌀 「混沌即毁灭」—— 股民遗言",
            "🌀 风暴中心的{nickname}，亲手葬送牛市",
            "🌀 混沌之力摧毁妖牛股，完蛋！",
            "🌀 {nickname} 被混沌反噬，股市陪葬",
            "🌀 「我命由天不由我」—— 混沌中的{nickname}",
            "🌀 混沌？成了{nickname}的绊脚石",
            "🌀 {nickname} 在混沌中迷失了方向",
            "🌀 混沌风暴成了{nickname}的绞肉机",
            "🌀 「混沌是最大的灾难」—— {nickname}",
            "🌀 {nickname} 用混沌毁灭了市场信心",
            "🌀 混沌过后，{nickname} 一无所有",
            "🌀 {nickname} 在风暴眼中失去了一切",
            "🌀 「诅咒混沌」—— {nickname}",
        ],
    },
    "global": {
        "up": [
            "🌍 全局事件爆发！妖牛股原地起飞",
            "🌍 {nickname} 引发大事件，全场沸腾",
            "🌍 重大事件！股价开启暴走模式",
            "🌍 {nickname} 改变了整个群的命运",
            "🌍 「历史性时刻」—— 今日股市",
            "🌍 {nickname} 创造历史，股价创新高",
            "🌍 全局震动！妖牛股一飞冲天",
            "🌍 {nickname} 的操作载入史册",
            "🌍 大事件触发，股民集体高潮",
            "🌍 {nickname} 成为今日MVP，股价致敬",
            "🌍 「一人得道，股价升天」",
            "🌍 {nickname} 的壮举让股市起立鼓掌",
            "🌍 全局事件利好！涨疯了！",
            "🌍 {nickname} 触发隐藏剧情，股价暴涨",
            "🌍 「见证历史」—— 妖牛股新高",
            "🌍 {nickname} 的操作被写入教科书",
            "🌍 「{nickname} 拯救了我们」—— 全体股民",
            "🌍 {nickname} 用一己之力撬动股市",
            "🌍 全局事件：{nickname} 成为救世主",
            "🌍 「神一般的操作」—— {nickname}",
            "🌍 {nickname} 的大事件让所有人受益",
            "🌍 妖牛股感谢{nickname}的鼎力相助",
            "🌍 {nickname} 改变世界，股价改变命运",
            "🌍 「今天，我们都是{nickname}」",
            "🌍 {nickname} 的传奇将被永远铭记",
        ],
        "down": [
            "🌍 全局事件冲击！股价原地去世",
            "🌍 {nickname} 的操作震动全局，震碎股价",
            "🌍 灾难性事件！妖牛股跳水",
            "🌍 {nickname} 毁灭了整个群的希望",
            "🌍 「黑色一刻」—— 今日股市",
            "🌍 {nickname} 创造历史，股价创新低",
            "🌍 全局震动！妖牛股坠入深渊",
            "🌍 {nickname} 的操作遗臭万年",
            "🌍 大事件触发，股民集体emo",
            "🌍 {nickname} 成为今日罪人，股价唾弃",
            "🌍 「一人作死，股价遭殃」",
            "🌍 {nickname} 的壮举让股市鸦雀无声",
            "🌍 全局事件利空！跌惨了！",
            "🌍 {nickname} 触发毁灭剧情，股价暴跌",
            "🌍 「见证历史」—— 妖牛股新低",
            "🌍 {nickname} 的操作被写入黑历史",
            "🌍 「{nickname} 害惨了我们」—— 全体股民",
            "🌍 {nickname} 用一己之力砸穿股市",
            "🌍 全局事件：{nickname} 成为毁灭者",
            "🌍 「鬼一般的操作」—— {nickname}",
            "🌍 {nickname} 的大事件让所有人遭殃",
            "🌍 妖牛股诅咒{nickname}的所作所为",
            "🌍 {nickname} 毁灭世界，股价毁灭一切",
            "🌍 「今天，我们都恨{nickname}」",
            "🌍 {nickname} 的罪行将被永远唾弃",
        ],
    },
}


class NiuniuStock:
    """牛牛股市管理器 - 单例"""
    _instance = None

    @classmethod
    def get(cls) -> 'NiuniuStock':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._load_data()

    def _load_data(self):
        """加载股市数据"""
        if os.path.exists(STOCK_DATA_FILE):
            try:
                with open(STOCK_DATA_FILE, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except:
                self._data = {}
        else:
            self._data = {}

    def _save_data(self):
        """保存股市数据"""
        os.makedirs('data', exist_ok=True)
        with open(STOCK_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _get_group_data(self, group_id: str) -> Dict[str, Any]:
        """获取群组股市数据，不存在则初始化"""
        group_id = str(group_id)
        if group_id not in self._data:
            self._data[group_id] = {
                "price": STOCK_CONFIG["base_price"],
                "holdings": {},      # {user_id: shares}
                "buy_times": {},     # {user_id: timestamp} 最近买入时间
                "events": [],        # 最近事件列表
                "last_update": time.time(),
            }
            self._save_data()
        return self._data[group_id]

    # ==================== 股价操作 ====================

    def get_price(self, group_id: str) -> float:
        """获取当前股价"""
        data = self._get_group_data(group_id)
        return data.get("price", STOCK_CONFIG["base_price"])

    def get_events(self, group_id: str, limit: int = 10) -> List[Dict]:
        """获取最近事件"""
        data = self._get_group_data(group_id)
        events = data.get("events", [])
        return events[-limit:] if events else []

    def _add_event(self, group_id: str, event_type: str, nickname: str,
                   direction: int, change_pct: float, length_change: float = 0):
        """添加事件记录"""
        data = self._get_group_data(group_id)

        # 选择事件描述
        templates = EVENT_TEMPLATES.get(event_type, EVENT_TEMPLATES["item"])
        template_list = templates["up"] if direction > 0 else templates["down"]
        desc = random.choice(template_list).format(
            nickname=nickname,
            change=abs(length_change)
        )

        event = {
            "time": time.time(),
            "type": event_type,
            "nickname": nickname,
            "direction": direction,
            "change_pct": change_pct,
            "desc": desc,
        }

        if "events" not in data:
            data["events"] = []
        data["events"].append(event)

        # 只保留最近50条
        if len(data["events"]) > 50:
            data["events"] = data["events"][-50:]

    def _update_price(self, group_id: str, event_type: str,
                      direction: int, magnitude: float = 1.0,
                      nickname: str = "???", length_change: float = 0) -> Tuple[float, float, int]:
        """
        更新股价

        Args:
            group_id: 群组ID
            event_type: 事件类型
            direction: 方向 (1=涨, -1=跌, 0=随机)
            magnitude: 幅度系数
            nickname: 触发者昵称
            length_change: 长度变化量

        Returns:
            (new_price, change_pct, actual_direction)
        """
        data = self._get_group_data(group_id)
        current_price = data.get("price", STOCK_CONFIG["base_price"])

        # 获取波动范围
        vol_range = STOCK_CONFIG["volatility"].get(event_type, (0.01, 0.05))
        min_vol, max_vol = vol_range

        # 计算波动幅度
        volatility = random.uniform(min_vol, max_vol) * magnitude

        # 决定方向
        if direction == 0:
            actual_direction = random.choice([1, -1])
        else:
            actual_direction = direction

        # 计算新价格
        change_pct = volatility * actual_direction
        new_price = current_price * (1 + change_pct)

        # 限制价格范围
        new_price = max(STOCK_CONFIG["min_price"],
                       min(STOCK_CONFIG["max_price"], new_price))
        new_price = round(new_price, 2)

        data["price"] = new_price
        data["last_update"] = time.time()

        # 记录事件
        self._add_event(group_id, event_type, nickname,
                       actual_direction, abs(change_pct) * 100, length_change)

        self._save_data()

        return new_price, change_pct, actual_direction

    # ==================== 用户操作 ====================

    def get_holdings(self, group_id: str, user_id: str) -> float:
        """获取用户持仓股数"""
        data = self._get_group_data(group_id)
        return data.get("holdings", {}).get(str(user_id), 0)

    def _get_user_stats(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """获取用户投资统计"""
        data = self._get_group_data(group_id)
        if "user_stats" not in data:
            data["user_stats"] = {}
        user_id_str = str(user_id)
        if user_id_str not in data["user_stats"]:
            data["user_stats"][user_id_str] = {
                "total_invested": 0,      # 累计投入金币
                "total_withdrawn": 0,     # 累计取出金币
                "cost_basis": 0,          # 当前持仓成本
                "total_profit": 0,        # 历史总盈利
                "total_loss": 0,          # 历史总亏损
                "buy_count": 0,           # 购买次数
                "sell_count": 0,          # 卖出次数
            }
        return data["user_stats"][user_id_str]

    def buy(self, group_id: str, user_id: str, coins: float) -> Tuple[bool, str, float]:
        """
        购买股票
        返回: (成功, 消息, 购买股数)
        注意：先涨价再成交，防止套利
        """
        if coins <= 0:
            return False, "❌ 购买金额必须大于0", 0

        # 计算手续费（3%）
        fee = round(coins * 0.03, 2)
        actual_coins = coins - fee

        data = self._get_group_data(group_id)
        old_price = data.get("price", STOCK_CONFIG["base_price"])

        # 先计算买入对价格的影响（用实际购买金额计算，先涨价再成交，防止套利）
        impact = min(0.02, 0.001 + actual_coins / 10000 * 0.01)  # 0.1%-2%
        new_price = old_price * (1 + impact)
        new_price = min(STOCK_CONFIG["max_price"], round(new_price, 2))
        price_change_pct = impact * 100

        # 按涨后的价格成交
        shares = actual_coins / new_price

        # 更新持仓
        user_id_str = str(user_id)
        if "holdings" not in data:
            data["holdings"] = {}

        current = data["holdings"].get(user_id_str, 0)
        data["holdings"][user_id_str] = current + shares

        # 记录买入时间
        if "buy_times" not in data:
            data["buy_times"] = {}
        data["buy_times"][user_id_str] = time.time()

        # 更新用户统计（记录实际投入，不包括手续费）
        stats = self._get_user_stats(group_id, user_id)
        stats["total_invested"] += actual_coins
        stats["cost_basis"] += actual_coins
        stats["buy_count"] += 1

        # 更新股价
        data["price"] = new_price

        self._save_data()

        return True, (
            f"✅ 购买成功！\n"
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']}\n"
            f"📦 +{shares:.4f}股\n"
            f"💰 支付 {coins:.0f}金币 (含手续费 {fee:.0f})\n"
            f"💵 实际购买 {actual_coins:.0f}金币\n"
            f"📈 成交价 {new_price:.2f}/股 (买入推高 +{price_change_pct:.2f}%)"
        ), shares

    # 救市文案
    BAILOUT_TEXTS = [
        "🏛️ 「中央牛行」宣布紧急救市！",
        "🚨 牛牛央行：「绝不允许股市崩盘！」",
        "💼 神秘资金入场！传闻是牛牛国家队！",
        "🦸 「大牛不能倒！」—— 牛牛财政部",
        "🏦 牛牛证监会：「我们有无限子弹！」",
        "📢 紧急通知：牛牛主权基金正在抄底！",
        "🎺 「救市号角」吹响！散户热泪盈眶！",
        "🛡️ 牛牛平准基金出手了！",
        "⚡ 「闪电救市」计划启动！",
        "🌟 神秘力量介入！妖牛股绝地反弹！",
        "📜 牛牛国务院：「股市稳定关乎国运！」",
        "🎯 传说中的「国家牛队」终于出手！",
        "💎 「钻石手」资金强势托底！",
        "🚀 「牛牛QE」来了！印钞救市！",
        "🏆 牛牛央妈出手，空头瑟瑟发抖！",
    ]

    BAILOUT_SUCCESS_TEXTS = [
        "🎉 救市成功！妖牛股重燃希望！",
        "✨ 股价已稳！散户高呼万岁！",
        "🐂 牛市回来了！感谢国家队！",
        "💪 妖牛股：「我胡汉三又回来了！」",
        "🌈 雨过天晴！股市重现彩虹！",
        "🎊 空头被按在地上摩擦！",
        "💰 「这就是国家的力量」—— 股民",
        "🔔 「抄底成功」的钟声响起！",
    ]

    # 砸盘文案
    DUMP_TEXTS = [
        "🏛️ 「中央牛行」宣布抛售国有股！",
        "🚨 牛牛央行：「市场需要冷静！」",
        "💼 神秘资金出逃！传闻是牛牛国家队！",
        "🦹 「让市场教训一下投机者」—— 牛牛财政部",
        "🏦 牛牛证监会：「泡沫必须挤破！」",
        "📢 紧急通知：牛牛主权基金正在减持！",
        "🎺 「砸盘号角」吹响！散户瑟瑟发抖！",
        "⚔️ 牛牛平准基金反手做空了！",
        "⚡ 「闪电砸盘」计划启动！",
        "🌑 神秘力量介入！妖牛股直线跳水！",
        "📜 牛牛国务院：「房住不炒，股也一样！」",
        "🎯 传说中的「国家牛队」居然砸盘！",
        "💀 「死亡螺旋」启动！",
        "🔨 「牛牛QT」来了！缩表砸盘！",
        "👻 牛牛央妈反手一刀，多头哭晕在厕所！",
    ]

    DUMP_SUCCESS_TEXTS = [
        "💀 砸盘成功！妖牛股跌入深渊！",
        "😱 股价崩了！散户欲哭无泪！",
        "🐻 熊市来了！感谢国家队？",
        "💔 妖牛股：「我还会回来的...吧？」",
        "🌧️ 乌云密布！股市一片哀嚎！",
        "😈 多头被按在地上摩擦！",
        "💸 「这就是国家的力量」—— 空头",
        "🔔 「逃顶成功」的钟声响起！",
    ]

    # 玩家操盘文案（拉盘）
    PLAYER_BAILOUT_TEXTS = [
        "🎩 {name} 一掷千金，强行拉盘！",
        "💰 {name} 化身庄家，疯狂扫货！",
        "🐋 {name} 大鲸鱼入场！散户跟上！",
        "🔥 {name} 怒砸真金白银，我就是国家队！",
        "🏦 {name}：「信我，梭哈！」",
        "🎰 {name} 用金币铺出一条牛路！",
        "⚡ {name} 以一己之力托住了盘面！",
        "💎 {name}：「钻石手永不卖出！」",
    ]

    # 玩家操盘文案（砸盘）
    PLAYER_DUMP_TEXTS = [
        "🎩 {name} 一掷千金，强行砸盘！",
        "💀 {name} 化身庄家，疯狂抛售！",
        "🐋 {name} 大鲸鱼出逃！散户慌了！",
        "🔥 {name} 怒砸真金白银做空！",
        "🏦 {name}：「给我跌！」",
        "🎰 {name} 用金币砸出一个大坑！",
        "⚡ {name} 以一己之力打崩了盘面！",
        "👻 {name}：「空头永远是对的！」",
    ]

    def bailout(self, group_id: str, coins: float, operator: str = None) -> Tuple[bool, str]:
        """
        救市/砸盘 - 系统/玩家资金操纵股价
        coins > 0: 救市（推高股价）
        coins < 0: 砸盘（压低股价）
        operator: 操作者昵称（None表示管理员/系统）
        返回: (成功, 消息)
        """
        if coins == 0:
            return False, "❌ 金额不能为0"

        data = self._get_group_data(group_id)
        old_price = data.get("price", STOCK_CONFIG["base_price"])

        # 计算影响（对数衰减：小额微波动，大额有上限）
        abs_coins = abs(coins)
        impact = 0.01 * math.log2(1 + abs_coins / 1000)

        is_player = operator is not None

        if coins > 0:
            # 救市：推高股价
            new_price = old_price * (1 + impact)
            new_price = min(STOCK_CONFIG["max_price"], round(new_price, 2))
            direction = 1
            if is_player:
                action_texts = self.PLAYER_BAILOUT_TEXTS
            else:
                action_texts = self.BAILOUT_TEXTS
            success_texts = self.BAILOUT_SUCCESS_TEXTS
            action_name = "操盘资金" if is_player else "救市资金"
            action_desc = "虚空购入"
            price_symbol = "📈"
            change_str = f"+{impact * 100:.2f}%"
        else:
            # 砸盘：压低股价
            new_price = old_price * (1 - impact)
            new_price = max(STOCK_CONFIG["min_price"], round(new_price, 2))
            direction = -1
            if is_player:
                action_texts = self.PLAYER_DUMP_TEXTS
            else:
                action_texts = self.DUMP_TEXTS
            success_texts = self.DUMP_SUCCESS_TEXTS
            action_name = "操盘资金" if is_player else "砸盘资金"
            action_desc = "虚空抛售"
            price_symbol = "📉"
            change_str = f"-{impact * 100:.2f}%"

        # 计算虚拟股数（用于显示）
        virtual_shares = abs_coins / old_price

        # 更新股价（不记录持仓！）
        data["price"] = new_price
        data["last_update"] = time.time()

        # 记录事件
        event_nickname = operator if is_player else "牛牛国家队"
        event = {
            "time": time.time(),
            "type": "bailout" if coins > 0 else "dump",
            "nickname": event_nickname,
            "direction": direction,
            "change_pct": impact * 100,
            "desc": random.choice(action_texts).format(name=event_nickname),
        }

        if "events" not in data:
            data["events"] = []
        data["events"].append(event)

        if len(data["events"]) > 50:
            data["events"] = data["events"][-50:]

        self._save_data()

        action_text = random.choice(action_texts).format(name=event_nickname)
        success_text = random.choice(success_texts)

        return True, (
            f"{action_text}\n"
            f"═══════════════════════\n"
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']}\n"
            f"💵 {action_name}: {abs_coins:.0f}金币\n"
            f"📦 {action_desc}: {virtual_shares:.4f}股 (已销毁)\n"
            f"{price_symbol} 股价变动: {old_price:.2f} → {new_price:.2f} ({change_str})\n"
            f"═══════════════════════\n"
            f"{success_text}"
        )

    # 重置文案
    RESET_TEXTS = [
        "🔄 「妖牛股」宣布退市重组！",
        "💥 牛牛证监会：「推倒重来！」",
        "🌪️ 金融风暴过后，一切归零...",
        "🏚️ 「妖牛股」破产清算完成！",
        "📜 历史翻篇，新的韭菜正在成长...",
        "🎰 牛牛赌场关门大吉，明天重新开业！",
        "🧹 大扫除完成！股市焕然一新！",
        "⚡ 系统维护完成，数据已重置！",
    ]

    RESET_SUCCESS_TEXTS = [
        "✨ 新的征程开始了！",
        "🐂 妖牛股涅槃重生！",
        "🌅 新的一天，新的韭菜！",
        "💰 所有人回到同一起跑线！",
        "🎯 重新开始，谁能成为股神？",
        "🚀 股市已重置，冲！",
    ]

    def reset(self, group_id: str) -> Tuple[bool, str]:
        """
        重置股市 - 清除所有数据，股价回归基准
        返回: (成功, 消息)
        """
        data = self._get_group_data(group_id)

        # 统计重置前的数据
        old_price = data.get("price", STOCK_CONFIG["base_price"])
        holder_count = len(data.get("holdings", {}))
        total_shares = sum(data.get("holdings", {}).values())

        # 重置所有数据
        self._data[str(group_id)] = {
            "price": STOCK_CONFIG["base_price"],
            "holdings": {},
            "user_stats": {},
            "events": [],
            "last_update": time.time(),
        }

        self._save_data()

        reset_text = random.choice(self.RESET_TEXTS)
        success_text = random.choice(self.RESET_SUCCESS_TEXTS)

        return True, (
            f"{reset_text}\n"
            f"═══════════════════════\n"
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']} 已重置\n"
            f"📊 原股价: {old_price:.2f} → 100.00\n"
            f"👥 清仓人数: {holder_count}人\n"
            f"📦 销毁股数: {total_shares:.4f}股\n"
            f"═══════════════════════\n"
            f"{success_text}"
        )

    def _calculate_tax(self, profit: float, avg_coins: float) -> Tuple[float, float, str]:
        """
        计算阶梯累进税
        返回: (税额, 有效税率, 税率档位描述)
        """
        from niuniu_config import StockTaxConfig

        if profit <= 0 or avg_coins <= 0:
            return 0, 0, ""

        total_tax = 0
        prev_threshold = 0
        bracket_details = []

        for multiplier, rate in StockTaxConfig.TAX_BRACKETS:
            threshold = avg_coins * multiplier
            if profit <= prev_threshold:
                break

            # 本档位的应税金额
            taxable_in_bracket = min(profit, threshold) - prev_threshold
            if taxable_in_bracket > 0:
                tax_in_bracket = taxable_in_bracket * rate
                total_tax += tax_in_bracket
                if rate > 0:
                    bracket_details.append(f"{int(rate*100)}%档:{tax_in_bracket:.0f}")

            prev_threshold = threshold

        effective_rate = total_tax / profit if profit > 0 else 0
        bracket_str = " + ".join(bracket_details) if bracket_details else "免税"

        return total_tax, effective_rate, bracket_str

    def sell(self, group_id: str, user_id: str,
             shares: float = None, avg_coins: float = 0) -> Tuple[bool, str, float]:
        """
        卖出股票
        shares=None 表示全部卖出
        avg_coins: 群内金币平均值，用于计算收益税
        返回: (成功, 消息, 获得金币-税后)
        注意：先跌价再成交，防止套利
        """
        from niuniu_config import StockTaxConfig

        data = self._get_group_data(group_id)
        user_id_str = str(user_id)

        current = data.get("holdings", {}).get(user_id_str, 0)
        if current <= 0:
            return False, f"❌ 你没有持有 {STOCK_CONFIG['name']}", 0

        # 全部卖出
        if shares is None or shares >= current:
            shares = current

        if shares <= 0:
            return False, "❌ 卖出数量必须大于0", 0

        old_price = data.get("price", STOCK_CONFIG["base_price"])

        # 先计算卖出对价格的影响（用旧价估算金额）
        estimated_coins = shares * old_price
        impact = min(0.02, 0.001 + estimated_coins / 10000 * 0.01)  # 0.1%-2%
        new_price = old_price * (1 - impact)
        new_price = max(STOCK_CONFIG["min_price"], round(new_price, 2))
        price_change_pct = impact * 100

        # 按跌后的价格成交（先跌价再成交，防止套利）
        coins = round(shares * new_price, 2)

        # 计算基础手续费（3%）
        fee = round(coins * 0.03, 2)

        # 计算这部分股票的成本（按比例）
        stats = self._get_user_stats(group_id, user_id)
        sell_ratio = shares / current
        cost_of_sold = stats["cost_basis"] * sell_ratio
        profit_or_loss = coins - cost_of_sold

        # 计算收益税（仅对正收益征税）
        tax_amount = 0
        tax_rate = 0
        tax_bracket_str = ""
        if profit_or_loss > 0 and avg_coins > 0:
            tax_amount, tax_rate, tax_bracket_str = self._calculate_tax(profit_or_loss, avg_coins)

        # 税后+扣除手续费后实际获得金币
        coins_after_all_fees = coins - tax_amount - fee

        # 更新统计（记录税后+手续费后的数据）
        stats["total_withdrawn"] += coins_after_all_fees
        stats["cost_basis"] -= cost_of_sold
        stats["sell_count"] += 1
        if profit_or_loss >= 0:
            stats["total_profit"] += (profit_or_loss - tax_amount - fee)
        else:
            stats["total_loss"] += abs(profit_or_loss) + fee  # 亏损时所有费用都算损失

        # 更新持仓
        data["holdings"][user_id_str] = current - shares
        if data["holdings"][user_id_str] <= 0:
            del data["holdings"][user_id_str]
            # 清仓时重置成本和买入时间
            stats["cost_basis"] = 0
            if user_id_str in data.get("buy_times", {}):
                del data["buy_times"][user_id_str]

        # 更新股价
        data["price"] = new_price

        self._save_data()

        # 构建消息
        lines = [
            f"✅ 卖出成功！",
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']}",
            f"📦 -{shares:.4f}股",
            f"📉 成交价 {new_price:.2f}/股 (卖出压低 -{price_change_pct:.2f}%)",
            f"💵 卖出总额 {coins:.0f}金币",
        ]

        # 盈亏显示
        if profit_or_loss >= 0:
            lines.append(f"📈 本次盈利 +{profit_or_loss:.0f}金币")
        else:
            lines.append(f"📉 本次亏损 {profit_or_loss:.0f}金币")

        # 手续费显示
        lines.append(f"💸 手续费: -{fee:.0f}金币 (3%)")

        # 税收显示
        if tax_amount > 0:
            lines.append("")
            lines.append(random.choice(StockTaxConfig.TAX_TEXTS))
            lines.append(f"📊 群平均财富: {avg_coins:.0f}金币")
            lines.append(f"📈 收益倍数: {profit_or_loss/avg_coins:.1f}倍")
            lines.append(f"💸 收益税: -{tax_amount:.0f}金币 ({tax_bracket_str})")
            lines.append(f"📋 有效税率: {tax_rate*100:.1f}%")

            # 根据税率选择文案
            if tax_rate >= 0.95:
                lines.append(random.choice(StockTaxConfig.ULTIMATE_TAX_TEXTS))
            elif tax_rate >= 0.50:
                lines.append(random.choice(StockTaxConfig.EXTREME_TAX_TEXTS))
            elif tax_rate >= 0.30:
                lines.append(random.choice(StockTaxConfig.HIGH_TAX_TEXTS))
            elif tax_rate <= 0.10:
                lines.append(random.choice(StockTaxConfig.LOW_TAX_TEXTS))

        # 最终到手
        lines.append("")
        lines.append(f"💰 最终到手: {coins_after_all_fees:.0f}金币")

        return True, "\n".join(lines), coins_after_all_fees

    def force_liquidate(self, group_id: str, user_id: str, shares: float) -> bool:
        """
        强制清算股票（含笑五步癫等场景使用）
        股票被强制销毁，用户不获得任何收益，记录为纯损失

        Args:
            group_id: 群组ID
            user_id: 用户ID
            shares: 要清算的股数

        Returns:
            是否成功
        """
        data = self._get_group_data(group_id)
        user_id_str = str(user_id)

        current = data.get("holdings", {}).get(user_id_str, 0)
        if current <= 0 or shares <= 0:
            return False

        shares = min(shares, current)  # 不能清算超过持有数量

        # 获取统计数据
        stats = self._get_user_stats(group_id, user_id)

        # 计算被清算股票的成本（按比例）
        sell_ratio = shares / current
        cost_of_liquidated = stats["cost_basis"] * sell_ratio

        # 记录为纯损失（没有收益）
        stats["total_loss"] += cost_of_liquidated
        stats["cost_basis"] -= cost_of_liquidated
        stats["sell_count"] += 1

        # 更新持仓
        data["holdings"][user_id_str] = current - shares
        if data["holdings"][user_id_str] <= 0:
            del data["holdings"][user_id_str]
            stats["cost_basis"] = 0
            if user_id_str in data.get("buy_times", {}):
                del data["buy_times"][user_id_str]

        self._save_data()
        return True

    # ==================== 显示格式化 ====================

    def format_market(self, group_id: str) -> str:
        """格式化股市行情（含最近事件）"""
        data = self._get_group_data(group_id)
        price = data.get("price", STOCK_CONFIG["base_price"])
        base = STOCK_CONFIG["base_price"]
        change_pct = (price - base) / base * 100

        # 涨跌趋势
        if change_pct > 50:
            trend = f"🚀🚀 +{change_pct:.1f}%"
            status = "疯牛行情"
        elif change_pct > 10:
            trend = f"🚀 +{change_pct:.1f}%"
            status = "牛市"
        elif change_pct > 0:
            trend = f"📈 +{change_pct:.1f}%"
            status = "小涨"
        elif change_pct > -10:
            trend = f"📉 {change_pct:.1f}%"
            status = "小跌"
        elif change_pct > -50:
            trend = f"💥 {change_pct:.1f}%"
            status = "熊市"
        else:
            trend = f"💀💀 {change_pct:.1f}%"
            status = "崩盘"

        lines = [
            f"{STOCK_CONFIG['emoji']} ═══ {STOCK_CONFIG['name']} ═══ {STOCK_CONFIG['emoji']}",
            "",
            f"💰 当前股价: {price:.2f}金币/股",
            f"📊 涨跌幅: {trend}",
            f"🎭 市场状态: {status}",
            "",
            "═══ 最近动态 ═══",
        ]

        # 最近事件
        events = self.get_events(group_id, 8)
        if events:
            for event in reversed(events):  # 最新的在前
                lines.append(f"  • {event['desc']}")
        else:
            lines.append("  暂无交易动态")

        lines.extend([
            "",
            "═══════════════════════",
            "📌 牛牛股市 购买 <金额|梭哈>",
            "📌 牛牛股市 出售 [数量/全部]",
            "📌 牛牛股市 持仓",
        ])

        return "\n".join(lines)

    def format_holdings(self, group_id: str, user_id: str, nickname: str) -> str:
        """格式化用户持仓"""
        shares = self.get_holdings(group_id, user_id)
        price = self.get_price(group_id)
        stats = self._get_user_stats(group_id, user_id)

        # 获取统计数据
        total_invested = stats.get("total_invested", 0)
        total_withdrawn = stats.get("total_withdrawn", 0)
        cost_basis = stats.get("cost_basis", 0)
        total_profit = stats.get("total_profit", 0)
        total_loss = stats.get("total_loss", 0)
        buy_count = stats.get("buy_count", 0)
        sell_count = stats.get("sell_count", 0)

        # 没有任何交易记录
        if buy_count == 0 and shares <= 0:
            return f"📊 {nickname} 的投资档案\n\n💼 还没有参与过股市交易\n💡 输入「牛牛股市 购买 <金额|梭哈>」开始投资"

        lines = [
            f"📊 {nickname} 的投资档案",
            f"═══════════════════════",
        ]

        # 当前持仓
        if shares > 0:
            value = shares * price
            # 浮动盈亏 = 当前市值 - 成本
            unrealized_pl = value - cost_basis
            if cost_basis > 0:
                unrealized_pct = unrealized_pl / cost_basis * 100
            else:
                unrealized_pct = 0

            if unrealized_pl >= 0:
                pl_str = f"📈 +{unrealized_pl:.0f} (+{unrealized_pct:.1f}%)"
            else:
                pl_str = f"📉 {unrealized_pl:.0f} ({unrealized_pct:.1f}%)"

            # 平均成本
            avg_cost = cost_basis / shares if shares > 0 else 0

            lines.extend([
                "",
                f"💼 ── 当前持仓 ──",
                f"   📦 持有股数: {shares:.4f}股",
                f"   💰 当前市值: {value:.0f}金币",
                f"   💵 持仓成本: {cost_basis:.0f}金币",
                f"   📊 平均成本: {avg_cost:.2f}/股",
                f"   📈 浮动盈亏: {pl_str}",
            ])
        else:
            lines.extend([
                "",
                f"💼 ── 当前持仓 ──",
                f"   📭 空仓",
            ])

        # 历史统计
        net_pl = total_profit - total_loss  # 已实现净盈亏
        total_net = net_pl + (shares * price - cost_basis if shares > 0 else 0)  # 总盈亏（已实现+浮动）

        lines.extend([
            "",
            f"📜 ── 历史统计 ──",
            f"   💸 累计投入: {total_invested:.0f}金币",
            f"   💰 累计取出: {total_withdrawn:.0f}金币",
            f"   ✅ 历史盈利: +{total_profit:.0f}金币",
            f"   ❌ 历史亏损: -{total_loss:.0f}金币",
            f"   📊 已实现净盈亏: {'+' if net_pl >= 0 else ''}{net_pl:.0f}金币",
        ])

        # 交易次数
        lines.extend([
            "",
            f"🔢 ── 交易统计 ──",
            f"   🛒 购买次数: {buy_count}次",
            f"   🏷️ 卖出次数: {sell_count}次",
        ])

        # 当前股价
        lines.extend([
            "",
            f"═══════════════════════",
            f"📈 当前股价: {price:.2f}金币/股",
        ])

        return "\n".join(lines)


# ==================== 钩子函数 ====================

# 事件类型中文名
EVENT_TYPE_NAMES = {
    "dajiao": "打胶",
    "compare": "比划",
    "item": "道具",
    "chaos": "混沌风暴",
    "global": "全局事件",
}


def stock_hook(group_id: str,
               nickname: str = "???",
               event_type: str = None,
               item_name: str = None,
               length_change: float = 0,
               hardness_change: int = 0,
               coins_change: float = 0,
               volatility: Tuple[float, float] = None,
               templates: Dict[str, List[str]] = None,
               mean_reversion: bool = False) -> str:
    """
    股市钩子函数 - 供其他模块调用

    所有游戏事件都应调用此函数，股市会根据事件类型和变化量更新股价

    Args:
        group_id: 群组ID
        nickname: 触发者昵称
        event_type: 事件类型 (dajiao/compare/chaos/global)，使用内置模板
        item_name: 道具名称（用于 plain 模板显示）
        length_change: 长度变化量
        hardness_change: 硬度变化量
        coins_change: 金币变化量
        volatility: 波动范围 (min, max)，如果不指定则根据 event_type 自动选择
        templates: 自定义模板 {"up": [...], "down": [...], "plain": [...]}
                   如果提供 plain，则使用 plain 模板（不区分涨跌）
                   如果提供了 templates，则忽略 event_type 的内置模板
        mean_reversion: 是否使用均值回归模式（道具购买专用）
                        True时涨跌概率由当前股价与基准价的偏离决定

    Returns:
        股市影响消息，可附加到事件输出末尾

    Examples:
        # 打胶/比划，使用内置模板
        msg = stock_hook(group_id, "小明", event_type="dajiao", length_change=10)

        # 普通道具，有专属模板
        msg = stock_hook(group_id, "小明", item_name="劫富济贫",
                         length_change=50,
                         volatility=(0.03, 0.10),
                         templates={"up": ["劫富成功！牛市狂欢！"], "down": ["劫富翻车！"]})

        # 道具购买，使用均值回归模式
        msg = stock_hook(group_id, "小明", item_name="巴黎牛家",
                         volatility=(0.02, 0.06),
                         mean_reversion=True)
    """
    try:
        stock = NiuniuStock.get()

        # 获取变化前价格
        old_price = stock.get_price(group_id)

        # 确定波动范围
        if volatility is None:
            if event_type and event_type in STOCK_CONFIG["volatility"]:
                volatility = STOCK_CONFIG["volatility"][event_type]
            else:
                volatility = (0.001, 0.005)  # 默认微波动

        min_vol, max_vol = volatility

        # 计算幅度系数：变化量越大，影响越大
        total_change = length_change + hardness_change * 10 + coins_change * 0.1
        magnitude = min(3.0, 1.0 + abs(total_change) / 50)

        # 计算涨跌概率
        if mean_reversion:
            # 均值回归模式（道具购买专用）
            # 股价高于基准 → 倾向下跌回归
            # 股价低于基准 → 倾向上涨回归
            base_price = STOCK_CONFIG["base_price"]
            deviation = (old_price - base_price) / base_price  # 偏离比例

            # 偏离越大，回归力度越大（最高85%概率回归）
            regression_strength = min(0.35, abs(deviation) * 0.5)

            if deviation > 0:
                # 股价偏高，倾向下跌回归
                up_probability = 0.5 - regression_strength
            elif deviation < 0:
                # 股价偏低，倾向上涨回归
                up_probability = 0.5 + regression_strength
            else:
                up_probability = 0.5
        elif event_type in ("chaos", "global"):
            # 混沌和全局事件保持 50/50
            up_probability = 0.5
        else:
            # 常规模式：变化量影响概率
            # 基础概率 50%，变化量可以将概率偏移到 15%-85%
            # 正变化 → 涨概率增加，负变化 → 跌概率增加
            bias = min(0.35, abs(total_change) / 50 * 0.35)  # 最多偏移 35%
            if total_change > 0:
                up_probability = 0.5 + bias  # 50%-85% 涨
            elif total_change < 0:
                up_probability = 0.5 - bias  # 15%-50% 涨（即 50%-85% 跌）
            else:
                up_probability = 0.5

        # 计算波动幅度
        vol = random.uniform(min_vol, max_vol) * magnitude

        # 根据概率决定实际方向
        actual_direction = 1 if random.random() < up_probability else -1

        # 计算新价格
        change_pct = vol * actual_direction
        data = stock._get_group_data(group_id)
        current_price = data.get("price", STOCK_CONFIG["base_price"])
        new_price = current_price * (1 + change_pct)

        # 限制价格范围
        new_price = max(STOCK_CONFIG["min_price"],
                       min(STOCK_CONFIG["max_price"], new_price))
        new_price = round(new_price, 2)

        data["price"] = new_price
        data["last_update"] = time.time()

        # 生成事件描述
        change_pct_display = abs(change_pct) * 100
        if actual_direction > 0:
            trend_emoji = "📈"
            trend_str = f"+{change_pct_display:.2f}%"
        else:
            trend_emoji = "📉"
            trend_str = f"-{change_pct_display:.2f}%"

        # 选择模板
        if templates and "plain" in templates:
            # 使用 plain 模板（不区分涨跌）
            template = random.choice(templates["plain"])
            desc = template.format(
                nickname=nickname,
                item_name=item_name or "道具",
                change=f"{trend_str}"
            )
        elif templates:
            # 使用自定义 up/down 模板
            template_list = templates.get("up" if actual_direction > 0 else "down", [])
            if template_list:
                template = random.choice(template_list)
                desc = template.format(
                    nickname=nickname,
                    item_name=item_name or "道具",
                    change=abs(length_change)
                )
            else:
                desc = f"{nickname} 的操作影响了股市"
        elif event_type and event_type in EVENT_TEMPLATES:
            # 使用内置 event_type 模板
            builtin_templates = EVENT_TEMPLATES[event_type]
            template_list = builtin_templates["up"] if actual_direction > 0 else builtin_templates["down"]
            template = random.choice(template_list)
            desc = template.format(
                nickname=nickname,
                change=abs(length_change)
            )
        else:
            # 无模板，使用简单描述
            desc = f"{nickname} 的操作影响了股市"

        # 记录事件
        event = {
            "time": time.time(),
            "type": event_type or "item",
            "nickname": nickname,
            "direction": actual_direction,
            "change_pct": abs(change_pct) * 100,
            "desc": desc,
        }

        if "events" not in data:
            data["events"] = []
        data["events"].append(event)

        # 只保留最近50条
        if len(data["events"]) > 50:
            data["events"] = data["events"][-50:]

        stock._save_data()

        # 格式化股市影响消息
        return f"📊 妖牛股 {trend_emoji}{trend_str} ({old_price:.2f}→{new_price:.2f})"

    except Exception as e:
        # 股市更新失败不应影响主流程
        return ""
