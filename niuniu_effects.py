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
    """夺牛魔蝌蚪罐头 - Steal/clear length before compare"""
    name = "夺牛魔蝌蚪罐头"
    triggers = [EffectTrigger.BEFORE_COMPARE]
    consume_on_use = True

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        effect_chance = random.random()

        if effect_chance < 0.5:  # 50% steal all
            # 检查目标的盾牌减伤（每层护盾抵挡10%，最高100%）
            target_shield_charges = 0
            if ctx.target_data:
                target_shield_charges = ctx.target_data.get('shield_charges', 0)

            damage_reduction = min(target_shield_charges * 0.1, 1.0)  # 最高100%减伤

            if damage_reduction >= 1.0:
                # 完全抵挡
                ctx.extra['duoxinmo_result'] = 'blocked'
                ctx.messages.extend([
                    "⚔️ 【牛牛对决结果】 ⚔️",
                    f"🛡️ {ctx.nickname} 使用夺牛魔蝌蚪罐头！",
                    f"💫 但 {ctx.target_nickname} 的牛牛盾牌（{target_shield_charges}层）完全抵挡了攻击！",
                ])
                ctx.intercept = True
            else:
                # 计算实际偷取量
                base_steal = ctx.target_length
                actual_steal = int(base_steal * (1 - damage_reduction))

                ctx.extra['duoxinmo_result'] = 'steal'
                ctx.extra['stolen_length'] = actual_steal
                ctx.length_change = actual_steal
                ctx.target_length_change = -actual_steal

                if damage_reduction > 0:
                    blocked_amount = base_steal - actual_steal
                    ctx.messages.extend([
                        "⚔️ 【牛牛对决结果】 ⚔️",
                        f"🎉 {ctx.nickname} 获得了夺牛魔技能！",
                        f"🛡️ {ctx.target_nickname} 的牛牛盾牌（{target_shield_charges}层）抵挡了{int(damage_reduction*100)}%伤害！",
                        f"💥 实际夺取 {actual_steal}cm（抵挡了{blocked_amount}cm）",
                    ])
                else:
                    ctx.messages.extend([
                        "⚔️ 【牛牛对决结果】 ⚔️",
                        f"🎉 {ctx.nickname} 获得了夺牛魔技能，夺取了 {ctx.target_nickname} 的全部长度！",
                    ])
                ctx.intercept = True

        elif effect_chance < 0.7:  # 20% self clear
            ctx.extra['duoxinmo_result'] = 'self_clear'
            ctx.length_change = -ctx.user_length  # Go to 0
            ctx.messages.extend([
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"💔 {ctx.nickname} 使用夺牛魔蝌蚪罐头，牛牛变成了夺牛魔！！！",
            ])
            ctx.intercept = True

        else:  # 30% no effect
            ctx.extra['duoxinmo_result'] = 'no_effect'
            ctx.messages.extend([
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"⚠️ {ctx.nickname} 使用夺牛魔蝌蚪罐头，但是罐头好像坏掉了...",
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
    """巴黎牛家 - +3 hardness"""
    name = "巴黎牛家"
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
        from datetime import datetime
        import pytz
        from niuniu_config import TIMEZONE

        # 检查每日冷却（每天0点重置）
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_midnight_ts = today_midnight.timestamp()

        last_use = ctx.user_data.get('last_jiefu_time', 0)
        if last_use >= today_midnight_ts:  # 今天已经用过
            # 计算到明天0点的时间
            tomorrow_midnight = today_midnight_ts + 86400
            remaining_secs = int(tomorrow_midnight - now.timestamp())
            remaining_hours = remaining_secs // 3600
            remaining_mins = (remaining_secs % 3600) // 60
            ctx.messages.append(f"⏰ 劫富济贫每天只能用一次！明天0点后再来（还需 {remaining_hours}小时{remaining_mins}分钟）")
            ctx.extra['refund'] = True
            ctx.intercept = True
            return ctx

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
        # 如果首富有护盾，不扣他的长度（steal_amount设为0），但穷人照样拿
        ctx.extra['robin_hood'] = {
            'richest_id': richest_id,
            'richest_name': richest_name,
            'steal_amount': 0 if richest_shielded else steal_amount,  # 有护盾则不扣
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

        if richest_shielded:
            # 首富有护盾的消息
            ctx.messages.extend([
                "🦸 ═══ 劫富济贫 ═══ 🦸",
                f"🎯 目标锁定：{richest_name}（{richest_length}cm）",
                f"🛡️ 但是...{richest_name} 有牛牛盾牌护盾！",
                f"💫 护盾抵挡了抢劫，但天降横财！",
                f"🎁 凭空产生 {steal_amount}cm 分给穷人：",
                *beneficiary_texts,
                f"📊 {richest_name} 护盾剩余：{richest_shield_charges - 1}次",
                "══════════════════"
            ])
        else:
            # 正常抢劫消息
            ctx.messages.extend([
                "🦸 ═══ 劫富济贫 ═══ 🦸",
                f"🎯 目标锁定：{richest_name}（{richest_length}cm）",
                f"💸 抢走了 {steal_amount}cm！",
                "📦 分发给最穷的群友：",
                *beneficiary_texts,
                "══════════════════"
            ])

        # 标记需要记录使用时间
        ctx.extra['record_jiefu_time'] = True

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
        ctx.extra['chaos_storm'] = {'changes': [], 'coin_changes': [], 'swaps': []}
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
            is_negative = event_id in ['length_down', 'hardness_down', 'coin_lose',
                                        'length_percent_down', 'halve', 'give_to_random']

            # 负面事件检查护盾
            if is_negative and shield_charges > 0:
                event_text = f"🛡️ {nickname}: 护盾抵挡！（剩余{shield_charges - 1}次）"
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

class BaoxianxiangEffect(ItemEffect):
    """牛牛盾牌 - Safe Box: grants 3 shield charges to protect against negative effects"""
    name = "牛牛盾牌"
    triggers = [EffectTrigger.ON_PURCHASE]
    consume_on_use = False  # Active item, no inventory

    def on_trigger(self, trigger: EffectTrigger, ctx: EffectContext) -> EffectContext:
        from niuniu_config import BaoxianxiangConfig

        # 增加护盾次数
        current_charges = ctx.user_data.get('shield_charges', 0)
        new_charges = current_charges + BaoxianxiangConfig.SHIELD_CHARGES

        ctx.extra['add_shield_charges'] = BaoxianxiangConfig.SHIELD_CHARGES

        ctx.messages.append("🛡️ ══ 牛牛盾牌 ══ 🛡️")
        ctx.messages.append(f"✨ {ctx.nickname} 购买了牛牛盾牌！")
        ctx.messages.append(f"🔒 获得 {BaoxianxiangConfig.SHIELD_CHARGES} 次护盾防护")
        if current_charges > 0:
            ctx.messages.append(f"📊 当前护盾：{current_charges} → {new_charges}")
        else:
            ctx.messages.append(f"📊 当前护盾：{new_charges}")
        ctx.messages.append("")
        ctx.messages.append("💡 护盾可抵挡劫富济贫/混沌风暴/月牙天冲/大自爆的负面效果")
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

    # Register active item effects
    manager.register(BalishijiaEffect())
    manager.register(BashideBanEffect())
    manager.register(BumiezhiwoEffect())
    manager.register(AmstlangEffect())
    manager.register(DutuyingbiEffect())
    manager.register(JiefuJipinEffect())
    manager.register(HundunFengbaoEffect())
    manager.register(YueyaTianchongEffect())
    manager.register(DazibaoEffect())
    manager.register(HuoshuiDongyinEffect())
    manager.register(ShangbaoxianEffect())
    manager.register(BaoxianxiangEffect())
    manager.register(QiongniuYishengEffect())
    manager.register(JueduizhiEffect())

    return manager
