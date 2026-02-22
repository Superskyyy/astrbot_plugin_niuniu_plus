import random
import yaml
import os
import re
import time
import json
import sys
import asyncio
from astrbot.api.all import *

# 热重载支持：导入前先清理模块缓存
_plugin_modules = ['niuniu_config', 'niuniu_shop', 'niuniu_games', 'niuniu_effects', 'niuniu_stock']
for _mod in _plugin_modules:
    if _mod in sys.modules:
        del sys.modules[_mod]

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from niuniu_shop import NiuniuShop
from niuniu_games import NiuniuGames
from niuniu_effects import create_effect_manager, EffectTrigger, EffectContext
from niuniu_stock import NiuniuStock, stock_hook
from niuniu_config import (
    PLUGIN_DIR, NIUNIU_LENGTHS_FILE, GAME_TEXTS_FILE, LAST_ACTION_FILE,
    DajiaoEvents, DajiaoCombo, DailyBonus, TimePeriod, TIMEZONE,
    CompareStreak, CompareBet, CompareAudience, RobberyConfig,
    format_length as config_format_length, format_length_change
)
import pytz
from datetime import datetime

# 确保目录存在
os.makedirs(PLUGIN_DIR, exist_ok=True)

@register("niuniu_plugin", "Superskyyy", "牛牛插件，包含注册牛牛、打胶、我的牛牛、比划比划、牛牛排行等功能", "4.29.5")
class NiuniuPlugin(Star):
    # 冷却时间常量（秒）
    COOLDOWN_10_MIN = 600    # 10分钟
    COOLDOWN_30_MIN = 1800   # 30分钟
    COMPARE_COOLDOWN = 600   # 比划冷却
    INVITE_LIMIT = 3         # 邀请次数限制

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.niuniu_texts = self._load_niuniu_texts()
        self.last_actions = self._load_last_actions()
        self.admins = self._load_admins()  # 加载管理员列表
        self.shop = NiuniuShop(self)  # 实例化商城模块
        self.games = NiuniuGames(self)  # 实例化游戏模块
        self.effects = create_effect_manager()  # 实例化效果管理器
        self.effects.set_shop(self)  # 设置主插件引用（用于访问get_user_data等方法）

        # 性能优化：命令级数据缓存
        self._data_cache = None  # 当前命令的数据缓存
        self._cache_dirty = False  # 缓存是否有修改
        self._cache_lock = asyncio.Lock()  # 缓存锁，防止并发问题

    async def terminate(self):
        """插件卸载时清理模块缓存，确保热重载生效"""
        # 清理本插件相关的模块缓存
        modules_to_remove = [
            'niuniu_config',
            'niuniu_shop',
            'niuniu_games',
            'niuniu_effects',
            'niuniu_stock',
        ]
        for module_name in modules_to_remove:
            if module_name in sys.modules:
                del sys.modules[module_name]

    # region 数据文件操作
    def _create_niuniu_lengths_file(self):
        """创建数据文件"""
        try:
            with open(NIUNIU_LENGTHS_FILE, 'w', encoding='utf-8') as f:
                yaml.dump({}, f)
        except Exception as e:
            self.context.logger.error(f"创建文件失败: {str(e)}")

    def _load_niuniu_lengths(self):
        """从文件加载牛牛数据"""
        if not os.path.exists(NIUNIU_LENGTHS_FILE):
            self._create_niuniu_lengths_file()
        
        try:
            with open(NIUNIU_LENGTHS_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            # 数据结构验证
            for group_id in list(data.keys()):
                group_data = data[group_id]
                if not isinstance(group_data, dict):
                    data[group_id] = {'plugin_enabled': False}
                elif 'plugin_enabled' not in group_data:
                    group_data['plugin_enabled'] = False
                for user_id in list(group_data.keys()):
                    user_data = group_data[user_id]
                    if isinstance(user_data, dict):
                        user_data.setdefault('coins', 0)
                        user_data.setdefault('items', {})
            return data
        except Exception as e:
            self.context.logger.error(f"加载数据失败: {str(e)}")
            return {}

    def _save_niuniu_lengths(self, data):
        """保存数据到文件"""
        try:
            with open(NIUNIU_LENGTHS_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True)
        except Exception as e:
            self.context.logger.error(f"保存失败: {str(e)}")

    def _load_niuniu_texts(self):
        """从 YAML 文件加载游戏文本"""
        try:
            with open(GAME_TEXTS_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.context.logger.error(f"加载文本失败: {str(e)}")
            raise RuntimeError(f"无法加载游戏文本配置: {GAME_TEXTS_FILE}")

    def _load_last_actions(self):
        """加载冷却数据"""
        try:
            with open(LAST_ACTION_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _save_last_actions(self, data):
        """保存冷却数据到文件"""
        try:
            with open(LAST_ACTION_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True)
        except Exception as e:
            self.context.logger.error(f"保存冷却数据失败: {str(e)}")

    def _load_admins(self):
        """加载管理员列表"""
        try:
            with open(os.path.join('data', 'cmd_config.json'), 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
                return config.get('admins_id', [])
        except Exception as e:
            self.context.logger.error(f"加载管理员列表失败: {str(e)}")
            return []

    def is_admin(self, user_id):
        """检查用户是否为管理员"""
        return str(user_id) in self.admins
    # endregion

    # region 性能优化：数据缓存
    async def _begin_data_cache_async(self):
        """开启数据缓存（命令开始时调用，使用锁保护避免并发冲突）"""
        async with self._cache_lock:
            if self._data_cache is None:
                self._data_cache = self._load_niuniu_lengths()
                self._cache_dirty = False

    async def _end_data_cache_async(self):
        """结束数据缓存并保存（命令结束时调用，使用锁保护）"""
        async with self._cache_lock:
            if self._data_cache is not None and self._cache_dirty:
                self._save_niuniu_lengths(self._data_cache)
            self._data_cache = None
            self._cache_dirty = False

    def _get_data(self):
        """获取数据（优先使用缓存）"""
        if self._data_cache is not None:
            return self._data_cache
        return self._load_niuniu_lengths()

    def _save_data(self, data):
        """保存数据（如果有缓存则标记为dirty，否则立即保存）"""
        if self._data_cache is not None:
            self._data_cache = data
            self._cache_dirty = True
        else:
            self._save_niuniu_lengths(data)
    # endregion

    # region 数据访问接口
    def get_group_data(self, group_id):
        """从文件/缓存获取群组数据"""
        group_id = str(group_id)
        data = self._get_data()
        if group_id not in data:
            data[group_id] = {'plugin_enabled': False}  # 默认关闭插件
            self._save_data(data)
        return data[group_id]

    def get_user_data(self, group_id, user_id):
        """从文件/缓存获取用户数据"""
        group_id = str(group_id)
        user_id = str(user_id)
        data = self._get_data()
        group_data = data.get(group_id, {'plugin_enabled': False})
        return group_data.get(user_id)

    def update_user_data(self, group_id, user_id, updates):
        """更新用户数据并保存到文件/缓存"""
        group_id = str(group_id)
        user_id = str(user_id)
        data = self._get_data()
        group_data = data.setdefault(group_id, {'plugin_enabled': False})
        user_data = group_data.setdefault(user_id, {
            'nickname': '',
            'length': 0,
            'hardness': 1,
            'coins': 0,
            'items': {}
        })
        user_data.update(updates)
        self._save_data(data)
        return user_data

    def consume_item(self, group_id: str, user_id: str, item_name: str) -> bool:
        """消耗道具（直接操作缓存数据，避免缓存不一致）"""
        group_id = str(group_id)
        user_id = str(user_id)
        data = self._get_data()
        group_data = data.get(group_id, {})
        user_data = group_data.get(user_id, {})
        items = user_data.get('items', {})

        if items.get(item_name, 0) > 0:
            items[item_name] -= 1
            if items[item_name] == 0:
                del items[item_name]
            self._save_data(data)
            return True
        return False

    def modify_coins_cached(self, group_id: str, user_id: str, delta: float):
        """修改金币（通过缓存，避免缓存不一致）"""
        group_id = str(group_id)
        user_id = str(user_id)
        data = self._get_data()
        group_data = data.get(group_id, {})
        user_data = group_data.get(user_id, {})
        user_data['coins'] = round(user_data.get('coins', 0) + delta)
        self._save_data(data)

    def update_group_data(self, group_id, updates):
        """更新群组数据并保存到文件/缓存"""
        group_id = str(group_id)
        data = self._get_data()
        group_data = data.setdefault(group_id, {'plugin_enabled': False})
        group_data.update(updates)
        self._save_data(data)
        return group_data

    def update_last_actions(self, data):
        """更新冷却数据并保存到文件"""
        self._save_last_actions(data)
    # endregion

    # region 工具方法
    def format_length(self, length):
        """格式化长度显示"""
        return config_format_length(length)

    def format_coins(self, coins):
        """格式化金币显示（k、m、b缩写）"""
        is_negative = coins < 0
        coins = abs(coins)

        if coins < 1000:
            result = str(int(coins))
        elif coins < 1000000:
            result = f"{coins/1000:.1f}k"
        elif coins < 1000000000:
            result = f"{coins/1000000:.1f}m"
        else:
            result = f"{coins/1000000000:.1f}b"

        return f"-{result}" if is_negative else result

    def check_insurance_claim(self, group_id: str, user_id: str, nickname: str,
                               length_loss: int = 0, hardness_loss: int = 0,
                               group_data: dict = None) -> dict:
        """
        通用保险理赔检查方法

        Args:
            group_id: 群组ID
            user_id: 用户ID
            nickname: 用户昵称
            length_loss: 长度损失（正数）
            hardness_loss: 硬度损失（正数）
            group_data: 可选的群组数据字典，如果提供则直接修改它（用于批量操作）

        Returns:
            {
                'triggered': bool,      # 是否触发理赔
                'payout': int,          # 赔付金额
                'charges_remaining': int,  # 剩余保险次数
                'message': str          # 理赔消息
            }
        """
        from niuniu_config import InsuranceConfig

        # 获取用户数据
        if group_data is not None:
            user_data = group_data.get(user_id, {})
            if not isinstance(user_data, dict):
                return {'triggered': False}
        else:
            user_data = self.get_user_data(group_id, user_id)

        # 检查是否有保险（订阅或旧道具）
        has_insurance_sub = self.effects.has_insurance_subscription(group_id, user_id)
        old_insurance_charges = user_data.get('insurance_charges', 0)

        if not has_insurance_sub and old_insurance_charges <= 0:
            return {'triggered': False}

        # 检查是否达到阈值
        length_triggered = length_loss >= InsuranceConfig.LENGTH_THRESHOLD
        hardness_triggered = hardness_loss >= InsuranceConfig.HARDNESS_THRESHOLD

        if not length_triggered and not hardness_triggered:
            return {'triggered': False}

        # 确定理赔金额和剩余次数
        if has_insurance_sub:
            payout = self.effects.get_insurance_payout(group_id, user_id)
            charges_remaining = "订阅中"
        else:
            # 使用旧道具次数
            payout = 200
            new_charges = old_insurance_charges - 1
            charges_remaining = new_charges

            # 更新旧道具次数
            if group_data is not None:
                group_data[user_id]['insurance_charges'] = new_charges
            else:
                self.update_user_data(group_id, user_id, {'insurance_charges': new_charges})

        # 更新金币
        if group_data is not None:
            current_coins = group_data[user_id].get('coins', 0)
            group_data[user_id]['coins'] = round(current_coins + payout)
        else:
            self.modify_coins_cached(group_id, user_id, payout)

        # 构建消息
        damage_parts = []
        if length_loss > 0:
            damage_parts.append(f"{length_loss}cm")
        if hardness_loss > 0:
            damage_parts.append(f"{hardness_loss}硬度")
        damage_str = "、".join(damage_parts) if damage_parts else "未知"

        return {
            'triggered': True,
            'payout': payout,
            'charges_remaining': charges_remaining,
            'message': f"📋 {nickname} 保险理赔！损失{damage_str}，赔付{payout:,}金币（{charges_remaining}）"
        }

    def _check_and_trigger_parasite(self, group_id: str, host_id: str, gain: float,
                                     processed_ids: set = None) -> list:
        """
        检查并触发寄生牛牛抽取效果（支持链式反应）

        Args:
            group_id: 群组ID
            host_id: 宿主ID（获得增益的人）
            gain: 增益数值
            processed_ids: 已处理的用户ID集合（防止无限循环）

        Returns:
            消息列表
        """
        from niuniu_config import NiuniuJishengConfig

        if processed_ids is None:
            processed_ids = set()

        # 防止无限循环
        if host_id in processed_ids:
            return []
        processed_ids.add(host_id)

        messages = []
        host_data = self.get_user_data(group_id, host_id)

        if not host_data:
            return messages

        # 检查宿主是否有寄生牛牛
        parasite = host_data.get('parasite')
        if not parasite:
            return messages

        beneficiary_id = parasite.get('beneficiary_id')
        beneficiary_name = parasite.get('beneficiary_name', '某人')

        if not beneficiary_id:
            return messages

        # 获取受益者（寄生者）数据
        beneficiary_data = self.get_user_data(group_id, beneficiary_id)
        if not beneficiary_data:
            return messages

        # 检查增益是否达到阈值（使用寄生者的长度，而不是宿主）
        beneficiary_length = beneficiary_data.get('length', 0)
        threshold = abs(beneficiary_length) * NiuniuJishengConfig.TRIGGER_THRESHOLD

        if gain <= threshold:
            return messages

        # 触发抽取！
        host_name = host_data.get('nickname', host_id)
        host_length = host_data.get('length', 0)

        # 计算抽取量（从增长中抽取25%）
        drain_length = int(gain * NiuniuJishengConfig.DRAIN_LENGTH_PERCENT)
        if drain_length < 1:
            drain_length = 1

        host_hardness = host_data.get('hardness', 1)
        drain_hardness = int(host_hardness * NiuniuJishengConfig.DRAIN_HARDNESS_PERCENT)
        # 硬度边界情况：如果硬度为1，抽取到0；如果硬度为0，不抽取
        if host_hardness == 1:
            drain_hardness = 1
        elif host_hardness == 0:
            drain_hardness = 0
        elif drain_hardness < 1:
            drain_hardness = 1

        # 扣除宿主的长度和硬度
        new_host_length = host_length - drain_length
        new_host_hardness = max(0, host_hardness - drain_hardness)
        self.update_user_data(group_id, host_id, {
            'length': new_host_length,
            'hardness': new_host_hardness
        })

        # 给受益者加长度和硬度
        new_beneficiary_length = beneficiary_data.get('length', 0) + drain_length
        new_beneficiary_hardness = min(100, beneficiary_data.get('hardness', 1) + drain_hardness)
        self.update_user_data(group_id, beneficiary_id, {
            'length': new_beneficiary_length,
            'hardness': new_beneficiary_hardness
        })

        # 生成消息
        drain_text = random.choice(NiuniuJishengConfig.DRAIN_TEXTS).format(
            host_name=host_name,
            gain=gain,
            beneficiary_name=beneficiary_name,
            drain_length=drain_length,
            drain_hardness=drain_hardness
        )
        messages.append(drain_text)

        # 链式反应：如果受益者也有寄生牛牛，检查是否触发
        if drain_length > 0:
            chain_messages = self._check_and_trigger_parasite(
                group_id, beneficiary_id, drain_length, processed_ids
            )
            messages.extend(chain_messages)

        return messages

    def _trigger_huagu_debuff(self, group_id: str, user_id: str) -> list:
        """
        触发「含笑五步癫」效果（在每次命令执行后调用）

        每次触发扣除快照值的19.6%长度、硬度、总资产（金币+股票），共5次（98%总量）
        含笑五步癫效果无法被任何东西抵挡

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            消息列表
        """
        from niuniu_config import HanxiaoWubudianConfig
        from niuniu_stock import NiuniuStock

        messages = []
        user_data = self.get_user_data(group_id, user_id)

        if not user_data:
            return messages

        # 检查是否有含笑五步癫
        huagu_debuff = user_data.get('huagu_debuff')
        if not huagu_debuff or not huagu_debuff.get('active'):
            return messages

        remaining = huagu_debuff.get('remaining_times', 0)
        if remaining <= 0:
            # 清除debuff
            self.update_user_data(group_id, user_id, {'huagu_debuff': None})
            return messages

        # 获取快照数据
        snapshot_length = huagu_debuff.get('snapshot_length', 0)
        snapshot_hardness = huagu_debuff.get('snapshot_hardness', 0)
        snapshot_asset = huagu_debuff.get('snapshot_asset', 0)

        # 计算伤害（快照值的19.6%）
        length_damage = int(snapshot_length * HanxiaoWubudianConfig.DEBUFF_DAMAGE_PERCENT)
        hardness_damage = int(snapshot_hardness * HanxiaoWubudianConfig.DEBUFF_DAMAGE_PERCENT)
        asset_damage = int(snapshot_asset * HanxiaoWubudianConfig.DEBUFF_DAMAGE_PERCENT)

        nickname = user_data.get('nickname', user_id)

        # 获取当前状态
        current_length = user_data.get('length', 0)
        current_hardness = user_data.get('hardness', 1)
        current_coins = self.shop.get_user_coins(group_id, user_id)

        # 获取股票信息
        stock = NiuniuStock.get()
        user_shares = stock.get_holdings(group_id, user_id)
        stock_price = stock.get_price(group_id)
        current_stock_value = user_shares * stock_price

        # 长度：直接减去（可以变负）
        new_length = current_length - length_damage
        # 硬度：最低为0
        new_hardness = max(0, current_hardness - hardness_damage)

        # 资产扣除：先扣金币，不够再卖股票
        remaining_asset_damage = asset_damage
        actual_coins_deducted = min(current_coins, remaining_asset_damage)
        new_coins = current_coins - actual_coins_deducted
        remaining_asset_damage -= actual_coins_deducted

        shares_sold = 0
        if remaining_asset_damage > 0 and user_shares > 0:
            # 需要强制卖出股票补足（含笑五步癫强制清算）
            shares_needed = min(user_shares, int(remaining_asset_damage / stock_price) + 1)
            while shares_needed * stock_price < remaining_asset_damage and shares_needed < user_shares:
                shares_needed += 1
            shares_sold = shares_needed

            # 使用 NiuniuStock 的强制清算方法（记录为损失，无收益）
            stock.force_liquidate(group_id, user_id, shares_sold)

        actual_asset_deducted = actual_coins_deducted + shares_sold * stock_price

        # 判断是否是第一步（转移给攻击方）
        step = HanxiaoWubudianConfig.DEBUFF_TIMES - remaining + 1
        is_first_step = (step == 1)
        applied_by = huagu_debuff.get('applied_by')

        # 第一步：将损失转移给攻击方
        if is_first_step and applied_by and applied_by != user_id:
            attacker_data = self.get_user_data(group_id, applied_by)
            if attacker_data:
                # 转移长度和硬度
                new_atk_length = attacker_data.get('length', 0) + length_damage
                new_atk_hardness = min(100, attacker_data.get('hardness', 1) + hardness_damage)
                self.update_user_data(group_id, applied_by, {
                    'length': new_atk_length,
                    'hardness': new_atk_hardness,
                })
                # 转移资产（金币）
                if asset_damage > 0:
                    atk_coins = self.shop.get_user_coins(group_id, applied_by)
                    self.shop.update_user_coins(group_id, applied_by, atk_coins + asset_damage)

                atk_nickname = attacker_data.get('nickname', applied_by)
                messages.append(
                    f"💰 【含笑五步癫·转移】第1步损失转移给 {atk_nickname}："
                    f"+{length_damage}cm / +{hardness_damage}硬 / +{asset_damage:,}资产"
                )

        # 更新剩余次数
        new_remaining = remaining - 1
        if new_remaining <= 0:
            # 最后一次，清除debuff
            self.update_user_data(group_id, user_id, {
                'length': new_length,
                'hardness': new_hardness,
                'huagu_debuff': None
            })
            self.shop.update_user_coins(group_id, user_id, new_coins)

            # 生成消息（最后一步）
            asset_loss_str = f"{actual_coins_deducted}币"
            if shares_sold > 0:
                asset_loss_str += f"+{shares_sold}股"
            messages.append(random.choice(HanxiaoWubudianConfig.DEBUFF_TRIGGER_TEXTS).format(
                nickname=nickname,
                length_loss=length_damage,
                hardness_loss=hardness_damage,
                asset_loss=asset_loss_str,
                remaining=0,
                step=step
            ))
            messages.append(random.choice(HanxiaoWubudianConfig.DEBUFF_END_TEXTS).format(nickname=nickname))
        else:
            # 还有剩余次数
            huagu_debuff['remaining_times'] = new_remaining
            self.update_user_data(group_id, user_id, {
                'length': new_length,
                'hardness': new_hardness,
                'huagu_debuff': huagu_debuff
            })
            self.shop.update_user_coins(group_id, user_id, new_coins)

            # 生成消息
            asset_loss_str = f"{actual_coins_deducted}币"
            if shares_sold > 0:
                asset_loss_str += f"+{shares_sold}股"
            messages.append(random.choice(HanxiaoWubudianConfig.DEBUFF_TRIGGER_TEXTS).format(
                nickname=nickname,
                length_loss=length_damage,
                hardness_loss=hardness_damage,
                asset_loss=asset_loss_str,
                remaining=new_remaining,
                step=step
            ))

        return messages

    def _process_delegated_chaos_storm(self, ctx, group_id):
        """处理夺牛魔委托的混沌风暴效果"""
        chaos_storm = ctx.extra['chaos_storm']
        niuniu_data = self._load_niuniu_lengths()
        group_data = niuniu_data.setdefault(group_id, {})

        # 应用所有人的长度和硬度变化
        for change in chaos_storm.get('changes', []):
            uid = change['user_id']
            if uid not in group_data:
                continue
            length_change = change.get('change', 0)
            hardness_change = change.get('hardness_change', 0)

            if length_change != 0:
                group_data[uid]['length'] = group_data[uid].get('length', 0) + length_change
            if hardness_change != 0:
                old_hardness = group_data[uid].get('hardness', 1)
                group_data[uid]['hardness'] = max(1, min(100, old_hardness + hardness_change))

        # 处理交换事件
        for swap in chaos_storm.get('swaps', []):
            u1_id = swap['user1_id']
            u2_id = swap['user2_id']
            if u1_id in group_data and u2_id in group_data:
                u1_old = swap['user1_old']
                u2_old = swap['user2_old']
                group_data[u1_id]['length'] = u2_old
                group_data[u2_id]['length'] = u1_old

        # 处理金币变化
        for coin_change in chaos_storm.get('coin_changes', []):
            uid = coin_change['user_id']
            amount = coin_change['amount']
            self.games.update_user_coins(group_id, uid, amount)

        # 处理护盾消耗
        for shield_info in ctx.extra.get('consume_shields', []):
            target_id = shield_info['user_id']
            if target_id in group_data:
                current = group_data[target_id].get('shield_charges', 0)
                group_data[target_id]['shield_charges'] = max(0, current - shield_info['amount'])

        # 处理全属性交换
        for full_swap in chaos_storm.get('full_swaps', []):
            u1_id = full_swap['user1_id']
            u2_id = full_swap['user2_id']
            if u1_id in group_data and u2_id in group_data:
                # 交换长度
                group_data[u1_id]['length'] = full_swap['user2_old_len']
                group_data[u2_id]['length'] = full_swap['user1_old_len']
                # 交换硬度
                group_data[u1_id]['hardness'] = full_swap['user2_old_hard']
                group_data[u2_id]['hardness'] = full_swap['user1_old_hard']

        # 处理冷却重置
        for uid in chaos_storm.get('cooldown_resets', []):
            if uid in group_data:
                group_data[uid]['last_dajiao_time'] = 0

        # 处理幸运祝福
        for uid in chaos_storm.get('lucky_buffs', []):
            if uid in group_data:
                group_data[uid]['next_dajiao_guaranteed'] = True

        # 处理量子纠缠
        for entangle in chaos_storm.get('quantum_entangles', []):
            u1_id = entangle['user1_id']
            u2_id = entangle['user2_id']
            avg_len = entangle['avg']
            if u1_id in group_data:
                group_data[u1_id]['length'] = avg_len
            if u2_id in group_data:
                group_data[u2_id]['length'] = avg_len

        # 处理寄生牛牛（使用单一寄生结构）
        for parasite_data in chaos_storm.get('parasites', []):
            host_id = parasite_data['host_id']
            if host_id in group_data:
                # 单一寄生：新寄生覆盖旧寄生
                group_data[host_id]['parasite'] = {
                    'beneficiary_id': parasite_data['beneficiary_id'],
                    'beneficiary_name': parasite_data.get('beneficiary_name', '某人')
                }

        # 处理全局事件
        for global_event in chaos_storm.get('global_events', []):
            event_type = global_event['type']
            selected_ids = [c['user_id'] for c in chaos_storm.get('changes', [])]
            for swap in chaos_storm.get('swaps', []):
                if swap['user1_id'] not in selected_ids:
                    selected_ids.append(swap['user1_id'])
                if swap['user2_id'] not in selected_ids:
                    selected_ids.append(swap['user2_id'])
            selected_ids = list(set(uid for uid in selected_ids if uid in group_data))

            if event_type == 'doomsday' and len(selected_ids) >= 2:
                lengths = [(uid, group_data[uid].get('length', 0)) for uid in selected_ids]
                lengths.sort(key=lambda x: x[1])
                shortest_uid = lengths[0][0]
                longest_uid = lengths[-1][0]
                old_longest = lengths[-1][1]
                group_data[shortest_uid]['length'] = 0
                group_data[longest_uid]['length'] = old_longest * 2
                ctx.messages.append(f"⚖️ 末日审判：{group_data[shortest_uid].get('nickname', shortest_uid)} 归零！{group_data[longest_uid].get('nickname', longest_uid)} 翻倍！")

            elif event_type == 'roulette' and len(selected_ids) >= 2:
                lengths = [group_data[uid].get('length', 0) for uid in selected_ids]
                random.shuffle(lengths)
                for i, uid in enumerate(selected_ids):
                    group_data[uid]['length'] = lengths[i]
                ctx.messages.append(f"🎰 轮盘重置：{len(selected_ids)}人的长度已重新洗牌！")

            elif event_type == 'reverse_talent' and len(selected_ids) >= 2:
                lengths = [(uid, group_data[uid].get('length', 0)) for uid in selected_ids]
                lengths.sort(key=lambda x: x[1])
                shortest_uid, shortest_len = lengths[0]
                longest_uid, longest_len = lengths[-1]
                group_data[shortest_uid]['length'] = longest_len
                group_data[longest_uid]['length'] = shortest_len
                ctx.messages.append(f"🔄 反向天赋：{group_data[shortest_uid].get('nickname', shortest_uid)} 和 {group_data[longest_uid].get('nickname', longest_uid)} 长度互换！")

            elif event_type == 'lottery_bomb':
                if global_event.get('jackpot'):
                    for uid in selected_ids:
                        old_len = group_data[uid].get('length', 0)
                        group_data[uid]['length'] = old_len * 2
                    ctx.messages.append(f"🎊 团灭彩票大奖！{len(selected_ids)}人长度全部翻倍！")
                else:
                    for uid in selected_ids:
                        old_len = group_data[uid].get('length', 0)
                        old_hard = group_data[uid].get('hardness', 1)
                        len_loss = int(abs(old_len) * 0.5)
                        hard_loss = int(old_hard * 0.5)
                        if old_len > 0:
                            group_data[uid]['length'] = old_len - len_loss
                        else:
                            group_data[uid]['length'] = old_len + len_loss
                        group_data[uid]['hardness'] = max(1, old_hard - hard_loss)
                    ctx.messages.append(f"💣 团灭彩票未中...{len(selected_ids)}人各-50%长度和硬度！")

        self._save_data(niuniu_data)

    def _process_delegated_dazibao(self, ctx, group_id, user_id):
        """处理夺牛魔委托的大自爆效果"""
        dazibao = ctx.extra['dazibao']
        niuniu_data = self._load_niuniu_lengths()
        group_data = niuniu_data.setdefault(group_id, {})

        # 自己归零
        if user_id in group_data:
            group_data[user_id]['length'] = 0
            group_data[user_id]['hardness'] = 1

        # 处理护盾消耗
        for shield_info in ctx.extra.get('consume_shields', []):
            target_id = shield_info['user_id']
            if target_id in group_data:
                current = group_data[target_id].get('shield_charges', 0)
                group_data[target_id]['shield_charges'] = max(0, current - shield_info['amount'])

        # 扣除受害者的长度和硬度
        for victim in dazibao.get('victims', []):
            uid = victim['user_id']
            if uid not in group_data or victim.get('shielded', False):
                continue
            length_damage = victim['length_damage']
            hardness_damage = victim['hardness_damage']
            group_data[uid]['length'] = group_data[uid].get('length', 0) - length_damage
            group_data[uid]['hardness'] = max(1, group_data[uid].get('hardness', 1) - hardness_damage)

        self._save_data(niuniu_data)

    def check_cooldown(self, last_time, cooldown):
        """检查冷却时间"""
        current = time.time()
        elapsed = current - last_time
        remaining = cooldown - elapsed
        return remaining > 0, remaining

    def parse_at_target(self, event):
        """解析@目标"""
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
        return None

    def parse_target(self, event):
        """解析@目标或用户名"""
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
        msg = event.message_str.strip()
        if msg.startswith("比划比划"):
            target_name = msg[len("比划比划"):].strip()
            if target_name:
                group_id = str(event.message_obj.group_id)
                group_data = self.get_group_data(group_id)
                for user_id, user_data in group_data.items():
                    if isinstance(user_data, dict): 
                        nickname = user_data.get('nickname', '')
                        if re.search(re.escape(target_name), nickname, re.IGNORECASE):
                            return user_id
        return None
    def run_command_middleware(self, group_id: str, user_id: str) -> list:
        """
        命令中间件统一入口

        在每个牛牛命令执行前调用，用于执行全局检查和清理逻辑

        当前注册的中间件：
        1. subscription_middleware - 订阅系统中间件（清理过期订阅、重置每日计数）

        未来可扩展：
        - daily_reset_middleware - 每日重置中间件（签到、任务等）
        - event_middleware - 事件中间件（全局事件触发）
        - statistics_middleware - 统计中间件（数据收集）

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            错误消息列表（如果有），空列表表示全部成功
        """
        errors = []

        try:
            # 执行订阅中间件
            error = self.effects.subscription_middleware(group_id, user_id)
            if error:
                errors.append(error)

            # 未来可以在这里添加更多中间件
            # error = self.daily_reset_middleware(group_id, user_id)
            # if error:
            #     errors.append(error)

        except Exception as e:
            error_msg = f"⚠️ 命令中间件异常: {str(e)}"
            print(f"[CommandMiddleware Error] {error_msg}")
            import traceback
            traceback.print_exc()
            errors.append(error_msg)

        return errors
    # endregion

    # region 事件处理
    niuniu_commands = ["牛牛菜单", "牛牛帮助", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛", "比划比划", "牛牛排行"]

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent, *args, **kwargs):
        """群聊消息处理器"""
        group_id = str(event.message_obj.group_id)
        group_data = self.get_group_data(group_id)

        msg = event.message_str.strip()
        if msg.startswith("牛牛开"):
            async for result in self._toggle_plugin(event, True):
                yield result
            return
        elif msg.startswith("牛牛关"):
            async for result in self._toggle_plugin(event, False):
                yield result
            return
        elif msg.startswith("牛牛菜单") or msg.startswith("牛牛帮助"):
            # 执行命令中间件
            user_id = str(event.get_sender_id())
            errors = self.run_command_middleware(group_id, user_id)
            for error in errors:
                yield event.plain_result(error)

            async for result in self._show_menu(event):
                yield result
            return
        # 如果插件未启用，忽略其他所有消息
        if not group_data.get('plugin_enabled', False):
            return

        # 统一检查是否在开冲
        user_id = str(event.get_sender_id())
        user_data = self.get_user_data(group_id, user_id)

        is_rushing = user_data.get('is_rushing', False) if user_data else False

        # 处理其他命令（开冲现在是非阻塞的，可以边冲边做其他事）
        if msg.startswith("开冲"):
            # 执行命令中间件
            errors = self.run_command_middleware(group_id, user_id)
            for error in errors:
                yield event.plain_result(error)

            if is_rushing:
                yield event.plain_result("❌ 你已经在开冲了，无需重复操作")
                return
            async for result in self.games.start_rush(event):
                yield result
            # 含笑五步癫触发
            huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
            for msg_text in huagu_msgs:
                yield event.plain_result(msg_text)
        elif msg.startswith("停止开冲"):
            # 执行命令中间件
            errors = self.run_command_middleware(group_id, user_id)
            for error in errors:
                yield event.plain_result(error)

            if not is_rushing:
                yield event.plain_result("❌ 你当前并未在开冲，无需停止")
                return
            async for result in self.games.stop_rush(event):
                yield result
            # 含笑五步癫触发
            huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
            for msg_text in huagu_msgs:
                yield event.plain_result(msg_text)
        elif msg.startswith("飞飞机"):
            # 执行命令中间件
            errors = self.run_command_middleware(group_id, user_id)
            for error in errors:
                yield event.plain_result(error)

            async for result in self.games.fly_plane(event):
                yield result
            # 含笑五步癫触发
            huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
            for msg_text in huagu_msgs:
                yield event.plain_result(msg_text)
        else:
            # 处理其他命令
            handler_map = {
                "注册牛牛": self._register,
                "打胶": self._dajiao,
                "我的牛牛": self._show_status,
                "比划比划": self._compare,
                "牛牛拜年": self._bainian,
                "牛牛抢劫": self._robbery,
                "牛牛打劫": self._robbery,
                "牛牛排行": self._show_ranking,
                "牛牛道具商城": self.shop.show_shop,  # 别名
                "牛牛道具商店": self.shop.show_shop,  # 别名
                "牛牛商城": self.shop.show_shop,
                "牛牛购买": self.shop.handle_buy,
                "牛牛背包": self.shop.show_items,
                "牛牛订阅商城": self._subscription_shop,  # 别名
                "牛牛订阅商店": self._subscription_shop,
                "牛牛取消订阅": self._unsubscribe,
                "牛牛订阅": self._subscribe,
                "牛牛股市 重置": self._niuniu_stock_reset,  # 放在 "牛牛股市" 前面
                "牛牛股市": self._niuniu_stock,
                "重置所有牛牛": self._reset_all_niuniu,
                "牛牛红包": self._niuniu_hongbao,
                "牛牛救市": self._niuniu_jiushi
            }

            for cmd, handler in handler_map.items():
                if msg.startswith(cmd):
                    # 执行命令中间件
                    errors = self.run_command_middleware(group_id, user_id)
                    for error in errors:
                        yield event.plain_result(error)

                    async for result in handler(event):
                        yield result
                    return
    @event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent, *args, **kwargs):
        """私聊消息处理器"""
        msg = event.message_str.strip()
        niuniu_commands = [
            "牛牛菜单", "牛牛帮助", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛",
            "比划比划", "牛牛排行", "牛牛商城", "牛牛购买", "牛牛背包",
            "牛牛股市", "开冲", "停止开冲", "飞飞机", "牛牛拜年"
        ]
        
        if any(msg.startswith(cmd) for cmd in niuniu_commands):
            yield event.plain_result("不许一个人偷偷玩牛牛")
        else:
            return
    async def _toggle_plugin(self, event, enable):
        """开关插件"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        self.update_group_data(group_id, {'plugin_enabled': enable})
        text_key = 'enable' if enable else 'disable'
        yield event.plain_result(self.niuniu_texts['system'][text_key])

    async def _reset_all_niuniu(self, event):
        """重置所有牛牛 - 仅管理员可用，支持分类重置"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        # 解析参数
        msg_parts = event.message_str.split()
        reset_type = msg_parts[1] if len(msg_parts) > 1 else None

        # 有效的重置类型
        valid_types = ['金币', '长度', '硬度', '股市', '全部']

        if reset_type and reset_type not in valid_types:
            yield event.plain_result(
                "❌ 无效的重置类型\n"
                "📌 用法: 重置所有牛牛 <类型>\n"
                "   • 金币 - 所有牛友金币归零\n"
                "   • 长度 - 所有牛牛长度随机重置\n"
                "   • 硬度 - 所有牛牛硬度归一\n"
                "   • 股市 - 清空所有牛友股票持仓\n"
                "   • 全部 - 重置以上所有数据"
            )
            return

        if not reset_type:
            yield event.plain_result(
                "📌 重置所有牛牛 <类型>\n"
                "   • 金币 - 所有牛友金币归零\n"
                "   • 长度 - 所有牛牛长度随机重置\n"
                "   • 硬度 - 所有牛牛硬度归一\n"
                "   • 股市 - 清空所有牛友股票持仓\n"
                "   • 全部 - 重置以上所有数据"
            )
            return

        # 加载数据
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {})

        # 统计重置人数
        reset_count = 0

        # 根据类型执行重置
        if reset_type == '股市':
            # 重置股市持仓
            stock = NiuniuStock.get()
            stock_data = stock._get_group_data(group_id)
            reset_count = len(stock_data.get("holdings", {}))
            stock_data["holdings"] = {}
            stock_data["user_stats"] = {}
            stock._save_data()
            yield event.plain_result(
                f"📊 股市持仓已清空！\n"
                f"👥 清仓牛友: {reset_count}位\n"
                f"💰 股价保持不变，所有牛友从零开始炒股~"
            )
            return

        # 处理牛牛数据重置
        for uid in list(group_data.keys()):
            if uid.startswith('_') or uid == 'plugin_enabled':
                continue
            if isinstance(group_data[uid], dict) and 'length' in group_data[uid]:
                if reset_type == '金币':
                    group_data[uid]['coins'] = 0
                elif reset_type == '长度':
                    group_data[uid]['length'] = random.randint(3, 10)
                elif reset_type == '硬度':
                    group_data[uid]['hardness'] = 1
                elif reset_type == '全部':
                    # 保留昵称，重置其他数据
                    nickname = group_data[uid].get('nickname', f'用户{uid}')
                    group_data[uid] = {
                        'nickname': nickname,
                        'length': random.randint(3, 10),
                        'hardness': 1,
                        'coins': 0,
                        'items': {}
                    }
                reset_count += 1

        data[group_id] = group_data
        self._save_niuniu_lengths(data)

        # 如果是全部重置，同时清空股市
        if reset_type == '全部':
            stock = NiuniuStock.get()
            stock_data = stock._get_group_data(group_id)
            stock_data["holdings"] = {}
            stock_data["user_stats"] = {}
            stock._save_data()

        # 生成结果消息
        type_names = {
            '金币': '金币已归零',
            '长度': '长度已随机重置',
            '硬度': '硬度已归一',
            '全部': '全部数据已重置（含股市持仓）'
        }
        yield event.plain_result(f"✅ 已重置本群 {reset_count} 个牛牛！\n📋 {type_names[reset_type]}")

    async def _subscription_shop(self, event):
        """牛牛订阅商店 - 显示所有订阅服务"""
        yield event.plain_result(self.effects.format_subscription_shop())

    async def _subscribe(self, event):
        """牛牛订阅 - 订阅服务"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        msg = event.message_str.strip()

        # 检查是否注册牛牛
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 你大概是没有牛牛的！请先使用「注册牛牛」")
            return

        # 解析参数: 牛牛订阅 <编号> [天数]
        parts = msg.split()
        if len(parts) < 2:
            yield event.plain_result("❌ 用法: 牛牛订阅 <编号> [天数]\n💡 输入「牛牛订阅商店」查看可用服务")
            return

        try:
            sub_index = int(parts[1]) - 1  # 编号从1开始
            days = int(parts[2]) if len(parts) > 2 else 1
        except ValueError:
            yield event.plain_result("❌ 编号和天数必须是数字")
            return

        if days <= 0:
            yield event.plain_result("❌ 天数必须大于0")
            return

        # 限制最大天数（避免整数溢出和不合理订阅）
        if days > 365:
            yield event.plain_result("❌ 单次订阅最多365天")
            return

        # 获取订阅名称
        from niuniu_effects import SUBSCRIPTION_CONFIGS
        sub_names = list(SUBSCRIPTION_CONFIGS.keys())
        if sub_index < 0 or sub_index >= len(sub_names):
            yield event.plain_result(f"❌ 无效的编号，请输入 1-{len(sub_names)}")
            return

        sub_name = sub_names[sub_index]
        config = SUBSCRIPTION_CONFIGS[sub_name]
        base_price = config["price_per_day"]

        # 获取用户当前金币
        current_coins = user_data.get('coins', 0)

        # 计算动态总价（循环计算，考虑金币递减）
        from niuniu_effects import _calculate_total_subscription_cost
        total_price, remaining_coins, can_afford = _calculate_total_subscription_cost(base_price, current_coins, days)

        # 检查金币是否足够
        if not can_afford:
            yield event.plain_result(f"❌ 金币不足！需要至少 {total_price:,}+ 金币，你只有 {current_coins:,} 金币")
            return

        try:
            # 扣除金币
            user_data['coins'] = remaining_coins
            self.update_user_data(group_id, user_id, user_data)

            # 保存订阅（传入原始金币数用于计算显示）
            success, message, actual_cost = self.effects.subscribe(group_id, user_id, sub_name, days, current_coins)

            if not success:
                # 订阅失败，退款
                user_data['coins'] = current_coins
                self.update_user_data(group_id, user_id, user_data)
                yield event.plain_result(message)
                return

            yield event.plain_result(message)
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_type = type(e).__name__

            # 发生异常，退款
            user_data['coins'] = current_coins
            self.update_user_data(group_id, user_id, user_data)

            # 打印到控制台
            print(f"[Subscribe] 订阅失败: {error_type}: {error_msg}")
            traceback.print_exc()

            # 返回到群里
            yield event.plain_result(
                f"❌ 订阅失败！已退款\n"
                f"错误类型: {error_type}\n"
                f"错误信息: {error_msg}\n"
                f"请截图反馈给管理员"
            )
            return

    async def _unsubscribe(self, event):
        """牛牛取消订阅 - 取消订阅服务"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        msg = event.message_str.strip()

        # 解析参数: 牛牛取消订阅 <编号>
        parts = msg.split()
        if len(parts) < 2:
            yield event.plain_result("❌ 用法: 牛牛取消订阅 <编号>\n💡 输入「牛牛背包」查看当前订阅")
            return

        try:
            sub_index = int(parts[1]) - 1
        except ValueError:
            yield event.plain_result("❌ 编号必须是数字")
            return

        # 获取订阅名称
        from niuniu_effects import SUBSCRIPTION_CONFIGS
        sub_names = list(SUBSCRIPTION_CONFIGS.keys())
        if sub_index < 0 or sub_index >= len(sub_names):
            yield event.plain_result(f"❌ 无效的编号，请输入 1-{len(sub_names)}")
            return

        sub_name = sub_names[sub_index]
        success, message = self.effects.unsubscribe(group_id, user_id, sub_name)

        yield event.plain_result(message)

    async def _niuniu_hongbao(self, event):
        """牛牛红包 - 给指定用户或所有人发放/扣除属性，仅管理员可用"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        msg = event.message_str.strip()
        msg_parts = msg.split()

        # 检查是否是"所有人"模式
        is_all = "所有人" in msg or "全体" in msg

        # 解析参数（长度、硬度、金币）
        numbers = []
        for part in msg_parts:
            try:
                # 支持负数和小数
                num = float(part) if '.' in part else int(part.lstrip('-') if part.lstrip('-').isdigit() else None)
                if part.startswith('-'):
                    num = -abs(num)
                numbers.append(int(num))
            except:
                pass

        if len(numbers) < 3:
            yield event.plain_result(
                "🧧 牛牛红包用法：\n"
                "━━━ 给指定牛友 ━━━\n"
                "牛牛红包 @用户 <长度> <硬度> <金币>\n"
                "例：牛牛红包 @xxx 10 5 100\n"
                "例：牛牛红包 @xxx 0 0 -50\n"
                "━━━ 给所有牛友 ━━━\n"
                "牛牛红包 所有人 <长度> <硬度> <金币>\n"
                "例：牛牛红包 所有人 1 1 100\n"
                "例：牛牛红包 所有人 -5 0 -50"
            )
            return

        length_change = numbers[0]
        hardness_change = numbers[1]
        coins_change = numbers[2]

        # 加载数据
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {})

        if is_all:
            # 给所有人发红包
            affect_count = 0
            for uid in list(group_data.keys()):
                if uid.startswith('_') or uid == 'plugin_enabled':
                    continue
                if isinstance(group_data[uid], dict) and 'length' in group_data[uid]:
                    group_data[uid]['length'] = group_data[uid].get('length', 0) + length_change
                    group_data[uid]['hardness'] = max(0, group_data[uid].get('hardness', 1) + hardness_change)
                    group_data[uid]['coins'] = round(group_data[uid].get('coins', 0) + coins_change)
                    affect_count += 1

            data[group_id] = group_data
            self._save_niuniu_lengths(data)

            # 构建结果消息
            result_parts = [f"🧧 红包已发放给全体 {affect_count} 位牛友！"]
            if length_change != 0:
                sign = "+" if length_change > 0 else ""
                result_parts.append(f"📏 长度：每人 {sign}{length_change}cm")
            if hardness_change != 0:
                sign = "+" if hardness_change > 0 else ""
                result_parts.append(f"💪 硬度：每人 {sign}{hardness_change}")
            if coins_change != 0:
                sign = "+" if coins_change > 0 else ""
                result_parts.append(f"💰 金币：每人 {sign}{coins_change}")

            if length_change == 0 and hardness_change == 0 and coins_change == 0:
                result_parts.append("（无变化）")

            yield event.plain_result("\n".join(result_parts))
        else:
            # 给指定用户发红包
            target_id = self.parse_target(event)
            if not target_id:
                yield event.plain_result(
                    "🧧 牛牛红包用法：\n"
                    "━━━ 给指定牛友 ━━━\n"
                    "牛牛红包 @用户 <长度> <硬度> <金币>\n"
                    "例：牛牛红包 @xxx 10 5 100\n"
                    "━━━ 给所有牛友 ━━━\n"
                    "牛牛红包 所有人 <长度> <硬度> <金币>\n"
                    "例：牛牛红包 所有人 1 1 100"
                )
                return

            # 检查目标是否已注册
            target_data = group_data.get(target_id)
            if not target_data or not isinstance(target_data, dict) or 'length' not in target_data:
                yield event.plain_result("❌ 该用户大概是没有牛牛的")
                return

            target_name = target_data.get('nickname', target_id)
            old_length = target_data.get('length', 0)
            old_hardness = target_data.get('hardness', 1)
            old_coins = target_data.get('coins', 0)

            # 应用变化
            new_length = old_length + length_change
            new_hardness = max(0, old_hardness + hardness_change)
            new_coins = round(old_coins + coins_change)

            target_data['length'] = new_length
            target_data['hardness'] = new_hardness
            target_data['coins'] = new_coins

            group_data[target_id] = target_data
            data[group_id] = group_data
            self._save_niuniu_lengths(data)

            # 构建结果消息
            result_parts = [f"🧧 红包已发给 {target_name}："]
            if length_change != 0:
                sign = "+" if length_change > 0 else ""
                result_parts.append(f"📏 长度：{old_length}cm → {new_length}cm ({sign}{length_change})")
            if hardness_change != 0:
                sign = "+" if hardness_change > 0 else ""
                result_parts.append(f"💪 硬度：{old_hardness} → {new_hardness} ({sign}{hardness_change})")
            if coins_change != 0:
                sign = "+" if coins_change > 0 else ""
                result_parts.append(f"💰 金币：{old_coins} → {new_coins} ({sign}{coins_change})")

            if length_change == 0 and hardness_change == 0 and coins_change == 0:
                result_parts.append("（无变化）")

            yield event.plain_result("\n".join(result_parts))

    async def _niuniu_jiushi(self, event):
        """牛牛救市/砸盘 - 系统资金操作股价，仅管理员可用"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        # 解析金额
        msg_parts = event.message_str.split()
        if len(msg_parts) < 2:
            yield event.plain_result(
                "❌ 格式：牛牛救市 <金额>\n"
                "例：牛牛救市 10000 (救市拉升)\n"
                "例：牛牛救市 -10000 (砸盘打压)"
            )
            return

        try:
            amount = float(msg_parts[1])
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")
            return

        if amount == 0:
            yield event.plain_result("❌ 金额不能为0")
            return

        # 执行救市/砸盘
        stock = NiuniuStock.get()
        success, msg = stock.bailout(group_id, amount)

        yield event.plain_result(msg)

    async def _niuniu_stock_reset(self, event):
        """牛牛股市 重置 - 清除所有股市数据，仅管理员可用"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        # 执行重置
        stock = NiuniuStock.get()
        success, msg = stock.reset(group_id)

        yield event.plain_result(msg)

    async def _niuniu_stock(self, event):
        """牛牛股市"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        msg = event.message_str.strip()

        # 检查是否已注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data or 'length' not in user_data:
            yield event.plain_result("❌ 你大概是没有牛牛的，请先注册牛牛！")
            return

        stock = NiuniuStock.get()

        # 解析子命令
        parts = msg.replace("牛牛股市", "").strip().split()

        if not parts:
            # 无参数：显示股市行情
            yield event.plain_result(stock.format_market(group_id))
            return

        subcmd = parts[0]

        if subcmd == "购买":
            # 牛牛股市 购买 <金额|梭哈>
            if len(parts) < 2:
                yield event.plain_result("❌ 格式：牛牛股市 购买 <金额|梭哈>")
                return

            user_coins = user_data.get('coins', 0)

            # 检查是否梭哈
            is_soha = False
            if parts[1] == "梭哈":
                is_soha = True
                coins = user_coins * 0.95
                if coins < 2:  # 考虑3%手续费，至少2金币才有意义
                    yield event.plain_result(f"❌ 金币不足！梭哈至少需要2金币（你只有 {user_coins:.0f} 金币）")
                    return
            else:
                try:
                    coins = float(parts[1])
                except:
                    yield event.plain_result("❌ 请输入有效的金额或「梭哈」")
                    return

                if coins > user_coins:
                    yield event.plain_result(f"❌ 金币不足！你只有 {user_coins:.0f} 金币")
                    return

            success, message, shares = stock.buy(group_id, user_id, coins)
            if success:
                # 扣除金币
                user_data['coins'] = round(user_coins - coins)
                self.update_user_data(group_id, user_id, {'coins': user_data['coins']})
                # 如果是梭哈，添加特殊提示
                if is_soha:
                    message = f"🎰 梭哈模式！投入95%财富\n{message}"
            yield event.plain_result(message)
            # 含笑五步癫触发（买股票也算行动）
            if success:
                huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
                for msg_text in huagu_msgs:
                    yield event.plain_result(msg_text)

        elif subcmd == "出售":
            # 牛牛股市 出售 [数量/全部]
            shares = None
            if len(parts) >= 2:
                if parts[1] == "全部":
                    shares = None  # 全部卖出
                else:
                    try:
                        shares = float(parts[1])
                    except:
                        yield event.plain_result("❌ 请输入有效的数量或「全部」")
                        return

            # 计算群内金币平均值（用于收益税计算）
            niuniu_data = self._load_niuniu_lengths()
            group_niuniu_data = niuniu_data.get(group_id, {})
            all_coins = [data.get('coins', 0) for uid, data in group_niuniu_data.items()
                        if isinstance(data, dict) and 'coins' in data and data.get('coins', 0) > 0]
            avg_coins = sum(all_coins) / len(all_coins) if all_coins else 0

            success, message, coins = stock.sell(group_id, user_id, shares, avg_coins)
            if success:
                # 增加金币（已是税后金额）
                user_coins = user_data.get('coins', 0)
                user_data['coins'] = round(user_coins + coins)  # 取整避免精度问题
                self.update_user_data(group_id, user_id, {'coins': user_data['coins']})
            yield event.plain_result(message)
            # 含笑五步癫触发（卖股票也算行动）
            if success:
                huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
                for msg_text in huagu_msgs:
                    yield event.plain_result(msg_text)

        elif subcmd == "持仓":
            # 牛牛股市 持仓
            yield event.plain_result(stock.format_holdings(group_id, user_id, nickname))

        elif subcmd == "操盘":
            # 牛牛股市 操盘 <金额> — 花自己的钱拉盘/砸盘
            if len(parts) < 2:
                yield event.plain_result(
                    "❌ 格式：牛牛股市 操盘 <金额>\n"
                    "正数拉盘，负数砸盘，花的是你自己的钱！\n"
                    "例：牛牛股市 操盘 5000\n"
                    "例：牛牛股市 操盘 -3000"
                )
                return

            try:
                amount = float(parts[1])
            except ValueError:
                yield event.plain_result("❌ 金额必须是数字")
                return

            if amount == 0:
                yield event.plain_result("❌ 金额不能为0")
                return

            abs_amount = abs(amount)
            user_coins = user_data.get('coins', 0)
            if user_coins < abs_amount:
                yield event.plain_result(f"❌ 金币不足！你只有 {user_coins:.0f} 金币，需要 {abs_amount:.0f} 金币")
                return

            # 扣除金币
            self.update_user_data(group_id, user_id, {'coins': round(user_coins - abs_amount)})

            # 执行操盘（复用bailout逻辑）
            success, msg = stock.bailout(group_id, amount, operator=nickname)
            yield event.plain_result(msg)

            # 含笑五步癫触发
            huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
            for msg_text in huagu_msgs:
                yield event.plain_result(msg_text)

        else:
            yield event.plain_result("❌ 未知命令\n📌 牛牛股市 购买 <金额|梭哈>\n📌 牛牛股市 出售 [数量/全部]\n📌 牛牛股市 持仓\n📌 牛牛股市 操盘 <金额>")

    async def _register(self, event):
        """注册牛牛"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        if self.get_user_data(group_id, user_id):
            text = self.niuniu_texts['register']['already_registered'].format(nickname=nickname)
            yield event.plain_result(text)
            return

        cfg = self.config.get('niuniu_config', {})
        user_data = {
            'nickname': nickname,
            'length': random.randint(cfg.get('min_length', 3), cfg.get('max_length', 10)),
            'hardness': 1,
            'coins': 0,
            'items': {}
        }
        self.update_user_data(group_id, user_id, user_data)

        text = random.choice(self.niuniu_texts['register']['success']).format(
            nickname=nickname,
            length=user_data['length'],
            hardness=user_data['hardness']
        )
        yield event.plain_result(text)

    async def _dajiao(self, event: AstrMessageEvent):
        """打胶功能 - 增强版：包含随机事件、连击系统、每日首次奖励"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            text = self.niuniu_texts['dajiao']['not_registered'].format(nickname=nickname)
            yield event.plain_result(text)
            return

        user_items = self.shop.get_user_items(group_id, user_id)
        last_actions = self._load_last_actions()
        last_time = last_actions.setdefault(group_id, {}).get(user_id, {}).get('dajiao', 0)

        # 获取订阅冷却减少
        cooldown_reduction = self.effects.get_cooldown_reduction(group_id, user_id)
        actual_cooldown = self.COOLDOWN_10_MIN * (1 - cooldown_reduction)

        # 检查是否处于冷却期
        on_cooldown, remaining = self.check_cooldown(last_time, actual_cooldown)

        # 创建效果上下文
        ctx = EffectContext(
            group_id=group_id,
            user_id=user_id,
            nickname=nickname,
            user_data=user_data,
            user_length=user_data['length'],
            user_hardness=user_data['hardness'],
            extra={'on_cooldown': on_cooldown, 'remaining': remaining}
        )

        # 触发 BEFORE_DAJIAO 效果
        ctx = self.effects.trigger(EffectTrigger.BEFORE_DAJIAO, ctx, user_items)

        # 消耗触发的道具
        self.effects.consume_items(group_id, user_id, ctx.items_to_consume)

        # 检查冷却（可能被效果跳过）
        if on_cooldown and not ctx.skip_cooldown:
            mins = int(remaining // 60) + 1
            text = random.choice(self.niuniu_texts['dajiao']['cooldown']).format(
                nickname=nickname, remaining=mins
            )
            yield event.plain_result(text)
            return

        # 计算经过时间
        if ctx.extra.get('force_bonus_window'):
            elapsed = self.COOLDOWN_30_MIN + 1  # 强制进入增益逻辑
        else:
            elapsed = time.time() - last_time

        current_time = time.time()
        result_msgs = []  # 收集所有消息
        old_hardness = user_data['hardness']
        hardness_change = 0
        extra_length = 0
        extra_coins = 0
        time_warp_triggered = False

        # ===== 每日首次奖励检查 =====
        shanghai_tz = pytz.timezone(TIMEZONE)
        today_str = datetime.now(shanghai_tz).strftime("%Y-%m-%d")
        last_dajiao_date = user_data.get('last_dajiao_date', '')
        is_daily_first = (last_dajiao_date != today_str)

        if is_daily_first:
            extra_length += DailyBonus.FIRST_DAJIAO_LENGTH_BONUS
            daily_text = random.choice(self.niuniu_texts['dajiao']['daily_first']).format(
                nickname=nickname, bonus=DailyBonus.FIRST_DAJIAO_LENGTH_BONUS
            )
            result_msgs.append(daily_text)

        # ===== 时段感知系统 =====
        current_hour = datetime.now(shanghai_tz).hour
        current_period = None
        period_config = None

        # 确定当前时段
        for period_key, config in TimePeriod.PERIODS.items():
            start_hour, end_hour = config['hours']
            if start_hour <= current_hour < end_hour:
                current_period = period_key
                period_config = config
                break

        # 时段问候语
        time_texts = self.niuniu_texts.get('dajiao', {}).get('time_period', {})
        if current_period and current_period in time_texts:
            period_texts = time_texts[current_period]
            if 'greeting' in period_texts:
                greeting = random.choice(period_texts['greeting']).format(nickname=nickname)
                result_msgs.append(greeting)

        # 时段加成
        time_success_bonus = period_config.get('success_bonus', 0) if period_config else 0
        time_length_bonus = period_config.get('length_bonus', 0) if period_config else 0

        # 订阅加成
        sub_success_boost = self.effects.get_dajiao_success_boost(group_id, user_id)
        time_success_bonus += sub_success_boost

        if time_length_bonus > 0 and current_period in time_texts:
            period_texts = time_texts[current_period]
            if 'bonus' in period_texts:
                bonus_text = random.choice(period_texts['bonus']).format(bonus=time_length_bonus)
                result_msgs.append(bonus_text)
            extra_length += time_length_bonus

        # 时段惩罚提示
        if time_success_bonus < 0 and current_period in time_texts:
            period_texts = time_texts[current_period]
            if 'penalty' in period_texts:
                penalty_text = random.choice(period_texts['penalty']).format(nickname=nickname)
                result_msgs.append(penalty_text)

        # 深夜/凌晨特殊事件
        special_chance = period_config.get('special_chance', 0) if period_config else 0
        time_special_triggered = False
        if special_chance > 0 and random.random() < special_chance:
            if current_period in time_texts and 'special' in time_texts[current_period]:
                special_bonus = random.randint(2, 5)
                special_text = random.choice(time_texts[current_period]['special']).format(
                    nickname=nickname, bonus=special_bonus
                )
                result_msgs.append(special_text)
                extra_length += special_bonus
                time_special_triggered = True

        # 凌晨警告（小概率）
        if current_period == 'midnight' and random.random() < 0.3:
            if 'warning' in time_texts.get('midnight', {}):
                warning_text = random.choice(time_texts['midnight']['warning']).format(nickname=nickname)
                result_msgs.append(warning_text)

        # ===== 灵感迸发检查（上次触发的buff） =====
        has_inspiration = user_data.get('inspiration_active', False)
        if has_inspiration:
            # 清除灵感状态
            self.update_user_data(group_id, user_id, {'inspiration_active': False})

        # ===== 幸运祝福检查（混沌风暴buff） =====
        has_lucky_buff = user_data.get('next_dajiao_guaranteed', False)
        if has_lucky_buff:
            # 清除幸运祝福状态
            self.update_user_data(group_id, user_id, {'next_dajiao_guaranteed': False})
            result_msgs.append("🍀 幸运祝福生效！")

        # ===== 计算基础变化 =====
        change = 0
        decrease_template = None

        if has_inspiration or has_lucky_buff:
            # 灵感迸发/幸运祝福：必定成功
            change = random.randint(3, 6)
        elif elapsed < self.COOLDOWN_30_MIN:  # 10-30分钟
            rand = random.random()
            # 时段加成影响成功率：基础40%增加 + 时段bonus
            increase_threshold = 0.4 + time_success_bonus
            decrease_threshold = 0.7  # 减少概率不受时段影响
            if rand < increase_threshold:
                change = random.randint(2, 5)
            elif rand < decrease_threshold:
                change = -random.randint(1, 3)
                decrease_template = random.choice(self.niuniu_texts['dajiao']['decrease'])
        else:  # 30分钟后
            rand = random.random()
            # 时段加成影响成功率：基础70%增加 + 时段bonus
            increase_threshold = 0.7 + time_success_bonus
            decrease_threshold = 0.9  # 减少概率不受时段影响
            if rand < increase_threshold:
                change = random.randint(3, 6)
                hardness_change += 1
            elif rand < decrease_threshold:
                change = -random.randint(1, 2)
                decrease_template = random.choice(self.niuniu_texts['dajiao']['decrease_30min'])

        # ===== 随机事件处理 =====
        event_triggered = False

        # 暴击 (3%) - 增长x3
        if not event_triggered and change > 0 and random.random() < DajiaoEvents.CRITICAL_CHANCE:
            change = change * 3
            crit_text = random.choice(self.niuniu_texts['dajiao']['critical']).format(nickname=nickname)
            result_msgs.append(crit_text)
            event_triggered = True

        # 失手 (2%) - 损失x2
        if not event_triggered and change < 0 and random.random() < DajiaoEvents.FUMBLE_CHANCE:
            change = change * 2
            fumble_text = random.choice(self.niuniu_texts['dajiao']['fumble']).format(nickname=nickname)
            result_msgs.append(fumble_text)
            event_triggered = True

        # 硬度觉醒 (5%) - +1~2硬度
        if not event_triggered and random.random() < DajiaoEvents.HARDNESS_AWAKENING_CHANCE:
            bonus = random.randint(DajiaoEvents.HARDNESS_AWAKENING_MIN, DajiaoEvents.HARDNESS_AWAKENING_MAX)
            hardness_change += bonus
            awakening_text = random.choice(self.niuniu_texts['dajiao']['hardness_awakening']).format(
                nickname=nickname, bonus=bonus
            )
            result_msgs.append(awakening_text)
            event_triggered = True

        # 金币掉落 (8%) - 10-30金币
        if not event_triggered and random.random() < DajiaoEvents.COIN_DROP_CHANCE:
            coins = random.randint(DajiaoEvents.COIN_DROP_MIN, DajiaoEvents.COIN_DROP_MAX)
            extra_coins += coins
            coin_text = random.choice(self.niuniu_texts['dajiao']['coin_drop']).format(
                nickname=nickname, coins=coins
            )
            result_msgs.append(coin_text)
            event_triggered = True

        # 时间扭曲 (2%) - 重置冷却
        if not event_triggered and random.random() < DajiaoEvents.TIME_WARP_CHANCE:
            time_warp_triggered = True
            warp_text = random.choice(self.niuniu_texts['dajiao']['time_warp']).format(nickname=nickname)
            result_msgs.append(warp_text)
            event_triggered = True

        # 灵感迸发 (3%) - 下次必成功
        if not event_triggered and random.random() < DajiaoEvents.INSPIRATION_CHANCE:
            self.update_user_data(group_id, user_id, {'inspiration_active': True})
            insp_text = random.choice(self.niuniu_texts['dajiao']['inspiration']).format(nickname=nickname)
            result_msgs.append(insp_text)
            event_triggered = True

        # 观众效应 (5%) - 5分钟内有人打胶则双方+1cm
        if not event_triggered and random.random() < DajiaoEvents.AUDIENCE_EFFECT_CHANCE:
            # 查找最近5分钟内打过胶的其他用户
            group_actions = last_actions.get(group_id, {})
            recent_dajiaoer = None
            for uid, actions in group_actions.items():
                if uid != user_id and isinstance(actions, dict):
                    other_time = actions.get('dajiao', 0)
                    if current_time - other_time < DajiaoEvents.AUDIENCE_EFFECT_WINDOW:
                        other_data = self.get_user_data(group_id, uid)
                        if other_data:
                            recent_dajiaoer = (uid, other_data)
                            break
            if recent_dajiaoer:
                other_uid, other_data = recent_dajiaoer
                # 双方各+1cm
                extra_length += 1
                self.update_user_data(group_id, other_uid, {'length': other_data['length'] + 1})
                audience_text = random.choice(self.niuniu_texts['dajiao']['audience_effect']).format(
                    nickname=nickname, other=other_data['nickname']
                )
                result_msgs.append(audience_text)
                event_triggered = True

        # 神秘力量 (2%) - 随机±5~15cm
        if not event_triggered and random.random() < DajiaoEvents.MYSTERIOUS_FORCE_CHANCE:
            mysterious_change = random.randint(DajiaoEvents.MYSTERIOUS_FORCE_MIN, DajiaoEvents.MYSTERIOUS_FORCE_MAX)
            if random.random() < 0.5:
                mysterious_change = -mysterious_change
            change_str = f"+{mysterious_change}" if mysterious_change > 0 else str(mysterious_change)
            extra_length += mysterious_change
            mysterious_text = random.choice(self.niuniu_texts['dajiao']['mysterious_force']).format(
                nickname=nickname, change=change_str
            )
            result_msgs.append(mysterious_text)
            event_triggered = True

        # ===== 连击系统 =====
        combo_count = user_data.get('combo_count', 0)
        if change >= 0:  # 成功或无效（非负数）
            combo_count += 1
            combo_bonus_msg = None

            # 检查连击奖励
            if combo_count == DajiaoCombo.COMBO_3_THRESHOLD:
                extra_length += DajiaoCombo.COMBO_3_LENGTH_BONUS
                combo_bonus_msg = random.choice(self.niuniu_texts['dajiao']['combo_3']).format(
                    nickname=nickname, bonus=DajiaoCombo.COMBO_3_LENGTH_BONUS
                )
            elif combo_count == DajiaoCombo.COMBO_5_THRESHOLD:
                extra_length += DajiaoCombo.COMBO_5_LENGTH_BONUS
                extra_coins += DajiaoCombo.COMBO_5_COIN_BONUS
                combo_bonus_msg = random.choice(self.niuniu_texts['dajiao']['combo_5']).format(
                    nickname=nickname,
                    length_bonus=DajiaoCombo.COMBO_5_LENGTH_BONUS,
                    coin_bonus=DajiaoCombo.COMBO_5_COIN_BONUS
                )
            elif combo_count == DajiaoCombo.COMBO_10_THRESHOLD:
                extra_length += DajiaoCombo.COMBO_10_LENGTH_BONUS
                extra_coins += DajiaoCombo.COMBO_10_COIN_BONUS
                hardness_change += DajiaoCombo.COMBO_10_HARDNESS_BONUS
                combo_bonus_msg = random.choice(self.niuniu_texts['dajiao']['combo_10']).format(
                    nickname=nickname,
                    length_bonus=DajiaoCombo.COMBO_10_LENGTH_BONUS,
                    coin_bonus=DajiaoCombo.COMBO_10_COIN_BONUS,
                    hardness_bonus=DajiaoCombo.COMBO_10_HARDNESS_BONUS
                )

            if combo_bonus_msg:
                result_msgs.append(combo_bonus_msg)
        else:
            # 失败，重置连击
            if combo_count >= 3:
                break_text = random.choice(self.niuniu_texts['dajiao']['combo_break']).format(
                    nickname=nickname, count=combo_count
                )
                result_msgs.append(break_text)
            combo_count = 0

        # ===== 额外百分比变化（基于当前长度的1-3%） =====
        current_length = user_data['length']
        percentage = random.randint(1, 3) / 100  # 1-3%
        percentage_change = int(current_length * percentage)

        # 根据打胶结果决定波动方向
        if change > 0:  # 打胶成功
            # 额外增加1-3%长度
            extra_length += percentage_change
            if percentage_change > 0:
                percent_text = f"📊 额外增长：+{percentage_change}cm ({int(percentage*100)}%)"
                result_msgs.append(percent_text)

            # 30%概率额外增加1-5硬度
            if random.random() < 0.3:
                hardness_delta = random.randint(1, 5)
                hardness_change += hardness_delta
                hardness_text = f"💎 硬度提升：+{hardness_delta}"
                result_msgs.append(hardness_text)

        elif change < 0:  # 打胶失败
            # 额外减少1-3%长度
            extra_length -= percentage_change
            if percentage_change > 0:
                percent_text = f"📊 额外损失：-{percentage_change}cm ({int(percentage*100)}%)"
                result_msgs.append(percent_text)

            # 30%概率额外减少1-5硬度
            if random.random() < 0.3:
                hardness_delta = random.randint(1, 5)
                hardness_change -= hardness_delta
                hardness_text = f"💎 硬度下降：-{hardness_delta}"
                result_msgs.append(hardness_text)

        # ===== 应用所有变化 =====
        total_change = change + extra_length
        new_hardness = min(100, max(1, old_hardness + hardness_change))
        hardness_updated = new_hardness != old_hardness

        updated_data = {
            'length': user_data['length'] + total_change,
            'combo_count': combo_count,
            'last_dajiao_date': today_str
        }
        if hardness_updated:
            updated_data['hardness'] = new_hardness

        self.update_user_data(group_id, user_id, updated_data)

        # ===== 含笑五步癫触发：每次行动后扣除快照值的19.6% =====
        huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
        result_msgs.extend(huagu_msgs)

        # ===== 寄生牛牛效果：如果有人在我身上种了寄生牛牛，检查是否触发抽取 =====
        if total_change > 0:
            parasite_msgs = self._check_and_trigger_parasite(
                group_id, user_id, total_change, processed_ids=set()
            )
            result_msgs.extend(parasite_msgs)

        # 更新金币
        if extra_coins > 0:
            self.games.update_user_coins(group_id, user_id, extra_coins)

        # ===== 触发 AFTER_DAJIAO 订阅效果（吃瓜群众等） =====
        after_ctx = EffectContext(
            group_id=group_id,
            user_id=user_id,
            nickname=nickname,
            user_data=self.get_user_data(group_id, user_id),
            length_change=total_change,
            hardness_change=hardness_change,
        )
        after_ctx = self.effects.trigger(EffectTrigger.AFTER_DAJIAO, after_ctx, user_items)
        if after_ctx.messages:
            result_msgs.extend(after_ctx.messages)

        # 更新冷却时间（如果没有时间扭曲）
        last_actions = self._load_last_actions()
        if time_warp_triggered:
            # 时间扭曲：设置为很久以前，这样下次不会冷却
            last_actions.setdefault(group_id, {}).setdefault(user_id, {})['dajiao'] = 0
        else:
            last_actions.setdefault(group_id, {}).setdefault(user_id, {})['dajiao'] = current_time
        self.update_last_actions(last_actions)

        # ===== 生成基础消息 =====
        if change > 0:
            template = random.choice(self.niuniu_texts['dajiao']['increase'])
            base_text = template.format(nickname=nickname, change=abs(change))
        elif change < 0:
            template = decrease_template or random.choice(self.niuniu_texts['dajiao']['decrease'])
            base_text = template.format(nickname=nickname, change=abs(change))
        else:
            # 无效果时触发安慰奖彩蛋
            no_effect_template = random.choice(self.niuniu_texts['dajiao']['no_effect'])
            base_text = no_effect_template.format(nickname=nickname)

            # 50%概率获得小长度，50%概率获得金币
            easter_egg_texts = self.niuniu_texts['dajiao'].get('no_effect_easter_egg', {})
            if random.random() < 0.5:
                # 获得小长度 1~3cm
                reward = random.randint(1, 3)
                user_data = self.get_user_data(group_id, user_id)
                self.update_user_data(group_id, user_id, {'length': user_data['length'] + reward})
                if easter_egg_texts.get('length'):
                    egg_template = random.choice(easter_egg_texts['length'])
                    result_msgs.append(egg_template.format(nickname=nickname, reward=reward))
            else:
                # 获得金币 5~20
                reward = random.randint(5, 20)
                self.games.update_user_coins(group_id, user_id, reward)
                if easter_egg_texts.get('coins'):
                    egg_template = random.choice(easter_egg_texts['coins'])
                    result_msgs.append(egg_template.format(nickname=nickname, reward=reward))

        # 合并效果消息（道具效果）
        if ctx.messages:
            result_msgs = ctx.messages + result_msgs

        # 添加基础消息
        result_msgs.append(base_text)

        # ===== 波及他人事件 (8%概率) =====
        if random.random() < 0.08:
            group_data = self.get_group_data(group_id)
            # 找到其他已注册用户
            other_users = [
                (uid, data) for uid, data in group_data.items()
                if isinstance(data, dict) and 'length' in data
                and uid != user_id and not uid.startswith('_') and uid != 'plugin_enabled'
            ]
            if other_users:
                victim_id, victim_data = random.choice(other_users)
                victim_name = victim_data.get('nickname', victim_id)
                collateral_texts = self.niuniu_texts['dajiao'].get('collateral_damage', {})

                # 70%长度事件，30%硬度事件
                if random.random() < 0.70:
                    # 长度事件：75%坏事，25%好事
                    if random.random() < 0.75:
                        # 坏事：扣别人 1~5cm（小意外）
                        damage = random.randint(1, 5)
                        new_length = victim_data['length'] - damage
                        self.update_user_data(group_id, victim_id, {'length': new_length})
                        if collateral_texts.get('bad'):
                            template = random.choice(collateral_texts['bad'])
                            result_msgs.append(template.format(nickname=nickname, victim=victim_name, damage=damage))
                    else:
                        # 好事：给别人 1~3cm
                        bonus = random.randint(1, 3)
                        new_length = victim_data['length'] + bonus
                        self.update_user_data(group_id, victim_id, {'length': new_length})
                        if collateral_texts.get('good'):
                            template = random.choice(collateral_texts['good'])
                            result_msgs.append(template.format(nickname=nickname, victim=victim_name, bonus=bonus))
                else:
                    # 硬度事件：75%坏事，25%好事
                    victim_old_hardness = victim_data.get('hardness', 1)
                    if random.random() < 0.75:
                        # 坏事：扣别人硬度 1~2
                        h_damage = random.randint(1, 2)
                        victim_new_hardness = max(1, victim_old_hardness - h_damage)
                        self.update_user_data(group_id, victim_id, {'hardness': victim_new_hardness})
                        if collateral_texts.get('hardness_bad'):
                            template = random.choice(collateral_texts['hardness_bad'])
                            result_msgs.append(template.format(nickname=nickname, victim=victim_name, h_damage=h_damage))
                            result_msgs.append(f"  └ {victim_name} 硬度: {victim_old_hardness} → {victim_new_hardness}")
                    else:
                        # 好事：给别人硬度 1~2
                        h_bonus = random.randint(1, 2)
                        victim_new_hardness = min(100, victim_old_hardness + h_bonus)
                        self.update_user_data(group_id, victim_id, {'hardness': victim_new_hardness})
                        if collateral_texts.get('hardness_good'):
                            template = random.choice(collateral_texts['hardness_good'])
                            result_msgs.append(template.format(nickname=nickname, victim=victim_name, h_bonus=h_bonus))
                            result_msgs.append(f"  └ {victim_name} 硬度: {victim_old_hardness} → {victim_new_hardness}")

        # ===== 构建最终输出 =====
        user_data = self.get_user_data(group_id, user_id)
        final_text = "\n".join(result_msgs)
        final_text += f"\n当前长度：{self.format_length(user_data['length'])}"

        if hardness_updated:
            final_text += f"\n💪 硬度变化: {old_hardness} → {new_hardness}"
        else:
            final_text += f"\n当前硬度：{user_data['hardness']}"

        # 显示连击数（如果有）
        if combo_count >= 2:
            final_text += f"\n🔥 当前连击：{combo_count}"

        # 股市钩子
        stock_msg = stock_hook(group_id, nickname, event_type="dajiao", length_change=total_change)
        if stock_msg:
            final_text += f"\n{stock_msg}"

        yield event.plain_result(final_text)

    def _calculate_win_probability(self, group_id: str, user_id: str,
                                   u_len: float, t_len: float,
                                   u_hardness: int, t_hardness: int,
                                   streak_bonus: float = 0.0) -> float:
        """
        计算胜负概率（复用比划逻辑）

        Args:
            group_id: 群组ID
            user_id: 用户ID
            u_len: 用户长度
            t_len: 目标长度
            u_hardness: 用户硬度
            t_hardness: 目标硬度
            streak_bonus: 连胜/连败加成

        Returns:
            胜率（0.15-0.85）
        """
        base_win = 0.5

        # 负数长度特殊处理
        if u_len <= 0 and t_len > 0:
            # 用户凹进去了，对方正常：极大劣势
            length_factor = -0.2
        elif u_len > 0 and t_len <= 0:
            # 用户正常，对方凹进去了：极大优势
            length_factor = 0.2
        elif u_len <= 0 and t_len <= 0:
            # 都凹进去了：谁更接近0谁有优势
            max_abs = max(abs(u_len), abs(t_len), 1)
            length_factor = (u_len - t_len) / max_abs * 0.2
        else:
            # 都是正数：正常计算
            length_factor = (u_len - t_len) / max(u_len, t_len, 1) * 0.2

        hardness_factor = (u_hardness - t_hardness) * 0.08

        # 获取订阅胜率加成
        sub_winrate_boost = self.effects.get_compare_winrate_boost(group_id, user_id)

        # 应用连击加成和订阅加成
        win_prob = min(max(base_win + length_factor + hardness_factor + streak_bonus + sub_winrate_boost, 0.15), 0.85)

        return win_prob

    async def _compare(self, event):
        """比划功能"""
        # 性能优化：批量加载数据，最后统一保存（使用锁保护避免并发冲突）
        await self._begin_data_cache_async()
        try:
            group_id = str(event.message_obj.group_id)
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name()

            group_data = self.get_group_data(group_id)
            if not group_data.get('plugin_enabled', False):
                yield event.plain_result("❌ 插件未启用")
                return

            # 获取自身数据
            user_data = self.get_user_data(group_id, user_id)
            if not user_data:
                yield event.plain_result(self.niuniu_texts['dajiao']['not_registered'].format(nickname=nickname))
                return

            # 解析目标
            target_id = self.parse_target(event)
            if not target_id:
                yield event.plain_result(self.niuniu_texts['compare']['no_target'].format(nickname=nickname))
                return

            if target_id == user_id:
                yield event.plain_result(self.niuniu_texts['compare']['self_compare'])
                return

            # 获取目标数据
            target_data = self.get_user_data(group_id, target_id)
            if not target_data:
                yield event.plain_result(self.niuniu_texts['compare']['target_not_registered'])
                return

            # 冷却检查
            last_actions = self._load_last_actions()
            compare_records = last_actions.setdefault(group_id, {}).setdefault(user_id, {})
            last_compare = compare_records.get(target_id, 0)
            on_cooldown, remaining = self.check_cooldown(last_compare, self.COMPARE_COOLDOWN)
            if on_cooldown:
                mins = int(remaining // 60) + 1
                text = self.niuniu_texts['compare']['cooldown'].format(
                    nickname=nickname,
                    remaining=mins
                )
                yield event.plain_result(text)
                return

            # 检查10分钟内比划次数
            last_compare_time = compare_records.get('last_time', 0)
            current_time = time.time()

            # 如果超过10分钟，重置计数
            if current_time - last_compare_time > 600:
                compare_records['count'] = 0
                compare_records['last_time'] = current_time
                self.update_last_actions(last_actions)

            compare_count = compare_records.get('count', 0)

            if compare_count >= 3:
                yield event.plain_result("❌ 10分钟内只能比划三次")
                return

            # ===== 解析赌注 =====
            bet_amount = 0
            msg_parts = event.message_str.split()
            for part in msg_parts:
                if part.isdigit():
                    bet_amount = int(part)
                    break

            # 验证赌注（只检查最小值，无上限）
            if bet_amount > 0:
                if bet_amount < CompareBet.MIN_BET:
                    yield event.plain_result(f"❌ 赌注最少 {CompareBet.MIN_BET} 金币")
                    return
                # 检查金币是否足够
                user_coins = self.shop.get_user_coins(group_id, user_id)
                if user_coins < bet_amount:
                    yield event.plain_result(
                        random.choice(self.niuniu_texts['compare'].get('bet_insufficient', ['❌ {nickname} 金币不足'])).format(
                            nickname=nickname, amount=bet_amount
                        )
                    )
                    return

            # 更新冷却时间和比划次数（在验证通过后才更新）
            compare_records[target_id] = current_time
            compare_records['count'] = compare_count + 1
            self.update_last_actions(last_actions)

            # 下注先扣除发起方金币（入池）
            if bet_amount > 0:
                self.modify_coins_cached(group_id, user_id, -bet_amount)

            # ===== 连胜/连败系统 =====
            win_streak = user_data.get('compare_win_streak', 0)
            lose_streak = user_data.get('compare_lose_streak', 0)
            streak_bonus = 0
            streak_msgs = []

            # 连胜/连败加成（影响胜率）
            if win_streak >= CompareStreak.WIN_STREAK_THRESHOLD:
                streak_bonus += CompareStreak.WIN_STREAK_BONUS

            if lose_streak >= CompareStreak.LOSE_STREAK_THRESHOLD:
                streak_bonus += CompareStreak.LOSE_STREAK_BONUS

            # 获取双方道具
            user_items = self.shop.get_user_items(group_id, user_id)
            target_items = self.shop.get_user_items(group_id, target_id)

            # 记录比划前的长度
            u_len = user_data['length']
            t_len = target_data['length']
            u_hardness = user_data['hardness']
            t_hardness = target_data['hardness']
            old_u_len = u_len
            old_t_len = t_len

            # 创建效果上下文（包含 group_data 供夺牛魔委托效果使用）
            all_group_data = self._get_data().get(group_id, {})
            ctx = EffectContext(
                group_id=group_id,
                user_id=user_id,
                nickname=nickname,
                user_data=user_data,
                target_id=target_id,
                target_nickname=target_data['nickname'],
                target_data=target_data,
                user_length=u_len,
                user_hardness=u_hardness,
                target_length=t_len,
                target_hardness=t_hardness
            )
            ctx.extra['group_data'] = all_group_data

            # 触发 BEFORE_COMPARE 效果（如夺牛魔）
            ctx = self.effects.trigger(EffectTrigger.BEFORE_COMPARE, ctx, user_items, target_items)

            # 消耗触发的道具
            self.effects.consume_items(group_id, user_id, ctx.items_to_consume)

            # 如果被拦截（如夺牛魔触发），直接返回结果
            if ctx.intercept:
                # 处理夺牛魔委托的混沌风暴效果
                if ctx.extra.get('chaos_storm'):
                    self._process_delegated_chaos_storm(ctx, group_id)
                    yield event.plain_result("\n".join(ctx.messages))
                    return

                # 处理夺牛魔委托的大自爆效果
                if ctx.extra.get('dazibao'):
                    self._process_delegated_dazibao(ctx, group_id, user_id)
                    yield event.plain_result("\n".join(ctx.messages))
                    return

                # 普通夺牛魔效果（steal/self_clear/blocked）
                # 处理护盾消耗
                for shield_info in ctx.extra.get('consume_shields', []):
                    shield_target_id = shield_info['user_id']
                    shield_amount = shield_info['amount']
                    current_shield = self.get_user_data(group_id, shield_target_id).get('shield_charges', 0)
                    self.update_user_data(group_id, shield_target_id, {
                        'shield_charges': max(0, current_shield - shield_amount)
                    })

                # 应用长度变化
                if ctx.length_change != 0:
                    new_user_len = user_data['length'] + ctx.length_change
                    self.update_user_data(group_id, user_id, {'length': new_user_len})
                if ctx.target_length_change != 0:
                    new_target_len = target_data['length'] + ctx.target_length_change
                    self.update_user_data(group_id, target_id, {'length': new_target_len})

                # 处理硬度变化（夺牛魔steal）
                if ctx.hardness_change != 0:
                    new_user_hard = max(1, min(100, user_data['hardness'] + ctx.hardness_change))
                    self.update_user_data(group_id, user_id, {'hardness': new_user_hard})
                if ctx.extra.get('target_hardness_change', 0) != 0:
                    new_target_hard = max(1, target_data['hardness'] + ctx.extra['target_hardness_change'])
                    self.update_user_data(group_id, target_id, {'hardness': new_target_hard})

                # 添加长度变化显示
                user_data = self.get_user_data(group_id, user_id)
                target_data = self.get_user_data(group_id, target_id)
                ctx.messages.append(f"🗡️ {nickname}: {self.format_length(old_u_len)} → {self.format_length(user_data['length'])}")
                ctx.messages.append(f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} → {self.format_length(target_data['length'])}")

                # 检查被夺取者的保险（夺牛魔steal效果）
                from niuniu_config import InsuranceConfig
                if ctx.target_length_change < 0:
                    target_length_loss = abs(ctx.target_length_change)
                    if target_length_loss >= InsuranceConfig.LENGTH_THRESHOLD:
                        # 检查订阅或旧道具次数
                        has_insurance_sub = self.effects.has_insurance_subscription(group_id, target_id)
                        old_insurance_charges = target_data.get('insurance_charges', 0)

                        if has_insurance_sub or old_insurance_charges > 0:
                            if has_insurance_sub:
                                payout = self.effects.get_insurance_payout(group_id, target_id)
                                remaining_msg = "订阅中"
                            else:
                                # 消耗旧道具次数
                                self.update_user_data(group_id, target_id, {'insurance_charges': old_insurance_charges - 1})
                                payout = 200
                                remaining_msg = f"剩余{old_insurance_charges - 1}次"

                            self.modify_coins_cached(group_id, target_id, payout)
                            ctx.messages.append(f"📋 {target_data['nickname']} 保险理赔！损失{target_length_loss}cm，赔付{payout:,}金币（{remaining_msg}）")

                yield event.plain_result("\n".join(ctx.messages))
                return

            # 计算胜负概率（复用通用方法）
            win_prob = self._calculate_win_probability(
                group_id, user_id, u_len, t_len,
                ctx.user_hardness, ctx.target_hardness, streak_bonus
            )

            # 执行判定
            is_win = random.random() < win_prob
            base_gain = random.randint(1, 5)
            base_loss = random.randint(1, 2)

            # ===== 更新连击状态 =====
            lose_streak_protection_active = False
            if is_win:
                new_win_streak = win_streak + 1
                new_lose_streak = 0
            else:
                new_win_streak = 0
                new_lose_streak = lose_streak + 1
                # 连败保护：输了不扣长度
                if lose_streak >= CompareStreak.LOSE_STREAK_THRESHOLD and CompareStreak.LOSE_STREAK_PROTECTION:
                    lose_streak_protection_active = True

            self.update_user_data(group_id, user_id, {
                'compare_win_streak': new_win_streak,
                'compare_lose_streak': new_lose_streak
            })

            # 生成连胜/连败消息（在比划结果确定后）
            if is_win and new_win_streak >= CompareStreak.WIN_STREAK_THRESHOLD:
                streak_text = random.choice(self.niuniu_texts['compare'].get('win_streak', ['🔥 【{count}连胜】'])).format(
                    nickname=nickname, count=new_win_streak
                )
                streak_msgs.append(streak_text)
            elif not is_win and new_lose_streak >= CompareStreak.LOSE_STREAK_THRESHOLD:
                streak_text = random.choice(self.niuniu_texts['compare'].get('lose_streak', ['🛡️ 【触底反弹】'])).format(
                    nickname=nickname, count=new_lose_streak
                )
                streak_msgs.append(streak_text)

            # 计算群内金币平均值（用于下注税计算）
            bet_tax_info = ""
            if bet_amount > 0:
                niuniu_data = self._get_data()
                group_niuniu_data = niuniu_data.get(group_id, {})
                all_coins = [data.get('coins', 0) for uid, data in group_niuniu_data.items()
                            if isinstance(data, dict) and 'coins' in data and data.get('coins', 0) > 0]
                avg_coins = sum(all_coins) / len(all_coins) if all_coins else 0

            if is_win:
                # 硬度影响伤害：赢家(user)硬度加成攻击，输家(target)硬度减少损失
                hardness_bonus = max(0, int((u_hardness - 5) * 0.15))
                hardness_defense = max(0, int((t_hardness - 5) * 0.2))
                gain = base_gain + hardness_bonus
                loss = max(1, base_loss - hardness_defense)
                # 触发 ON_COMPARE_WIN 效果
                ctx = self.effects.trigger(EffectTrigger.ON_COMPARE_WIN, ctx, user_items, target_items)
                self.effects.consume_items(group_id, user_id, ctx.items_to_consume)

                # 基础增益 + 效果增益
                total_gain = gain + ctx.length_change

                # 更新数据
                self.update_user_data(group_id, user_id, {'length': user_data['length'] + total_gain})
                self.update_user_data(group_id, target_id, {'length': target_data['length'] - loss})

                # 处理金币下注（获胜方）
                if bet_amount > 0:
                    # 获取输家当前金币，不允许扣到负数
                    target_coins = self.shop.get_user_coins(group_id, target_id)
                    target_pay = min(bet_amount, max(0, target_coins))
                    if target_pay > 0:
                        # 计算税收仅针对对手赔付部分（复用股市税率）
                        tax_amount, effective_rate, bracket_str = NiuniuStock.get()._calculate_tax(target_pay, avg_coins)
                        net_from_target = target_pay - tax_amount
                    else:
                        tax_amount, effective_rate, bracket_str = 0.0, 0.0, ""
                        net_from_target = 0.0
                    # 返还自己的赌注 + 对手赔付（税后）
                    total_return = bet_amount + int(net_from_target)
                    bet_tax_info = f"\n💰 赢得赌注池！返还 {bet_amount} + 对手赔付 {net_from_target:.0f}（税前 {target_pay}，税收 {tax_amount:.0f}，税率 {effective_rate*100:.1f}%）"
                    if bracket_str and bracket_str != "免税":
                        bet_tax_info += f"\n📊 税率明细：{bracket_str}"
                    if target_pay < bet_amount:
                        bet_tax_info += f"\n⚠️ {target_data['nickname']} 金币不足，实际赔付 {target_pay} 枚（原赌注 {bet_amount}）"
                    # 扣除输家金币（最多扣到0）
                    self.modify_coins_cached(group_id, target_id, -target_pay)
                    # 返还赢家自己的赌注 + 对手赔付（税后）
                    self.modify_coins_cached(group_id, user_id, total_return)

                text = random.choice(self.niuniu_texts['compare']['win']).format(
                    winner=nickname,
                    loser=target_data['nickname'],
                    gain=total_gain
                )

                # 负数/0长度特殊文案
                if u_len == 0 or t_len == 0:
                    zero_text = random.choice(self.niuniu_texts['compare'].get('zero_length', ['👻 0长度牛牛参战！']))
                    text += f"\n{zero_text}"
                if u_len < 0 and t_len < 0:
                    special_text = random.choice(self.niuniu_texts['compare'].get('both_negative_win', ['🕳️ 凹牛牛对决！'])).format(winner=nickname, loser=target_data['nickname'])
                    text += f"\n{special_text}"
                elif u_len < 0 < t_len:
                    special_text = random.choice(self.niuniu_texts['compare'].get('negative_win', ['🎊 逆天！负数赢了！'])).format(winner=nickname, loser=target_data['nickname'])
                    text += f"\n{special_text}"
                elif t_len < 0 < u_len:
                    special_text = random.choice(self.niuniu_texts['compare'].get('vs_negative_win', ['💀 凹牛牛毫无还手之力...'])).format(winner=nickname, loser=target_data['nickname'])
                    text += f"\n{special_text}"

                # 长度悬殊特殊文案（差距>50cm）
                length_diff = abs(u_len - t_len)
                if length_diff > 50:
                    if u_len > t_len:
                        # 大的赢了，正常碾压
                        gap_text = random.choice(self.niuniu_texts['compare'].get('length_gap_win', ['🐘 碾压局！'])).format(winner=nickname, loser=target_data['nickname'])
                    else:
                        # 小的赢了，大翻车
                        gap_text = random.choice(self.niuniu_texts['compare'].get('length_gap_upset', ['😱 大翻车！'])).format(winner=nickname, loser=target_data['nickname'])
                    text += f"\n{gap_text}"

                # 硬度悬殊特殊文案（差距>=5）
                hardness_diff = abs(u_hardness - t_hardness)
                if hardness_diff >= 5:
                    if u_hardness > t_hardness:
                        # 硬的赢了，正常
                        h_gap_text = random.choice(self.niuniu_texts['compare'].get('hardness_gap_win', ['🗿 以刚克柔！'])).format(winner=nickname, loser=target_data['nickname'])
                    else:
                        # 软的赢了，翻车
                        h_gap_text = random.choice(self.niuniu_texts['compare'].get('hardness_gap_upset', ['🫠 以柔克刚！'])).format(winner=nickname, loser=target_data['nickname'])
                    text += f"\n{h_gap_text}"

                # 添加效果消息
                for msg in ctx.messages:
                    text += f"\n{msg}"

                # 额外逻辑：极大劣势但硬度优势获胜奖励
                if u_len < t_len and abs(u_len - t_len) >= 20 and u_hardness > t_hardness:
                    extra_gain = random.randint(0, 5)
                    self.update_user_data(group_id, user_id, {'length': user_data['length'] + total_gain + extra_gain})
                    total_gain += extra_gain
                    text += f"\n🎁 由于极大劣势获胜，额外增加 {extra_gain}cm！"

                # 额外逻辑：掠夺（非道具触发，仅当目标战前长度为正时）
                if abs(u_len - t_len) > 10 and u_len < t_len and t_len > 0:
                    current_user = self.get_user_data(group_id, user_id)
                    current_target = self.get_user_data(group_id, target_id)
                    if current_target['length'] <= 0:
                        # 战后目标变成0/负数
                        status = '凹进去' if current_target['length'] < 0 else '归零'
                        text += f"\n🕳️ {target_data['nickname']} 被打到{status}了，没什么可掠夺的..."
                    else:
                        stolen_length = int(current_target['length'] * 0.2)
                        if stolen_length > 0:
                            self.update_user_data(group_id, user_id, {'length': current_user['length'] + stolen_length})
                            self.update_user_data(group_id, target_id, {'length': current_target['length'] - stolen_length})
                            text += f"\n🎉 {nickname} 掠夺了 {stolen_length}cm！"
                        else:
                            # 长度太短，20%不足1cm
                            text += f"\n😅 {target_data['nickname']} 长度太短了，掠夺不到什么..."

                # 硬度优势获胜提示
                if abs(u_len - t_len) <= 5 and u_hardness > t_hardness:
                    text += f"\n🎉 {nickname} 因硬度优势获胜！"

                if total_gain == 0:
                    text += f"\n{self.niuniu_texts['compare']['user_no_increase'].format(nickname=nickname)}"

                # 添加下注税收信息
                if bet_tax_info:
                    text += bet_tax_info
            else:
                # 硬度影响伤害：赢家(target)硬度加成攻击，输家(user)硬度减少损失
                hardness_bonus = max(0, int((t_hardness - 5) * 0.15))
                hardness_defense = max(0, int((u_hardness - 5) * 0.2))
                gain = base_gain + hardness_bonus
                loss = max(1, base_loss - hardness_defense)

                # 触发 ON_COMPARE_LOSE 效果
                ctx = self.effects.trigger(EffectTrigger.ON_COMPARE_LOSE, ctx, user_items, target_items)
                self.effects.consume_items(group_id, user_id, ctx.items_to_consume)

                # 更新目标数据
                self.update_user_data(group_id, target_id, {'length': target_data['length'] + gain})

                # 检查是否防止损失（道具效果或连败保护）
                prevent_loss = ctx.prevent_loss or lose_streak_protection_active
                if prevent_loss:
                    # 不减少长度
                    pass
                else:
                    self.update_user_data(group_id, user_id, {'length': user_data['length'] - loss})

                # 处理金币下注（失败方）
                if bet_amount > 0:
                    # 发起方已在开始时扣除赌注，直接给赢家（税后）
                    tax_amount, effective_rate, bracket_str = NiuniuStock.get()._calculate_tax(bet_amount, avg_coins)
                    net_gain = bet_amount - tax_amount
                    bet_tax_info = f"\n💸 损失赌注 {bet_amount} 枚（{target_data['nickname']} 获得 {net_gain:.0f}，税收 {tax_amount:.0f}，税率 {effective_rate*100:.1f}%）"
                    if bracket_str and bracket_str != "免税":
                        bet_tax_info += f"\n📊 税率明细：{bracket_str}"
                    # 增加赢家金币（税后）
                    self.modify_coins_cached(group_id, target_id, int(net_gain))

                text = random.choice(self.niuniu_texts['compare']['lose']).format(
                    loser=nickname,
                    winner=target_data['nickname'],
                    loss=loss if not prevent_loss else 0
                )

                # 连败保护提示
                if lose_streak_protection_active and not ctx.prevent_loss:
                    protection_text = random.choice(self.niuniu_texts['compare'].get('lose_streak_protection', ['🛡️ 【连败保护】不扣长度！'])).format(nickname=nickname)
                    text += f"\n{protection_text}"

                # 负数/0长度特殊文案
                if u_len == 0 or t_len == 0:
                    zero_text = random.choice(self.niuniu_texts['compare'].get('zero_length', ['👻 0长度牛牛参战！']))
                    text += f"\n{zero_text}"
                if u_len < 0 and t_len < 0:
                    special_text = random.choice(self.niuniu_texts['compare'].get('both_negative_lose', ['🕳️ 凹牛牛对决！'])).format(loser=nickname, winner=target_data['nickname'])
                    text += f"\n{special_text}"
                elif u_len < 0 < t_len:
                    special_text = random.choice(self.niuniu_texts['compare'].get('negative_lose', ['😭 凹着还敢挑战...'])).format(loser=nickname, winner=target_data['nickname'])
                    text += f"\n{special_text}"
                elif t_len < 0 < u_len:
                    special_text = random.choice(self.niuniu_texts['compare'].get('vs_negative_lose', ['😱 居然输给了凹牛牛！'])).format(loser=nickname, winner=target_data['nickname'])
                    text += f"\n{special_text}"

                # 长度悬殊特殊文案（差距>50cm）
                length_diff = abs(u_len - t_len)
                if length_diff > 50:
                    if u_len > t_len:
                        # 大的输了，大翻车
                        gap_text = random.choice(self.niuniu_texts['compare'].get('length_gap_upset', ['😱 大翻车！'])).format(winner=target_data['nickname'], loser=nickname)
                    else:
                        # 小的输了，正常碾压
                        gap_text = random.choice(self.niuniu_texts['compare'].get('length_gap_win', ['🐘 碾压局！'])).format(winner=target_data['nickname'], loser=nickname)
                    text += f"\n{gap_text}"

                # 硬度悬殊特殊文案（差距>=5）
                hardness_diff = abs(u_hardness - t_hardness)
                if hardness_diff >= 5:
                    if u_hardness > t_hardness:
                        # 硬的输了，翻车
                        h_gap_text = random.choice(self.niuniu_texts['compare'].get('hardness_gap_upset', ['🫠 以柔克刚！'])).format(winner=target_data['nickname'], loser=nickname)
                    else:
                        # 软的输了，正常
                        h_gap_text = random.choice(self.niuniu_texts['compare'].get('hardness_gap_win', ['🗿 以刚克柔！'])).format(winner=target_data['nickname'], loser=nickname)
                    text += f"\n{h_gap_text}"

                # 添加效果消息
                for msg in ctx.messages:
                    text += f"\n{msg}"

                # 添加下注税收信息
                if bet_tax_info:
                    text += bet_tax_info

            # 硬度衰减（只有输家有概率衰减，15%概率）
            hardness_decay_msg = ""
            if is_win:
                # 用户赢了，目标(输家)可能衰减
                if random.random() < 0.15:
                    current_target = self.get_user_data(group_id, target_id)
                    old_hardness = current_target['hardness']
                    new_hardness = max(1, old_hardness - 1)
                    if new_hardness < old_hardness:
                        self.update_user_data(group_id, target_id, {'hardness': new_hardness})
                        hardness_decay_msg = f"\n💪 {target_data['nickname']} 硬度下降: {old_hardness} → {new_hardness}"
            else:
                # 用户输了，用户(输家)可能衰减
                if random.random() < 0.15:
                    current_user = self.get_user_data(group_id, user_id)
                    old_hardness = current_user['hardness']
                    new_hardness = max(1, old_hardness - 1)
                    if new_hardness < old_hardness:
                        self.update_user_data(group_id, user_id, {'hardness': new_hardness})
                        hardness_decay_msg = f"\n💪 {nickname} 硬度下降: {old_hardness} → {new_hardness}"

            # 重新获取最新数据
            user_data = self.get_user_data(group_id, user_id)
            target_data = self.get_user_data(group_id, target_id)

            # 计算硬度变化显示
            u_hardness_now = user_data['hardness']
            t_hardness_now = target_data['hardness']
            u_h_str = f"硬度{u_hardness}" if u_hardness == u_hardness_now else f"硬度{u_hardness}→{u_hardness_now}"
            t_h_str = f"硬度{t_hardness}" if t_hardness == t_hardness_now else f"硬度{t_hardness}→{t_hardness_now}"

            result_msg = [
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"📊 {nickname}({self.format_length(old_u_len)}/{u_h_str}) vs {target_data['nickname']}({self.format_length(old_t_len)}/{t_h_str})",
                f"🗡️ {nickname}: {self.format_length(old_u_len)} → {self.format_length(user_data['length'])}",
                f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} → {self.format_length(target_data['length'])}",
                f"📢 {text}"
            ]

            # 添加硬度衰减提示
            if hardness_decay_msg:
                result_msg.append(hardness_decay_msg.strip())

            # 特殊事件
            special_event_triggered = False

            # 势均力敌
            if abs(u_len - t_len) <= 5 and random.random() < 0.075:
                draw_text = random.choice(self.niuniu_texts['compare']['draw'])
                result_msg.append(draw_text)
                special_event_triggered = True

            # 双方硬度都低于平均值时触发缠绕（20%概率）
            if not special_event_triggered and u_hardness < 5 and t_hardness < 5 and random.random() < 0.20:
                async for msg in self._handle_halving_event(group_id, user_id, target_id, nickname, target_data['nickname'], user_items, target_items, result_msg):
                    pass
                tangle_text = random.choice(self.niuniu_texts['compare']['tangle']).format(
                    nickname1=nickname, nickname2=target_data['nickname'],
                    hardness1=u_hardness, hardness2=t_hardness
                )
                result_msg.append(tangle_text)
                special_event_triggered = True

            # 激烈碰撞：长度比例接近 + 总长度越大概率越高
            u_len_positive = max(1, u_len)  # 避免除以0，负数按1算
            t_len_positive = max(1, t_len)
            length_ratio = min(u_len_positive, t_len_positive) / max(u_len_positive, t_len_positive)
            total_length = max(0, u_len) + max(0, t_len)
            collision_chance = min(0.01 + total_length / 1500 * 0.10, 0.12)  # 1%~12%
            # 只有比例 >= 0.8 才可能触发
            if not special_event_triggered and length_ratio >= 0.8 and random.random() < collision_chance:
                # 计算各自损失：至少10cm，或自身10%取较大值
                user_collision_loss = max(10, int(max(0, u_len) * 0.10))
                target_collision_loss = max(10, int(max(0, t_len) * 0.10))
                # 应用损失
                current_user = self.get_user_data(group_id, user_id)
                current_target = self.get_user_data(group_id, target_id)
                self.update_user_data(group_id, user_id, {'length': current_user['length'] - user_collision_loss})
                self.update_user_data(group_id, target_id, {'length': current_target['length'] - target_collision_loss})
                collision_text = random.choice(self.niuniu_texts['compare'].get('collision', [
                    '💥 【激烈碰撞】双方牛牛猛烈撞击！{nickname1} -{loss1}cm，{nickname2} -{loss2}cm！'
                ])).format(
                    nickname1=nickname, nickname2=target_data['nickname'],
                    loss1=user_collision_loss, loss2=target_collision_loss
                )
                result_msg.append(collision_text)
                special_event_triggered = True

            # ===== 随机趣味事件 =====
            # 重新获取最新数据
            current_user = self.get_user_data(group_id, user_id)
            current_target = self.get_user_data(group_id, target_id)

            # 暴击 (3%) - 赢家额外造成伤害
            if not special_event_triggered and is_win and random.random() < 0.03:
                extra_damage = loss  # 额外造成等量伤害
                self.update_user_data(group_id, target_id, {'length': current_target['length'] - extra_damage})
                crit_text = random.choice(self.niuniu_texts['compare'].get('critical', ['💥 【暴击】伤害翻倍！'])).format(winner=nickname)
                result_msg.append(crit_text)
                special_event_triggered = True

            # 闪避 (3%) - 输家免疫损失
            if not special_event_triggered and not is_win and random.random() < 0.03:
                # 恢复输家损失的长度
                self.update_user_data(group_id, user_id, {'length': current_user['length'] + loss})
                dodge_text = random.choice(self.niuniu_texts['compare'].get('dodge', ['💨 【闪避】免疫损失！'])).format(loser=nickname)
                result_msg.append(dodge_text)
                special_event_triggered = True

            # 反噬 (2%) - 结果反转
            if not special_event_triggered and random.random() < 0.02:
                # 交换双方的变化
                user_change = current_user['length'] - old_u_len
                target_change = current_target['length'] - old_t_len
                self.update_user_data(group_id, user_id, {'length': old_u_len + target_change})
                self.update_user_data(group_id, target_id, {'length': old_t_len + user_change})
                backfire_text = random.choice(self.niuniu_texts['compare'].get('backfire', ['🔄 【反噬】结果反转！'])).format(
                    winner=nickname if is_win else target_data['nickname'],
                    loser=target_data['nickname'] if is_win else nickname
                )
                result_msg.append(backfire_text)
                special_event_triggered = True

            # 双赢 (2%) - 双方都获益
            if not special_event_triggered and random.random() < 0.02:
                bonus = random.randint(2, 5)
                current_user = self.get_user_data(group_id, user_id)
                current_target = self.get_user_data(group_id, target_id)
                self.update_user_data(group_id, user_id, {'length': current_user['length'] + bonus})
                self.update_user_data(group_id, target_id, {'length': current_target['length'] + bonus})
                double_win_text = random.choice(self.niuniu_texts['compare'].get('double_win', ['🎊 【双赢】双方都+{gain}cm！'])).format(gain=bonus)
                result_msg.append(double_win_text)
                special_event_triggered = True

            # 硬度觉醒 (5%) - 赢家硬度<=3时触发
            winner_id = user_id if is_win else target_id
            winner_name = nickname if is_win else target_data['nickname']
            winner_data = self.get_user_data(group_id, winner_id)
            if not special_event_triggered and winner_data['hardness'] <= 3 and random.random() < 0.05:
                hardness_bonus = random.randint(1, 3)
                new_hardness = min(100, winner_data['hardness'] + hardness_bonus)
                self.update_user_data(group_id, winner_id, {'hardness': new_hardness})
                awakening_text = random.choice(self.niuniu_texts['compare'].get('hardness_awakening', ['💪 【硬度觉醒】硬度+{bonus}！'])).format(nickname=winner_name, bonus=hardness_bonus)
                result_msg.append(awakening_text)
                special_event_triggered = True

            # 长度互换 (1%) - 长度差>30cm时触发
            if not special_event_triggered and abs(u_len - t_len) > 30 and random.random() < 0.01:
                current_user = self.get_user_data(group_id, user_id)
                current_target = self.get_user_data(group_id, target_id)
                user_len_now = current_user['length']
                target_len_now = current_target['length']
                self.update_user_data(group_id, user_id, {'length': target_len_now})
                self.update_user_data(group_id, target_id, {'length': user_len_now})
                swap_text = random.choice(self.niuniu_texts['compare'].get('length_swap', ['🔀 【长度互换】双方长度交换！'])).format(
                    nickname1=nickname, nickname2=target_data['nickname']
                )
                result_msg.append(swap_text)
                special_event_triggered = True

            # 幸运一击 (10%) - 输家长度<5cm时触发
            loser_id = target_id if is_win else user_id
            loser_name = target_data['nickname'] if is_win else nickname
            loser_data = self.get_user_data(group_id, loser_id)
            if not special_event_triggered and loser_data['length'] < 5 and random.random() < 0.10:
                lucky_bonus = random.randint(3, 7)
                self.update_user_data(group_id, loser_id, {'length': loser_data['length'] + lucky_bonus})
                lucky_text = random.choice(self.niuniu_texts['compare'].get('lucky_strike', ['🍀 【幸运一击】+{bonus}cm！'])).format(loser=loser_name, bonus=lucky_bonus)
                result_msg.append(lucky_text)
                special_event_triggered = True

            # 更新最终显示的长度
            final_user = self.get_user_data(group_id, user_id)
            final_target = self.get_user_data(group_id, target_id)
            result_msg[2] = f"🗡️ {nickname}: {self.format_length(old_u_len)} → {self.format_length(final_user['length'])}"
            result_msg[3] = f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} → {self.format_length(final_target['length'])}"

            # ===== 连击提示 =====
            for msg in streak_msgs:
                result_msg.insert(5, msg)  # 插入到结果消息后面

            # ===== 围观效应 =====
            # 记录本次比划时间
            last_actions = self._load_last_actions()
            group_compares = last_actions.setdefault(group_id, {}).setdefault('_recent_compares', [])
            # 清理5分钟前的记录
            group_compares = [t for t in group_compares if current_time - t < CompareAudience.TIME_WINDOW]
            group_compares.append(current_time)
            last_actions[group_id]['_recent_compares'] = group_compares
            self.update_last_actions(last_actions)

            # 检查是否触发围观效应
            if len(group_compares) >= CompareAudience.MIN_COMPARES and random.random() < CompareAudience.TRIGGER_CHANCE:
                # 根据权重随机选择效果类型
                effects = list(CompareAudience.EFFECT_WEIGHTS.keys())
                weights = list(CompareAudience.EFFECT_WEIGHTS.values())
                effect_type = random.choices(effects, weights=weights, k=1)[0]

                final_user = self.get_user_data(group_id, user_id)
                final_target = self.get_user_data(group_id, target_id)

                if effect_type == 'bonus_length':
                    # 加长度
                    bonus = random.randint(CompareAudience.BONUS_LENGTH_MIN, CompareAudience.BONUS_LENGTH_MAX)
                    self.update_user_data(group_id, user_id, {'length': final_user['length'] + bonus})
                    self.update_user_data(group_id, target_id, {'length': final_target['length'] + bonus})
                    audience_text = random.choice(self.niuniu_texts['compare'].get('audience_effect', ['👀 【围观效应】+{bonus}cm！'])).format(
                        bonus=bonus, count=len(group_compares)
                    )
                elif effect_type == 'penalty_length':
                    # 副作用：减长度
                    penalty = random.randint(CompareAudience.PENALTY_LENGTH_MIN, CompareAudience.PENALTY_LENGTH_MAX)
                    self.update_user_data(group_id, user_id, {'length': final_user['length'] - penalty})
                    self.update_user_data(group_id, target_id, {'length': final_target['length'] - penalty})
                    audience_text = random.choice(self.niuniu_texts['compare'].get('audience_penalty', ['😱 【围观副作用】太多人看了，双方都-{penalty}cm！'])).format(
                        penalty=penalty, count=len(group_compares)
                    )
                elif effect_type == 'bonus_coins':
                    # 奖励金币（双方）
                    coins = random.randint(CompareAudience.BONUS_COINS_MIN, CompareAudience.BONUS_COINS_MAX)
                    self.modify_coins_cached(group_id, user_id, coins)
                    self.modify_coins_cached(group_id, target_id, coins)
                    audience_text = random.choice(self.niuniu_texts['compare'].get('audience_coins', ['💰 【围观打赏】观众们打赏了，双方各获得{coins}金币！'])).format(
                        coins=coins, count=len(group_compares)
                    )
                elif effect_type == 'group_bonus':
                    # 群友福利：给全群注册用户发金币
                    coins = random.randint(CompareAudience.GROUP_BONUS_COINS_MIN, CompareAudience.GROUP_BONUS_COINS_MAX)
                    group_data = self.get_group_data(group_id)
                    beneficiaries = 0
                    for uid, udata in group_data.items():
                        if uid.startswith('_') or uid == 'plugin_enabled' or not isinstance(udata, dict):
                            continue
                        self.modify_coins_cached(group_id, uid, coins)
                        beneficiaries += 1
                    audience_text = random.choice(self.niuniu_texts['compare'].get('group_bonus', ['🎁 【群友福利】全群{beneficiaries}人每人获得{coins}金币！'])).format(
                        coins=coins, beneficiaries=beneficiaries, count=len(group_compares)
                    )
                else:  # group_penalty
                    # 群友惩罚：全群注册用户减长度
                    penalty = random.randint(CompareAudience.GROUP_PENALTY_LENGTH_MIN, CompareAudience.GROUP_PENALTY_LENGTH_MAX)
                    group_data = self.get_group_data(group_id)
                    victims = 0
                    for uid, udata in group_data.items():
                        if uid.startswith('_') or uid == 'plugin_enabled' or not isinstance(udata, dict):
                            continue
                        self.update_user_data(group_id, uid, {'length': udata.get('length', 0) - penalty})
                        victims += 1
                    audience_text = random.choice(self.niuniu_texts['compare'].get('group_penalty', ['💀 【群友遭殃】全群{victims}人每人-{penalty}cm！'])).format(
                        penalty=penalty, victims=victims, count=len(group_compares)
                    )

                result_msg.append(audience_text)
                # 更新显示（仅长度变化时更新）
                if effect_type in ('bonus_length', 'penalty_length', 'group_penalty'):
                    final_user = self.get_user_data(group_id, user_id)
                    final_target = self.get_user_data(group_id, target_id)
                    result_msg[2] = f"🗡️ {nickname}: {self.format_length(old_u_len)} → {self.format_length(final_user['length'])}"
                    result_msg[3] = f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} → {self.format_length(final_target['length'])}"

            # ===== 保险理赔检查 =====
            final_user = self.get_user_data(group_id, user_id)
            final_target = self.get_user_data(group_id, target_id)

            # 检查用户的保险（用户输了的情况）
            user_length_loss = max(0, old_u_len - final_user['length'])
            user_insurance = self.check_insurance_claim(
                group_id, user_id, nickname, length_loss=user_length_loss
            )
            if user_insurance['triggered']:
                result_msg.append(user_insurance['message'])

            # 检查目标的保险（目标输了的情况）
            target_length_loss = max(0, old_t_len - final_target['length'])
            target_insurance = self.check_insurance_claim(
                group_id, target_id, final_target['nickname'], length_loss=target_length_loss
            )
            if target_insurance['triggered']:
                result_msg.append(target_insurance['message'])

            # ===== 寄生牛牛检查 =====
            # 检查用户的寄生牛牛触发（用户赢了的情况）
            user_length_gain = max(0, final_user['length'] - old_u_len)
            if user_length_gain > 0:
                parasite_msgs = self._check_and_trigger_parasite(group_id, user_id, user_length_gain, processed_ids=set())
                result_msg.extend(parasite_msgs)

            # 检查目标的寄生牛牛触发（目标赢了的情况）
            target_length_gain = max(0, final_target['length'] - old_t_len)
            if target_length_gain > 0:
                parasite_msgs = self._check_and_trigger_parasite(group_id, target_id, target_length_gain, processed_ids=set())
                result_msg.extend(parasite_msgs)

            # ===== 含笑五步癫触发：只有主动发起命令的人才触发 =====
            huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
            result_msg.extend(huagu_msgs)

            # 股市钩子 - 用赢家的增益作为变化量
            compare_change = user_length_gain if user_length_gain > 0 else -target_length_gain
            stock_msg = stock_hook(group_id, nickname, event_type="compare", length_change=compare_change)
            if stock_msg:
                result_msg.append(stock_msg)

                yield event.plain_result("\n".join(result_msg))
        finally:
            # 保存缓存的数据（使用锁保护）
            await self._end_data_cache_async()

    # 负数牛牛缠绕因祸得福文案
    NEGATIVE_TANGLE_BLESSING_TEXTS = [
        "🎭 等等...负数减半是往0靠近？因祸得福！",
        "🤡 缠绕把负能量甩掉了一半！",
        "🌀 「负负得...少负？」数学老师哭了",
        "😂 本想互相伤害，负数却偷偷回血！",
        "🎪 负数牛牛：谢谢缠绕，拉我一把！",
        "🃏 命运的玩笑：想减半却加倍快乐！",
        "✨ 缠绕净化了负能量！",
        "🦠 软成一团反而把负数挤出去了！",
        "🎰 缠绕对负数牛牛是buff！",
        "💫 缠绕：「负数？帮你减负！」",
    ]

    async def _handle_halving_event(self, group_id, user_id, target_id, nickname, target_nickname, user_items, target_items, result_msg):
        """处理减半事件，使用效果系统"""
        user_data = self.get_user_data(group_id, user_id)
        target_data = self.get_user_data(group_id, target_id)
        original_user_len = user_data['length']
        original_target_len = target_data['length']

        # 先执行减半
        self.update_user_data(group_id, user_id, {'length': original_user_len // 2})
        self.update_user_data(group_id, target_id, {'length': original_target_len // 2})

        # 检查负数牛牛因祸得福
        if original_user_len < 0:
            blessing_text = random.choice(self.NEGATIVE_TANGLE_BLESSING_TEXTS)
            result_msg.append(f"🍀 {nickname}: {blessing_text} ({original_user_len}→{original_user_len // 2}cm)")
        if original_target_len < 0:
            blessing_text = random.choice(self.NEGATIVE_TANGLE_BLESSING_TEXTS)
            result_msg.append(f"🍀 {target_nickname}: {blessing_text} ({original_target_len}→{original_target_len // 2}cm)")

        # 检查用户的妙脆角
        ctx_user = EffectContext(
            group_id=group_id,
            user_id=user_id,
            nickname=nickname,
            user_data=user_data,
            user_length=original_user_len
        )
        ctx_user = self.effects.trigger(EffectTrigger.ON_HALVING, ctx_user, user_items)

        if ctx_user.prevent_halving:
            self.update_user_data(group_id, user_id, {'length': original_user_len})
            result_msg.extend(ctx_user.messages)
            self.effects.consume_items(group_id, user_id, ctx_user.items_to_consume)

        # 检查目标的妙脆角
        ctx_target = EffectContext(
            group_id=group_id,
            user_id=target_id,
            nickname=target_nickname,
            user_data=target_data,
            user_length=original_target_len
        )
        ctx_target = self.effects.trigger(EffectTrigger.ON_HALVING, ctx_target, target_items)

        if ctx_target.prevent_halving:
            self.update_user_data(group_id, target_id, {'length': original_target_len})
            result_msg.extend(ctx_target.messages)
            self.effects.consume_items(group_id, target_id, ctx_target.items_to_consume)

        yield None  # Generator placeholder

    async def _robbery(self, event):
        """牛牛抢劫功能 - 尝试抢劫目标的金币"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 获取自身数据
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['dajiao']['not_registered'].format(nickname=nickname))
            return

        # 解析目标
        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result("❌ 请@要抢劫的牛牛！用法：牛牛抢劫 @目标")
            return

        if target_id == user_id:
            yield event.plain_result("❌ 不能抢劫自己！")
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result("❌ 该用户大概是没有牛牛的！")
            return

        # 检查目标是否有金币（先检查，避免浪费冷却）
        target_coins = self.shop.get_user_coins(group_id, target_id)
        if target_coins <= 0:
            yield event.plain_result(f"❌ {target_data['nickname']} 一分钱都没有，抢个寂寞...")
            return

        # 冷却检查
        last_actions = self._load_last_actions()
        robbery_records = last_actions.setdefault(group_id, {}).setdefault(user_id, {}).setdefault('robbery', {})
        last_robbery = robbery_records.get(target_id, 0)
        on_cooldown, remaining = self.check_cooldown(last_robbery, RobberyConfig.COOLDOWN)
        if on_cooldown:
            mins = int(remaining // 60) + 1
            yield event.plain_result(f"❌ 冷却中！还需要 {mins} 分钟才能再次抢劫 {target_data['nickname']}")
            return

        # 注意：冷却时间将在抢劫结束后更新（成功或失败都消耗冷却）

        # 获取双方数据用于胜负判定
        u_len = user_data['length']
        t_len = target_data['length']
        u_hardness = user_data['hardness']
        t_hardness = target_data['hardness']

        # 计算连胜/连败加成（复用比划的streak系统）
        win_streak = user_data.get('robbery_win_streak', 0)
        lose_streak = user_data.get('robbery_lose_streak', 0)
        streak_bonus = 0
        if win_streak >= CompareStreak.WIN_STREAK_THRESHOLD:
            streak_bonus += CompareStreak.WIN_STREAK_BONUS
        if lose_streak >= CompareStreak.LOSE_STREAK_THRESHOLD:
            streak_bonus += CompareStreak.LOSE_STREAK_BONUS

        # 使用通用胜负判定方法（完全复用比划逻辑）
        win_prob = self._calculate_win_probability(
            group_id, user_id, u_len, t_len,
            u_hardness, t_hardness, streak_bonus
        )

        # 执行判定
        is_win = random.random() < win_prob

        # 更新冷却时间（成功或失败都消耗冷却）
        current_time = time.time()
        robbery_records[target_id] = current_time
        self.update_last_actions(last_actions)

        # 更新连胜/连败
        if is_win:
            new_win_streak = win_streak + 1
            new_lose_streak = 0
        else:
            new_win_streak = 0
            new_lose_streak = lose_streak + 1

        self.update_user_data(group_id, user_id, {
            'robbery_win_streak': new_win_streak,
            'robbery_lose_streak': new_lose_streak
        })

        if not is_win:
            # 抢劫失败 - 使用配置中的失败文本
            fail_text = random.choice(RobberyConfig.ROBBERY_FAIL_TEXTS).format(
                robber=nickname,
                victim=target_data['nickname']
            )
            # 添加调试信息
            debug_info = f"\n📊 胜率: {win_prob:.1%} | ⏰ CD已更新: {RobberyConfig.COOLDOWN//60}分钟"
            yield event.plain_result(fail_text + debug_info)
            # 含笑五步癫触发（抢劫失败也算行动）
            huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
            for msg_text in huagu_msgs:
                yield event.plain_result(msg_text)
            return

        # === 抢劫成功！===

        # 选择抢劫金额档位
        rand = random.random()
        cumulative_prob = 0
        robbery_percent = 0.05  # 默认5%

        for min_pct, max_pct, prob in RobberyConfig.ROBBERY_AMOUNT_TIERS:
            cumulative_prob += prob
            if rand < cumulative_prob:
                robbery_percent = random.uniform(min_pct, max_pct)
                break

        # 计算抢劫金额
        robbery_amount = int(target_coins * robbery_percent)
        if robbery_amount <= 0:
            robbery_amount = 1  # 至少抢1枚

        # === 检查目标的防护道具（在打斗之前检查） ===
        protection_msg = []
        actual_victim_id = target_id
        actual_victim_name = target_data['nickname']
        actual_victim_data = target_data

        # 1. 检查护盾（优先级最高，完全抵挡抢劫和打斗）
        target_shield = target_data.get('shield_charges', 0)
        if target_shield > 0:
            # 护盾抵挡抢劫（包括打斗）
            self.update_user_data(group_id, target_id, {
                'shield_charges': target_shield - 1
            })
            result_lines = [
                "💰 ══ 牛牛抢劫结果 ══ 💰",
                f"🎯 {nickname} 试图抢劫 {target_data['nickname']}！",
                "",
                f"🛡️ {target_data['nickname']} 的护盾完全抵挡了抢劫！",
                f"📊 护盾剩余：{target_shield - 1} 层",
                f"💨 {nickname} 空手而归，连打斗都没发生...",
                "═══════════════════"
            ]
            yield event.plain_result("\n".join(result_lines))
            return

        # 2. 检查祸水东引（护盾之后检查，打斗伤害也转嫁）
        target_transfer = target_data.get('risk_transfer_charges', 0)
        if target_transfer > 0 and robbery_amount >= 50:  # 只有损失>=50才触发转嫁
            # 找一个随机群友来承担
            all_users = self.get_group_data(group_id)
            valid_targets = [
                (uid, data) for uid, data in all_users.items()
                if isinstance(data, dict) and 'length' in data
                and uid != target_id and uid != user_id  # 排除原目标和抢劫者
            ]
            if valid_targets:
                new_victim_id, new_victim_data = random.choice(valid_targets)
                new_victim_name = new_victim_data.get('nickname', new_victim_id)
                new_victim_coins = self.shop.get_user_coins(group_id, new_victim_id)

                # 消耗转嫁次数
                self.update_user_data(group_id, target_id, {
                    'risk_transfer_charges': target_transfer - 1
                })

                # 更新实际受害者（打斗伤害也转嫁给新目标）
                actual_victim_id = new_victim_id
                actual_victim_name = new_victim_name
                actual_victim_data = new_victim_data

                # 基于新目标重新计算抢劫金额（按比例，防止弱者被抢巨额固定金额）
                old_robbery_amount = robbery_amount
                robbery_amount = int(new_victim_coins * robbery_percent)
                if robbery_amount <= 0:
                    robbery_amount = 1

                protection_msg.append(f"🔄 {target_data['nickname']} 触发祸水东引！抢劫转嫁给 {new_victim_name}！（剩余{target_transfer - 1}次）")
                protection_msg.append(f"📊 原抢{old_robbery_amount}→重算{robbery_amount}（{new_victim_name}的{robbery_percent*100:.1f}%）")

        # === 打斗判定（50%概率，基于实际受害者） ===
        is_fight = random.random() < RobberyConfig.FIGHT_CHANCE
        fight_info = []

        # 获取实际受害者的长度和硬度
        v_len = actual_victim_data.get('length', 0)
        v_hardness = actual_victim_data.get('hardness', 1)

        if is_fight:
            # 触发打斗！双方都会损失长度和硬度
            rand = random.random()
            cumulative_prob = 0
            damage_percent = 0.05  # 默认5%

            for min_pct, max_pct, prob in RobberyConfig.FIGHT_DAMAGE_TIERS:
                cumulative_prob += prob
                if rand < cumulative_prob:
                    damage_percent = random.uniform(min_pct, max_pct)
                    break

            # 抢劫者损失
            robber_length_loss = int(abs(u_len) * damage_percent)
            robber_hardness_loss = int(u_hardness * damage_percent)
            if robber_hardness_loss == 0 and damage_percent > 0:
                robber_hardness_loss = 1

            # 实际受害者损失（可能是转嫁后的新目标）
            victim_length_loss = int(abs(v_len) * damage_percent)
            victim_hardness_loss = int(v_hardness * damage_percent)
            if victim_hardness_loss == 0 and damage_percent > 0:
                victim_hardness_loss = 1

            # 应用损失
            new_robber_len = u_len - robber_length_loss
            new_robber_hard = max(1, u_hardness - robber_hardness_loss)
            new_victim_len = v_len - victim_length_loss
            new_victim_hard = max(1, v_hardness - victim_hardness_loss)

            # 更新数据
            self.update_user_data(group_id, user_id, {
                'length': new_robber_len,
                'hardness': new_robber_hard
            })
            self.update_user_data(group_id, actual_victim_id, {
                'length': new_victim_len,
                'hardness': new_victim_hard
            })

            # 记录打斗信息
            fight_text = random.choice(RobberyConfig.FIGHT_TEXTS)
            fight_info.append(fight_text)
            fight_info.append(f"💔 {nickname}：-{robber_length_loss}cm长度, -{robber_hardness_loss}硬度")
            fight_info.append(f"💔 {actual_victim_name}：-{victim_length_loss}cm长度, -{victim_hardness_loss}硬度")
            fight_info.append(f"📊 损失比例：{damage_percent*100:.1f}%")
        else:
            # 不打斗，一方投降
            surrender_text = random.choice(RobberyConfig.SURRENDER_TEXTS_WIN).format(
                victim=actual_victim_name,
                robber=nickname
            )
            fight_info.append(surrender_text)

        # === 触发抢劫后事件 ===
        # 选择事件
        event_rand = random.random()
        cumulative_prob = 0
        selected_event = None

        for event_id, prob, desc_template, params in RobberyConfig.ROBBERY_EVENTS:
            cumulative_prob += prob
            if event_rand < cumulative_prob:
                selected_event = (event_id, desc_template, params)
                break

        if not selected_event:
            # 默认完美逃脱
            selected_event = ('perfect_escape', '🏃 完美逃脱！没人发现你！', {'keep_ratio': 1.0})

        event_id, desc_template, event_params = selected_event

        # 处理不同事件类型
        final_gain = 0
        return_to_victim = 0
        event_desc = ""

        if 'keep_ratio' in event_params:
            # 固定保留比例
            keep_ratio = event_params['keep_ratio']
            final_gain = int(robbery_amount * keep_ratio)
            event_desc = desc_template

        elif 'return_min' in event_params:
            # 归还部分给受害者
            return_ratio = random.uniform(event_params['return_min'], event_params['return_max'])
            return_to_victim = int(robbery_amount * return_ratio)
            final_gain = robbery_amount - return_to_victim
            return_pct = int(return_ratio * 100)
            event_desc = desc_template.format(return_pct=return_pct, victim=target_data['nickname'])

        elif 'loss_min' in event_params:
            # 损失大部分（金币消失）
            loss_ratio = random.uniform(event_params['loss_min'], event_params['loss_max'])
            loss_amount = int(robbery_amount * loss_ratio)
            final_gain = robbery_amount - loss_amount
            loss_pct = int(loss_ratio * 100)
            event_desc = desc_template.format(loss_pct=loss_pct)

        elif 'bonus_min' in event_params:
            # 额外收获
            bonus_ratio = random.uniform(event_params['bonus_min'], event_params['bonus_max'])
            bonus_amount = int(robbery_amount * bonus_ratio)
            final_gain = robbery_amount + bonus_amount
            bonus_pct = int(bonus_ratio * 100)
            event_desc = desc_template.format(bonus_pct=bonus_pct)

        else:
            # 未知事件类型，默认完美逃脱
            final_gain = robbery_amount
            event_desc = "🏃 完美逃脱！（未知事件类型，请联系管理员）"
            print(f"[WARNING] Unknown robbery event type: {event_id}, params: {event_params}")

        # 执行金币转移（使用实际受害者ID）
        self.shop.modify_coins(group_id, actual_victim_id, -robbery_amount)  # 扣除受害者金币
        if return_to_victim > 0:
            self.shop.modify_coins(group_id, actual_victim_id, return_to_victim)  # 归还部分
        if final_gain > 0:
            self.shop.modify_coins(group_id, user_id, final_gain)  # 给抢劫者

        # 构建结果消息
        result_lines = [
            "💰 ══ 牛牛抢劫结果 ══ 💰",
            f"🎯 {nickname} 抢劫 {actual_victim_name} 成功！",
            f"💵 抢到：{robbery_amount} 枚金币（{robbery_percent*100:.1f}%）",
            ""
        ]

        # 添加祸水东引信息
        if protection_msg:
            result_lines.extend(protection_msg)
            result_lines.append("")

        # 添加打斗信息
        if fight_info:
            result_lines.extend(fight_info)
            result_lines.append("")

        # 添加抢劫后事件
        result_lines.append(f"🎲 {event_desc}")
        result_lines.append("")

        if return_to_victim > 0:
            result_lines.append(f"↩️ 归还给 {actual_victim_name}：{return_to_victim} 枚")
        if final_gain > 0:
            result_lines.append(f"✅ {nickname} 最终获得：{final_gain} 枚金币")
        elif final_gain == 0:
            result_lines.append(f"😭 {nickname} 最终什么都没得到...")

        # 连胜提示
        if new_win_streak >= 3:
            result_lines.append(f"🔥 抢劫{new_win_streak}连胜！")

        result_lines.append("═══════════════════")

        # 股市钩子 - 抢劫金币变动影响股市
        stock_msg = stock_hook(group_id, nickname, event_type="compare", coins_change=final_gain)
        if stock_msg:
            result_lines.append(stock_msg)

        yield event.plain_result("\n".join(result_lines))

        # 含笑五步癫触发（只有主动发起命令的人才触发）
        huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
        for msg_text in huagu_msgs:
            yield event.plain_result(msg_text)

    async def _bainian(self, event):
        """牛牛拜年 - 春节互动功能"""
        from niuniu_config import BainianConfig

        # 检查是否是"所有人"批量模式
        msg = event.message_str.strip()
        bainian_suffix = msg[len("牛牛拜年"):].strip()
        if "所有人" in bainian_suffix or "全体" in bainian_suffix:
            async for result in self._bainian_all(event):
                yield result
            return

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 获取自身数据
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['bainian']['not_registered'].format(nickname=nickname))
            return

        # 解析目标
        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result(self.niuniu_texts['bainian']['no_target'])
            return

        if target_id == user_id:
            yield event.plain_result(self.niuniu_texts['bainian']['self_bainian'])
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result(self.niuniu_texts['bainian']['target_not_registered'])
            return

        # 获取当前日期（上海时区）
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        # 检查每日重置
        bainian_date = user_data.get('bainian_date', '')
        if bainian_date != today:
            self.update_user_data(group_id, user_id, {
                'bainian_date': today,
                'bainian_count': 0,
                'bainian_targets': [],
            })
            user_data = self.get_user_data(group_id, user_id)

        bainian_count = user_data.get('bainian_count', 0)
        bainian_targets = user_data.get('bainian_targets', [])

        # 检查每日上限
        if bainian_count >= BainianConfig.DAILY_LIMIT:
            yield event.plain_result(self.niuniu_texts['bainian']['daily_limit'].format(count=bainian_count))
            return

        # 检查是否已拜访过该目标
        if target_id in bainian_targets:
            yield event.plain_result(self.niuniu_texts['bainian']['already_visited'].format(target_name=target_data['nickname']))
            return

        # === 计算基础奖励 ===
        sender_length = random.randint(BainianConfig.SENDER_LENGTH_MIN, BainianConfig.SENDER_LENGTH_MAX)
        sender_coins = random.randint(BainianConfig.SENDER_COINS_MIN, BainianConfig.SENDER_COINS_MAX)
        sender_hardness = 1 if random.random() < BainianConfig.SENDER_HARDNESS_CHANCE else 0

        target_length = random.randint(BainianConfig.TARGET_LENGTH_MIN, BainianConfig.TARGET_LENGTH_MAX)
        target_coins = random.randint(BainianConfig.TARGET_COINS_MIN, BainianConfig.TARGET_COINS_MAX)
        target_hardness = 1 if random.random() < BainianConfig.TARGET_HARDNESS_CHANCE else 0

        # === 特殊事件 ===
        event_text = ""
        event_extra = []
        special_triggered = False
        chosen_event = None
        swap_lengths = False  # 牛转乾坤标记

        if random.random() < BainianConfig.SPECIAL_EVENT_CHANCE:
            # 按权重选择事件
            total_weight = sum(e['weight'] for e in BainianConfig.SPECIAL_EVENTS)
            rand_val = random.random() * total_weight
            cumulative = 0
            for evt in BainianConfig.SPECIAL_EVENTS:
                cumulative += evt['weight']
                if rand_val < cumulative:
                    chosen_event = evt
                    break

            if chosen_event:
                special_triggered = True
                eid = chosen_event['id']

                if eid == 'niuqi_chongtian':
                    extra_length = random.randint(chosen_event['both_length_min'], chosen_event['both_length_max'])
                    extra_coins = random.randint(chosen_event['both_coins_min'], chosen_event['both_coins_max'])
                    sender_length += extra_length
                    sender_coins += extra_coins
                    target_length += extra_length
                    target_coins += extra_coins
                    event_text = self.niuniu_texts['bainian']['event_niuqi']
                    event_extra.append(f"   双方额外：+{extra_length}cm, +{extra_coins}金币")

                elif eid == 'hongbao_yu':
                    extra_coins = random.randint(chosen_event['both_coins_min'], chosen_event['both_coins_max'])
                    sender_coins += extra_coins
                    target_coins += extra_coins
                    event_text = self.niuniu_texts['bainian']['event_hongbao']
                    event_extra.append(f"   双方额外：+{extra_coins}金币")

                elif eid == 'nianshou_laixi':
                    length_loss = random.randint(chosen_event['both_length_min'], chosen_event['both_length_max'])
                    hardness_gain = random.randint(chosen_event['both_hardness_min'], chosen_event['both_hardness_max'])
                    sender_length += length_loss  # 负数
                    target_length += length_loss
                    sender_hardness += hardness_gain
                    target_hardness += hardness_gain
                    event_text = self.niuniu_texts['bainian']['event_nianshou']
                    event_extra.append(f"   双方：{length_loss}cm, +{hardness_gain}硬度")

                elif eid == 'fuxing_gaozhao':
                    sender_length *= 2
                    sender_coins *= 2
                    sender_hardness *= 2
                    event_text = self.niuniu_texts['bainian']['event_fuxing'].format(sender=nickname)

                elif eid == 'bai_cuo_men':
                    sender_length = 0
                    sender_coins = 0
                    sender_hardness = 0
                    target_length *= 2
                    target_coins *= 2
                    target_hardness *= 2
                    event_text = self.niuniu_texts['bainian']['event_baicuomen'].format(
                        sender=nickname, target=target_data['nickname']
                    )

                elif eid == 'caishen_dao':
                    extra_coins = random.randint(chosen_event['both_coins_min'], chosen_event['both_coins_max'])
                    sender_coins += extra_coins
                    target_coins += extra_coins
                    event_text = self.niuniu_texts['bainian']['event_caishen']
                    event_extra.append(f"   双方额外：+{extra_coins}金币")

                elif eid == 'tuanyuan_fan':
                    all_users_data = self.get_group_data(group_id)
                    valid_users = [
                        (uid, data) for uid, data in all_users_data.items()
                        if isinstance(data, dict) and 'length' in data
                        and uid != user_id and uid != target_id
                    ]
                    count = min(
                        random.randint(chosen_event['group_count_min'], chosen_event['group_count_max']),
                        len(valid_users)
                    )
                    if count > 0:
                        lucky_users = random.sample(valid_users, count)
                        feast_names = []
                        for uid, udata in lucky_users:
                            gain = random.randint(chosen_event['group_length_min'], chosen_event['group_length_max'])
                            self.update_user_data(group_id, uid, {
                                'length': udata['length'] + gain
                            })
                            feast_names.append(f"{udata['nickname']}(+{gain}cm)")
                        event_text = self.niuniu_texts['bainian']['event_tuanyuan'].format(
                            sender=nickname, target=target_data['nickname'], count=count
                        )
                        event_extra.append(f"   蹭饭牛友：{'、'.join(feast_names)}")
                    else:
                        special_triggered = False

                elif eid == 'niu_zhuan_qiankun':
                    s_len = user_data['length']
                    t_len = target_data['length']
                    if abs(s_len - t_len) > chosen_event['length_diff_threshold']:
                        swap_lengths = True
                        event_text = self.niuniu_texts['bainian']['event_niuzhuan'].format(
                            sender=nickname, target=target_data['nickname']
                        )
                        event_extra.append(f"   {nickname}: {self.format_length(s_len)} → {self.format_length(t_len)}")
                        event_extra.append(f"   {target_data['nickname']}: {self.format_length(t_len)} → {self.format_length(s_len)}")
                    else:
                        special_triggered = False

                elif eid == 'baozu_jingniu':
                    length_loss = random.randint(chosen_event['both_length_min'], chosen_event['both_length_max'])
                    sender_length += length_loss
                    target_length += length_loss
                    event_text = self.niuniu_texts['bainian']['event_baozu']
                    event_extra.append(f"   双方：{length_loss}cm")

                elif eid == 'yasuiqian':
                    sender_total_coins = user_data.get('coins', 0)
                    yasuiqian = int(sender_total_coins * chosen_event['percent'])
                    yasuiqian = max(chosen_event['min_amount'], min(yasuiqian, chosen_event['max_amount']))
                    sender_coins -= yasuiqian
                    target_coins += yasuiqian
                    event_text = self.niuniu_texts['bainian']['event_yasuiqian'].format(
                        sender=nickname, target=target_data['nickname'], amount=yasuiqian
                    )

        # === 应用奖励 ===
        # 更新拜年者数据
        if swap_lengths:
            # 牛转乾坤：互换长度，然后在互换后的基础上加奖励
            new_sender_length = target_data['length'] + sender_length
            new_target_length = user_data['length'] + target_length
        else:
            new_sender_length = user_data['length'] + sender_length
            new_target_length = target_data['length'] + target_length

        new_sender_hardness = min(100, user_data['hardness'] + sender_hardness)
        new_sender_coins = round(user_data.get('coins', 0) + sender_coins)

        sender_updates = {
            'length': new_sender_length,
            'hardness': new_sender_hardness,
            'coins': new_sender_coins,
            'bainian_date': today,
            'bainian_count': bainian_count + 1,
            'bainian_targets': bainian_targets + [target_id],
        }
        self.update_user_data(group_id, user_id, sender_updates)

        # 更新被拜者数据
        new_target_hardness = min(100, target_data['hardness'] + target_hardness)
        new_target_coins = round(target_data.get('coins', 0) + target_coins)
        self.update_user_data(group_id, target_id, {
            'length': new_target_length,
            'hardness': new_target_hardness,
            'coins': new_target_coins,
        })

        # === 集五福 ===
        fu_text = ""
        fu_complete_text = ""

        # 已集齐过五福的玩家不再掉落
        user_data_fu_check = self.get_user_data(group_id, user_id)
        fu_already_completed = user_data_fu_check.get('bainian_fu_completed', False)

        if not fu_already_completed and random.random() < BainianConfig.FU_DROP_CHANCE:
            # 按权重选择福卡
            total_fu_weight = sum(f['weight'] for f in BainianConfig.FU_CARDS)
            rand_fu = random.random() * total_fu_weight
            cumulative_fu = 0
            chosen_fu = None
            for fu in BainianConfig.FU_CARDS:
                cumulative_fu += fu['weight']
                if rand_fu < cumulative_fu:
                    chosen_fu = fu
                    break

            if chosen_fu:
                fu_name = chosen_fu['name']
                fu_emoji = chosen_fu['emoji']

                user_data_fresh = self.get_user_data(group_id, user_id)
                items = user_data_fresh.get('items', {})

                if items.get(fu_name, 0) > 0:
                    # 重复的福，转化为金币
                    dup_coins = BainianConfig.FU_DUPLICATE_COINS
                    self.update_user_data(group_id, user_id, {
                        'coins': round(user_data_fresh.get('coins', 0) + dup_coins)
                    })
                    fu_text = self.niuniu_texts['bainian']['fu_duplicate'].format(
                        fu_emoji=fu_emoji, fu_name=fu_name, coins=dup_coins
                    )
                else:
                    # 新的福！
                    items[fu_name] = 1
                    reward_text = ""
                    reward_updates = {'items': items}
                    if 'reward_coins' in chosen_fu:
                        reward_updates['coins'] = round(user_data_fresh.get('coins', 0) + chosen_fu['reward_coins'])
                        reward_text = f"+{chosen_fu['reward_coins']}金币"
                    if 'reward_hardness' in chosen_fu:
                        reward_updates['hardness'] = min(100, user_data_fresh.get('hardness', 1) + chosen_fu['reward_hardness'])
                        reward_text = f"+{chosen_fu['reward_hardness']}硬度"
                    if 'reward_length' in chosen_fu:
                        reward_updates['length'] = user_data_fresh.get('length', 0) + chosen_fu['reward_length']
                        reward_text = f"+{chosen_fu['reward_length']}cm"

                    self.update_user_data(group_id, user_id, reward_updates)

                    fu_text = self.niuniu_texts['bainian']['fu_drop'].format(
                        fu_emoji=fu_emoji, fu_name=fu_name, reward_text=reward_text
                    )

                    # 检查是否集齐五福
                    user_data_check = self.get_user_data(group_id, user_id)
                    items_check = user_data_check.get('items', {})
                    all_fu_names = [f['name'] for f in BainianConfig.FU_CARDS]

                    if all(items_check.get(fn, 0) > 0 for fn in all_fu_names):
                        # 集齐五福！发放大奖并清除
                        for fn in all_fu_names:
                            if fn in items_check:
                                del items_check[fn]

                        # 计算50%总资产奖励（金币 + 股票市值）
                        current_coins = user_data_check.get('coins', 0)
                        stock = NiuniuStock.get()
                        user_shares = stock.get_holdings(group_id, user_id)
                        stock_price = stock.get_price(group_id)
                        stock_value = user_shares * stock_price
                        total_asset = max(0, current_coins) + stock_value
                        asset_bonus = round(total_asset * BainianConfig.FU_ASSET_BONUS_PERCENT)
                        total_coin_reward = BainianConfig.FU_COMPLETE_COINS + asset_bonus

                        self.update_user_data(group_id, user_id, {
                            'items': items_check,
                            'length': user_data_check['length'] + BainianConfig.FU_COMPLETE_LENGTH,
                            'hardness': min(100, user_data_check['hardness'] + BainianConfig.FU_COMPLETE_HARDNESS),
                            'coins': round(current_coins + total_coin_reward),
                            'bainian_fu_completed': True,
                        })

                        fu_complete_text = self.niuniu_texts['bainian']['fu_complete'].format(
                            length=BainianConfig.FU_COMPLETE_LENGTH,
                            hardness=BainianConfig.FU_COMPLETE_HARDNESS,
                            base_coins=BainianConfig.FU_COMPLETE_COINS,
                            asset_bonus=asset_bonus,
                            total_coins=total_coin_reward,
                        )

        # === 构建输出 ===
        result_lines = ["🧧 ══ 牛牛拜年 ══ 🧧"]
        result_lines.append(random.choice(self.niuniu_texts['bainian']['success']).format(
            sender=nickname, target=target_data['nickname']
        ))
        result_lines.append("")

        # 特殊事件
        if special_triggered and event_text:
            result_lines.append(event_text)
            result_lines.extend(event_extra)
            result_lines.append("")

        # 奖励总结 - 拜年者
        sender_parts = []
        if sender_length != 0:
            sender_parts.append(f"{'+' if sender_length > 0 else ''}{sender_length}cm")
        if sender_coins != 0:
            sender_parts.append(f"{'+' if sender_coins > 0 else ''}{sender_coins}金币")
        if sender_hardness > 0:
            sender_parts.append(f"+{sender_hardness}硬度")
        if sender_parts:
            result_lines.append(f"📦 {nickname}：{', '.join(sender_parts)}")
        else:
            result_lines.append(f"📦 {nickname}：（空手而归~）")

        # 奖励总结 - 被拜者
        target_parts = []
        if target_length != 0:
            target_parts.append(f"{'+' if target_length > 0 else ''}{target_length}cm")
        if target_coins != 0:
            target_parts.append(f"{'+' if target_coins > 0 else ''}{target_coins}金币")
        if target_hardness > 0:
            target_parts.append(f"+{target_hardness}硬度")
        if target_parts:
            result_lines.append(f"🎁 {target_data['nickname']}：{', '.join(target_parts)}")

        # 集福信息
        if fu_text:
            result_lines.append("")
            result_lines.append(fu_text)

        if fu_complete_text:
            result_lines.append("")
            result_lines.append(fu_complete_text)

        # 集福进度
        user_data_final = self.get_user_data(group_id, user_id)
        items_final = user_data_final.get('items', {})
        all_fu = BainianConfig.FU_CARDS
        progress_parts = []
        fu_count = 0
        for fu in all_fu:
            if items_final.get(fu['name'], 0) > 0:
                progress_parts.append(f"{fu['emoji']}✅")
                fu_count += 1
            else:
                progress_parts.append(f"{fu['emoji']}❌")

        if fu_count > 0:
            result_lines.append("")
            result_lines.append(self.niuniu_texts['bainian']['fu_progress'].format(
                progress=" ".join(progress_parts), count=fu_count
            ))

        # 今日拜年次数
        result_lines.append(self.niuniu_texts['bainian']['remaining'].format(
            count=bainian_count + 1, limit=BainianConfig.DAILY_LIMIT
        ))

        result_lines.append("═══════════════════")

        yield event.plain_result("\n".join(result_lines))

        # 含笑五步癫触发
        huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
        for msg_text in huagu_msgs:
            yield event.plain_result(msg_text)

    async def _bainian_all(self, event):
        """牛牛拜年 所有人 - 一次性拜年到今日上限并汇总结算"""
        from niuniu_config import BainianConfig

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['bainian']['not_registered'].format(nickname=nickname))
            return

        # 获取当前日期（上海时区）
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).strftime('%Y-%m-%d')

        # 检查每日重置
        bainian_date = user_data.get('bainian_date', '')
        if bainian_date != today:
            self.update_user_data(group_id, user_id, {
                'bainian_date': today,
                'bainian_count': 0,
                'bainian_targets': [],
            })
            user_data = self.get_user_data(group_id, user_id)

        bainian_count = user_data.get('bainian_count', 0)
        bainian_targets = list(user_data.get('bainian_targets', []))

        if bainian_count >= BainianConfig.DAILY_LIMIT:
            yield event.plain_result(self.niuniu_texts['bainian']['daily_limit'].format(count=bainian_count))
            return

        # 查找所有可拜年的目标（已注册、非自己、今天未拜访过）
        all_targets = []
        for uid, udata in group_data.items():
            if (isinstance(udata, dict) and 'length' in udata
                    and uid != user_id and uid not in bainian_targets):
                all_targets.append(uid)

        if not all_targets:
            yield event.plain_result("❌ 群里没有可以拜年的牛友了！今天已经拜遍了~")
            return

        random.shuffle(all_targets)
        remaining = BainianConfig.DAILY_LIMIT - bainian_count
        targets_to_visit = all_targets[:remaining]

        # 记录初始状态，用于计算总变化
        initial_data = self.get_user_data(group_id, user_id)
        initial_length = initial_data['length']
        initial_hardness = initial_data['hardness']
        initial_coins = initial_data.get('coins', 0)

        # 结算累计
        visited_count = 0
        special_events_summary = []
        fu_cards_obtained = []
        fu_complete_text = ""
        visit_details = []

        for target_id in targets_to_visit:
            # 每次迭代重新读取最新数据
            user_data = self.get_user_data(group_id, user_id)
            target_data = self.get_user_data(group_id, target_id)
            if not target_data:
                continue

            target_name = target_data.get('nickname', target_id)

            # === 计算基础奖励 ===
            sender_length = random.randint(BainianConfig.SENDER_LENGTH_MIN, BainianConfig.SENDER_LENGTH_MAX)
            sender_coins = random.randint(BainianConfig.SENDER_COINS_MIN, BainianConfig.SENDER_COINS_MAX)
            sender_hardness = 1 if random.random() < BainianConfig.SENDER_HARDNESS_CHANCE else 0

            target_length = random.randint(BainianConfig.TARGET_LENGTH_MIN, BainianConfig.TARGET_LENGTH_MAX)
            target_coins = random.randint(BainianConfig.TARGET_COINS_MIN, BainianConfig.TARGET_COINS_MAX)
            target_hardness = 1 if random.random() < BainianConfig.TARGET_HARDNESS_CHANCE else 0

            # === 特殊事件 ===
            special_triggered = False
            chosen_event = None
            swap_lengths = False

            if random.random() < BainianConfig.SPECIAL_EVENT_CHANCE:
                total_weight = sum(e['weight'] for e in BainianConfig.SPECIAL_EVENTS)
                rand_val = random.random() * total_weight
                cumulative = 0
                for evt in BainianConfig.SPECIAL_EVENTS:
                    cumulative += evt['weight']
                    if rand_val < cumulative:
                        chosen_event = evt
                        break

                if chosen_event:
                    special_triggered = True
                    eid = chosen_event['id']

                    if eid == 'niuqi_chongtian':
                        extra_length = random.randint(chosen_event['both_length_min'], chosen_event['both_length_max'])
                        extra_coins = random.randint(chosen_event['both_coins_min'], chosen_event['both_coins_max'])
                        sender_length += extra_length
                        sender_coins += extra_coins
                        target_length += extra_length
                        target_coins += extra_coins

                    elif eid == 'hongbao_yu':
                        extra_coins = random.randint(chosen_event['both_coins_min'], chosen_event['both_coins_max'])
                        sender_coins += extra_coins
                        target_coins += extra_coins

                    elif eid == 'nianshou_laixi':
                        length_loss = random.randint(chosen_event['both_length_min'], chosen_event['both_length_max'])
                        hardness_gain = random.randint(chosen_event['both_hardness_min'], chosen_event['both_hardness_max'])
                        sender_length += length_loss
                        target_length += length_loss
                        sender_hardness += hardness_gain
                        target_hardness += hardness_gain

                    elif eid == 'fuxing_gaozhao':
                        sender_length *= 2
                        sender_coins *= 2
                        sender_hardness *= 2

                    elif eid == 'bai_cuo_men':
                        sender_length = 0
                        sender_coins = 0
                        sender_hardness = 0
                        target_length *= 2
                        target_coins *= 2
                        target_hardness *= 2

                    elif eid == 'caishen_dao':
                        extra_coins = random.randint(chosen_event['both_coins_min'], chosen_event['both_coins_max'])
                        sender_coins += extra_coins
                        target_coins += extra_coins

                    elif eid == 'tuanyuan_fan':
                        all_users_data = self.get_group_data(group_id)
                        valid_users = [
                            (uid, data) for uid, data in all_users_data.items()
                            if isinstance(data, dict) and 'length' in data
                            and uid != user_id and uid != target_id
                        ]
                        count = min(
                            random.randint(chosen_event['group_count_min'], chosen_event['group_count_max']),
                            len(valid_users)
                        )
                        if count > 0:
                            lucky_users = random.sample(valid_users, count)
                            for uid, udata in lucky_users:
                                gain = random.randint(chosen_event['group_length_min'], chosen_event['group_length_max'])
                                self.update_user_data(group_id, uid, {
                                    'length': udata['length'] + gain
                                })
                        else:
                            special_triggered = False

                    elif eid == 'niu_zhuan_qiankun':
                        s_len = user_data['length']
                        t_len = target_data['length']
                        if abs(s_len - t_len) > chosen_event['length_diff_threshold']:
                            swap_lengths = True
                        else:
                            special_triggered = False

                    elif eid == 'baozu_jingniu':
                        length_loss = random.randint(chosen_event['both_length_min'], chosen_event['both_length_max'])
                        sender_length += length_loss
                        target_length += length_loss

                    elif eid == 'yasuiqian':
                        sender_total_coins = user_data.get('coins', 0)
                        yasuiqian = int(sender_total_coins * chosen_event['percent'])
                        yasuiqian = max(chosen_event['min_amount'], min(yasuiqian, chosen_event['max_amount']))
                        sender_coins -= yasuiqian
                        target_coins += yasuiqian

            # 记录特殊事件
            if special_triggered and chosen_event:
                special_events_summary.append(f"{chosen_event['name']}→{target_name}")

            # === 应用奖励 ===
            if swap_lengths:
                new_sender_length = target_data['length'] + sender_length
                new_target_length = user_data['length'] + target_length
            else:
                new_sender_length = user_data['length'] + sender_length
                new_target_length = target_data['length'] + target_length

            new_sender_hardness = min(100, user_data['hardness'] + sender_hardness)
            new_sender_coins = round(user_data.get('coins', 0) + sender_coins)

            # 更新拜年追踪
            bainian_count += 1
            bainian_targets.append(target_id)

            sender_updates = {
                'length': new_sender_length,
                'hardness': new_sender_hardness,
                'coins': new_sender_coins,
                'bainian_date': today,
                'bainian_count': bainian_count,
                'bainian_targets': bainian_targets,
            }
            self.update_user_data(group_id, user_id, sender_updates)

            # 更新被拜者数据
            new_target_hardness = min(100, target_data['hardness'] + target_hardness)
            new_target_coins = round(target_data.get('coins', 0) + target_coins)
            self.update_user_data(group_id, target_id, {
                'length': new_target_length,
                'hardness': new_target_hardness,
                'coins': new_target_coins,
            })

            # 记录拜年明细
            detail_parts = []
            if swap_lengths:
                swap_delta = (target_data['length'] - user_data['length']) + sender_length
                detail_parts.append(f"🔄{'+' if swap_delta > 0 else ''}{swap_delta}cm")
            elif sender_length != 0:
                detail_parts.append(f"{'+' if sender_length > 0 else ''}{sender_length}cm")
            if sender_coins != 0:
                detail_parts.append(f"{'+' if sender_coins > 0 else ''}{sender_coins}💰")
            if sender_hardness > 0:
                detail_parts.append(f"+{sender_hardness}硬度")
            detail_str = ', '.join(detail_parts) if detail_parts else "空手而归"
            visit_details.append(f"  {target_name}：{detail_str}")

            visited_count += 1

            # === 集五福 ===
            user_data_fu = self.get_user_data(group_id, user_id)
            fu_already_completed = user_data_fu.get('bainian_fu_completed', False)

            if not fu_already_completed and random.random() < BainianConfig.FU_DROP_CHANCE:
                total_fu_weight = sum(f['weight'] for f in BainianConfig.FU_CARDS)
                rand_fu = random.random() * total_fu_weight
                cumulative_fu = 0
                chosen_fu = None
                for fu in BainianConfig.FU_CARDS:
                    cumulative_fu += fu['weight']
                    if rand_fu < cumulative_fu:
                        chosen_fu = fu
                        break

                if chosen_fu:
                    fu_name = chosen_fu['name']
                    fu_emoji = chosen_fu['emoji']

                    user_data_fresh = self.get_user_data(group_id, user_id)
                    items = user_data_fresh.get('items', {})

                    if items.get(fu_name, 0) > 0:
                        # 重复的福，转化为金币
                        dup_coins = BainianConfig.FU_DUPLICATE_COINS
                        self.update_user_data(group_id, user_id, {
                            'coins': round(user_data_fresh.get('coins', 0) + dup_coins)
                        })
                        fu_cards_obtained.append(f"  {fu_emoji}{fu_name}（重复，+{dup_coins}金币）")
                    else:
                        # 新的福！
                        items[fu_name] = 1
                        reward_text = ""
                        reward_updates = {'items': items}
                        if 'reward_coins' in chosen_fu:
                            reward_updates['coins'] = round(user_data_fresh.get('coins', 0) + chosen_fu['reward_coins'])
                            reward_text = f"+{chosen_fu['reward_coins']}金币"
                        if 'reward_hardness' in chosen_fu:
                            reward_updates['hardness'] = min(100, user_data_fresh.get('hardness', 1) + chosen_fu['reward_hardness'])
                            reward_text = f"+{chosen_fu['reward_hardness']}硬度"
                        if 'reward_length' in chosen_fu:
                            reward_updates['length'] = user_data_fresh.get('length', 0) + chosen_fu['reward_length']
                            reward_text = f"+{chosen_fu['reward_length']}cm"

                        self.update_user_data(group_id, user_id, reward_updates)
                        fu_cards_obtained.append(f"  {fu_emoji}{fu_name}（{reward_text}）")

                        # 检查是否集齐五福
                        user_data_check = self.get_user_data(group_id, user_id)
                        items_check = user_data_check.get('items', {})
                        all_fu_names = [f['name'] for f in BainianConfig.FU_CARDS]

                        if all(items_check.get(fn, 0) > 0 for fn in all_fu_names):
                            # 集齐五福！发放大奖并清除福卡
                            for fn in all_fu_names:
                                if fn in items_check:
                                    del items_check[fn]

                            # 计算50%总资产奖励（金币 + 股票市值）
                            current_coins = user_data_check.get('coins', 0)
                            stock = NiuniuStock.get()
                            user_shares = stock.get_holdings(group_id, user_id)
                            stock_price = stock.get_price(group_id)
                            stock_value = user_shares * stock_price
                            total_asset = max(0, current_coins) + stock_value
                            asset_bonus = round(total_asset * BainianConfig.FU_ASSET_BONUS_PERCENT)
                            total_coin_reward = BainianConfig.FU_COMPLETE_COINS + asset_bonus

                            self.update_user_data(group_id, user_id, {
                                'items': items_check,
                                'length': user_data_check['length'] + BainianConfig.FU_COMPLETE_LENGTH,
                                'hardness': min(100, user_data_check['hardness'] + BainianConfig.FU_COMPLETE_HARDNESS),
                                'coins': round(current_coins + total_coin_reward),
                                'bainian_fu_completed': True,
                            })

                            fu_complete_text = self.niuniu_texts['bainian']['fu_complete'].format(
                                length=BainianConfig.FU_COMPLETE_LENGTH,
                                hardness=BainianConfig.FU_COMPLETE_HARDNESS,
                                base_coins=BainianConfig.FU_COMPLETE_COINS,
                                asset_bonus=asset_bonus,
                                total_coins=total_coin_reward,
                            )

        if visited_count == 0:
            yield event.plain_result("❌ 没有找到可以拜年的牛友！")
            return

        # === 构建汇总输出 ===
        result_lines = ["🧧 ══ 牛牛群拜年 ══ 🧧"]
        result_lines.append(f"🏃 {nickname} 挨家挨户拜年，一口气拜了 {visited_count} 家！")
        result_lines.append("")

        # 拜年明细
        result_lines.append("📋 拜年明细：")
        result_lines.extend(visit_details)
        result_lines.append("")

        # 计算实际总变化（包含所有效果：基础奖励、特殊事件、福卡奖励、五福大奖等）
        final_data = self.get_user_data(group_id, user_id)
        total_length_change = final_data['length'] - initial_length
        total_hardness_change = final_data['hardness'] - initial_hardness
        total_coins_change = round(final_data.get('coins', 0) - initial_coins)

        total_parts = []
        if total_length_change != 0:
            total_parts.append(f"{'+' if total_length_change > 0 else ''}{total_length_change}cm")
        if total_coins_change != 0:
            total_parts.append(f"{'+' if total_coins_change > 0 else ''}{total_coins_change}金币")
        if total_hardness_change > 0:
            total_parts.append(f"+{total_hardness_change}硬度")
        if total_parts:
            result_lines.append(f"📦 总计收获：{', '.join(total_parts)}")
        else:
            result_lines.append("📦 总计收获：竟然空手而归了！")

        # 特殊事件汇总
        if special_events_summary:
            result_lines.append("")
            result_lines.append(f"✨ 触发事件：{'、'.join(special_events_summary)}")

        # 集福信息
        if fu_cards_obtained:
            result_lines.append("")
            result_lines.append("🎴 获得福卡：")
            result_lines.extend(fu_cards_obtained)

        if fu_complete_text:
            result_lines.append("")
            result_lines.append(fu_complete_text)

        # 集福进度（未集齐时显示）
        user_data_final = self.get_user_data(group_id, user_id)
        if not user_data_final.get('bainian_fu_completed', False):
            items_final = user_data_final.get('items', {})
            all_fu = BainianConfig.FU_CARDS
            progress_parts = []
            fu_count = 0
            for fu in all_fu:
                if items_final.get(fu['name'], 0) > 0:
                    progress_parts.append(f"{fu['emoji']}✅")
                    fu_count += 1
                else:
                    progress_parts.append(f"{fu['emoji']}❌")

            if fu_count > 0:
                result_lines.append("")
                result_lines.append(self.niuniu_texts['bainian']['fu_progress'].format(
                    progress=" ".join(progress_parts), count=fu_count
                ))

        # 今日拜年次数
        result_lines.append(self.niuniu_texts['bainian']['remaining'].format(
            count=bainian_count, limit=BainianConfig.DAILY_LIMIT
        ))

        result_lines.append("═══════════════════")

        yield event.plain_result("\n".join(result_lines))

        # 含笑五步癫触发
        huagu_msgs = self._trigger_huagu_debuff(group_id, user_id)
        for msg_text in huagu_msgs:
            yield event.plain_result(msg_text)

    async def _show_status(self, event):
        """查看牛牛状态"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['my_niuniu']['not_registered'].format(nickname=nickname))
            return

        # 评价系统
        length = user_data['length']
        length_str = self.format_length(length)
        if length < 0:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation'].get('negative', ['你的牛牛已经凹进去了...']))
        elif length == 0:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation'].get('zero', ['你的牛牛消失了...']))
        elif length < 12:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['short'])
        elif length < 25:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['medium'])
        elif length < 50:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['long'])
        elif length < 100:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['very_long'])
        elif length < 200:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['super_long'])
        else:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['ultra_long'])

        text = self.niuniu_texts['my_niuniu']['info'].format(
            nickname=nickname,
            length=length_str,
            hardness=user_data['hardness'],
            evaluation=evaluation
        )

        # 如果有寄生牛牛，显示寄生信息
        parasite = user_data.get('parasite')
        if parasite:
            beneficiary_name = parasite.get('beneficiary_name', '某人')
            text += f"\n🦠【寄】寄生牛牛来自：{beneficiary_name}"

        # 集福进度
        from niuniu_config import BainianConfig
        if user_data.get('bainian_fu_completed', False):
            text += "\n🎴 集福: 🎊 已集齐五福！大奖已领取！"
        else:
            items = user_data.get('items', {})
            all_fu = BainianConfig.FU_CARDS
            fu_count = sum(1 for fu in all_fu if items.get(fu['name'], 0) > 0)
            if fu_count > 0:
                progress_parts = []
                for fu in all_fu:
                    if items.get(fu['name'], 0) > 0:
                        progress_parts.append(f"{fu['emoji']}✅")
                    else:
                        progress_parts.append(f"{fu['emoji']}❌")
                text += f"\n🎴 集福进度: {' '.join(progress_parts)} ({fu_count}/5)"

        yield event.plain_result(text)

    async def _show_ranking(self, event):
        """显示排行榜（支持参数：长度/金币，默认长度）"""
        group_id = str(event.message_obj.group_id)
        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 解析参数
        msg = event.message_str.strip()
        parts = msg.split()
        rank_type = "长度"  # 默认按长度排序
        if len(parts) > 1:
            param = parts[1]
            if param == "金币":
                rank_type = "金币"

        # 过滤有效用户数据
        all_data = self._load_niuniu_lengths()
        group_data = all_data.get(group_id, {'plugin_enabled': False})
        valid_users = [
            (uid, udata) for uid, udata in group_data.items()
            if isinstance(udata, dict) and 'length' in udata
        ]

        if not valid_users:
            yield event.plain_result(self.niuniu_texts['ranking']['no_data'])
            return

        # 根据类型排序
        if rank_type == "金币":
            sorted_users = sorted(valid_users, key=lambda x: x[1].get('coins', 0), reverse=True)
            header = "💰 牛牛金币排行榜：\n"
        else:
            sorted_users = sorted(valid_users, key=lambda x: x[1]['length'], reverse=True)
            header = self.niuniu_texts['ranking']['header']

        total_users = len(sorted_users)
        ranking = [header]

        # 显示前10名
        top_users = sorted_users[:10]
        for idx, (uid, data) in enumerate(top_users, 1):
            hardness = data.get('hardness', 1)
            coins = data.get('coins', 0)
            parasite_info = " 【🐛寄】" if data.get('parasite') else ""
            dian_info = "【🤪癫】" if data.get('huagu_debuff') else ""
            nickname_display = dian_info + data['nickname']

            if rank_type == "金币":
                ranking.append(f"{idx}. {nickname_display} ➜ 💰{self.format_coins(coins)}")
                ranking.append(f"   📏 {self.format_length(data['length'])}")
            else:
                ranking.append(f"{idx}. {nickname_display} ➜ {self.format_length(data['length'])} 💪{hardness}")
                ranking.append(f"   💰 {self.format_coins(coins)}{parasite_info}")

        # 如果总人数超过10，显示...和后3名
        if total_users > 10:
            ranking.append("...")
            bottom_start = max(10, total_users - 3)
            bottom_users = sorted_users[bottom_start:]
            for idx, (uid, data) in enumerate(bottom_users, bottom_start + 1):
                hardness = data.get('hardness', 1)
                coins = data.get('coins', 0)
                parasite_info = " 【🐛寄】" if data.get('parasite') else ""
                dian_info = "【🤪癫】" if data.get('huagu_debuff') else ""
                nickname_display = dian_info + data['nickname']

                if rank_type == "金币":
                    ranking.append(f"{idx}. {nickname_display} ➜ 💰{self.format_coins(coins)}")
                    ranking.append(f"   📏 {self.format_length(data['length'])}")
                else:
                    ranking.append(f"{idx}. {nickname_display} ➜ {self.format_length(data['length'])} 💪{hardness}")
                    ranking.append(f"   💰 {self.format_coins(coins)}{parasite_info}")

        yield event.plain_result("\n".join(ranking))

    async def _show_menu(self, event):
        """显示菜单"""
        yield event.plain_result(self.niuniu_texts['menu']['default'])
    # endregion
