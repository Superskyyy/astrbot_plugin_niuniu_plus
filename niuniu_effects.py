# Niuniu Effect System
# Decouples item effects from core game logic

import random
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class EffectTrigger(str, Enum):
    """Effect trigger points"""
    # Dajiao triggers
    BEFORE_DAJIAO = "before_dajiao"          # Before dajiao executes (can skip cooldown)
    AFTER_DAJIAO = "after_dajiao"            # After dajiao result calculated

    # Compare triggers
    BEFORE_COMPARE = "before_compare"        # Before compare starts (can intercept)
    ON_COMPARE_WIN = "on_compare_win"        # When user wins
    ON_COMPARE_LOSE = "on_compare_lose"      # When user loses
    AFTER_COMPARE = "after_compare"          # After compare ends
    ON_HALVING = "on_halving"                # When halving event triggers

    # Shop triggers
    ON_PURCHASE = "on_purchase"              # When item is purchased (active items)


@dataclass
class EffectContext:
    """Context passed to effect handlers"""
    # Common fields
    group_id: str
    user_id: str
    nickname: str
    user_data: Dict[str, Any]

    # Target fields (for compare)
    target_id: Optional[str] = None
    target_nickname: Optional[str] = None
    target_data: Optional[Dict[str, Any]] = None

    # State fields
    user_length: int = 0
    user_hardness: int = 0
    target_length: int = 0
    target_hardness: int = 0

    # Result fields (modified by effects)
    length_change: int = 0                   # Change to user's length
    target_length_change: int = 0            # Change to target's length
    hardness_change: int = 0                 # Change to user's hardness
    target_hardness_change: int = 0          # Change to target's hardness

    # Control flags
    skip_cooldown: bool = False              # Skip cooldown check
    intercept: bool = False                  # Intercept and stop processing
    prevent_loss: bool = False               # Prevent length loss
    prevent_halving: bool = False            # Prevent halving for user
    target_prevent_halving: bool = False     # Prevent halving for target

    # Messages
    messages: List[str] = field(default_factory=list)

    # Items to consume
    items_to_consume: List[str] = field(default_factory=list)
    target_items_to_consume: List[str] = field(default_factory=list)

    # Extra data for complex effects
    extra: Dict[str, Any] = field(default_factory=dict)


class ItemEffect:
    """Base class for item effects"""
    name: str = ""                           # Item name (must match shop item)
    triggers: List[EffectTrigger] = []       # Which triggers this effect listens to
    consume_on_use: bool = True              # Whether to consume item when effect triggers

    def should_trigger(self, trigger: EffectTrigger, ctx: EffectContext, user_items: Dict[str, int]) -> bool:
        """Check if this effect should trigger"""
        if trigger not in self.triggers:
            return False
        if user_items.get(self.name, 0) <= 0:
            return False
        return True

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        """Handle the trigger, modify context as needed"""
        raise NotImplementedError


class EffectManager:
    """Manages all item effects"""

    def __init__(self):
        self.effects: Dict[str, ItemEffect] = {}
        self._shop_ref = None  # Will be set by main plugin

    def set_shop(self, shop):
        """Set reference to shop for item operations"""
        self._shop_ref = shop

    def register(self, effect: ItemEffect):
        """Register an effect"""
        self.effects[effect.name] = effect

    def trigger(self, trigger: EffectTrigger, ctx: EffectContext,
                user_items: Dict[str, int], target_items: Optional[Dict[str, int]] = None) -> EffectContext:
        """
        Trigger all relevant effects.

        Args:
            trigger: The trigger point
            ctx: The effect context
            user_items: User's items dict
            target_items: Target's items dict (for compare)

        Returns:
            Modified context
        """
        for effect in self.effects.values():
            # Check user's items
            if effect.should_trigger(trigger, ctx, user_items):
                ctx = effect.on_trigger(trigger, ctx)
                if effect.consume_on_use and effect.name not in ctx.items_to_consume:
                    ctx.items_to_consume.append(effect.name)

                # If intercepted, stop processing
                if ctx.intercept:
                    break

        return ctx

    def consume_items(self, group_id: str, user_id: str, items: List[str]):
        """Consume items after effect processing"""
        if self._shop_ref:
            for item_name in items:
                self._shop_ref.consume_item(group_id, user_id, item_name)


# =============================================================================
# Built-in Item Effects
# =============================================================================

class ZhimingJiezouEffect(ItemEffect):
    """致命节奏 - Skip dajiao cooldown"""
    name = "致命节奏"
    triggers = [EffectTrigger.BEFORE_DAJIAO]
    consume_on_use = True

    def should_trigger(self, trigger: EffectTrigger, ctx: EffectContext, user_items: Dict[str, int]) -> bool:
        if not super().should_trigger(trigger, ctx, user_items):
            return False
        # Only trigger if actually on cooldown
        return ctx.extra.get('on_cooldown', False)

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        ctx.skip_cooldown = True
        ctx.messages.append(f"⚡ 触发致命节奏！{ctx.nickname} 无视冷却强行打胶！")
        # Force into bonus time window
        ctx.extra['force_bonus_window'] = True
        return ctx


class DuoxinmoEffect(ItemEffect):
    """夺心魔蝌蚪罐头 - Steal/clear length before compare"""
    name = "夺心魔蝌蚪罐头"
    triggers = [EffectTrigger.BEFORE_COMPARE]
    consume_on_use = True

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        effect_chance = random.random()

        if effect_chance < 0.5:  # 50% steal all
            stolen = ctx.target_length
            ctx.extra['duoxinmo_result'] = 'steal'
            ctx.extra['stolen_length'] = stolen
            ctx.length_change = stolen
            ctx.target_length_change = -ctx.target_length  # Target goes to 0
            ctx.messages.extend([
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"🎉 {ctx.nickname} 获得了夺心魔技能，夺取了 {ctx.target_nickname} 的全部长度！",
            ])
            ctx.intercept = True

        elif effect_chance < 0.7:  # 20% self clear
            ctx.extra['duoxinmo_result'] = 'self_clear'
            ctx.length_change = -ctx.user_length  # Go to 0
            ctx.messages.extend([
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"💔 {ctx.nickname} 使用夺心魔蝌蚪罐头，牛牛变成了夺心魔！！！",
            ])
            ctx.intercept = True

        else:  # 40% no effect
            ctx.extra['duoxinmo_result'] = 'no_effect'
            ctx.messages.extend([
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"⚠️ {ctx.nickname} 使用夺心魔蝌蚪罐头，但是罐头好像坏掉了...",
            ])
            ctx.intercept = True

        return ctx


class CuihuoZhuadaoEffect(ItemEffect):
    """淬火爪刀 - Extra plunder on win when underdog"""
    name = "淬火爪刀"
    triggers = [EffectTrigger.ON_COMPARE_WIN]
    consume_on_use = True

    def should_trigger(self, trigger: EffectTrigger, ctx: EffectContext, user_items: Dict[str, int]) -> bool:
        if not super().should_trigger(trigger, ctx, user_items):
            return False
        # Only trigger if length diff > 10 and user is shorter
        length_diff = abs(ctx.user_length - ctx.target_length)
        return length_diff > 10 and ctx.user_length < ctx.target_length

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        extra_loot = int(ctx.target_length * 0.1)
        ctx.length_change += extra_loot
        ctx.messages.append(f"🔥 淬火爪刀触发！额外掠夺 {extra_loot}cm！")
        return ctx


class YuzhenEffect(ItemEffect):
    """余震 - Prevent length loss on compare lose"""
    name = "余震"
    triggers = [EffectTrigger.ON_COMPARE_LOSE]
    consume_on_use = True

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        ctx.prevent_loss = True
        ctx.messages.append(f"🛡️ 【余震生效】{ctx.nickname} 未减少长度！")
        return ctx


class MiaocuijiaoEffect(ItemEffect):
    """妙脆角 - Prevent halving"""
    name = "妙脆角"
    triggers = [EffectTrigger.ON_HALVING]
    consume_on_use = True

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        ctx.prevent_halving = True
        ctx.messages.append(f"🛡️ {ctx.nickname} 的妙脆角生效，防止了长度减半！")
        return ctx


class MiaocuijiaoTargetEffect(ItemEffect):
    """妙脆角 (for target) - Prevent halving for target"""
    name = "妙脆角_target"  # Internal name, maps to same item
    triggers = [EffectTrigger.ON_HALVING]
    consume_on_use = True

    def should_trigger(self, trigger: EffectTrigger, ctx: EffectContext, user_items: Dict[str, int]) -> bool:
        # This effect checks target's items, not user's
        return False  # Will be handled specially in manager

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        ctx.target_prevent_halving = True
        ctx.messages.append(f"🛡️ {ctx.target_nickname} 的妙脆角生效，防止了长度减半！")
        ctx.target_items_to_consume.append("妙脆角")
        return ctx


# =============================================================================
# Active Item Effects (ON_PURCHASE)
# =============================================================================

class ActiveItemEffect(ItemEffect):
    """Base class for active items that apply stat changes on purchase"""
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active items don't go to inventory

    # Override these in subclasses
    length_change: int = 0
    hardness_change: int = 0

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        if self.length_change != 0:
            ctx.length_change += self.length_change
            if self.length_change > 0:
                ctx.messages.append(f"✨ 长度增加了{self.length_change}cm")
            else:
                ctx.messages.append(f"✨ 长度减少了{-self.length_change}cm")

        if self.hardness_change != 0:
            ctx.hardness_change += self.hardness_change
            if self.hardness_change > 0:
                ctx.messages.append(f"✨ 硬度增加了{self.hardness_change}")
            else:
                ctx.messages.append(f"✨ 硬度减少了{-self.hardness_change}")

        return ctx


class BalishijiaEffect(ActiveItemEffect):
    """巴黎世家 - +3 hardness"""
    name = "巴黎世家"
    hardness_change = 3


class BashideBanEffect(ActiveItemEffect):
    """巴适得板生长素 - +20 length, -2 hardness"""
    name = "巴适得板生长素"
    length_change = 20
    hardness_change = -2


class BumiezhiwoEffect(ActiveItemEffect):
    """不灭之握 - +30 length"""
    name = "不灭之握"
    length_change = 30


class AmstlangEffect(ActiveItemEffect):
    """阿姆斯特朗旋风喷射炮 - +100 length, +10 hardness"""
    name = "阿姆斯特朗旋风喷射炮"
    length_change = 100
    hardness_change = 10


class DutuyingbiEffect(ItemEffect):
    """赌徒硬币 - 50% double length, 50% halve length"""
    name = "赌徒硬币"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        current_length = ctx.user_length
        is_heads = random.random() < 0.5

        if current_length > 0:
            # 正数：正面翻倍(好)，反面减半(坏)
            if is_heads:
                ctx.length_change = current_length  # 翻倍
                ctx.messages.append(f"🎰 硬币正面朝上！长度翻倍！+{current_length}cm")
            else:
                loss = current_length // 2
                ctx.length_change = -loss
                ctx.messages.append(f"🎰 硬币反面朝上...长度减半！-{loss}cm")
        elif current_length < 0:
            # 负数：正面减半(好，接近0)，反面翻倍(坏，更负)
            if is_heads:
                gain = abs(current_length) // 2  # 向0靠近
                ctx.length_change = gain
                ctx.messages.append(f"🎰 硬币正面朝上！凹陷减半！+{gain}cm")
            else:
                loss = abs(current_length)  # 翻倍负数
                ctx.length_change = -loss
                ctx.messages.append(f"🎰 硬币反面朝上...凹得更深了！-{loss}cm")
        else:
            # 长度为0：随机±10
            change = random.randint(-10, 10)
            ctx.length_change = change
            if change >= 0:
                ctx.messages.append(f"🎰 硬币在空中悬停...从虚无中获得了{change}cm！")
            else:
                ctx.messages.append(f"🎰 硬币落入虚空...凹进去了{-change}cm！")
        return ctx


# =============================================================================
# 劫富济贫 Effect
# =============================================================================

class JiefuJipinEffect(ItemEffect):
    """劫富济贫 - Robin Hood: steal from richest, give to poorest 3"""
    name = "劫富济贫"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        # 需要从 extra 获取群组数据
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 无法获取群组数据")
            ctx.intercept = True
            return ctx

        # 过滤有效用户（有长度数据的）
        valid_users = [(uid, data) for uid, data in group_data.items()
                       if isinstance(data, dict) and 'length' in data]

        if len(valid_users) < 4:
            ctx.messages.append("❌ 群里牛牛不足4人，无法发动劫富济贫！")
            ctx.intercept = True
            return ctx

        # 按长度排序
        sorted_users = sorted(valid_users, key=lambda x: x[1].get('length', 0), reverse=True)

        # 找出首富
        richest_id, richest_data = sorted_users[0]
        richest_length = richest_data.get('length', 0)
        richest_name = richest_data.get('nickname', richest_id)

        # 检查自己是不是首富
        if richest_id == ctx.user_id:
            ctx.messages.append("😅 你就是群首富，劫谁？劫自己？")
            ctx.intercept = True
            ctx.extra['refund'] = True  # 标记需要退款
            return ctx

        # 检查首富长度
        if richest_length <= 0:
            ctx.messages.append(f"🤔 群里最长的是 {richest_name}（{richest_length}cm）...这也叫富？算了不抢了")
            ctx.intercept = True
            ctx.extra['refund'] = True
            return ctx

        # 计算抢夺数量（15%）
        steal_amount = int(richest_length * 0.15)
        if steal_amount < 1:
            steal_amount = 1

        # 找出最穷的3人（排除首富）
        poorest_3 = sorted_users[-3:]

        # 检查最穷的人里有没有首富（理论上不会，但防止边界情况）
        poorest_3 = [(uid, data) for uid, data in poorest_3 if uid != richest_id]

        if len(poorest_3) == 0:
            ctx.messages.append("❌ 找不到可以接济的穷人！")
            ctx.intercept = True
            ctx.extra['refund'] = True
            return ctx

        # 平分给最穷的人
        share_each = steal_amount // len(poorest_3)
        remainder = steal_amount % len(poorest_3)

        # 记录需要更新的数据
        ctx.extra['robin_hood'] = {
            'richest_id': richest_id,
            'richest_name': richest_name,
            'steal_amount': steal_amount,
            'beneficiaries': []
        }

        for i, (uid, data) in enumerate(poorest_3):
            # 第一个人获得余数
            amount = share_each + (remainder if i == 0 else 0)
            if amount > 0:
                ctx.extra['robin_hood']['beneficiaries'].append({
                    'user_id': uid,
                    'nickname': data.get('nickname', uid),
                    'amount': amount
                })

        # 构建消息
        beneficiary_texts = []
        for b in ctx.extra['robin_hood']['beneficiaries']:
            beneficiary_texts.append(f"  💰 {b['nickname']} +{b['amount']}cm")

        ctx.messages.extend([
            "🦸 ═══ 劫富济贫 ═══ 🦸",
            f"🎯 目标锁定：{richest_name}（{richest_length}cm）",
            f"💸 抢走了 {steal_amount}cm！",
            "📦 分发给最穷的群友：",
            *beneficiary_texts,
            "══════════════════"
        ])

        return ctx


# =============================================================================
# Effect Manager Factory
# =============================================================================

def create_effect_manager() -> EffectManager:
    """Create and initialize the effect manager with all built-in effects"""
    manager = EffectManager()

    # Register passive item effects
    manager.register(ZhimingJiezouEffect())
    manager.register(DuoxinmoEffect())
    manager.register(CuihuoZhuadaoEffect())
    manager.register(YuzhenEffect())
    manager.register(MiaocuijiaoEffect())

    # Register active item effects
    manager.register(BalishijiaEffect())
    manager.register(BashideBanEffect())
    manager.register(BumiezhiwoEffect())
    manager.register(AmstlangEffect())
    manager.register(DutuyingbiEffect())
    manager.register(JiefuJipinEffect())

    return manager
