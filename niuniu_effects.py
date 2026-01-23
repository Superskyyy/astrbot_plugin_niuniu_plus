# Niuniu Effect System
# Decouples item effects from core game logic

import random
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from niuniu_config import format_length, format_length_change


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

    # 股市配置 - 子类可覆盖
    # 格式: {"volatility": (min, max), "templates": {"up": [...], "down": [...], "plain": [...]}}
    # None 表示不影响股市
    # 只有 "plain" 表示工具类道具，使用平淡文案
    stock_config: Optional[Dict[str, Any]] = None

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

    # 夺取负数目标的趣味文案
    STEAL_NEGATIVE_TARGET_TEXTS = [
        "🎭 等等...对方是负数牛牛？？",
        "🤡 夺牛魔：「这负数...我帮你背了！」",
        "🌀 你主动吸收了对方的负能量债务！",
        "😱 本想抢劫却背上了债务！",
        "🕳️ 夺牛魔把对方的负数转移给你了！",
        "💀 恭喜你接盘了一个负数牛牛！",
        "🎪 对方的债务现在是你的了！",
        "🃏 夺牛魔：「负数？照样夺！」",
    ]

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

            # 根据目标长度正负显示不同文案
            if base_steal_len < 0:
                # 目标是负数，夺取负数意味着吸收债务
                ctx.messages.extend([
                    random.choice(self.STEAL_NEGATIVE_TARGET_TEXTS),
                    f"💸 你接收了 {abs(actual_steal_len)}cm 的负数债务！",
                    f"🎉 {ctx.target_nickname} 债务清零，重获新生！",
                ])
            else:
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

    # 负数牛牛自爆的趣味文案（因祸得福）
    SELF_CLEAR_NEGATIVE_TEXTS = [
        "🎭 等等...负负得正？？？",
        "🤡 蝌蚪看到负数牛牛，吓得把它吸成0了！",
        "🌀 罐头里的蝌蚪：「这负数太恶心了，给你清零算了」",
        "😂 本想自爆却意外翻身？？什么运气！",
        "🎪 夺牛魔：「负数？不存在的，归零！」",
        "🃏 命运的玩笑：想死却活了过来！",
        "✨ 蝌蚪被负能量反噬，把你净化了！",
        "🦠 负数牛牛太臭，蝌蚪消毒后归零了！",
        "🎰 最倒霉的事变成了最幸运的事！",
        "💫 蝌蚪：「负数？不合规，重置！」",
    ]

    def _handle_self_clear(self, ctx: EffectContext):
        """10% 清空自己长度和硬度"""
        ctx.extra['duoxinmo_result'] = 'self_clear'
        ctx.length_change = -ctx.user_length  # 归零
        ctx.hardness_change = -(ctx.user_hardness - 1)  # 硬度归1

        if ctx.user_length > 0:
            # 正数牛牛：正常自爆，很惨
            ctx.messages.extend([
                "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
                random.choice(self.SELF_CLEAR_TEXTS),
                f"💀 {ctx.nickname} 长度归零！硬度归1！",
                "😱 这罐头有毒！！！",
            ])
        else:
            # 负数牛牛：因祸得福，归零反而是好事！
            ctx.messages.extend([
                "🥫 ══ 夺牛魔蝌蚪罐头 ══ 🥫",
                random.choice(self.SELF_CLEAR_NEGATIVE_TEXTS),
                f"🎊 {ctx.nickname} 从 {ctx.user_length}cm 归零了！",
                "🍀 因祸得福！负数牛牛重获新生！",
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

    # 股市配置 - 中等影响道具
    stock_config = {
        "volatility": (0.02, 0.06),
        "templates": {
            "up": [
                "🏠 {nickname} 住进巴黎牛家！股市看好！",
                "🏠 硬度+10！股价跟着硬起来！",
                "🏠 {nickname} 的硬度提升振奋了市场！",
                "🏠 「巴黎牛家是硬实力」—— 股评家",
            ],
            "down": [
                "🏠 {nickname} 巴黎牛家入住失败！股市失望！",
                "🏠 硬度换长度...股市：这波亏了！",
                "🏠 {nickname} 的操作让股民迷惑！",
                "🏠 「长度换硬度不划算」—— 股评家",
            ],
        }
    }

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

    # 股市配置 - 赌徒硬币是中等影响道具
    stock_config = {
        "volatility": (0.02, 0.08),
        "templates": {
            "up": [
                "🎰 {nickname} 赌赢了！股民跟着沾光！",
                "🪙 硬币翻倍成功！股价应声上涨！",
                "🎰 {nickname} 的赌运带动了股市！",
                "✨ 赌神附体！股价跟着起飞！",
                "🎰 「赌就是干」—— {nickname} 成功了！",
                "🪙 硬币正面！股市也跟着翻身！",
                "🎰 {nickname} 用运气征服了股市！",
                "💰 赌徒精神感染股民，集体买入！",
            ],
            "down": [
                "🎰 {nickname} 赌输了！股民心态崩了！",
                "🪙 硬币减半...股价跟着腰斩！",
                "🎰 {nickname} 的霉运传染了股市！",
                "💀 赌神背弃了你，股价背弃了我们！",
                "🎰 「赌狗终究是赌狗」—— 股评家",
                "🪙 硬币反面！股市也跟着翻车！",
                "🎰 {nickname} 用运气毁灭了股市！",
                "💸 赌徒精神吓跑股民，集体抛售！",
            ],
        }
    }

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

    # 负数专属文案
    NEGATIVE_DOUBLE_TEXTS = [
        "🎰 硬币正面朝上！凹陷减半！",
        "🌀 负负...得少负？数学真奇妙！",
        "🎭 硬币帮你把坑填了一半！",
        "✨ 正面！凹下去的牛牛回弹了一点！",
        "🪙 叮！命运垂怜，凹陷修复中...",
        "🍀 硬币说：「给你减点负担」",
        "🔧 硬币化身维修工，填坑ing~",
        "💫 正面朝上！负能量被吸走一半！",
    ]

    NEGATIVE_HALVE_TEXTS = [
        "🎰 硬币反面朝上...凹得更深了！",
        "🕳️ 硬币砸出一个更大的坑！",
        "💀 反面！深渊在凝视你...",
        "😱 硬币：「挖呀挖呀挖~」",
        "🌑 凹陷加倍！地心探险开始！",
        "☠️ 硬币跳进坑里，还往下挖！",
        "🔨 硬币化身挖掘机，凹凹凹！",
        "💔 反面...你和地心更近了一步",
    ]

    NEGATIVE_JACKPOT_TEXTS = [
        "🎰✨ 硬币爆发金光！负数牛牛起死回生！",
        "🌟 天降神迹！从地底飞升天际！",
        "💫 硬币立起来了！负转正！逆天改命！",
        "🎇 叮叮叮！从深渊到巅峰！",
        "⭐ 硬币：「从今天起，你不再是负数！」",
        "🚀 负数牛牛一飞冲天！！！",
        "🔮 硬币施展禁术：负数逆转！",
        "🎊 从欠债到暴富！命运的馈赠！",
    ]

    NEGATIVE_BADLUCK_TEXTS = [
        "🎰💀 硬币裂开...负数牛牛坠入深渊！",
        "☠️ 硬币变成铲子，疯狂往下挖！",
        "🌑 霉运降临！凹到地心去吧！",
        "💔 硬币：「让你体验什么叫真正的负」",
        "👻 负数还能更负？硬币说可以！",
        "🕳️ 挖穿地球的节奏！凹到极限！",
        "😈 硬币邪笑：「负无止境~」",
        "💀 从负数到超级负数！深渊加深！",
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
        if current_length < 0:
            ctx.messages.append(random.choice(self.NEGATIVE_JACKPOT_TEXTS))
        else:
            ctx.messages.append(random.choice(self.JACKPOT_TEXTS))
        ctx.messages.append("🏆 ═══ 头 等 奖 ═══ 🏆")

        if current_length > 0:
            gain = current_length * 3
            ctx.length_change = gain
            ctx.messages.append(f"💰 长度暴涨！{format_length(current_length)} → {format_length(current_length + gain)} ({format_length_change(gain)})")
        elif current_length < 0:
            # 负数变成正的4倍绝对值
            gain = abs(current_length) * 4
            ctx.length_change = gain
            ctx.messages.append(f"💰 逆天改命！{format_length(current_length)} → {format_length(current_length + gain)} ({format_length_change(gain)})")
            ctx.messages.append("🎊 负数牛牛的春天来了！！！")
            return
        else:
            gain = 100
            ctx.length_change = gain
            ctx.messages.append(f"💰 从零开始的暴富！0cm → {format_length(gain)}")

        ctx.messages.append("🎊 运气爆棚！今天一定要买彩票！")

    def _apply_bad_luck(self, ctx: EffectContext, current_length: float):
        """霉运：长度变成-2倍"""
        if current_length < 0:
            ctx.messages.append(random.choice(self.NEGATIVE_BADLUCK_TEXTS))
        else:
            ctx.messages.append(random.choice(self.BAD_LUCK_TEXTS))
        ctx.messages.append("💀 ═══ 霉 运 降 临 ═══ 💀")

        if current_length > 0:
            # 正数变成负2倍
            loss = current_length * 3
            ctx.length_change = -loss
            ctx.messages.append(f"😱 长度暴跌！{format_length(current_length)} → {format_length(current_length - loss)} ({format_length_change(-loss)})")
        elif current_length < 0:
            # 负数变得更负
            loss = abs(current_length) * 3
            ctx.length_change = -loss
            ctx.messages.append(f"😱 凹到地心！{format_length(current_length)} → {format_length(current_length - loss)} ({format_length_change(-loss)})")
            ctx.messages.append("🕳️ 负数牛牛的噩梦...")
            return
        else:
            loss = 100
            ctx.length_change = -loss
            ctx.messages.append(f"😱 从零坠入深渊！0cm → {format_length(-loss)}")

        ctx.messages.append("🥀 今天不宜出门...")

    def _apply_double(self, ctx: EffectContext, current_length: float):
        """翻倍"""
        if current_length > 0:
            text = random.choice(self.DOUBLE_TEXTS)
            ctx.length_change = current_length
            ctx.messages.append(f"{text} {format_length_change(current_length)}")
        elif current_length < 0:
            text = random.choice(self.NEGATIVE_DOUBLE_TEXTS)
            gain = abs(current_length) // 2
            ctx.length_change = gain
            ctx.messages.append(f"{text} {format_length_change(gain)}")
            ctx.messages.append(f"🍀 {format_length(current_length)} → {format_length(current_length + gain)} 往0迈进！")
        else:
            change = random.randint(5, 15)
            ctx.length_change = change
            ctx.messages.append(f"🎰 硬币悬浮！从虚无中获得了{change}cm！")

    def _apply_halve(self, ctx: EffectContext, current_length: float):
        """减半"""
        if current_length > 0:
            text = random.choice(self.HALVE_TEXTS)
            loss = current_length / 2
            ctx.length_change = -loss
            ctx.messages.append(f"{text} {format_length_change(-loss)}")
        elif current_length < 0:
            text = random.choice(self.NEGATIVE_HALVE_TEXTS)
            loss = abs(current_length)
            ctx.length_change = -loss
            ctx.messages.append(f"{text} {format_length_change(-loss)}")
            ctx.messages.append(f"💀 {format_length(current_length)} → {format_length(current_length - loss)} 更深了...")
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

    # 股市配置 - 劫富济贫是中等影响道具
    stock_config = {
        "volatility": (0.03, 0.10),
        "templates": {
            "up": [
                "💰 {nickname} 劫富成功！牛市狂欢！",
                "💰 财富重新分配，股价飙升！",
                "💰 劫富济贫大获成功，市场振奋！",
                "💰 首富被洗劫，散户：涨涨涨！",
                "💰 {nickname} 替天行道，股市点赞！",
                "💰 均贫富行动成功，股价大涨！",
                "💰 「劫富济贫利好散户」—— 股评家",
                "💰 {nickname} 成为人民英雄，股价致敬！",
            ],
            "down": [
                "💸 {nickname} 劫富翻车！市场恐慌！",
                "💸 劫富失败，首富反击！股价暴跌！",
                "💸 财富动荡，股市不安！",
                "💸 劫富行动引发市场担忧！",
                "💸 {nickname} 被首富教做人，股价陪葬！",
                "💸 「劫富济贫破坏市场秩序」—— 股评家",
                "💸 均贫富行动失败，股价崩盘！",
                "💸 首富护盾太硬，{nickname} 碰了一鼻子灰！",
            ],
        }
    }

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

    # 股市配置 - 混沌风暴是大事件
    stock_config = {
        "volatility": (0.05, 0.20),
        "templates": {
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
            ],
        }
    }

    # 有趣的事件文案
    LENGTH_UP_TEXTS = [
        "被混沌之风眷顾，牛牛疯长！",
        "时空裂缝中飘来一股神秘力量...",
        "混沌能量注入！膨胀！",
        "「恭喜你被选中成为混沌的宠儿」",
        "风暴中捡到了失落的长度！",
        "混沌龙卷风带来了意外之喜！",
        "「系统提示：检测到长度异常增长」",
        "时空碎片融入，牛牛进化了！",
        "混沌之神微微一笑：赏你！",
        "虫洞里飘出来一根...等等这是什么？！",
        "量子涨落导致意外增长！",
        "平行宇宙的你送来了援助！",
        "混沌彩票头奖！长度暴涨！",
        "「叮！您的牛牛已升级」",
        "被混沌祝福击中！超级加倍！",
        "混沌精灵偷偷塞了点私货给你~",
        "风暴眼中心居然很安全，还捡到宝了！",
        "「检测到非法增长...算了不管了」",
        "混沌之神打了个喷嚏，喷到你了！",
        "时空缝隙里掉出来一截，接住了！",
        "被混沌射线扫描：基因优化完成！",
        "「恭喜触发SSR：天降横财」",
        "混沌蘑菇的孢子落在你身上了...",
        "量子隧穿：别人的长度跑你这来了！",
        "混沌快递：您的加长包裹已签收！",
    ]
    LENGTH_DOWN_TEXTS = [
        "被混沌漩涡吸走了一截...",
        "时空乱流撕裂了你的牛牛！",
        "混沌税收员来了！",
        "「你的长度已被混沌没收」",
        "风暴把你的牛牛刮飞了一段！",
        "混沌黑洞：嗝~吃饱了",
        "时空裂缝把你的长度吞了！",
        "「警告：检测到长度异常流失」",
        "混沌之神皱了皱眉：罚你！",
        "平行宇宙的你来讨债了！",
        "量子坍缩导致长度缩水！",
        "被混沌诅咒击中！缩缩缩！",
        "混沌小偷：这个我收下了~",
        "「叮！您的牛牛已被降级」",
        "虫洞把你的一部分吸到另一个宇宙去了！",
        "混沌啃食者路过，咬了一口！",
        "时空折叠时不小心夹到了...",
        "「系统回收：多余部分已清理」",
        "混沌法院判决：没收违法所得！",
        "风暴碎片削掉了一截...",
        "被混沌蚊子叮了一口，肿...不对，缩了！",
        "量子波动：检测到负增长！",
        "混沌剪刀手路过：咔嚓~",
        "时空虫子在你身上打了个洞！",
        "「触发陷阱：缩小光线」",
    ]
    HARDNESS_UP_TEXTS = [
        "混沌结晶附着在牛牛上！",
        "被雷劈了一下，反而更硬了？",
        "时空碎片嵌入，硬度飙升！",
        "「混沌祝福：钢铁意志」",
        "混沌矿石融入！硬度MAX！",
        "时空压缩：密度增加！",
        "「叮！获得被动：金刚不坏」",
        "混沌锻造炉加持！",
        "被混沌射线照射，硬化了！",
        "平行宇宙的硬度传送过来了！",
        "量子强化：结构稳定！",
        "混沌之神：赐你钢铁之躯！",
        "「系统提示：硬度突破限制」",
        "时空晶体附着成功！",
        "混沌陨石砸中！钛合金打造！",
        "吸收了风暴中的混沌精华！",
        "「检测到异常硬化，但这是好事」",
        "混沌铁匠连夜加工！",
        "被时空压力压实了！更硬！",
        "量子纠缠到了钻石的硬度！",
        "「获得buff：坚如磐石」",
        "混沌淬火成功！硬度+！",
    ]
    HARDNESS_DOWN_TEXTS = [
        "混沌侵蚀了你的硬度...",
        "被软化射线击中！",
        "时空扭曲导致结构松散...",
        "「混沌诅咒：豆腐化」",
        "混沌酸雨腐蚀！硬度下降！",
        "时空膨胀：密度降低...",
        "「叮！失去被动：金刚不坏」",
        "被混沌虫啃食了！",
        "平行宇宙的软弱传染过来了！",
        "量子衰变：结构崩坏！",
        "混沌之神：收回你的力量！",
        "「警告：硬度低于安全值」",
        "时空裂缝带走了你的坚硬！",
        "被混沌诅咒：软趴趴...",
        "混沌融化术！变软了！",
        "风暴带来的湿气让你...",
        "「debuff获得：面条化」",
        "被时空高温融化了一点...",
        "混沌史莱姆黏住了！软化中...",
        "量子退相干：结构不稳定了！",
        "「系统警告：检测到软化」",
        "混沌橡皮擦蹭了一下...",
    ]
    COIN_GAIN_TEXTS = [
        "风暴中飘来一袋金币！",
        "混沌商人路过，撒了一地钱！",
        "时空裂缝掉出了财宝！",
        "「恭喜！混沌彩票中奖」",
        "混沌银行利息到账！",
        "平行宇宙的你汇款过来了！",
        "「叮！收到混沌红包」",
        "时空走私犯丢下了赃款！",
        "混沌之神心情好，打赏！",
        "量子钱包bug：凭空多了钱！",
        "风暴里捡到了别人的钱包！",
        "混沌保险理赔到账！",
        "「系统错误：金币异常增加」",
        "虫洞吐出一堆金币！",
        "混沌ATM机故障，多吐钱了！",
        "时空海盗的宝藏被你发现了！",
        "「恭喜抽中：混沌年终奖」",
        "混沌财神路过，撒币！",
        "量子彩票开奖：你中了！",
        "风暴把别人的钱吹到你这了！",
        "「叮！混沌众筹成功」",
        "混沌银行：利息结算完毕！",
    ]
    COIN_LOSE_TEXTS = [
        "钱包被混沌漩涡吸走了！",
        "混沌小偷光顾了你的口袋！",
        "金币被时空乱流卷走...",
        "「混沌税：已自动扣款」",
        "混沌银行：服务费扣除！",
        "平行宇宙的你来借钱了！",
        "「叮！混沌红包被抢」",
        "时空裂缝吞噬了你的财产！",
        "混沌之神：上供！",
        "量子钱包bug：钱凭空消失！",
        "风暴把你的钱吹跑了！",
        "混沌骗子：这是手续费~",
        "「警告：金币异常流失」",
        "虫洞偷走了你的存款！",
        "混沌收费站：过路费！",
        "时空罚款单：违规停车！",
        "「系统扣款：混沌维护费」",
        "混沌乞丐：给点呗~（强制）",
        "量子诈骗：您的账户异常...",
        "风暴掀翻了你的存钱罐！",
        "「触发陷阱：钱袋漏了」",
        "混沌城管：没收违法所得！",
    ]
    SWAP_TEXTS = [
        "时空错乱！你俩的牛牛互换了！",
        "混沌法则：交换命运！",
        "「灵魂互换术·牛牛版」",
        "量子纠缠触发！尺寸对调！",
        "平行宇宙融合：身份互换！",
        "混沌之神：换着玩玩！",
        "「叮！检测到非法数据交换」",
        "时空虫洞：两边各取一个！",
        "混沌转盘：交换大成功！",
        "命运交织：你们的牛牛换了！",
        "「系统混乱：数据互换」",
        "混沌天平：追求平衡！",
        "量子叠加态坍缩：互换！",
        "时空折叠点重合！",
    ]
    DOUBLE_TEXTS = [
        "混沌翻倍术！牛牛暴涨！",
        "时空复制成功！Double！",
        "「欧皇附体！翻倍大成功」",
        "混沌赌场：你赢了！",
        "量子分裂：一变二！",
        "平行宇宙的你也加入了！",
        "「叮！触发隐藏buff：翻倍」",
        "混沌之神大手一挥：Double！",
        "时空镜像：复制成功！",
        "混沌轮盘停在翻倍格！",
        "「系统异常：长度x2」",
        "虫洞传来增援！",
        "量子涨落的奇迹！",
        "命运眷顾：翻倍快乐！",
        "混沌复印机：复制完成！",
        "时空克隆术大成功！",
        "「触发彩蛋：长度暴击」",
        "混沌乘法器：x2！",
        "量子叠加：1+1=2倍的你！",
        "风暴带来了你的分身！",
        "「恭喜抽中：翻倍卡」",
        "混沌镜子：照出两个你！",
    ]
    HALVE_TEXTS = [
        "混沌二分法：一刀两断！",
        "时空折叠把你的牛牛对折了...",
        "「很遗憾，你被选中减半」",
        "混沌剪刀手：咔嚓！",
        "量子坍缩：只剩一半！",
        "平行宇宙的你拿走了一半！",
        "「叮！触发debuff：减半」",
        "混沌之神无情地比了个剪刀手",
        "时空裂缝吞掉了一半！",
        "混沌轮盘停在减半格！",
        "「系统惩罚：长度÷2」",
        "虫洞把一半吸走了！",
        "量子衰变：对半砍！",
        "命运捉弄：一分为二！",
        "混沌锯子：滋滋滋~",
        "时空除法器启动！÷2！",
        "「触发陷阱：对半分」",
        "混沌分割术：切！",
        "量子减半：波函数坍缩！",
        "风暴刮走了一半...",
        "「抽中惩罚卡：50% off」",
        "混沌数学家：来，除以二！",
    ]
    STEAL_TEXTS = [
        "化身混沌盗贼！偷取成功！",
        "时空扒手出击！得手！",
        "「你的长度？不，是我的了」",
        "混沌之手：巧取豪夺！",
        "量子隧穿：偷渡成功！",
        "平行宇宙大盗降临！",
        "「叮！完成成就：神偷」",
        "混沌忍者：无声偷取！",
        "时空裂缝传送：得手！",
        "混沌黑手党出击！",
        "「系统：检测到非法转移」",
        "虫洞偷运成功！",
        "量子小偷：来无影去无踪！",
        "命运小偷：这个归我了！",
        "混沌窃贼天赋觉醒！",
        "时空海盗：抢劫！",
        "「技能发动：顺手牵羊」",
        "混沌蟊贼：这个好，我要了！",
        "量子黑客：入侵成功！",
        "风暴掩护下的完美偷窃！",
        "「恭喜获得：他人の长度」",
        "混沌罗宾汉：劫...呃，直接拿！",
    ]
    GIVE_TEXTS = [
        "被混沌慈善协会强制捐款...",
        "时空邮递员把你的牛牛寄走了！",
        "「混沌法则：劫富济贫」",
        "强制分享！你的长度被转移了！",
        "混沌税务局：强制转账！",
        "平行宇宙的你在做慈善！",
        "「叮！被动触发：乐善好施」",
        "混沌圣诞老人：礼物送出！",
        "时空快递：已签收！",
        "混沌红十字会：感谢捐赠！",
        "「系统：强制执行转移」",
        "虫洞传送带启动！",
        "量子传输：已送达！",
        "命运安排：你该分享！",
        "混沌强制外卖：打包送出！",
        "时空拍卖会：你的被拍走了！",
        "「触发debuff：散财童子」",
        "混沌转账机：滴！转账成功！",
        "量子快递：寄出去了~",
        "风暴把你的刮给别人了！",
        "「强制分享：做人要大方」",
        "混沌社会主义：共同富裕！",
    ]
    NOTHING_TEXTS = [
        "混沌之眼扫过，决定放过你...",
        "风暴绕开了你，什么都没发生",
        "「混沌：今天心情好，饶你一次」",
        "时空护盾自动展开，安全！",
        "你太普通了，混沌懒得理你...",
        "混沌打了个哈欠，略过了你",
        "量子态未坍缩：无事发生",
        "平行宇宙的你替你挡了一劫",
        "「叮！触发被动：透明人」",
        "混沌之神眨了眨眼：下次再说",
        "时空夹缝中的幸运儿！",
        "混沌轮盘停在空白格！",
        "「系统：未检测到变化」",
        "虫洞绕过了你~",
        "命运休息中...请稍后再试",
        "混沌路过，但没看到你...",
        "风暴眼：这里出奇的平静",
        "「恭喜获得：啥也没有」",
        "混沌之神：你是谁来着？",
        "时空跳过了这一帧！",
        "量子观测失败：未找到目标",
        "「触发空气：无效果」",
        "混沌表示：懒得动了",
        "你与混沌擦肩而过~",
        "「系统已读不回」",
    ]
    REVERSE_TEXTS = [
        "混沌镜像术！正负颠倒！",
        "时空反转！黑变白，白变黑！",
        "「物极必反·混沌版」",
        "平行宇宙的你入侵了！",
        "量子镜像：正负互换！",
        "混沌之神：让你尝尝颠倒的滋味！",
        "「叮！触发反转效果」",
        "时空倒流：正变负，负变正！",
        "混沌翻转术：乾坤颠倒！",
        "命运反转：塞翁失马！",
        "「系统混乱：符号反转」",
        "虫洞镜像：你被反过来了！",
        "量子叠加态反转！",
        "混沌天平翻转！",
    ]
    QUANTUM_TEXTS = [
        "量子纠缠！命运共享！",
        "薛定谔的牛牛：取平均值！",
        "时空同步：你们现在一样长了",
        "「混沌公平法则：平分秋色」",
        "量子态坍缩：趋向平均！",
        "平行宇宙融合：各取一半！",
        "「叮！触发量子纠缠效果」",
        "混沌之神：追求平衡！",
        "时空重叠：取中间值！",
        "混沌天平：一碗水端平！",
        "「系统：执行平均化」",
        "虫洞同步：长度统一！",
        "命运交织：平分命运！",
        "混沌公式：(A+B)/2！",
    ]
    SACRIFICE_TEXTS = [
        "黑暗献祭！痛苦转化为力量！",
        "混沌祭坛：牺牲自己，成全他人",
        "「献出心脏！...不对，献出牛牛！」",
        "血祭成功：3倍奉还！",
        "暗黑仪式启动！",
        "混沌之神：我要看到诚意！",
        "「叮！完成献祭仪式」",
        "时空祭品：已签收！",
        "混沌邪教：献祭大成功！",
        "命运代价：牺牲换取力量！",
        "「系统：检测到能量转换」",
        "虫洞祭坛：3倍返还！",
        "量子转化：痛苦→力量！",
        "黑暗契约：我愿意献出！",
    ]
    PARASITE_TEXTS = [
        "混沌寄生虫已植入！",
        "时空虫卵附着成功！",
        "「恭喜，你获得了一个寄生者」",
        "混沌蛔虫：以后打胶我也有份！",
        "量子寄生体附着！",
        "平行宇宙虫子入侵！",
        "「叮！获得被动：吸血鬼」",
        "混沌之神：给你个小伙伴！",
        "时空水蛭：我住这了~",
        "混沌共生体：我们是一体的！",
        "「系统：检测到寄生程序」",
        "虫洞虫子：找到宿主了！",
        "命运共享者：你打胶我收益！",
        "混沌蚂蝗：嘿嘿，蹭饭！",
    ]
    GLOBAL_DOOMSDAY_TEXTS = [
        "天崩地裂！末日审判降临！",
        "混沌法官：最弱者，接受制裁！",
        "「审判日：适者生存」",
        "混沌之神宣判：弱者出局！",
        "时空审判庭开庭！",
        "「叮！触发全局事件：末日」",
        "量子审判：最小值归零！",
        "混沌天平：淘汰最轻的！",
        "命运裁决：弱肉强食！",
        "虫洞审判：最短者消失！",
        "「系统：执行末日协议」",
        "混沌达尔文：物竞天择！",
        "时空清洗：清除最弱！",
    ]
    GLOBAL_ROULETTE_TEXTS = [
        "命运轮盘转动！全员大洗牌！",
        "混沌赌场：重新发牌！",
        "「时空重置：随机分配」",
        "混沌之神：换换口味！",
        "时空搅拌机启动！",
        "「叮！触发全局事件：洗牌」",
        "量子随机化：全部打乱！",
        "混沌轮盘：重新分配！",
        "命运骰子：重投一次！",
        "虫洞搅拌：随机重排！",
        "「系统：执行随机化」",
        "混沌shuffle：打乱顺序！",
        "时空重组：随机就是公平！",
    ]
    GLOBAL_REVERSE_TEXTS = [
        "乾坤大挪移！王者与青铜互换！",
        "混沌天平倾斜！强弱颠倒！",
        "「反向天赋：第一变倒一」",
        "混沌之神：让你们换换位置！",
        "时空颠倒术！",
        "「叮！触发全局事件：反转」",
        "量子反转：最大最小互换！",
        "混沌公平法：让强者体验弱者！",
        "命运捉弄：风水轮流转！",
        "虫洞反转：极值互换！",
        "「系统：执行反转协议」",
        "混沌恶作剧：第一第倒一换！",
        "时空翻转：龙头变龙尾！",
    ]
    GLOBAL_LOTTERY_TEXTS = [
        "团灭彩票开奖！全员屏息！",
        "混沌核弹发射中...祈祷吧！",
        "「5%的希望 vs 95%的绝望」",
        "混沌之神：来玩俄罗斯轮盘！",
        "时空彩票：全员参与！",
        "「叮！触发全局事件：团灭」",
        "量子彩票：5%翻倍，95%减半！",
        "混沌豪赌：要么天堂，要么地狱！",
        "命运轮盘：生死一线！",
        "虫洞彩票：开奖中...",
        "「系统：执行团灭彩票」",
        "混沌大乐透：全体参与！",
        "时空赌局：赌上一切！",
    ]

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
                event_text = f"📈 {nickname}: {random.choice(self.LENGTH_UP_TEXTS)} +{value}cm！"

            elif event_id == 'length_down':
                value = random.randint(params['min'], params['max'])
                length_change = -value
                event_text = f"📉 {nickname}: {random.choice(self.LENGTH_DOWN_TEXTS)} -{value}cm！"

            elif event_id == 'hardness_up':
                value = random.randint(params['min'], params['max'])
                hardness_change = value
                event_text = f"💪 {nickname}: {random.choice(self.HARDNESS_UP_TEXTS)} +{value}硬度！"

            elif event_id == 'hardness_down':
                value = random.randint(params['min'], params['max'])
                hardness_change = -value
                event_text = f"😵 {nickname}: {random.choice(self.HARDNESS_DOWN_TEXTS)} -{value}硬度！"

            elif event_id == 'coin_gain':
                value = random.randint(params['min'], params['max'])
                coin_change = value
                event_text = f"💰 {nickname}: {random.choice(self.COIN_GAIN_TEXTS)} +{value}金币！"

            elif event_id == 'coin_lose':
                value = random.randint(params['min'], params['max'])
                coin_change = -value
                event_text = f"💸 {nickname}: {random.choice(self.COIN_LOSE_TEXTS)} -{value}金币！"

            elif event_id == 'length_percent_up':
                value = random.randint(params['min'], params['max'])
                length_change = int(abs(old_length) * value / 100)
                event_text = f"🚀 {nickname}: {random.choice(self.LENGTH_UP_TEXTS)} +{value}%（+{length_change}cm）！"

            elif event_id == 'length_percent_down':
                value = random.randint(params['min'], params['max'])
                length_change = -int(abs(old_length) * value / 100)
                event_text = f"📉 {nickname}: {random.choice(self.LENGTH_DOWN_TEXTS)} -{value}%（{length_change}cm）！"

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
                    event_text = f"🔄 {nickname} ↔ {target_name}: {random.choice(self.SWAP_TEXTS)} （{old_length}cm ↔ {target_len}cm）"
                else:
                    event_text = f"🤷 {nickname}: 混沌想让你交换，但周围空无一人..."

            elif event_id == 'double_or_nothing':
                if old_length > 0:
                    value = min(old_length, 50)  # 最多翻倍50cm
                    length_change = value
                else:
                    value = max(old_length, -50)  # 负数也翻倍但限制
                    length_change = value
                event_text = f"✨ {nickname}: {random.choice(self.DOUBLE_TEXTS)} +{abs(length_change)}cm！"

            elif event_id == 'halve':
                value = abs(old_length) // 2
                length_change = -value if old_length > 0 else value
                event_text = f"💔 {nickname}: {random.choice(self.HALVE_TEXTS)} -{value}cm！"

            elif event_id == 'hardness_reset':
                value = random.randint(params['min'], params['max'])
                hardness_change = value - old_hardness
                direction = "↑" if hardness_change > 0 else "↓"
                event_text = f"🎲 {nickname}: 混沌轮盘决定你的硬度！{old_hardness} → {value} {direction}"

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
                    event_text = f"🦹 {nickname} → {target_name}: {random.choice(self.STEAL_TEXTS)} 偷走{value}cm！"
                else:
                    event_text = f"🤷 {nickname}: 混沌盗贼出击...但周围没人可偷！"

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
                    event_text = f"🎁 {nickname} → {target_name}: {random.choice(self.GIVE_TEXTS)} 送出{value}cm！"
                else:
                    event_text = f"🤷 {nickname}: 想送人...但周围没人接收！"

            elif event_id == 'nothing':
                event_text = f"😶 {nickname}: {random.choice(self.NOTHING_TEXTS)}"

            elif event_id == 'reverse_sign':
                new_len = -old_length
                length_change = new_len - old_length
                event_text = f"🔀 {nickname}: {random.choice(self.REVERSE_TEXTS)} {old_length}cm → {new_len}cm！"

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
                    event_text = f"🔄 {nickname} ⇄ {target_name}: 「灵魂互换·完全版」！（{old_length}cm/{old_hardness}硬 ⇄ {target_len}cm/{target_hard}硬）"
                else:
                    event_text = f"🤷 {nickname}: 想要全属性交换...但没找到对象！"

            elif event_id == 'cooldown_reset':
                # 打胶冷却清零
                ctx.extra['chaos_storm'].setdefault('cooldown_resets', []).append(uid)
                event_text = f"⏰ {nickname}: 「时间回溯」！打胶冷却归零，可以立刻再来！"

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
                event_text = f"⚡ {nickname}: 「混沌连锁反应」！双重打击！{' & '.join(chain_results)}"

            elif event_id == 'hardness_to_length':
                # 硬度转长度：消耗一半硬度（保底剩1），获得长度
                max_convert = max(0, old_hardness - 1)  # 至少保留1点硬度
                convert_hardness = max(1, max_convert // 2) if max_convert > 0 else 0
                if convert_hardness > 0:
                    convert_length = convert_hardness * 3  # 1硬度=3cm
                    hardness_change = -convert_hardness
                    length_change = convert_length
                    event_text = f"🔄 {nickname}: 「炼金术·硬转长」！燃烧{convert_hardness}点硬度 → 获得{convert_length}cm！"
                else:
                    event_text = f"😅 {nickname}: 混沌想帮你转化...但你硬度不够啊！"

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
                        event_text = f"🔄 {nickname}: 「炼金术·长转硬」！压缩{convert_length}cm → 获得{convert_hardness}点硬度！"
                    else:
                        event_text = f"💯 {nickname}: 硬度已达巅峰100！无法再硬了！"
                else:
                    event_text = f"😅 {nickname}: 混沌想帮你转化...但你长度不够啊！"

            elif event_id == 'chaos_tax':
                # 混沌税：被收5%长度给使用者
                if old_length > 0:
                    tax = max(1, int(old_length * 0.05))
                    length_change = -tax
                    ctx.extra['chaos_storm'].setdefault('tax_collected', 0)
                    ctx.extra['chaos_storm']['tax_collected'] += tax
                    event_text = f"💰 {nickname}: 「混沌税务局」上门收税！-{tax}cm 上交国库！"
                else:
                    event_text = f"😅 {nickname}: 混沌税务局看了一眼负数的你...算了，免税！"

            elif event_id == 'clone_length':
                # 克隆别人的长度
                others = [u for u in valid_users if u[0] != uid]
                if others:
                    target_uid, target_data = random.choice(others)
                    target_name = target_data.get('nickname', target_uid)
                    target_len = target_data.get('length', 0)
                    length_change = target_len - old_length
                    direction = "赚了" if length_change > 0 else "亏了"
                    event_text = f"🧬 {nickname}: 「基因克隆」！复制{target_name}的长度！{old_length}→{target_len}cm，{direction}！"
                else:
                    event_text = f"🤷 {nickname}: 混沌克隆仪启动...但找不到DNA样本！"

            elif event_id == 'lucky_buff':
                # 幸运祝福：下次打胶必定成功
                ctx.extra['chaos_storm'].setdefault('lucky_buffs', []).append(uid)
                event_text = f"🍀 {nickname}: 「四叶草の祝福」！下次打胶必定增长！欧皇附体！"

            elif event_id == 'length_quake':
                # 长度震荡：大幅随机波动
                change_val = random.randint(params['min'], params['max'])
                length_change = change_val
                if change_val >= 0:
                    event_text = f"🌋 {nickname}: 「时空震荡」！剧烈波动！+{change_val}cm！"
                else:
                    event_text = f"🌋 {nickname}: 「时空震荡」！剧烈波动！{change_val}cm！"

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
                    event_text = f"🔮 {nickname} ⟷ {target_name}: {random.choice(self.QUANTUM_TEXTS)} ({old_length}+{target_len})/2 = {avg_len}cm"
                else:
                    event_text = f"🤷 {nickname}: 量子纠缠失败...周围没有可以纠缠的对象！"

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
                    event_text = f"🖤 {nickname} → {target_name}: {random.choice(self.SACRIFICE_TEXTS)} 献祭{sacrifice}cm，{target_name}获得{gift}cm！"
                else:
                    event_text = f"😅 {nickname}: 黑暗祭坛拒绝了你...没有可献祭的东西！"

            elif event_id == 'resurrection':
                # 牛牛复活：负数变正数
                if old_length <= 0:
                    new_len = random.randint(params['min'], params['max'])
                    length_change = new_len - old_length
                    event_text = f"✨ {nickname}: 「凤凰涅槃」！牛牛从负数中复活！{old_length}cm → {new_len}cm！重获新生！"
                else:
                    event_text = f"😊 {nickname}: 混沌想复活你的牛牛...但它还活着呢！白给的buff错过了！"

            elif event_id == 'doomsday':
                # 末日审判：全局事件，在后处理中执行
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'doomsday',
                    'trigger_by': nickname
                })
                event_text = f"⚖️ {nickname}: {random.choice(self.GLOBAL_DOOMSDAY_TEXTS)}"

            elif event_id == 'roulette':
                # 轮盘重置：全局事件
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'roulette',
                    'trigger_by': nickname
                })
                event_text = f"🎰 {nickname}: {random.choice(self.GLOBAL_ROULETTE_TEXTS)}"

            elif event_id == 'reverse_talent':
                # 反向天赋：全局事件
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'reverse_talent',
                    'trigger_by': nickname
                })
                event_text = f"🔄 {nickname}: {random.choice(self.GLOBAL_REVERSE_TEXTS)}"

            elif event_id == 'lottery_bomb':
                # 团灭彩票：全局事件
                is_jackpot = random.random() < 0.05  # 5%
                ctx.extra['chaos_storm'].setdefault('global_events', []).append({
                    'type': 'lottery_bomb',
                    'trigger_by': nickname,
                    'jackpot': is_jackpot
                })
                event_text = f"💣 {nickname}: {random.choice(self.GLOBAL_LOTTERY_TEXTS)}"
                if is_jackpot:
                    event_text += " 🎊🎊🎊 中了！！！全体翻倍！！！"
                else:
                    event_text += " 💀 没中...全员遭殃！-50%！"

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
                    event_text = f"🦠 {nickname} → {target_name}: {random.choice(self.PARASITE_TEXTS)} 以后{target_name}打胶你也有份！"
                else:
                    event_text = f"🤷 {nickname}: 寄生虫找不到宿主...孤独地死去了..."

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

    # 股市配置 - 黑洞是大型全局事件
    stock_config = {
        "volatility": (0.08, 0.25),
        "templates": {
            "up": [
                "🕳️ 黑洞吞噬长度，股市疯涨！",
                "⚫ {nickname} 的黑洞创造了财富神话！",
                "🌌 虚空之力注入股市！涨！涨！涨！",
                "🕳️ 黑洞把亏损都吸走了！股价暴涨！",
                "⚫ 「黑洞理论应用于股市」—— 诺贝尔经济学奖",
                "🌀 {nickname} 用黑洞吸引了所有资金！",
                "🕳️ 黑洞：我吸的是空头！股价起飞！",
                "⚫ 时空扭曲！股价突破天际！",
            ],
            "down": [
                "🕳️ 黑洞反噬！股市崩塌！",
                "⚫ {nickname} 的黑洞把股市也吸进去了！",
                "🌌 虚空之力失控！股价暴跌！",
                "🕳️ 黑洞把利好都吞了！股价跳水！",
                "⚫ 「黑洞就是股市的噩梦」—— 股评家",
                "🌀 {nickname} 的黑洞把散户都吓跑了！",
                "🕳️ 黑洞：我吸的是多头...对不起！",
                "⚫ 时空扭曲！股价坠入深渊！",
            ],
        }
    }

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

    # 股市配置 - 月牙天冲是中等影响道具
    stock_config = {
        "volatility": (0.03, 0.10),
        "templates": {
            "up": [
                "🌙 {nickname} 月牙天冲命中！股市沸腾！",
                "⚔️ 一刀两断！股价却一飞冲天！",
                "🌙 月光之力注入股市！涨！",
                "⚔️ {nickname} 的剑气带动了股价！",
                "🌙 「月牙天冲是牛市信号」—— 股评家",
                "⚔️ 剑光过处，股价暴涨！",
            ],
            "down": [
                "🌙 {nickname} 月牙天冲失手！股市受伤！",
                "⚔️ 一刀两断！股价也断了！",
                "🌙 月光之力失控！股市暴跌！",
                "⚔️ {nickname} 的剑气误伤了股市！",
                "🌙 「月牙天冲是熊市信号」—— 股评家",
                "⚔️ 剑光过处，股价跳水！",
            ],
        }
    }

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

        # 负数牛牛的特殊文案
        is_negative = user_length < 0
        negative_flavor_texts = [
            "🕳️ 从深渊中汲取力量！",
            "⚫ 负能量爆发！",
            "🌑 黑暗面的力量觉醒！",
            "💀 以诅咒之力发动攻击！",
            "👻 怨念化作了刀刃！",
            "🦇 从地狱深处发出的一击！",
            "⬛ 负值也是一种力量！",
            "🔮 逆转的牛牛，逆转的命运！",
        ]

        if target_shielded:
            messages = [
                "🌙 ══ 月牙天冲 ══ 🌙",
                f"⚔️ {ctx.nickname} 对 {target_name} 发动了月牙天冲！",
            ]
            if is_negative:
                messages.append(random.choice(negative_flavor_texts))
            messages.extend([
                f"💥 伤害：{format_length(damage)}（{percent_display}）",
                "",
                f"🛡️ {target_name} 的护盾抵挡了攻击！（剩余{target_shield_charges - 1}次）",
                f"📉 {ctx.nickname}: {format_length(user_length)}→{format_length(user_length - damage)}",
                "",
            ])
            if is_negative:
                messages.append("💀 自损八百！负数牛牛越陷越深...")
            else:
                messages.append("💀 自损八百！")
            messages.append("═══════════════════")
            ctx.messages.extend(messages)
        else:
            messages = [
                "🌙 ══ 月牙天冲 ══ 🌙",
                f"⚔️ {ctx.nickname} 对 {target_name} 发动了月牙天冲！",
            ]
            if is_negative:
                messages.append(random.choice(negative_flavor_texts))
            messages.extend([
                f"💥 伤害：{format_length(damage)}（{percent_display}）",
                "",
                f"📉 {target_name}: {format_length(target_length)}→{format_length(target_length - damage)}",
                f"📉 {ctx.nickname}: {format_length(user_length)}→{format_length(user_length - damage)}",
                "",
            ])
            if is_negative:
                messages.append("💀 同归于尽！以己之负，伤彼之正！")
            else:
                messages.append("💀 同归于尽！")
            messages.append("═══════════════════")
            ctx.messages.extend(messages)

        return ctx


# =============================================================================
# 牛牛大自爆 Effect
# =============================================================================

class DazibaoEffect(ItemEffect):
    """牛牛大自爆 - Self Destruct: go to zero, distribute damage to top 5"""
    name = "牛牛大自爆"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 股市配置 - 大自爆是大型全局事件
    stock_config = {
        "volatility": (0.08, 0.25),
        "templates": {
            "up": [
                "💥 {nickname} 自爆！但股市反而涨了？",
                "💣 爆炸带来了新生！股价暴涨！",
                "💥 {nickname} 用自爆创造了牛市！",
                "💣 「毁灭就是新生」—— 股评家",
                "💥 自爆清除了市场负能量！涨！",
            ],
            "down": [
                "💥 {nickname} 自爆！股市跟着炸了！",
                "💣 爆炸摧毁了市场信心！暴跌！",
                "💥 {nickname} 用自爆毁灭了股市！",
                "💣 「自爆就是灾难」—— 股评家",
                "💥 自爆恐慌蔓延！股价跳水！",
            ],
        }
    }

    # 负数自爆因祸得福文案
    NEGATIVE_SELF_DESTRUCT_TEXTS = [
        "🎭 等等...负数自爆会归零？？因祸得福！",
        "🤡 本想同归于尽，结果自己反而得救了！",
        "🌀 炸弹把负能量炸没了！",
        "😂 自爆失败...不对，是成功？？",
        "🎪 负数牛牛：「自爆？谢谢，我正需要归零！」",
        "🃏 命运的玩笑：想死却重生了！",
        "✨ 爆炸净化了负能量！",
        "🦠 负数太臭，爆炸后反而清新了！",
        "🎰 史上最幸运的自爆！",
        "💫 「系统：检测到负数自爆，自动修正为归零」",
    ]

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

        # 负数牛牛自爆 - 因祸得福归零！（不造成伤害）
        if user_length < 0:
            ctx.length_change = -user_length  # 归零
            ctx.hardness_change = -(user_hardness - 1)  # 硬度归1
            ctx.extra['dazibao'] = {'victims': []}  # 无受害者
            ctx.messages.extend([
                "💥 ══ 牛牛大自爆 ══ 💥",
                random.choice(self.NEGATIVE_SELF_DESTRUCT_TEXTS),
                f"🎊 {ctx.nickname} 从 {user_length}cm 归零了！",
                f"📊 长度：{user_length}cm → 0cm",
                f"📊 硬度：{user_hardness} → 1",
                "🍀 因祸得福！但由于没有正数长度，没有对别人造成伤害！",
                "═══════════════════"
            ])
            return ctx

        # 零长度或硬度为1不能自爆
        if user_length == 0 or user_hardness <= 1:
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
# 牛牛反弹 Effect
# =============================================================================

class FantanEffect(ItemEffect):
    """牛牛反弹 - Reflect: reflect damage back to attacker"""
    name = "牛牛反弹"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 股市配置
    stock_config = {
        "volatility": (0.02, 0.06),
        "templates": {
            "up": [
                "🔄 反弹护盾激活！股市被反弹的气势感染 {change}",
                "🛡️ {nickname} 开启反弹模式，股市跟着弹了 {change}",
            ],
            "down": [
                "🔄 反弹护盾就位，但股市反向波动 {change}",
                "🛡️ {nickname} 准备反弹，股市却先跌为敬 {change}",
            ]
        }
    }

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import FantanConfig

        # 增加反弹次数
        current_charges = ctx.user_data.get('reflect_charges', 0)
        new_charges = current_charges + 1

        ctx.extra['add_reflect_charges'] = 1

        ctx.messages.extend([
            "🔄 ══ 牛牛反弹 ══ 🔄",
            f"✨ {ctx.nickname} 获得了反弹能力！",
            f"🎯 下次受到>={FantanConfig.DAMAGE_THRESHOLD}cm长度伤害时，反弹给攻击者！",
            "⚠️ 无法反弹夺牛魔的伤害",
            f"📊 当前反弹次数：{new_charges}",
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

    # 股市配置 - 工具类道具，微波动+平淡文案
    stock_config = {
        "volatility": (0.001, 0.005),
        "templates": {
            "plain": [
                "🛡️ {nickname} 买了保险，股市反应平淡 {change}",
                "🛡️ 保险生效，股市打了个哈欠 {change}",
                "🛡️ {nickname} 给牛牛上了保险，股市：哦 {change}",
            ]
        }
    }

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

    # 股市配置 - 盾牌是中等影响道具（献祭50%换保护）
    stock_config = {
        "volatility": (0.02, 0.06),
        "templates": {
            "up": [
                "🛡️ {nickname} 献祭换盾牌！市场认可这波操作！",
                "🛡️ 防御姿态！股市：稳住！",
                "🛡️ {nickname} 开启护盾模式，股价跟着稳！",
                "🛡️ 牛牛有了保护，股民也安心了！",
            ],
            "down": [
                "🛡️ {nickname} 献祭太多了！股市心疼！",
                "🛡️ 防御代价太高！股价跟着跌！",
                "🛡️ {nickname} 割肉买盾，股市：这操作亏了！",
                "🛡️ 盾牌到手，但股价没了！",
            ],
        }
    }

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

        # 动态价格 = 长度的绝对值 * 0.1
        dynamic_price = int(abs(current_length) * 0.1)
        ctx.extra['dynamic_price'] = dynamic_price

        # 检查金币是否足够（由商店传入）
        user_coins = ctx.extra.get('user_coins', 0)
        if user_coins < dynamic_price:
            shortfall = dynamic_price - user_coins
            ctx.messages.extend([
                "❌ ══ 绝对值！ ══ ❌",
                "💰 金币不足，无法购买",
                f"📋 需要: {dynamic_price} 金币",
                f"📊 你有: {user_coins} 金币",
                f"⚠️ 还差: {shortfall} 金币",
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
# 牛牛寄生 Effect
# =============================================================================
class NiuniuJishengEffect(ItemEffect):
    """牛牛寄生 - Parasite: plant a parasite on a random host"""
    name = "牛牛寄生"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 股市配置 - 寄生是中等影响道具
    stock_config = {
        "volatility": (0.02, 0.06),
        "templates": {
            "up": [
                "🦠 {nickname} 种下寄生虫！股市：这波血赚！",
                "🦠 寄生成功！被动收入让股民羡慕！",
                "🦠 {nickname} 开启躺赚模式，股价跟着涨！",
                "🦠 「寄生就是生产力」—— 股评家",
            ],
            "down": [
                "🦠 {nickname} 种寄生虫...股市：恶心！",
                "🦠 寄生行为引发市场反感！",
                "🦠 {nickname} 的寄生计划被股市唾弃！",
                "🦠 「寄生虫是市场毒瘤」—— 股评家",
            ],
        }
    }

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import NiuniuJishengConfig

        group_data = ctx.extra.get('group_data', {})
        user_id = ctx.user_id
        nickname = ctx.nickname

        # 获取指定的目标
        host_id = ctx.extra.get('target_id')
        if not host_id:
            ctx.messages.extend([
                "❌ ══ 牛牛寄生 ══ ❌",
                "⚠️ 未指定寄生目标！",
                "💡 格式：牛牛购买 18 @目标",
                "═══════════════════"
            ])
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 检查目标是否存在且已注册
        host_data = group_data.get(host_id)
        if not host_data or not isinstance(host_data, dict) or 'length' not in host_data:
            ctx.messages.extend([
                "❌ ══ 牛牛寄生 ══ ❌",
                "⚠️ 目标用户未注册牛牛！",
                "═══════════════════"
            ])
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        host_name = host_data.get('nickname', host_id)

        # 检查宿主是否已有寄生牛牛
        old_parasite = host_data.get('parasite')
        override_msg = None
        if old_parasite:
            old_beneficiary_name = old_parasite.get('beneficiary_name', '某人')
            override_msg = random.choice(NiuniuJishengConfig.OVERRIDE_TEXTS).format(
                old_beneficiary_name=old_beneficiary_name,
                host_name=host_name
            )

        # 设置新的寄生信息（存储到ctx.extra，让shop处理）
        ctx.extra['parasite'] = {
            'host_id': host_id,
            'host_name': host_name,
            'beneficiary_id': user_id,
            'beneficiary_name': nickname
        }

        # 生成消息
        parasite_text = random.choice(NiuniuJishengConfig.PARASITE_TEXTS).format(
            host_name=host_name
        )

        ctx.messages.extend([
            "🦠 ══ 牛牛寄生 ══ 🦠",
            f"✨ {parasite_text}",
        ])

        if override_msg:
            ctx.messages.append(f"⚔️ {override_msg}")

        ctx.messages.append("═══════════════════")

        return ctx


class QuniuyaoEffect(ItemEffect):
    """驱牛药 - Cure: remove parasite from self"""
    name = "驱牛药"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 股市配置 - 工具类道具，微波动+平淡文案
    stock_config = {
        "volatility": (0.001, 0.005),
        "templates": {
            "plain": [
                "💊 {nickname} 用了驱牛药，股市反应平淡 {change}",
                "💊 驱牛药生效，股市打了个哈欠 {change}",
                "💊 {nickname} 清除了寄生虫，股市：哦 {change}",
            ]
        }
    }

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import NiuniuJishengConfig

        # 检查自己是否有寄生牛牛
        parasite = ctx.user_data.get('parasite')

        if not parasite:
            ctx.messages.extend([
                "❌ ══ 驱牛药 ══ ❌",
                random.choice(NiuniuJishengConfig.NO_PARASITE_TEXTS),
                "═══════════════════"
            ])
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        beneficiary_name = parasite.get('beneficiary_name', '某人')

        # 标记需要清除寄生
        ctx.extra['cure_parasite'] = True

        cure_text = random.choice(NiuniuJishengConfig.CURE_TEXTS)

        ctx.messages.extend([
            "💊 ══ 驱牛药 ══ 💊",
            f"✨ {cure_text}",
            f"🔓 {beneficiary_name} 的寄生牛牛被清除了！",
            "═══════════════════"
        ])

        return ctx


# =============================================================================
# 牛牛均富/负卡 Effect
# =============================================================================

class JunfukaEffect(ItemEffect):
    """牛牛均富/负卡 - Communism Card: all players' lengths become the average"""
    name = "牛牛均富/负卡"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    # 股市配置 - 均富卡是超大型全局事件
    stock_config = {
        "volatility": (0.10, 0.30),
        "templates": {
            "up": [
                "☭ 共产主义万岁！股市全员红！",
                "⚖️ {nickname} 发动均富！牛市普照！",
                "🔴 财富重新分配，股价暴涨！",
                "☭ 「均富卡是股市的春天」—— 股评家",
                "⚖️ 大佬血亏散户笑，股价跟着往上跳！",
                "🔴 {nickname} 用均富卡创造了股市奇迹！",
                "☭ 均贫富，股市欢呼！",
                "⚖️ 这一刻，股市属于人民！",
            ],
            "down": [
                "☭ 共产主义...翻车了！股市全员绿！",
                "⚖️ {nickname} 发动均富失败！熊市降临！",
                "🔴 财富动荡！股价暴跌！",
                "☭ 「均富卡是股市的噩梦」—— 股评家",
                "⚖️ 均富均成了均穷，股价跟着往下冲！",
                "🔴 {nickname} 用均富卡毁灭了股市！",
                "☭ 均贫富？均贫苦！股市哭晕！",
                "⚖️ 这一刻，股市属于空头！",
            ],
        }
    }

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import JunfukaConfig

        # 需要从 extra 获取群组数据
        group_data = ctx.extra.get('group_data', {})
        if not group_data:
            ctx.messages.append("❌ 无法获取群组数据")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 过滤有效用户（有长度数据的）
        all_valid_users = [(uid, data) for uid, data in group_data.items()
                          if isinstance(data, dict) and 'length' in data]

        if len(all_valid_users) < JunfukaConfig.MIN_PLAYERS:
            ctx.messages.append(f"❌ 群里牛牛不足{JunfukaConfig.MIN_PLAYERS}人，无法发动均富！")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

        # 随机漏掉0-10%的人（向下取整）
        escape_rate = random.uniform(0, 0.10)
        escape_count = int(len(all_valid_users) * escape_rate)

        escaped_users = []
        valid_users = all_valid_users[:]

        if escape_count > 0:
            # 随机选择漏网之鱼
            escaped_indices = random.sample(range(len(all_valid_users)), escape_count)
            escaped_users = [all_valid_users[i] for i in escaped_indices]
            valid_users = [u for i, u in enumerate(all_valid_users) if i not in escaped_indices]

        # 计算平均长度和平均硬度（只计算参与均富的人）
        total_length = sum(data.get('length', 0) for _, data in valid_users)
        total_hardness = sum(data.get('hardness', 1) for _, data in valid_users)
        avg_length = int(total_length / len(valid_users))
        avg_hardness = max(1, int(total_hardness / len(valid_users)))  # 硬度最低为1

        # 记录变化（只有参与均富的人）
        changes = []
        for uid, data in valid_users:
            old_length = data.get('length', 0)
            old_hardness = data.get('hardness', 1)
            length_diff = avg_length - old_length
            hardness_diff = avg_hardness - old_hardness
            # 综合变化：长度变化 + 硬度变化*10（硬度权重更高）
            total_diff = length_diff + hardness_diff * 10
            nickname = data.get('nickname', uid)
            changes.append({
                'uid': uid,
                'nickname': nickname,
                'old_length': old_length,
                'old_hardness': old_hardness,
                'new_length': avg_length,
                'new_hardness': avg_hardness,
                'length_diff': length_diff,
                'hardness_diff': hardness_diff,
                'total_diff': total_diff
            })

        # 按综合变化量排序（亏最多的在前，赚最多的在后）
        changes.sort(key=lambda x: x['total_diff'])

        # 存储变更信息，由 shop 统一处理
        ctx.extra['junfuka'] = {
            'avg_length': avg_length,
            'avg_hardness': avg_hardness,
            'changes': changes
        }

        # 构建消息
        ctx.messages.extend(JunfukaConfig.OPENING_TEXTS)
        ctx.messages.append(f"📊 群平均长度：{format_length(avg_length)} | 平均硬度：{avg_hardness}")
        ctx.messages.append(f"👥 参与人数：{len(valid_users)}人")
        ctx.messages.append("")

        # 显示漏网之鱼
        if escaped_users:
            ctx.messages.append("🐂 漏网之牛（意外错过均富）：")
            for uid, data in escaped_users:
                nickname = data.get('nickname', uid)
                length = data.get('length', 0)
                hardness = data.get('hardness', 1)
                ctx.messages.append(f"  🍀 {nickname}: {format_length(length)} 💪{hardness} (保持不变)")
            ctx.messages.append("")

        # 显示变化（最多显示10人，优先显示变化最大的）
        losers = [c for c in changes if c['total_diff'] < 0][:5]
        winners = [c for c in changes if c['total_diff'] > 0][-5:]

        if losers:
            ctx.messages.append("📉 大佬们哭晕了：")
            for c in losers:
                length_str = f"{format_length(c['old_length'])}→{format_length(c['new_length'])}"
                hardness_str = f"{c['old_hardness']}→{c['new_hardness']}硬"
                diff_parts = []
                if c['length_diff'] != 0:
                    diff_parts.append(f"{format_length_change(c['length_diff'])}")
                if c['hardness_diff'] != 0:
                    diff_parts.append(f"{c['hardness_diff']:+}硬")
                diff_str = " ".join(diff_parts) if diff_parts else "无变化"
                ctx.messages.append(f"  😭 {c['nickname']}: {length_str} {hardness_str} ({diff_str})")

        if winners:
            ctx.messages.append("📈 小弟们狂喜：")
            for c in reversed(winners):
                length_str = f"{format_length(c['old_length'])}→{format_length(c['new_length'])}"
                hardness_str = f"{c['old_hardness']}→{c['new_hardness']}硬"
                diff_parts = []
                if c['length_diff'] != 0:
                    diff_parts.append(f"{format_length_change(c['length_diff'])}")
                if c['hardness_diff'] != 0:
                    diff_parts.append(f"{c['hardness_diff']:+}硬")
                diff_str = " ".join(diff_parts) if diff_parts else "无变化"
                ctx.messages.append(f"  🎉 {c['nickname']}: {length_str} {hardness_str} ({diff_str})")

        ctx.messages.append("")
        ctx.messages.extend(JunfukaConfig.ENDING_TEXTS)

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
    manager.register(FantanEffect())
    manager.register(ShangbaoxianEffect())
    manager.register(NiuniuDunpaiEffect())
    manager.register(QiongniuYishengEffect())
    manager.register(JueduizhiEffect())
    manager.register(NiuniuJishengEffect())
    manager.register(QuniuyaoEffect())
    manager.register(JunfukaEffect())

    return manager
