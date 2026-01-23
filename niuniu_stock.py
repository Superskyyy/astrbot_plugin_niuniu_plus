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

# 事件描述模板
EVENT_TEMPLATES = {
    "dajiao": {
        "up": [
            "📈 {nickname} 打胶增长 {change}cm，股价微涨",
            "📈 {nickname} 勤劳打胶，市场看好",
            "📈 {nickname} 的努力带动了股价",
        ],
        "down": [
            "📉 {nickname} 打胶缩水 {change}cm，股价下跌",
            "📉 {nickname} 打胶翻车，市场恐慌",
            "📉 {nickname} 的失误拖累股价",
        ],
    },
    "compare": {
        "up": [
            "📈 {nickname} 比划大胜，股价上涨",
            "📈 {nickname} 碾压对手，市场沸腾",
            "📈 一场精彩比划，股价飙升",
        ],
        "down": [
            "📉 {nickname} 比划惨败，股价暴跌",
            "📉 {nickname} 被对手碾压，市场哀嚎",
            "📉 惨烈比划，股价跳水",
        ],
    },
    "item": {
        "up": [
            "📈 {nickname} 使用道具大赚，股价上涨",
            "📈 道具效果爆表，市场狂欢",
            "📈 {nickname} 的操作引爆股价",
        ],
        "down": [
            "📉 {nickname} 道具翻车，股价暴跌",
            "📉 道具反噬！市场恐慌抛售",
            "📉 {nickname} 的失误震动股市",
        ],
    },
    "chaos": {
        "up": [
            "🌀 混沌风暴来袭！股价剧烈波动后上涨",
            "🌀 {nickname} 触发混沌，股市狂飙",
            "🌀 混沌能量注入，妖牛股疯涨",
        ],
        "down": [
            "🌀 混沌风暴肆虐！股价崩盘",
            "🌀 {nickname} 引发混沌，股市地震",
            "🌀 混沌吞噬一切，妖牛股暴跌",
        ],
    },
    "global": {
        "up": [
            "🌍 全局事件爆发！股价疯涨",
            "🌍 {nickname} 引发大事件，市场沸腾",
            "🌍 重大事件！妖牛股起飞",
        ],
        "down": [
            "🌍 全局事件冲击！股价崩盘",
            "🌍 {nickname} 的操作震动全局",
            "🌍 灾难性事件！妖牛股跳水",
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
