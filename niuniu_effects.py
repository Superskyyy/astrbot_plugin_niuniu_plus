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
    """夺牛魔蝌蚪罐头 - Steal/clear/chaos/explode before compare"""
    name = "夺牛魔蝌蚪罐头"
    triggers = [EffectTrigger.BEFORE_COMPARE]
    consume_on_use = True

    # 夺取成功文案
    STEAL_TEXTS = [
        "🎭 罐头打开了...里面是一只愤怒的夺牛魔！",
        "👹 夺牛魔苏醒了！「你的牛牛现在是我的了！」",
        "🌀 罐头散发出诡异的光芒...夺取成功！",
        "⚡ 夺牛魔：「谢谢你的牛牛，很好吃！」",
        "🔮 蝌蚪化身夺牛魔，疯狂吸收对方精华！",
    ]

    # 自爆文案
    SELF_CLEAR_TEXTS = [
        "💀 罐头里的蝌蚪暴走了...攻击了自己！",
        "😱 夺牛魔：「搞错了，我是来夺你的！」",
        "🌑 罐头黑化了...你的牛牛消失在黑暗中",
        "☠️ 蝌蚪叛变！你被自己的武器背刺了！",
        "🕳️ 罐头变成黑洞，吞噬了你的一切...",
    ]

    # 混沌风暴文案
    CHAOS_TEXTS = [
        "🌪️ 罐头爆炸了！混沌能量席卷战场！",
        "🎲 蝌蚪疯狂了！触发了混沌风暴！",
        "⚡ 罐头不稳定...时空裂缝出现了！",
        "🌀 「这不是普通的罐头...是混沌之源！」",
    ]

    # 大自爆文案
    EXPLODE_TEXTS = [
        "💥 罐头临界了...同归于尽吧！！！",
        "🔥 蝌蚪：「我带你们一起走！」",
        "☢️ 核爆警告！双方都遭殃！",
        "💣 罐头变成了炸弹...轰！！！",
    ]

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import DuoxinmoConfig
        roll = random.random()

        threshold1 = DuoxinmoConfig.STEAL_ALL_CHANCE  # 0.5
        threshold2 = threshold1 + DuoxinmoConfig.CHAOS_STORM_CHANCE  # 0.7
        threshold3 = threshold2 + DuoxinmoConfig.DAZIBAO_CHANCE  # 0.9
        # Remaining = SELF_CLEAR_CHANCE (0.1) -> 1.0

        if roll < threshold1:  # 50% 夺取全部长度和硬度
            self._handle_steal(ctx)

        elif roll < threshold2:  # 20% 触发原版混沌风暴
            self._handle_chaos(ctx)

        elif roll < threshold3:  # 20% 触发原版大自爆
            self._handle_explode(ctx)

        else:  # 10% 清空自己长度和硬度
            self._handle_self_clear(ctx)

        return ctx

    def _handle_steal(self, ctx: EffectContext):
        """50% 夺取对方全部长度和硬度"""
        target_shield_charges = 0
        if ctx.target_data:
            target_shield_charges = ctx.target_data.get('shield_charges', 0)

        damage_reduction = min(target_shield_charges * 0.1, 1.0)

        if damage_reduction >= 1.0:
            ctx.extra['duoxinmo_result'] = 'blocked'
            ctx.messages.extend([
                "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
                random.choice(self.STEAL_TEXTS),
                f"🛡️ 但 {ctx.target_nickname} 的护盾（{target_shield_charges}层）完全抵挡！",
                "💨 夺牛魔悻悻离去...",
            ])
            ctx.intercept = True
        else:
            # 夺取长度
            base_steal_len = ctx.target_length
            actual_steal_len = int(base_steal_len * (1 - damage_reduction))
            # 夺取硬度
            base_steal_hard = ctx.target_hardness - 1  # 保底1点
            actual_steal_hard = int(base_steal_hard * (1 - damage_reduction))

            ctx.extra['duoxinmo_result'] = 'steal'
            ctx.extra['stolen_length'] = actual_steal_len
            ctx.extra['stolen_hardness'] = actual_steal_hard
            ctx.length_change = actual_steal_len
            ctx.target_length_change = -actual_steal_len
            ctx.hardness_change = actual_steal_hard
            ctx.extra['target_hardness_change'] = -actual_steal_hard

            ctx.messages.extend([
                "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
                random.choice(self.STEAL_TEXTS),
            ])
            if damage_reduction > 0:
                ctx.messages.append(f"🛡️ {ctx.target_nickname} 护盾抵挡了{int(damage_reduction*100)}%！")
            ctx.messages.extend([
                f"💰 夺取 {actual_steal_len}cm + {actual_steal_hard}点硬度！",
                f"😭 {ctx.target_nickname} 被掏空了...",
            ])
            ctx.intercept = True

    def _handle_chaos(self, ctx: EffectContext):
        """20% 触发原版混沌风暴效果"""
        ctx.extra['duoxinmo_result'] = 'chaos'

        # 添加夺牛魔前缀消息
        ctx.messages.extend([
            "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
            random.choice(self.CHAOS_TEXTS),
            ""
        ])

        # 检查是否有 group_data（需要 main.py 传入）
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 混沌风暴失败：无法获取群组数据")
            ctx.intercept = True
            return

        # 延迟导入避免循环引用（HundunFengbaoEffect 定义在后面）
        from niuniu_effects import HundunFengbaoEffect
        chaos_effect = HundunFengbaoEffect()
        chaos_ctx = EffectContext(
            group_id=ctx.group_id,
            user_id=ctx.user_id,
            nickname=ctx.nickname,
            user_data=ctx.user_data,
            user_length=ctx.user_length,
            user_hardness=ctx.user_hardness
        )
        chaos_ctx.extra['group_data'] = group_data

        # 触发混沌风暴
        chaos_ctx = chaos_effect.on_trigger(EffectTrigger.ON_PURCHASE, chaos_ctx)

        # 合并结果
        ctx.messages.extend(chaos_ctx.messages)
        ctx.extra['chaos_storm'] = chaos_ctx.extra.get('chaos_storm', {})
        ctx.extra['consume_shields'] = chaos_ctx.extra.get('consume_shields', [])
        ctx.intercept = True

    def _handle_explode(self, ctx: EffectContext):
        """20% 触发原版大自爆效果"""
        ctx.extra['duoxinmo_result'] = 'explode'

        # 添加夺牛魔前缀消息
        ctx.messages.extend([
            "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
            random.choice(self.EXPLODE_TEXTS),
            ""
        ])

        # 检查是否有 group_data
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 大自爆失败：无法获取群组数据")
            ctx.intercept = True
            return

        # 延迟导入避免循环引用（DazibaoEffect 定义在后面）
        from niuniu_effects import DazibaoEffect
        dazibao_effect = DazibaoEffect()
        dazibao_ctx = EffectContext(
            group_id=ctx.group_id,
            user_id=ctx.user_id,
            nickname=ctx.nickname,
            user_data=ctx.user_data,
            user_length=ctx.user_length,
            user_hardness=ctx.user_hardness
        )
        dazibao_ctx.extra['group_data'] = group_data

        # 触发大自爆
        dazibao_ctx = dazibao_effect.on_trigger(EffectTrigger.ON_PURCHASE, dazibao_ctx)

        # 合并结果
        ctx.messages.extend(dazibao_ctx.messages)
        ctx.extra['dazibao'] = dazibao_ctx.extra.get('dazibao', {})
        ctx.extra['consume_shields'] = dazibao_ctx.extra.get('consume_shields', [])
        ctx.length_change = dazibao_ctx.length_change
        ctx.hardness_change = dazibao_ctx.hardness_change
        ctx.intercept = True

    def _handle_self_clear(self, ctx: EffectContext):
        """10% 清空自己长度和硬度"""
        ctx.extra['duoxinmo_result'] = 'self_clear'
        ctx.length_change = -ctx.user_length  # 归零
        ctx.hardness_change = -(ctx.user_hardness - 1)  # 硬度归1

        ctx.messages.extend([
            "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
            random.choice(self.SELF_CLEAR_TEXTS),
            f"💀 {ctx.nickname} 长度归零！硬度归1！",
            "😱 这罐头有毒！！！",
        ])
        ctx.intercept = True


class CuihuoZhuadaoEffect(ItemEffect):
    """淬火爪刀 - Extra plunder on win when underdog: +10% length and +10% hardness"""
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
        extra_length = int(ctx.target_length * 0.1)
        extra_hardness = max(1, int(ctx.target_hardness * 0.1))
        ctx.length_change += extra_length
        ctx.hardness_change += extra_hardness
        ctx.messages.append(f"🔥 淬火爪刀触发！额外掠夺 {extra_length}cm 和 {extra_hardness}点硬度！")
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


class XiaolanpianEffect(ItemEffect):
    """小蓝片 - Next compare hardness is 100"""
    name = "小蓝片"
    triggers = [EffectTrigger.BEFORE_COMPARE]
    consume_on_use = True

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        ctx.user_hardness = 100
        ctx.messages.append(f"💊 {ctx.nickname} 的小蓝片生效！硬度暴涨至100！")
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


class BalishijiaEffect(ItemEffect):
    """巴黎牛家 - +10 hardness, but -1~10% length"""
    name = "巴黎牛家"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        # +10 硬度
        ctx.hardness_change = 10

        # 随机降低 1-10% 长度
        length_percent = random.uniform(0.01, 0.10)
        length_loss = int(abs(ctx.user_length) * length_percent)
        if length_loss < 1:
            length_loss = 1
        ctx.length_change = -length_loss

        percent_display = f"{length_percent * 100:.1f}%"
        ctx.messages.extend([
            "🏠 ══ 巴黎牛家 ══ 🏠",
            f"💪 {ctx.nickname} 硬度 +10！",
            f"📉 但是...代价是缩短了 {length_loss}cm（{percent_display}）",
            "💊 变硬了，但变短了...",
            "═══════════════════"
        ])

        return ctx


class DutuyingbiEffect(ItemEffect):
    """赌徒硬币 - 50% double, 48% halve, 1% jackpot (x4), 1% bad luck (x-2)"""
    name = "赌徒硬币"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 头等奖文案
    JACKPOT_TEXTS = [
        "🎰✨ 硬币在空中炸裂成金光！！！",
        "🌟 天降祥瑞！硬币化作一道金龙！",
        "💫 硬币立了起来！传说中的...头等奖！！",
        "🎇 叮叮叮！恭喜你中了头等奖！",
        "⭐ 硬币发出耀眼的光芒，你感觉自己被命运眷顾了！"
    ]

    # 霉运文案
    BAD_LUCK_TEXTS = [
        "🎰💀 硬币裂开了...黑雾涌出！",
        "☠️ 硬币变成了骷髅头！这是...霉运诅咒！",
        "🌑 硬币坠入深渊，带走了你的一切...",
        "💔 硬币碎成粉末，厄运降临！",
        "👻 硬币消失了，取而代之的是一阵阴风..."
    ]

    # 翻倍文案
    DOUBLE_TEXTS = [
        "🎰 硬币正面朝上！长度翻倍！",
        "🪙 叮！正面！你的牛牛膨胀了！",
        "✨ 硬币闪闪发光，好运降临！"
    ]

    # 减半文案
    HALVE_TEXTS = [
        "🎰 硬币反面朝上...长度减半！",
        "🪙 哐当...反面...你的牛牛缩水了",
        "💨 硬币滚走了，带走了一半的你..."
    ]

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        current_length = ctx.user_length
        roll = random.random()

        # 概率分布：50% 翻倍, 48% 减半, 1% 头等奖, 1% 霉运
        if roll < 0.01:
            # 1% 头等奖：长度 x4
            self._apply_jackpot(ctx, current_length)
        elif roll < 0.02:
            # 1% 霉运：长度变成 -2倍
            self._apply_bad_luck(ctx, current_length)
        elif roll < 0.52:
            # 50% 翻倍
            self._apply_double(ctx, current_length)
        else:
            # 48% 减半
            self._apply_halve(ctx, current_length)

        return ctx

    def _apply_jackpot(self, ctx: EffectContext, current_length: float):
        """头等奖：长度变成4倍"""
        ctx.messages.append(random.choice(self.JACKPOT_TEXTS))
        ctx.messages.append("🏆 ═══ 头 等 奖 ═══ 🏆")

        if current_length > 0:
            gain = current_length * 3
            ctx.length_change = gain
            ctx.messages.append(f"💰 长度暴涨！{current_length:.1f}cm → {current_length + gain:.1f}cm (+{gain:.1f}cm)")
        elif current_length < 0:
            # 负数变成正的4倍绝对值
            gain = abs(current_length) * 4
            ctx.length_change = gain
            ctx.messages.append(f"💰 逆天改命！{current_length:.1f}cm → {current_length + gain:.1f}cm (+{gain:.1f}cm)")
        else:
            gain = 100
            ctx.length_change = gain
            ctx.messages.append(f"💰 从零开始的暴富！0cm → {gain}cm")

        ctx.messages.append("🎊 运气爆棚！今天一定要买彩票！")

    def _apply_bad_luck(self, ctx: EffectContext, current_length: float):
        """霉运：长度变成-2倍"""
        ctx.messages.append(random.choice(self.BAD_LUCK_TEXTS))
        ctx.messages.append("💀 ═══ 霉 运 降 临 ═══ 💀")

        if current_length > 0:
            # 正数变成负2倍
            loss = current_length * 3
            ctx.length_change = -loss
            ctx.messages.append(f"😱 长度暴跌！{current_length:.1f}cm → {current_length - loss:.1f}cm (-{loss:.1f}cm)")
        elif current_length < 0:
            # 负数变得更负
            loss = abs(current_length) * 3
            ctx.length_change = -loss
            ctx.messages.append(f"😱 凹到地心！{current_length:.1f}cm → {current_length - loss:.1f}cm (-{loss:.1f}cm)")
        else:
            loss = 100
            ctx.length_change = -loss
            ctx.messages.append(f"😱 从零坠入深渊！0cm → -{loss}cm")

        ctx.messages.append("🥀 今天不宜出门...")

    def _apply_double(self, ctx: EffectContext, current_length: float):
        """翻倍"""
        text = random.choice(self.DOUBLE_TEXTS)

        if current_length > 0:
            ctx.length_change = current_length
            ctx.messages.append(f"{text} +{current_length:.1f}cm")
        elif current_length < 0:
            gain = abs(current_length) // 2
            ctx.length_change = gain
            ctx.messages.append(f"🎰 硬币正面朝上！凹陷减半！+{gain:.1f}cm")
        else:
            change = random.randint(5, 15)
            ctx.length_change = change
            ctx.messages.append(f"🎰 硬币悬浮！从虚无中获得了{change}cm！")

    def _apply_halve(self, ctx: EffectContext, current_length: float):
        """减半"""
        text = random.choice(self.HALVE_TEXTS)

        if current_length > 0:
            loss = current_length / 2
            ctx.length_change = -loss
            ctx.messages.append(f"{text} -{loss:.1f}cm")
        elif current_length < 0:
            loss = abs(current_length)
            ctx.length_change = -loss
            ctx.messages.append(f"🎰 硬币反面朝上...凹得更深了！-{loss:.1f}cm")
        else:
            change = random.randint(-15, -5)
            ctx.length_change = change
            ctx.messages.append(f"🎰 硬币落入虚空...凹进去了{-change}cm！")


# =============================================================================
# 劫富济贫 Effect
# =============================================================================

class JiefuJipinEffect(ItemEffect):
    """劫富济贫 - Robin Hood: steal 50% length and 20% hardness from richest, give to random 3"""
    name = "劫富济贫"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        import random
        from niuniu_config import JiefuJipinConfig

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
        richest_hardness = richest_data.get('hardness', 1)
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

        # 计算抢夺数量（50%长度，20%硬度）
        steal_length = int(richest_length * JiefuJipinConfig.STEAL_LENGTH_PERCENT)
        steal_hardness = int(richest_hardness * JiefuJipinConfig.STEAL_HARDNESS_PERCENT)
        if steal_length < 1:
            steal_length = 1
        if steal_hardness < 1:
            steal_hardness = 1

        # 检查首富是否有护盾
        richest_shielded = False
        richest_shield_charges = richest_data.get('shield_charges', 0)
        if richest_shield_charges > 0:
            richest_shielded = True
            # 记录需要消耗护盾
            ctx.extra['consume_shield'] = {
                'user_id': richest_id,
                'amount': 1
            }

        # 随机选3人（排除首富，可以包括发起人）
        candidates = [(uid, data) for uid, data in valid_users if uid != richest_id]

        if len(candidates) < 3:
            # 如果候选人不足3人，全部选中
            lucky_3 = candidates
        else:
            lucky_3 = random.sample(candidates, 3)

        if len(lucky_3) == 0:
            ctx.messages.append("❌ 找不到可以接济的人！")
            ctx.intercept = True
            ctx.extra['refund'] = True
            return ctx

        # 平分长度和硬度
        length_share_each = steal_length // len(lucky_3)
        length_remainder = steal_length % len(lucky_3)
        hardness_share_each = steal_hardness // len(lucky_3)
        hardness_remainder = steal_hardness % len(lucky_3)

        # 记录需要更新的数据
        # 如果首富有护盾，不扣他的长度/硬度，但其他人照样拿
        ctx.extra['robin_hood'] = {
            'richest_id': richest_id,
            'richest_name': richest_name,
            'steal_amount': 0 if richest_shielded else steal_length,  # 有护盾则不扣长度
            'steal_hardness': 0 if richest_shielded else steal_hardness,  # 有护盾则不扣硬度
            'beneficiaries': []
        }

        for i, (uid, data) in enumerate(lucky_3):
            # 第一个人获得余数
            length_amount = length_share_each + (length_remainder if i == 0 else 0)
            hardness_amount = hardness_share_each + (hardness_remainder if i == 0 else 0)
            if length_amount > 0 or hardness_amount > 0:
                ctx.extra['robin_hood']['beneficiaries'].append({
                    'user_id': uid,
                    'nickname': data.get('nickname', uid),
                    'amount': length_amount,
                    'hardness': hardness_amount
                })

        # 构建消息
        beneficiary_texts = []
        for b in ctx.extra['robin_hood']['beneficiaries']:
            beneficiary_texts.append(f"  💰 {b['nickname']} +{b['amount']}cm +{b['hardness']}硬度")

        if richest_shielded:
            # 首富有护盾的消息
            ctx.messages.extend([
                "🦸 ═══ 劫富济贫 ═══ 🦸",
                f"🎯 目标锁定：{richest_name}（{richest_length}cm/{richest_hardness}硬度）",
                f"🛡️ 但是...{richest_name} 有牛牛盾牌护盾！",
                f"💫 护盾抵挡了抢劫，但天降横财！",
                f"🎁 凭空产生 {steal_length}cm/{steal_hardness}硬度 分给幸运儿：",
                *beneficiary_texts,
                f"📊 {richest_name} 护盾剩余：{richest_shield_charges - 1}次",
                "══════════════════"
            ])
        else:
            # 正常抢劫消息
            ctx.messages.extend([
                "🦸 ═══ 劫富济贫 ═══ 🦸",
                f"🎯 目标锁定：{richest_name}（{richest_length}cm/{richest_hardness}硬度）",
                f"💸 抢走了 {steal_length}cm 和 {steal_hardness}硬度！",
                "📦 分发给随机幸运群友：",
                *beneficiary_texts,
                "══════════════════"
            ])

        return ctx


# =============================================================================
# 混沌风暴 Effect
# =============================================================================

class HundunFengbaoEffect(ItemEffect):
    """混沌风暴 - Chaos Storm: random chaotic events for up to 10 people"""
    name = "混沌风暴"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def _pick_event(self, events):
        """根据权重随机选择事件"""
        total = sum(e[0] for e in events)
        r = random.randint(1, total)
        cumulative = 0
        for weight, event_id, template, params in events:
            cumulative += weight
            if r <= cumulative:
                return event_id, template, params
        return events[-1][1], events[-1][2], events[-1][3]

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import HundunFengbaoConfig

        # 需要从 extra 获取群组数据
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 无法获取群组数据")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 过滤有效用户（有长度数据的）
        valid_users = [(uid, data) for uid, data in group_data.items()
                       if isinstance(data, dict) and 'length' in data]

        if len(valid_users) < HundunFengbaoConfig.MIN_PLAYERS:
            ctx.messages.append(f"❌ 群里牛牛不足{HundunFengbaoConfig.MIN_PLAYERS}人，风暴刮不起来！")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 随机选择最多10人
        selected = random.sample(valid_users, min(len(valid_users), HundunFengbaoConfig.MAX_TARGETS))

        # 记录变化
        ctx.extra['chaos_storm'] = {
            'changes': [],
            'coin_changes': [],
            'swaps': [],
            'all_selected_ids': [uid for uid, _ in selected]  # 跟踪所有被选中的人
        }
        ctx.extra['consume_shields'] = []
        changes = ctx.extra['chaos_storm']['changes']
        coin_changes = ctx.extra['chaos_storm']['coin_changes']
        event_lines = []

        for uid, data in selected:
            old_length = data.get('length', 0)
            old_hardness = data.get('hardness', 1)
            nickname = data.get('nickname', uid)
            shield_charges = data.get('shield_charges', 0)

            # 抽取事件
            event_id, template, params = self._pick_event(HundunFengbaoConfig.CHAOS_EVENTS)

            # 处理各种事件
            length_change = 0
            hardness_change = 0
            coin_change = 0
            event_text = ""

            # 静态负面事件列表（护盾可抵挡）
            # 注意：chaos_tax 不在列表中，因为这是混沌风暴的核心收益机制
            static_negative_events = [
                'length_down', 'hardness_down', 'coin_lose',
                'length_percent_down', 'halve', 'give_to_random',
                'dark_sacrifice'
            ]

            # 动态判断是否负面
            is_negative = event_id in static_negative_events
            # reverse_sign: 正数变负数是负面
            if event_id == 'reverse_sign' and old_length > 0:
                is_negative = True

            # 负面事件检查护盾
            if is_negative and shield_charges > 0:
                event_text = f"🛡️ {nickname}: 护盾抵挡了【{template.split('！')[0] if '！' in template else event_id}】！（剩余{shield_charges - 1}次）"
                ctx.extra['consume_shields'].append({'user_id': uid, 'amount': 1})
                event_lines.append(event_text)
                continue

            if event_id == 'length_up':
                value = random.randint(params['min'], params['max'])
                length_change = value
                event_text = f"📈 {nickname}: {template.format(value=value)}"

            elif event_id == 'length_down':
                value = random.randint(params['min'], params['max'])
                length_change = -value
                event_text = f"📉 {nickname}: {template.format(value=value)}"

            elif event_id == 'hardness_up':
                value = random.randint(params['min'], params['max'])
                hardness_change = value
                event_text = f"💪 {nickname}: {template.format(value=value)}"

            elif event_id == 'hardness_down':
                value = random.randint(params['min'], params['max'])
                hardness_change = -value
                event_text = f"😵 {nickname}: {template.format(value=value)}"

            elif event_id == 'coin_gain':
                value = random.randint(params['min'], params['max'])
                coin_change = value
                event_text = f"💰 {nickname}: {template.format(value=value)}"

            elif event_id == 'coin_lose':
                value = random.randint(params['min'], params['max'])
                coin_change = -value
                event_text = f"💸 {nickname}: {template.format(value=value)}"

            elif event_id == 'length_percent_up':
                value = random.randint(params['min'], params['max'])
                length_change = int(abs(old_length) * value / 100)
                event_text = f"🚀 {nickname}: {template.format(value=value)} (+{length_change}cm)"

            elif event_id == 'length_percent_down':
                value = random.randint(params['min'], params['max'])
                length_change = -int(abs(old_length) * value / 100)
                event_text = f"📉 {nickname}: {template.format(value=value)} ({length_change}cm)"

            elif event_id == 'swap_random':
                # 随机找一个其他人交换
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    target_len = target_data.get('length', 0)
                    # 记录交换
                    ctx.extra['chaos_storm']['swaps'].append({
                        'user1_id': uid, 'user1_old': old_length,
                        'user2_id': target_uid, 'user2_old': target_len
                    })
                    event_text = f"🔄 {nickname}: {template.format(target=target_name)} ({old_length}↔{target_len})"
                else:
                    event_text = f"🤷 {nickname}: 没人可以交换..."

            elif event_id == 'double_or_nothing':
                if old_length > 0:
                    value = min(old_length, 50)  # 最多翻倍50cm
                    length_change = value
                else:
                    value = max(old_length, -50)  # 负数也翻倍但限制
                    length_change = value
                event_text = f"✨ {nickname}: {template.format(value=abs(length_change))}"

            elif event_id == 'halve':
                value = abs(old_length) // 2
                length_change = -value if old_length > 0 else value
                event_text = f"💔 {nickname}: {template.format(value=value)}"

            elif event_id == 'hardness_reset':
                value = random.randint(params['min'], params['max'])
                hardness_change = value - old_hardness
                event_text = f"🎲 {nickname}: {template.format(value=value)}"

            elif event_id == 'steal_from_random':
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    value = random.randint(params['min'], params['max'])
                    length_change = value
                    # 记录被偷的人
                    changes.append({
                        'user_id': target_uid,
                        'nickname': target_name,
                        'change': -value,
                        'hardness_change': 0
                    })
                    event_text = f"🦹 {nickname}: {template.format(target=target_name, value=value)}"
                else:
                    event_text = f"🤷 {nickname}: 没人可以偷..."

            elif event_id == 'give_to_random':
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    value = random.randint(params['min'], params['max'])
                    length_change = -value
                    # 记录收到的人
                    changes.append({
                        'user_id': target_uid,
                        'nickname': target_name,
                        'change': value,
                        'hardness_change': 0
                    })
                    event_text = f"🎁 {nickname}: {template.format(target=target_name, value=value)}"
                else:
                    event_text = f"🤷 {nickname}: 没人可以送..."

            elif event_id == 'nothing':
                event_text = f"😶 {nickname}: {template}"

            elif event_id == 'reverse_sign':
                new_len = -old_length
                length_change = new_len - old_length
                event_text = f"🔀 {nickname}: {template.format(old=old_length, new=new_len)}"

            elif event_id == 'full_swap':
                # 全属性互换（长度+硬度）
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    target_len = target_data.get('length', 0)
                    target_hard = target_data.get('hardness', 1)
                    # 记录全属性交换
                    ctx.extra['chaos_storm'].setdefault('full_swaps', []).append({
                        'user1_id': uid, 'user1_old_len': old_length, 'user1_old_hard': old_hardness,
                        'user2_id': target_uid, 'user2_old_len': target_len, 'user2_old_hard': target_hard
                    })
                    event_text = f"🔄 {nickname}: 与{target_name}交换全部属性！（{old_length}cm/{old_hardness}硬 ↔ {target_len}cm/{target_hard}硬）"
                else:
                    event_text = f"🤷 {nickname}: 没人可以交换..."

            elif event_id == 'cooldown_reset':
                # 打胶冷却清零
                ctx.extra['chaos_storm'].setdefault('cooldown_resets', []).append(uid)
                event_text = f"⏰ {nickname}: 打胶冷却清零！"

            elif event_id == 'chaos_chain':
                # 混沌连锁：触发2个简单数值事件
                # 只筛选简单数值事件，避免复杂事件导致 ???
                simple_events = [
                    'length_up', 'length_down', 'hardness_up', 'hardness_down',
                    'coin_gain', 'coin_lose', 'length_percent_up', 'length_percent_down'
                ]
                chain_events = [e for e in HundunFengbaoConfig.CHAOS_EVENTS if e[1] in simple_events]
                chain_results = []
                for _ in range(2):
                    chain_event_id, chain_template, chain_params = self._pick_event(chain_events)
                    if chain_event_id == 'length_up':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        length_change += val
                        chain_results.append(f"+{val}cm")
                    elif chain_event_id == 'length_down':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        length_change -= val
                        chain_results.append(f"-{val}cm")
                    elif chain_event_id == 'hardness_up':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        hardness_change += val
                        chain_results.append(f"+{val}硬度")
                    elif chain_event_id == 'hardness_down':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        hardness_change -= val
                        chain_results.append(f"-{val}硬度")
                    elif chain_event_id == 'coin_gain':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        coin_change += val
                        chain_results.append(f"+{val}金币")
                    elif chain_event_id == 'coin_lose':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        coin_change -= val
                        chain_results.append(f"-{val}金币")
                    elif chain_event_id == 'length_percent_up':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        change = int(abs(old_length) * val / 100)
                        length_change += change
                        chain_results.append(f"+{val}%长度(+{change}cm)")
                    elif chain_event_id == 'length_percent_down':
                        val = random.randint(chain_params['min'], chain_params['max'])
                        change = int(abs(old_length) * val / 100)
                        length_change -= change
                        chain_results.append(f"-{val}%长度(-{change}cm)")
                event_text = f"⚡ {nickname}: 混沌连锁！{' & '.join(chain_results)}"

            elif event_id == 'hardness_to_length':
                # 硬度转长度：消耗一半硬度（保底剩1），获得长度
                max_convert = max(0, old_hardness - 1)  # 至少保留1点硬度
                convert_hardness = max(1, max_convert // 2) if max_convert > 0 else 0
                if convert_hardness > 0:
                    convert_length = convert_hardness * 3  # 1硬度=3cm
                    hardness_change = -convert_hardness
                    length_change = convert_length
                    event_text = f"🔄 {nickname}: 硬度转长度！-{convert_hardness}硬度 → +{convert_length}cm"
                else:
                    event_text = f"😅 {nickname}: 硬度太低，无法转化..."

            elif event_id == 'length_to_hardness':
                # 长度转硬度：消耗20%长度，获得硬度（不超过100上限）
                from niuniu_config import DajiaoConfig
                if old_length > 0:
                    convert_length = max(1, int(old_length * 0.2))
                    raw_hardness = max(1, convert_length // 5)  # 5cm=1硬度
                    # 检查硬度上限
                    max_gain = DajiaoConfig.MAX_HARDNESS - old_hardness
                    convert_hardness = min(raw_hardness, max_gain)
                    if convert_hardness > 0:
                        length_change = -convert_length
                        hardness_change = convert_hardness
                        event_text = f"🔄 {nickname}: 长度转硬度！-{convert_length}cm → +{convert_hardness}硬度"
                    else:
                        event_text = f"💯 {nickname}: 硬度已满100，无法转化！"
                else:
                    event_text = f"😅 {nickname}: 长度太少，无法转化..."

            elif event_id == 'chaos_tax':
                # 混沌税：被收5%长度给使用者
                if old_length > 0:
                    tax = max(1, int(old_length * 0.05))
                    length_change = -tax
                    ctx.extra['chaos_storm'].setdefault('tax_collected', 0)
                    ctx.extra['chaos_storm']['tax_collected'] += tax
                    event_text = f"💰 {nickname}: 被混沌收税！-{tax}cm"
                else:
                    event_text = f"😅 {nickname}: 负数牛牛免税..."

            elif event_id == 'clone_length':
                # 克隆别人的长度
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    target_len = target_data.get('length', 0)
                    length_change = target_len - old_length
                    event_text = f"🧬 {nickname}: 克隆了{target_name}的长度！{old_length}cm → {target_len}cm"
                else:
                    event_text = f"🤷 {nickname}: 没人可以克隆..."

            elif event_id == 'lucky_buff':
                # 幸运祝福：下次打胶必定成功
                ctx.extra['chaos_storm'].setdefault('lucky_buffs', []).append(uid)
                event_text = f"🍀 {nickname}: 获得幸运祝福！下次打胶必增长！"

            elif event_id == 'length_quake':
                # 长度震荡：大幅随机波动
                change_val = random.randint(params['min'], params['max'])
                length_change = change_val
                if change_val >= 0:
                    event_text = f"🌋 {nickname}: 长度震荡！+{change_val}cm"
                else:
                    event_text = f"🌋 {nickname}: 长度震荡！{change_val}cm"

            elif event_id == 'quantum_entangle':
                # 量子纠缠：与随机一人双方取平均
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    target_len = target_data.get('length', 0)
                    avg_len = (old_length + target_len) // 2
                    # 记录量子纠缠
                    ctx.extra['chaos_storm'].setdefault('quantum_entangles', []).append({
                        'user1_id': uid, 'user1_old': old_length,
                        'user2_id': target_uid, 'user2_old': target_len,
                        'avg': avg_len
                    })
                    event_text = f"🔮 {nickname}: 与{target_name}量子纠缠！({old_length}+{target_len})/2 = {avg_len}cm"
                else:
                    event_text = f"🤷 {nickname}: 没人可以纠缠..."

            elif event_id == 'dark_sacrifice':
                # 黑暗献祭：牺牲20%长度，×3给随机人
                others = [u for u in valid_users if u[0] != uid]
                if others and old_length > 0:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    sacrifice = max(1, int(old_length * 0.2))
                    gift = sacrifice * 3
                    length_change = -sacrifice
                    # 记录受益者
                    changes.append({
                        'user_id': target_uid,
                        'nickname': target_name,
                        'change': gift,
                        'hardness_change': 0
                    })
                    event_text = f"🖤 {nickname}: 黑暗献祭！-{sacrifice}cm → {target_name} +{gift}cm"
                else:
                    event_text = f"😅 {nickname}: 没有足够的长度献祭..."

            elif event_id == 'resurrection':
                # 牛牛复活：负数变正数
                if old_length <= 0:
                    new_len = random.randint(params['min'], params['max'])
                    length_change = new_len - old_length
                    event_text = f"✨ {nickname}: 牛牛复活！{old_length}cm → {new_len}cm"
                else:
                    event_text = f"😊 {nickname}: 牛牛还活着，不需要复活~"

            elif event_id == 'doomsday':
                # 末日审判：全局事件，在后处理中执行
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'doomsday',
                    'trigger_by': nickname
                })
                event_text = f"⚖️ {nickname}: 触发了【末日审判】！"

            elif event_id == 'roulette':
                # 轮盘重置：全局事件
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'roulette',
                    'trigger_by': nickname
                })
                event_text = f"🎰 {nickname}: 触发了【轮盘重置】！"

            elif event_id == 'reverse_talent':
                # 反向天赋：全局事件
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'reverse_talent',
                    'trigger_by': nickname
                })
                event_text = f"🔄 {nickname}: 触发了【反向天赋】！"

            elif event_id == 'lottery_bomb':
                # 团灭彩票：全局事件
                is_jackpot = random.random() < 0.05  # 5%
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'lottery_bomb',
                    'trigger_by': nickname,
                    'jackpot': is_jackpot
                })
                if is_jackpot:
                    event_text = f"🎊 {nickname}: 【团灭彩票】中了！！全体翻倍！"
                else:
                    event_text = f"💣 {nickname}: 【团灭彩票】没中...全体-50%长度和硬度！"

            elif event_id == 'parasite':
                # 寄生虫：在别人身上种下标记
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    ctx.extra['chaos_storm'].setdefault('parasites', []).append({
                        'host_id': target_uid,
                        'host_name': target_name,
                        'beneficiary_id': uid,
                        'beneficiary_name': nickname
                    })
                    event_text = f"🦠 {nickname}: 在{target_name}身上种下寄生虫！"
                else:
                    event_text = f"🤷 {nickname}: 没人可以寄生..."

            # 记录变化
            if length_change != 0 or hardness_change != 0:
                changes.append({
                    'user_id': uid,
                    'nickname': nickname,
                    'change': length_change,
                    'hardness_change': hardness_change
                })

            if coin_change != 0:
                coin_changes.append({
                    'user_id': uid,
                    'amount': coin_change
                })

            event_lines.append(event_text)

        # 构建消息
        ctx.messages.append("🌪️ ══ 混沌风暴 ══ 🌪️")
        ctx.messages.append(f"💨 {ctx.nickname} 召唤了混沌风暴！")
        ctx.messages.append(f"🎲 随机选中 {len(selected)} 人！")
        ctx.messages.append("")

        # 显示每个人的事件
        for line in event_lines:
            ctx.messages.append(line)

        ctx.messages.append("")
        ctx.messages.append("═══════════════════")

        return ctx


# =============================================================================
# 牛牛黑洞 Effect
# =============================================================================

class HeidongEffect(ItemEffect):
    """牛牛黑洞 - Black Hole: absorb 3-10% length from 5-15 random people"""
    name = "牛牛黑洞"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 成功吸取文案
    SUCCESS_TEXTS = [
        "🕳️ 虚空之力，为我所用！",
        "🌌 黑洞：谢谢款待~",
        "⚫ 无尽深渊已经张开了嘴...",
        "🔮 时空扭曲！精华归我！",
        "💀 黑洞：你们的牛牛，我收下了"
    ]

    # 不稳定喷射文案
    UNSTABLE_TEXTS = [
        "⚠️ 黑洞过载！部分能量逃逸！",
        "💥 黑洞不稳定，发生了霍金辐射！",
        "🌪️ 时空裂缝！一半被吸到平行宇宙去了！",
        "🎰 黑洞打了个喷嚏，喷了一地...",
        "⚡ 能量溢出！无法完全吸收！"
    ]

    # 反噬文案
    BACKFIRE_TEXTS = [
        "💀 黑洞：等等，我好像搞反了方向...",
        "😱 反噬！召唤师被自己的黑洞吸进去了！",
        "🌀 黑洞：你以为你在召唤我？其实是我在召唤你！",
        "☠️ 玩火自焚，玩洞...自吸？",
        "💫 黑洞坍缩成白矮星，砸在了你头上"
    ]

    # 吃撑反喷文案
    REVERSE_TEXTS = [
        "🤡 黑洞吃撑了！呕————",
        "🌀 黑洞打了个饱嗝，把所有东西都喷出来了！",
        "😂 黑洞消化不良，反向喷射！",
        "🎪 这不是黑洞，这是喷泉！",
        "💫 黑洞：吃太多了，受不了，还给你们！",
        "🤮 黑洞食物中毒了！全吐出来了！",
        "🎭 黑洞：开玩笑的，其实我是白洞~"
    ]

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import HeidongConfig

        # 需要从 extra 获取群组数据
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 无法获取群组数据")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 过滤有效用户（有长度数据的）
        valid_users = [(uid, data) for uid, data in group_data.items()
                       if isinstance(data, dict) and 'length' in data]

        if len(valid_users) < HeidongConfig.MIN_PLAYERS:
            ctx.messages.append(f"❌ 群里牛牛不足{HeidongConfig.MIN_PLAYERS}人，黑洞无法形成！")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 随机选择5-15人（不排除自己，增加趣味性）
        num_targets = random.randint(
            min(HeidongConfig.MIN_TARGETS, len(valid_users)),
            min(HeidongConfig.MAX_TARGETS, len(valid_users))
        )
        selected = random.sample(valid_users, num_targets)

        # 计算每个人被吸取的长度
        total_stolen = 0
        victims = []
        ctx.extra['consume_shields'] = []

        for uid, data in selected:
            nickname = data.get('nickname', uid)
            length = data.get('length', 0)
            shield_charges = data.get('shield_charges', 0)

            # 随机吸取3-10%
            steal_percent = random.uniform(
                HeidongConfig.STEAL_PERCENT_MIN,
                HeidongConfig.STEAL_PERCENT_MAX
            )
            steal_amount = int(abs(length) * steal_percent)
            if steal_amount < 1:
                steal_amount = 1

            # 检查护盾
            if shield_charges > 0:
                victims.append({
                    'user_id': uid,
                    'nickname': nickname,
                    'amount': 0,
                    'shielded': True,
                    'shield_remaining': shield_charges - 1
                })
                ctx.extra['consume_shields'].append({'user_id': uid, 'amount': 1})
            else:
                victims.append({
                    'user_id': uid,
                    'nickname': nickname,
                    'amount': steal_amount,
                    'shielded': False
                })
                total_stolen += steal_amount

        # 决定结果
        roll = random.random()
        ctx.extra['black_hole'] = {
            'victims': victims,
            'total_stolen': total_stolen,
            'result': None,
            'spray_targets': []
        }

        if roll < HeidongConfig.RESULT_ALL_TO_USER:
            # 40%: 全部归使用者
            ctx.extra['black_hole']['result'] = 'all_to_user'
            ctx.length_change = total_stolen
            ctx.messages.extend([
                "🌀 ══ 牛牛黑洞 ══ 🌀",
                f"🕳️ {ctx.nickname} 召唤了黑洞！",
                "",
                random.choice(self.SUCCESS_TEXTS),
                f"💫 吸取了 {len(victims)} 人的精华！",
                ""
            ])
            for v in victims:
                if v['shielded']:
                    ctx.messages.append(f"  🛡️ {v['nickname']} 护盾抵挡！（剩余{v['shield_remaining']}层）")
                else:
                    ctx.messages.append(f"  💨 {v['nickname']} -{v['amount']}cm")
            ctx.messages.extend([
                "",
                f"✨ 完美吸收！{ctx.nickname} +{total_stolen}cm",
                "═══════════════════"
            ])

        elif roll < HeidongConfig.RESULT_ALL_TO_USER + HeidongConfig.RESULT_HALF_SPRAY:
            # 30%: 一半喷给路人
            ctx.extra['black_hole']['result'] = 'half_spray'
            user_gain = total_stolen // 2
            spray_amount = total_stolen - user_gain
            ctx.length_change = user_gain

            # 随机选几个路人获得喷射
            non_victims = [(uid, data) for uid, data in valid_users
                          if uid not in [v['user_id'] for v in victims] and uid != ctx.user_id]
            if non_victims:
                spray_count = min(3, len(non_victims))
                spray_targets = random.sample(non_victims, spray_count)
                spray_each = spray_amount // spray_count
                for uid, data in spray_targets:
                    ctx.extra['black_hole']['spray_targets'].append({
                        'user_id': uid,
                        'nickname': data.get('nickname', uid),
                        'amount': spray_each
                    })

            ctx.messages.extend([
                "🌀 ══ 牛牛黑洞 ══ 🌀",
                f"🕳️ {ctx.nickname} 召唤了黑洞！",
                f"💫 吸取了 {len(victims)} 人的精华！",
                "",
                random.choice(self.UNSTABLE_TEXTS),
                ""
            ])
            for v in victims:
                if v['shielded']:
                    ctx.messages.append(f"  🛡️ {v['nickname']} 护盾抵挡！（剩余{v['shield_remaining']}层）")
                else:
                    ctx.messages.append(f"  💨 {v['nickname']} -{v['amount']}cm")
            ctx.messages.append("")
            ctx.messages.append(f"📥 {ctx.nickname} 勉强吸到 +{user_gain}cm")
            if ctx.extra['black_hole']['spray_targets']:
                ctx.messages.append("📤 剩下的喷射给了路人：")
                for t in ctx.extra['black_hole']['spray_targets']:
                    ctx.messages.append(f"  🎁 {t['nickname']} 捡漏 +{t['amount']}cm")
            ctx.messages.append("═══════════════════")

        elif roll < HeidongConfig.RESULT_ALL_TO_USER + HeidongConfig.RESULT_HALF_SPRAY + HeidongConfig.RESULT_BACKFIRE:
            # 20%: 反噬自己
            ctx.extra['black_hole']['result'] = 'backfire'
            backfire_loss = int(abs(ctx.user_length) * HeidongConfig.BACKFIRE_PERCENT)
            ctx.length_change = -backfire_loss

            ctx.messages.extend([
                "🌀 ══ 牛牛黑洞 ══ 🌀",
                f"🕳️ {ctx.nickname} 召唤了黑洞！",
                "",
                random.choice(self.BACKFIRE_TEXTS),
                "",
                f"😱 {ctx.nickname} 被自己的黑洞吞噬！",
                f"📉 损失 {backfire_loss}cm！",
                "",
                "（其他人的牛牛安然无恙，全部消散在虚空中...）",
                "═══════════════════"
            ])
            # 不扣受害者的长度
            for v in victims:
                v['amount'] = 0

        else:
            # 10%: 吃撑反喷
            ctx.extra['black_hole']['result'] = 'reverse'
            # 使用者损失，受害者反而获得
            ctx.length_change = -total_stolen

            ctx.messages.extend([
                "🌀 ══ 牛牛黑洞 ══ 🌀",
                f"🕳️ {ctx.nickname} 召唤了黑洞！",
                "",
                random.choice(self.REVERSE_TEXTS),
                "",
                "🎉 黑洞变成了喷泉！所有人反而变长了！",
                ""
            ])
            for v in victims:
                if not v['shielded'] and v['amount'] > 0:
                    # 反转：受害者获得长度而不是失去
                    v['reverse_gain'] = v['amount']
                    ctx.messages.append(f"  🎁 {v['nickname']} 白捡 +{v['amount']}cm")
                    v['amount'] = 0  # 不扣他们的
            ctx.messages.extend([
                "",
                f"💸 而 {ctx.nickname} 作为代价... -{total_stolen}cm",
                "",
                "🤡 群友们：谢谢老板！",
                "═══════════════════"
            ])

        return ctx


# =============================================================================
# 月牙天冲 Effect
# =============================================================================

class YueyaTianchongEffect(ItemEffect):
    """月牙天冲 - Moon Slash: random target, both lose same percentage of length"""
    name = "月牙天冲"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import YueyaTianchongConfig

        # 需要从 extra 获取群组数据
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 无法获取群组数据")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 过滤有效用户（有长度数据的，排除自己）
        valid_targets = [(uid, data) for uid, data in group_data.items()
                         if isinstance(data, dict) and 'length' in data and uid != ctx.user_id]

        if len(valid_targets) < 1:
            ctx.messages.append("❌ 群里没有其他牛牛可以开炮！")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 随机选择目标
        target_id, target_data = random.choice(valid_targets)
        target_name = target_data.get('nickname', target_id)
        target_length = target_data.get('length', 0)
        user_length = ctx.user_length

        # 随机伤害百分比
        damage_percent = random.uniform(
            YueyaTianchongConfig.DAMAGE_PERCENT_MIN,
            YueyaTianchongConfig.DAMAGE_PERCENT_MAX
        )

        # 计算伤害（基于发起人的长度）
        damage = int(abs(user_length) * damage_percent)
        if damage < 1:
            damage = 1

        # 检查目标是否有护盾
        target_shielded = False
        target_shield_charges = target_data.get('shield_charges', 0)
        if target_shield_charges > 0:
            target_shielded = True
            ctx.extra['consume_shield'] = {
                'user_id': target_id,
                'amount': 1
            }

        # 记录变化（如果目标有护盾则不扣目标）
        ctx.extra['yueya_tianchong'] = {
            'target_id': target_id,
            'target_name': target_name,
            'damage': 0 if target_shielded else damage,
            'target_old_length': target_length,
            'user_old_length': user_length
        }

        # 自己也扣长度（无论目标是否有护盾）
        ctx.length_change = -damage

        # 构建消息
        percent_display = f"{damage_percent*100:.0f}%"
        if target_shielded:
            ctx.messages.extend([
                "🌙 ══ 月牙天冲 ══ 🌙",
                f"⚔️ {ctx.nickname} 对 {target_name} 发动了月牙天冲！",
                f"💥 伤害：{damage}cm（{percent_display}）",
                "",
                f"🛡️ {target_name} 的护盾抵挡了攻击！（剩余{target_shield_charges - 1}次）",
                f"📉 {ctx.nickname}: {user_length}→{user_length - damage}cm",
                "",
                "💀 自损八百！",
                "═══════════════════"
            ])
        else:
            ctx.messages.extend([
                "🌙 ══ 月牙天冲 ══ 🌙",
                f"⚔️ {ctx.nickname} 对 {target_name} 发动了月牙天冲！",
                f"💥 伤害：{damage}cm（{percent_display}）",
                "",
                f"📉 {target_name}: {target_length}→{target_length - damage}cm",
                f"📉 {ctx.nickname}: {user_length}→{user_length - damage}cm",
                "",
                "💀 同归于尽！",
                "═══════════════════"
            ])

        return ctx


# =============================================================================
# 牛牛大自爆 Effect
# =============================================================================

class DazibaoEffect(ItemEffect):
    """牛牛大自爆 - Self Destruct: go to zero, distribute damage to top 5"""
    name = "牛牛大自爆"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import DazibaoConfig

        # 需要从 extra 获取群组数据
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 无法获取群组数据")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 检查自己的长度和硬度
        user_length = ctx.user_length
        user_hardness = ctx.user_hardness

        if user_length <= 0 and user_hardness <= 1:
            ctx.messages.append("❌ 你已经是废牛了，没有可以自爆的资本！")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 过滤有效用户（有长度数据的，排除自己），按长度排序
        valid_users = [(uid, data) for uid, data in group_data.items()
                       if isinstance(data, dict) and 'length' in data and uid != ctx.user_id]

        if len(valid_users) < 1:
            ctx.messages.append("❌ 群里没有其他牛牛可以炸！")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 按长度排序取top N
        sorted_users = sorted(valid_users, key=lambda x: x[1].get('length', 0), reverse=True)
        top_n = sorted_users[:DazibaoConfig.TOP_N]

        # 计算自爆伤害
        length_damage = max(0, user_length)  # 只有正数长度才算伤害
        hardness_damage = max(0, user_hardness)  # 硬度也归0

        # 随机权重分配
        victims = []
        ctx.extra['consume_shields'] = []

        if length_damage > 0 or hardness_damage > 0:
            # 生成随机权重
            weights = [random.random() for _ in top_n]
            total_weight = sum(weights)
            weights = [w / total_weight for w in weights]

            remaining_length = length_damage
            remaining_hardness = hardness_damage

            for i, (uid, data) in enumerate(top_n):
                nickname = data.get('nickname', uid)
                old_length = data.get('length', 0)
                old_hardness = data.get('hardness', 1)
                shield_charges = data.get('shield_charges', 0)

                # 计算这个人分到的伤害
                if i == len(top_n) - 1:
                    # 最后一个人拿剩余的
                    len_dmg = remaining_length
                    hard_dmg = remaining_hardness
                else:
                    len_dmg = int(length_damage * weights[i])
                    hard_dmg = int(hardness_damage * weights[i])
                    remaining_length -= len_dmg
                    remaining_hardness -= hard_dmg

                # 检查护盾
                if shield_charges > 0:
                    victims.append({
                        'user_id': uid,
                        'nickname': nickname,
                        'length_damage': 0,
                        'hardness_damage': 0,
                        'old_length': old_length,
                        'old_hardness': old_hardness,
                        'shielded': True,
                        'shield_remaining': shield_charges - 1
                    })
                    ctx.extra['consume_shields'].append({
                        'user_id': uid,
                        'amount': 1
                    })
                else:
                    victims.append({
                        'user_id': uid,
                        'nickname': nickname,
                        'length_damage': len_dmg,
                        'hardness_damage': hard_dmg,
                        'old_length': old_length,
                        'old_hardness': old_hardness,
                        'shielded': False
                    })

        # 记录变化
        ctx.extra['dazibao'] = {
            'victims': victims,
            'user_old_length': user_length,
            'user_old_hardness': user_hardness
        }

        # 自己归零
        ctx.length_change = -user_length
        ctx.hardness_change = -user_hardness  # 硬度也归0

        # 构建消息
        ctx.messages.extend([
            "💥 ══ 牛牛大自爆 ══ 💥",
            f"🔥 {ctx.nickname} 启动了自爆程序！",
            f"💀 牺牲：长度 {user_length}cm，硬度 {user_hardness - 1}",
            ""
        ])

        if victims:
            ctx.messages.append("🎯 波及top5：")
            for v in victims:
                if v['shielded']:
                    ctx.messages.append(f"  🛡️ {v['nickname']} 护盾抵挡！（剩余{v['shield_remaining']}次）")
                else:
                    new_len = v['old_length'] - v['length_damage']
                    new_hard = max(1, v['old_hardness'] - v['hardness_damage'])
                    ctx.messages.append(f"  💥 {v['nickname']}: 长度-{v['length_damage']}cm 硬度-{v['hardness_damage']}")

        ctx.messages.extend([
            "",
            f"📊 {ctx.nickname}: 长度→0cm 硬度→0",
            "🔥 玉石俱焚！",
            "═══════════════════"
        ])

        return ctx


# =============================================================================
# 祸水东引 Effect
# =============================================================================

class HuoshuiDongyinEffect(ItemEffect):
    """祸水东引 - Risk Transfer: transfer large damage to random group member"""
    name = "祸水东引"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import HuoshuiDongyinConfig

        # 增加转嫁次数
        current_charges = ctx.user_data.get('risk_transfer_charges', 0)
        new_charges = current_charges + 1

        ctx.extra['add_risk_transfer_charges'] = 1

        ctx.messages.extend([
            "🔄 ══ 祸水东引 ══ 🔄",
            f"✨ {ctx.nickname} 获得了转嫁能力！",
            f"🎯 下次受到>={HuoshuiDongyinConfig.DAMAGE_THRESHOLD}cm长度伤害时，转嫁给随机群友",
            "⚠️ 无法转移夺牛魔的伤害",
            f"📊 当前转嫁次数：{new_charges}",
            "═══════════════════"
        ])

        return ctx


# =============================================================================
# 上保险 Effect
# =============================================================================

class ShangbaoxianEffect(ItemEffect):
    """上保险 - Insurance: get payout when suffering large damage"""
    name = "上保险"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import ShangbaoxianConfig

        # 增加保险次数
        current_charges = ctx.user_data.get('insurance_charges', 0)
        new_charges = current_charges + ShangbaoxianConfig.CHARGES

        ctx.extra['add_insurance_charges'] = ShangbaoxianConfig.CHARGES

        ctx.messages.extend([
            "📋 ══ 上保险 ══ 📋",
            f"✨ {ctx.nickname} 购买了保险！",
            f"🔒 获得 {ShangbaoxianConfig.CHARGES} 次保险",
            f"💰 真正损失>={ShangbaoxianConfig.LENGTH_THRESHOLD}cm长度时赔付{ShangbaoxianConfig.PAYOUT}金币",
            f"⚠️ 注意：自残类不赔付（自爆/月牙天冲）",
            f"📊 当前保险次数：{new_charges}",
            "═══════════════════"
        ])

        return ctx


# =============================================================================
# 牛牛盾牌 Effect
# =============================================================================

class NiuniuDunpaiEffect(ItemEffect):
    """牛牛盾牌 - Safe Box: grants 3 shield charges to protect against negative effects"""
    name = "牛牛盾牌"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import NiuniuDunpaiConfig

        # 扣除50%长度和硬度作为代价
        old_length = ctx.user_length
        old_hardness = ctx.user_hardness
        length_cost = int(abs(old_length) * 0.5)
        hardness_cost = int(old_hardness * 0.5)
        if old_length > 0:
            ctx.length_change = -length_cost
        else:
            ctx.length_change = length_cost  # 负数长度：扣代价让它更接近0
        ctx.hardness_change = -hardness_cost

        # 增加护盾次数
        current_charges = ctx.user_data.get('shield_charges', 0)
        new_charges = current_charges + NiuniuDunpaiConfig.SHIELD_CHARGES

        ctx.extra['add_shield_charges'] = NiuniuDunpaiConfig.SHIELD_CHARGES

        ctx.messages.append("🛡️ ══ 牛牛盾牌 ══ 🛡️")
        ctx.messages.append(f"✨ {ctx.nickname} 购买了牛牛盾牌！")
        ctx.messages.append(f"⚠️ 代价：长度 {old_length}cm → {old_length + ctx.length_change}cm ({ctx.length_change:+}cm)")
        ctx.messages.append(f"⚠️ 代价：硬度 {old_hardness} → {old_hardness + ctx.hardness_change} ({ctx.hardness_change:+})")
        ctx.messages.append(f"🔒 获得 {NiuniuDunpaiConfig.SHIELD_CHARGES} 次护盾防护")
        if current_charges > 0:
            ctx.messages.append(f"📊 当前护盾：{current_charges} → {new_charges}")
        else:
            ctx.messages.append(f"📊 当前护盾：{new_charges}")
        ctx.messages.append("")
        ctx.messages.append("💡 护盾可抵挡：")
        ctx.messages.append("  • 劫富济贫（被抢时）")
        ctx.messages.append("  • 月牙天冲（被冲时）")
        ctx.messages.append("  • 大自爆（被炸时）")
        ctx.messages.append("  • 混沌风暴负面事件")
        ctx.messages.append("  • 夺牛魔（减免10%/层）")
        ctx.messages.append("═══════════════════")

        return ctx


# =============================================================================
# 穷牛一生 Effect
# =============================================================================

class QiongniuYishengEffect(ItemEffect):
    """穷牛一生 - 便宜的赌博，期望值略正"""
    name = "穷牛一生"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import QiongniuYishengConfig

        # 根据概率选择结果
        roll = random.random()
        cumulative = 0
        selected_outcome = None

        for outcome in QiongniuYishengConfig.OUTCOMES:
            cumulative += outcome['chance']
            if roll < cumulative:
                selected_outcome = outcome
                break

        if not selected_outcome:
            selected_outcome = QiongniuYishengConfig.OUTCOMES[-1]

        # 计算变化值
        length_change = random.randint(selected_outcome['length_min'], selected_outcome['length_max'])
        hardness_change = random.randint(selected_outcome['hardness_min'], selected_outcome['hardness_max'])

        ctx.length_change = length_change
        ctx.hardness_change = hardness_change

        # 生成消息
        outcome_name = selected_outcome['name']
        if outcome_name == 'bad':
            ctx.messages.append("🐄 ══ 穷牛一生 ══ 🐄")
            ctx.messages.append(f"😭 {ctx.nickname} 运气不好...")
            if length_change < 0:
                ctx.messages.append(f"📉 长度 {length_change}cm")
            if hardness_change < 0:
                ctx.messages.append(f"💔 硬度 {hardness_change}")
            ctx.messages.append("穷牛的命运就是这样...")
        elif outcome_name == 'neutral':
            ctx.messages.append("🐄 ══ 穷牛一生 ══ 🐄")
            ctx.messages.append(f"😊 {ctx.nickname} 小有收获！")
            ctx.messages.append(f"📈 长度 +{length_change}cm")
            ctx.messages.append("穷牛也有春天~")
        elif outcome_name == 'good':
            ctx.messages.append("🐄 ══ 穷牛一生 ══ 🐄")
            ctx.messages.append(f"🎉 {ctx.nickname} 运气不错！")
            ctx.messages.append(f"📈 长度 +{length_change}cm")
            ctx.messages.append(f"💪 硬度 +{hardness_change}")
            ctx.messages.append("穷牛翻身！")
        else:  # jackpot
            ctx.messages.append("🐄 ══ 穷牛一生 ══ 🐄")
            ctx.messages.append(f"🎊🎊🎊 大奖！！！ 🎊🎊🎊")
            ctx.messages.append(f"✨ {ctx.nickname} 触发了穷牛逆袭！")
            ctx.messages.append(f"🚀 长度 +{length_change}cm")
            ctx.messages.append(f"💪 硬度 +{hardness_change}")
            ctx.messages.append("穷牛一朝翻身把歌唱！")

        ctx.messages.append("═══════════════════")
        return ctx


# =============================================================================
# 绝对值！ Effect
# =============================================================================

class JueduizhiEffect(ItemEffect):
    """绝对值！ - Absolute Value: convert negative length to positive"""
    name = "绝对值！"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        current_length = ctx.user_length

        # 检查是否是负数
        if current_length >= 0:
            ctx.messages.extend([
                "❌ ══ 绝对值！ ══ ❌",
                f"⚠️ {ctx.nickname} 你的牛牛不是负数！",
                f"📊 当前长度：{current_length}cm",
                "💡 这个道具只有负数牛牛才能用哦~",
                "═══════════════════"
            ])
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 动态价格 = 长度的绝对值
        dynamic_price = abs(current_length)
        ctx.extra['dynamic_price'] = dynamic_price

        # 检查金币是否足够（由商店传入）
        user_coins = ctx.extra.get('user_coins', 0)
        if user_coins < dynamic_price:
            ctx.messages.extend([
                "❌ ══ 绝对值！ ══ ❌",
                f"💰 需要 {dynamic_price} 金币（= |{current_length}|）",
                f"📊 你只有 {user_coins} 金币，不够！",
                "═══════════════════"
            ])
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 取绝对值：从负数变成正数
        # 例如 -100 变成 100，需要 +200
        change = abs(current_length) * 2
        ctx.length_change = change

        ctx.messages.extend([
            "🔢 ══ 绝对值！ ══ 🔢",
            f"💰 花费 {dynamic_price} 金币",
            f"✨ {ctx.nickname} 使用了绝对值！",
            f"📊 {current_length}cm → {abs(current_length)}cm",
            f"🎉 咸鱼翻身！长度 +{change}cm！",
            "═══════════════════"
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
    manager.register(MiaocuijiaoEffect())
    manager.register(XiaolanpianEffect())

    # Register active item effects
    manager.register(BalishijiaEffect())
    manager.register(DutuyingbiEffect())
    manager.register(JiefuJipinEffect())
    manager.register(HundunFengbaoEffect())
    manager.register(HeidongEffect())
    manager.register(YueyaTianchongEffect())
    manager.register(DazibaoEffect())
    manager.register(HuoshuiDongyinEffect())
    manager.register(ShangbaoxianEffect())
    manager.register(NiuniuDunpaiEffect())
    manager.register(QiongniuYishengEffect())
    manager.register(JueduizhiEffect())

    return manager
