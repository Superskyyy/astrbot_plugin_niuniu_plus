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
import random
import time
from typing import Dict, Any, Tuple, List
from collections import deque

# 数据文件路径
PLUGIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STOCK_DATA_FILE = os.path.join(PLUGIN_DIR, "niuniu_stock.json")

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
        "chaos": (0.05, 0.20),       # 混沌：5%-20%
        "global": (0.10, 0.30),      # 全局：10%-30%
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
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        with open(STOCK_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _get_group_data(self, group_id: str) -> Dict[str, Any]:
        """获取群组股市数据，不存在则初始化"""
        group_id = str(group_id)
        if group_id not in self._data:
            self._data[group_id] = {
                "price": STOCK_CONFIG["base_price"],
                "holdings": {},      # {user_id: shares}
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

    def buy(self, group_id: str, user_id: str, coins: float) -> Tuple[bool, str, float]:
        """
        购买股票
        返回: (成功, 消息, 购买股数)
        """
        if coins <= 0:
            return False, "❌ 购买金额必须大于0", 0

        data = self._get_group_data(group_id)
        price = data.get("price", STOCK_CONFIG["base_price"])

        shares = coins / price

        # 更新持仓
        user_id_str = str(user_id)
        if "holdings" not in data:
            data["holdings"] = {}

        current = data["holdings"].get(user_id_str, 0)
        data["holdings"][user_id_str] = current + shares

        self._save_data()

        return True, (
            f"✅ 购买成功！\n"
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']}\n"
            f"📦 +{shares:.4f}股\n"
            f"💰 花费 {coins:.0f}金币\n"
            f"📈 成交价 {price:.2f}/股"
        ), shares

    def sell(self, group_id: str, user_id: str,
             shares: float = None) -> Tuple[bool, str, float]:
        """
        卖出股票
        shares=None 表示全部卖出
        返回: (成功, 消息, 获得金币)
        """
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

        price = data.get("price", STOCK_CONFIG["base_price"])
        coins = shares * price

        # 更新持仓
        data["holdings"][user_id_str] = current - shares
        if data["holdings"][user_id_str] <= 0:
            del data["holdings"][user_id_str]

        self._save_data()

        return True, (
            f"✅ 卖出成功！\n"
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']}\n"
            f"📦 -{shares:.4f}股\n"
            f"💰 获得 {coins:.0f}金币\n"
            f"📉 成交价 {price:.2f}/股"
        ), coins

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
            "📌 牛牛股市 购买 <金额>",
            "📌 牛牛股市 出售 [数量/全部]",
            "📌 牛牛股市 持仓",
        ])

        return "\n".join(lines)

    def format_holdings(self, group_id: str, user_id: str, nickname: str) -> str:
        """格式化用户持仓"""
        shares = self.get_holdings(group_id, user_id)
        price = self.get_price(group_id)

        if shares <= 0:
            return f"📊 {nickname} 的持仓\n\n💼 空仓，快去买点妖牛股吧！"

        value = shares * price
        base_value = shares * STOCK_CONFIG["base_price"]
        profit = value - base_value
        profit_pct = (value - base_value) / base_value * 100 if base_value > 0 else 0

        if profit >= 0:
            profit_str = f"📈 +{profit:.0f}金币 (+{profit_pct:.1f}%)"
        else:
            profit_str = f"📉 {profit:.0f}金币 ({profit_pct:.1f}%)"

        lines = [
            f"📊 {nickname} 的持仓",
            "",
            f"{STOCK_CONFIG['emoji']} {STOCK_CONFIG['name']}",
            f"   📦 持有 {shares:.4f}股",
            f"   💰 市值 {value:.0f}金币",
            f"   📊 盈亏 {profit_str}",
            "",
            f"📈 当前股价: {price:.2f}/股",
        ]

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


def stock_hook(group_id: str, event_type: str,
               nickname: str = "???",
               length_change: float = 0,
               hardness_change: int = 0,
               coins_change: float = 0,
               extra: Dict = None) -> str:
    """
    股市钩子函数 - 供其他模块调用

    所有游戏事件都应调用此函数，股市会根据事件类型和变化量更新股价

    Args:
        group_id: 群组ID
        event_type: 事件类型 (dajiao/compare/item/chaos/global)
        nickname: 触发者昵称
        length_change: 长度变化量
        hardness_change: 硬度变化量
        coins_change: 金币变化量
        extra: 额外数据

    Returns:
        股市影响消息，可附加到事件输出末尾

    Examples:
        msg = stock_hook(group_id, "dajiao", "小明", length_change=10)
        # 返回: "📊 妖牛股 📈+1.5% (98.50→100.00)"
    """
    try:
        stock = NiuniuStock.get()

        # 获取变化前价格
        old_price = stock.get_price(group_id)

        # 计算方向：正变化=涨，负变化=跌，无变化=随机
        total_change = length_change + hardness_change * 10
        if total_change > 0:
            direction = 1
        elif total_change < 0:
            direction = -1
        else:
            direction = 0  # 随机

        # 计算幅度系数：变化量越大，影响越大
        magnitude = min(3.0, 1.0 + abs(total_change) / 50)

        # 混沌和全局事件：方向随机，幅度更大
        if event_type in ("chaos", "global"):
            direction = 0
            magnitude *= 1.5

        new_price, change_pct, actual_direction = stock._update_price(
            group_id, event_type, direction, magnitude, nickname, length_change
        )

        # 格式化股市影响消息
        change_pct_display = abs(change_pct) * 100
        if actual_direction > 0:
            trend = f"📈+{change_pct_display:.2f}%"
        else:
            trend = f"📉-{change_pct_display:.2f}%"

        return f"📊 妖牛股 {trend} ({old_price:.2f}→{new_price:.2f})"

    except Exception as e:
        # 股市更新失败不应影响主流程
        return ""
