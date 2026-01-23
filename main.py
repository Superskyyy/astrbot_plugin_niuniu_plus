import random
import yaml
import os
import re
import time
import json
import sys
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
    CompareStreak, CompareBet, CompareAudience,
    format_length as config_format_length, format_length_change
)
import pytz
from datetime import datetime

# 确保目录存在
os.makedirs(PLUGIN_DIR, exist_ok=True)

@register("niuniu_plugin", "Superskyyy", "牛牛插件，包含注册牛牛、打胶、我的牛牛、比划比划、牛牛排行等功能", "4.13.3")
class NiuniuPlugin(Star):
    # 冷却时间常量（秒）
    COOLDOWN_10_MIN = 600    # 10分钟
    COOLDOWN_30_MIN = 1800   # 30分钟
    COMPARE_COOLDOWN = 600   # 比划冷却
    KAITAN_COOLDOWN = 3600   # 开团冷却（1小时）
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
        self.effects.set_shop(self.shop)  # 设置商城引用

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

    # region 数据访问接口
    def get_group_data(self, group_id):
        """从文件获取群组数据"""
        group_id = str(group_id)
        data = self._load_niuniu_lengths()
        if group_id not in data:
            data[group_id] = {'plugin_enabled': False}  # 默认关闭插件
            self._save_niuniu_lengths(data)
        return data[group_id]

    def get_user_data(self, group_id, user_id):
        """从文件获取用户数据"""
        group_id = str(group_id)
        user_id = str(user_id)
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {'plugin_enabled': False})
        return group_data.get(user_id)

    def update_user_data(self, group_id, user_id, updates):
        """更新用户数据并保存到文件"""
        group_id = str(group_id)
        user_id = str(user_id)
        data = self._load_niuniu_lengths()
        group_data = data.setdefault(group_id, {'plugin_enabled': False})
        user_data = group_data.setdefault(user_id, {
            'nickname': '',
            'length': 0,
            'hardness': 1,
            'coins': 0,
            'items': {}
        })
        user_data.update(updates)
        self._save_niuniu_lengths(data)
        return user_data

    def update_group_data(self, group_id, updates):
        """更新群组数据并保存到文件"""
        group_id = str(group_id)
        data = self._load_niuniu_lengths()
        group_data = data.setdefault(group_id, {'plugin_enabled': False})
        group_data.update(updates)
        self._save_niuniu_lengths(data)
        return group_data

    def update_last_actions(self, data):
        """更新冷却数据并保存到文件"""
        self._save_last_actions(data)
    # endregion

    # region 工具方法
    def format_length(self, length):
        """格式化长度显示"""
        return config_format_length(length)

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
        from niuniu_config import ShangbaoxianConfig

        # 获取用户数据
        if group_data is not None:
            user_data = group_data.get(user_id, {})
            if not isinstance(user_data, dict):
                return {'triggered': False}
        else:
            user_data = self.get_user_data(group_id, user_id)

        # 检查保险次数
        insurance_charges = user_data.get('insurance_charges', 0)
        if insurance_charges <= 0:
            return {'triggered': False}

        # 检查是否达到阈值
        length_triggered = length_loss >= ShangbaoxianConfig.LENGTH_THRESHOLD
        hardness_triggered = hardness_loss >= ShangbaoxianConfig.HARDNESS_THRESHOLD

        if not length_triggered and not hardness_triggered:
            return {'triggered': False}

        # 触发保险理赔
        new_charges = insurance_charges - 1

        # 更新数据
        if group_data is not None:
            # 直接修改 group_data（用于批量操作，稍后统一保存）
            group_data[user_id]['insurance_charges'] = new_charges
            current_coins = group_data[user_id].get('coins', 0)
            group_data[user_id]['coins'] = round(current_coins + ShangbaoxianConfig.PAYOUT)
        else:
            # 独立操作，立即保存
            self.update_user_data(group_id, user_id, {'insurance_charges': new_charges})
            self.games.update_user_coins(group_id, user_id, ShangbaoxianConfig.PAYOUT)

        # 构建消息
        damage_parts = []
        if length_loss > 0:
            damage_parts.append(f"{length_loss}cm")
        if hardness_loss > 0:
            damage_parts.append(f"{hardness_loss}硬度")
        damage_str = "、".join(damage_parts) if damage_parts else "未知"

        return {
            'triggered': True,
            'payout': ShangbaoxianConfig.PAYOUT,
            'charges_remaining': new_charges,
            'message': f"📋 {nickname} 保险理赔！损失{damage_str}，赔付{ShangbaoxianConfig.PAYOUT}金币（剩余{new_charges}次）"
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

        # 检查增益是否达到阈值
        host_length = host_data.get('length', 0)
        threshold = abs(host_length) * NiuniuJishengConfig.TRIGGER_THRESHOLD

        if gain <= threshold:
            return messages

        # 触发抽取！
        host_name = host_data.get('nickname', host_id)

        # 计算抽取量
        drain_length = int(abs(host_length) * NiuniuJishengConfig.DRAIN_LENGTH_PERCENT)
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
        beneficiary_data = self.get_user_data(group_id, beneficiary_id)
        if beneficiary_data:
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

        self._save_niuniu_data(niuniu_data)

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

        self._save_niuniu_data(niuniu_data)

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
    # endregion

    # region 事件处理
    niuniu_commands = ["牛牛菜单", "牛牛帮助", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛", "比划比划", "牛牛排行"]

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
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
            if is_rushing:
                yield event.plain_result("❌ 你已经在开冲了，无需重复操作")
                return
            async for result in self.games.start_rush(event):
                yield result
        elif msg.startswith("停止开冲"):
            if not is_rushing:
                yield event.plain_result("❌ 你当前并未在开冲，无需停止")
                return
            async for result in self.games.stop_rush(event):
                yield result
        elif msg.startswith("飞飞机"):
            async for result in self.games.fly_plane(event):
                yield result
        else:
            # 处理其他命令
            handler_map = {
                "注册牛牛": self._register,
                "打胶": self._dajiao,
                "我的牛牛": self._show_status,
                "比划比划": self._compare,
                "开团": self._kaitan,
                "牛牛排行": self._show_ranking,
                "牛牛商城": self.shop.show_shop,
                "牛牛购买": self.shop.handle_buy,
                "牛牛背包": self.shop.show_items,
                "牛牛股市": self._niuniu_stock,
                "重置所有牛牛": self._reset_all_niuniu,
                "牛牛红包": self._niuniu_hongbao,
                "牛牛补贴": self._niuniu_butie
            }

            for cmd, handler in handler_map.items():
                if msg.startswith(cmd):
                    async for result in handler(event):
                        yield result
                    return
    @event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """私聊消息处理器"""
        msg = event.message_str.strip()
        niuniu_commands = [
            "牛牛菜单", "牛牛帮助", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛",
            "比划比划", "牛牛排行", "牛牛商城", "牛牛购买", "牛牛背包",
            "牛牛股市", "开冲", "停止开冲", "飞飞机"
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
        """重置所有牛牛 - 仅管理员可用"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        # 加载数据
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {})

        # 统计重置人数
        reset_count = 0
        plugin_enabled = group_data.get('plugin_enabled', False)

        # 重置所有用户数据
        for uid in list(group_data.keys()):
            if uid.startswith('_') or uid == 'plugin_enabled':
                continue
            if isinstance(group_data[uid], dict) and 'length' in group_data[uid]:
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

        # 保留插件启用状态
        group_data['plugin_enabled'] = plugin_enabled
        data[group_id] = group_data
        self._save_niuniu_lengths(data)

        yield event.plain_result(f"✅ 已重置本群 {reset_count} 个牛牛的数据！\n所有人重新开始，公平竞争~")

    async def _niuniu_hongbao(self, event):
        """牛牛红包 - 给所有人发金币，仅管理员可用"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        # 解析金币数量
        msg_parts = event.message_str.split()
        if len(msg_parts) < 2 or not msg_parts[1].isdigit():
            yield event.plain_result("❌ 格式：牛牛红包 金币数量\n例：牛牛红包 100")
            return

        amount = int(msg_parts[1])
        if amount <= 0:
            yield event.plain_result("❌ 红包金额必须大于0")
            return

        if amount > 10000:
            yield event.plain_result("❌ 单次红包金额不能超过10000")
            return

        # 加载数据
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {})

        # 给所有用户发红包
        receive_count = 0
        for uid in list(group_data.keys()):
            if uid.startswith('_') or uid == 'plugin_enabled':
                continue
            if isinstance(group_data[uid], dict) and 'length' in group_data[uid]:
                group_data[uid]['coins'] = round(group_data[uid].get('coins', 0) + amount)
                receive_count += 1

        data[group_id] = group_data
        self._save_niuniu_lengths(data)

        total = amount * receive_count
        yield event.plain_result(f"🧧 发红包成功！\n💰 每人 {amount} 金币\n👥 共 {receive_count} 人领取\n💵 总计发出 {total} 金币")

    async def _niuniu_butie(self, event):
        """牛牛补贴 - 给指定用户补贴长度/硬度/金币，仅管理员可用"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        # 解析@目标
        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result("❌ 格式：牛牛补贴 @用户 长度 硬度 金币\n例：牛牛补贴 @xxx 10 5 100\n例：牛牛补贴 @xxx 0 0 -50（倒扣50金币）")
            return

        # 解析参数（长度、硬度、金币）
        msg_parts = event.message_str.split()
        numbers = []
        for part in msg_parts:
            # 支持负数
            try:
                if part.lstrip('-').isdigit():
                    numbers.append(int(part))
            except:
                pass

        if len(numbers) < 3:
            yield event.plain_result("❌ 格式：牛牛补贴 @用户 长度 硬度 金币\n例：牛牛补贴 @xxx 10 5 100\n例：牛牛补贴 @xxx 0 0 -50（倒扣50金币）")
            return

        length_change = numbers[0]
        hardness_change = numbers[1]
        coins_change = numbers[2]

        # 加载数据
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {})

        # 检查目标是否已注册
        target_data = group_data.get(target_id)
        if not target_data or not isinstance(target_data, dict) or 'length' not in target_data:
            yield event.plain_result("❌ 目标用户尚未注册牛牛")
            return

        target_name = target_data.get('nickname', target_id)
        old_length = target_data.get('length', 0)
        old_hardness = target_data.get('hardness', 1)
        old_coins = target_data.get('coins', 0)

        # 应用变化
        new_length = old_length + length_change
        new_hardness = max(0, old_hardness + hardness_change)  # 硬度最低为0
        new_coins = round(old_coins + coins_change)  # 金币可以为负数（欠账）

        target_data['length'] = new_length
        target_data['hardness'] = new_hardness
        target_data['coins'] = new_coins

        group_data[target_id] = target_data
        data[group_id] = group_data
        self._save_niuniu_lengths(data)

        # 构建结果消息
        result_parts = [f"✅ 已补贴 {target_name}："]
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

    async def _niuniu_stock(self, event):
        """牛牛股市"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        msg = event.message_str.strip()

        # 检查是否已注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data or 'length' not in user_data:
            yield event.plain_result("❌ 请先注册牛牛！")
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
            # 牛牛股市 购买 <金额>
            if len(parts) < 2:
                yield event.plain_result("❌ 格式：牛牛股市 购买 <金额>")
                return

            try:
                coins = float(parts[1])
            except:
                yield event.plain_result("❌ 请输入有效的金额")
                return

            user_coins = user_data.get('coins', 0)
            if coins > user_coins:
                yield event.plain_result(f"❌ 金币不足！你只有 {user_coins:.0f} 金币")
                return

            success, message, shares = stock.buy(group_id, user_id, coins)
            if success:
                # 扣除金币
                user_data['coins'] = round(user_coins - coins)
                self.update_user_data(group_id, user_id, {'coins': user_data['coins']})
            yield event.plain_result(message)

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

        elif subcmd == "持仓":
            # 牛牛股市 持仓
            yield event.plain_result(stock.format_holdings(group_id, user_id, nickname))

        else:
            yield event.plain_result("❌ 未知命令\n📌 牛牛股市 购买 <金额>\n📌 牛牛股市 出售 [数量/全部]\n📌 牛牛股市 持仓")

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

        # 检查是否处于冷却期
        on_cooldown, remaining = self.check_cooldown(last_time, self.COOLDOWN_10_MIN)

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

        # ===== 寄生牛牛效果：如果有人在我身上种了寄生牛牛，检查是否触发抽取 =====
        if total_change > 0:
            parasite_msgs = self._check_and_trigger_parasite(
                group_id, user_id, total_change, processed_ids=set()
            )
            result_msgs.extend(parasite_msgs)

        # 更新金币
        if extra_coins > 0:
            self.games.update_user_coins(group_id, user_id, extra_coins)

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

    async def _compare(self, event):
        """比划功能"""
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

        # 更新冷却时间和比划次数
        compare_records[target_id] = current_time
        compare_records['count'] = compare_count + 1
        self.update_last_actions(last_actions)

        # ===== 解析赌注 =====
        bet_amount = 0
        msg_parts = event.message_str.split()
        for part in msg_parts:
            if part.isdigit():
                bet_amount = int(part)
                break

        # 验证赌注
        if bet_amount > 0:
            if bet_amount < CompareBet.MIN_BET or bet_amount > CompareBet.MAX_BET:
                yield event.plain_result(
                    self.niuniu_texts['compare'].get('bet_invalid', ['❌ 赌注必须在 {min}-{max} 之间'])[0].format(
                        min=CompareBet.MIN_BET, max=CompareBet.MAX_BET
                    )
                )
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
        all_group_data = self._load_niuniu_lengths().get(group_id, {})
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

            # 普通夺牛魔效果（steal/self_clear）
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
            from niuniu_config import ShangbaoxianConfig
            if ctx.target_length_change < 0:
                target_length_loss = abs(ctx.target_length_change)
                if target_length_loss >= ShangbaoxianConfig.LENGTH_THRESHOLD:
                    target_insurance = target_data.get('insurance_charges', 0)
                    if target_insurance > 0:
                        # 消耗保险并赔付
                        self.update_user_data(group_id, target_id, {'insurance_charges': target_insurance - 1})
                        self.games.update_user_coins(group_id, target_id, ShangbaoxianConfig.PAYOUT)
                        ctx.messages.append(f"📋 {target_data['nickname']} 保险理赔！损失{target_length_loss}cm，赔付{ShangbaoxianConfig.PAYOUT}金币（剩余{target_insurance - 1}次）")

            yield event.plain_result("\n".join(ctx.messages))
            return

        # 计算胜负 (支持负数长度)
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
        hardness_factor = (ctx.user_hardness - ctx.target_hardness) * 0.08
        # 应用连击加成
        win_prob = min(max(base_win + length_factor + hardness_factor + streak_bonus, 0.15), 0.85)

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

        # ===== 赌注结算 =====
        if bet_amount > 0:
            if is_win:
                winnings = int(bet_amount * CompareBet.WINNER_MULTIPLIER)
                self.games.update_user_coins(group_id, user_id, winnings)
                bet_text = random.choice(self.niuniu_texts['compare'].get('bet_win', ['💰 赢得 {amount} 金币！'])).format(
                    nickname=nickname, amount=winnings
                )
            else:
                self.games.update_user_coins(group_id, user_id, -bet_amount)
                bet_text = random.choice(self.niuniu_texts['compare'].get('bet_lose', ['💸 失去 {amount} 金币'])).format(
                    nickname=nickname, amount=bet_amount
                )
            result_msg.append(bet_text)

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
                self.games.update_user_coins(group_id, user_id, coins)
                self.games.update_user_coins(group_id, target_id, coins)
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
                    self.games.update_user_coins(group_id, uid, coins)
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

        # 股市钩子 - 用赢家的增益作为变化量
        compare_change = user_length_gain if user_length_gain > 0 else -target_length_gain
        stock_msg = stock_hook(group_id, nickname, event_type="compare", length_change=compare_change)
        if stock_msg:
            result_msg.append(stock_msg)

        yield event.plain_result("\n".join(result_msg))

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

    async def _kaitan(self, event):
        """开团功能 - 群友混战（固定8场）"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查发起者是否注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查开团冷却
        last_actions = self._load_last_actions()
        last_kaitan = last_actions.setdefault(group_id, {}).setdefault(user_id, {}).get('kaitan', 0)
        on_cooldown, remaining = self.check_cooldown(last_kaitan, self.KAITAN_COOLDOWN)
        if on_cooldown:
            mins = int(remaining // 60) + 1
            yield event.plain_result(f"❌ {nickname}，你开团太频繁了！还需等待 {mins} 分钟后才能再次开团")
            return

        # 解析所有@的用户
        at_users = []
        if hasattr(event.message_obj, 'message') and event.message_obj.message:
            for seg in event.message_obj.message:
                if hasattr(seg, 'type') and seg.type == 'at':
                    target_id = str(seg.data.get('qq', ''))
                    if target_id:
                        at_users.append(target_id)

        # 构建参与者列表
        participants = []

        if at_users:
            # 有@人：发起者 + @的人
            participants.append((user_id, nickname))
            for target_id in at_users:
                if target_id != user_id:
                    target_data = self.get_user_data(group_id, target_id)
                    if target_data:
                        participants.append((target_id, target_data.get('nickname', f'用户{target_id}')))
        else:
            # 没@人：全群已注册用户参与
            # 先确保发起者在参与者列表中
            participants.append((user_id, nickname))
            data = self._load_niuniu_lengths()
            group_users = data.get(group_id, {})
            for uid, udata in group_users.items():
                # 跳过非用户数据（如plugin_enabled, _recent_compares等）
                if uid.startswith('_') or uid == 'plugin_enabled':
                    continue
                # 跳过发起者（已添加）
                if uid == user_id:
                    continue
                if isinstance(udata, dict) and 'length' in udata:
                    participants.append((uid, udata.get('nickname', f'用户{uid}')))

        # 去重
        seen = set()
        unique_participants = []
        for p in participants:
            if p[0] not in seen:
                seen.add(p[0])
                unique_participants.append(p)
        participants = unique_participants

        # 至少需要3人才能叫"团"
        if len(participants) < 3:
            yield event.plain_result("❌ 开团至少需要3人！\n用法：开团 或 开团 @群友1 @群友2 ...")
            return

        # 打乱顺序
        random.shuffle(participants)

        result_msgs = ["⚔️ ═══ 牛牛大乱斗 ═══ ⚔️", f"👥 参与者：{len(participants)}人", ""]

        # 记录战绩
        wins = {p[0]: 0 for p in participants}
        length_changes = {p[0]: 0 for p in participants}

        # 固定8场战斗
        MAX_BATTLES = 8
        battle_count = 0
        failed_attempts = 0

        while battle_count < MAX_BATTLES and failed_attempts < 20:
            # 随机选两个不同的参与者
            if len(participants) < 2:
                break
            p1, p2 = random.sample(participants, 2)
            p1_id, p1_name = p1
            p2_id, p2_name = p2

            # 获取最新数据
            p1_data = self.get_user_data(group_id, p1_id)
            p2_data = self.get_user_data(group_id, p2_id)

            if not p1_data or not p2_data:
                failed_attempts += 1
                continue

            p1_len = p1_data['length']
            p2_len = p2_data['length']
            p1_hard = p1_data['hardness']
            p2_hard = p2_data['hardness']

            # 简化胜率计算
            base_win = 0.5
            if p1_len > 0 and p2_len > 0:
                length_factor = (p1_len - p2_len) / max(p1_len, p2_len, 1) * 0.2
            elif p1_len <= 0 and p2_len > 0:
                length_factor = -0.2
            elif p1_len > 0 and p2_len <= 0:
                length_factor = 0.2
            else:
                length_factor = 0
            hardness_factor = (p1_hard - p2_hard) * 0.08
            win_prob = min(max(base_win + length_factor + hardness_factor, 0.15), 0.85)

            # 判定
            p1_wins = random.random() < win_prob

            # 按双方长度绝对值计算涨跌幅度（3%-8%获胜，2%-5%失败）
            avg_abs_len = (abs(p1_len) + abs(p2_len)) / 2
            base_change = max(5, int(avg_abs_len * random.uniform(0.03, 0.08)))  # 最少5cm
            gain = base_change
            loss = max(3, int(avg_abs_len * random.uniform(0.02, 0.05)))  # 最少3cm

            if p1_wins:
                wins[p1_id] += 1
                length_changes[p1_id] += gain
                length_changes[p2_id] -= loss
                self.update_user_data(group_id, p1_id, {'length': p1_data['length'] + gain})
                self.update_user_data(group_id, p2_id, {'length': p2_data['length'] - loss})
                result_msgs.append(f"⚔️ {p1_name} 🆚 {p2_name} → 🏆 {p1_name} (+{self.format_length(gain)})")
            else:
                wins[p2_id] += 1
                length_changes[p2_id] += gain
                length_changes[p1_id] -= loss
                self.update_user_data(group_id, p1_id, {'length': p1_data['length'] - loss})
                self.update_user_data(group_id, p2_id, {'length': p2_data['length'] + gain})
                result_msgs.append(f"⚔️ {p1_name} 🆚 {p2_name} → 🏆 {p2_name} (+{self.format_length(gain)})")

            battle_count += 1

        # 统计结果
        result_msgs.append("")
        result_msgs.append("📊 ═══ 战绩统计 ═══ 📊")

        # 只显示参与过战斗的人（有胜场或有长度变化）
        active_participants = [p for p in participants if wins[p[0]] > 0 or length_changes[p[0]] != 0]

        # 按胜场排序
        sorted_participants = sorted(active_participants, key=lambda p: (wins[p[0]], length_changes[p[0]]), reverse=True)

        for rank, (pid, pname) in enumerate(sorted_participants, 1):
            final_data = self.get_user_data(group_id, pid)
            change = length_changes[pid]
            change_str = f"+{change}" if change >= 0 else str(change)
            if rank == 1:
                result_msgs.append(f"👑 {pname}: {wins[pid]}胜 ({change_str}cm) → {self.format_length(final_data['length'])}")
            else:
                result_msgs.append(f"{rank}. {pname}: {wins[pid]}胜 ({change_str}cm) → {self.format_length(final_data['length'])}")

        # 宣布冠军
        if sorted_participants:
            champion = sorted_participants[0]
            result_msgs.append("")
            result_msgs.append(f"🎉 本次大乱斗冠军：{champion[1]}！")

        # 更新开团冷却时间
        last_actions = self._load_last_actions()
        last_actions.setdefault(group_id, {}).setdefault(user_id, {})['kaitan'] = time.time()
        self.update_last_actions(last_actions)

        # 股市影响：开团是混沌事件，波动较大
        total_length_change = sum(length_changes.values())
        stock_msg = stock_hook(
            group_id,
            nickname,
            event_type="chaos",
            length_change=total_length_change
        )
        if stock_msg:
            result_msgs.append("")
            result_msgs.append(stock_msg)

        yield event.plain_result("\n".join(result_msgs))

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

        yield event.plain_result(text)

    async def _show_ranking(self, event):
        """显示排行榜（从文件读取数据）"""
        group_id = str(event.message_obj.group_id)
        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

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

        # 排序所有用户
        sorted_users = sorted(valid_users, key=lambda x: x[1]['length'], reverse=True)
        total_users = len(sorted_users)

        # 构建排行榜
        ranking = [self.niuniu_texts['ranking']['header']]

        # 显示前10名
        top_users = sorted_users[:10]
        for idx, (uid, data) in enumerate(top_users, 1):
            hardness = data.get('hardness', 1)
            # 检查是否有寄生牛牛
            parasite_mark = "【寄】" if data.get('parasite') else ""
            ranking.append(
                f"{idx}. {data['nickname']}{parasite_mark} ➜ {self.format_length(data['length'])} 💪{hardness}"
            )

        # 如果总人数超过10，显示...和后3名
        if total_users > 10:
            ranking.append("...")
            # 取后3名（避免与前10重复）
            bottom_start = max(10, total_users - 3)
            bottom_users = sorted_users[bottom_start:]
            for idx, (uid, data) in enumerate(bottom_users, bottom_start + 1):
                hardness = data.get('hardness', 1)
                # 检查是否有寄生牛牛
                parasite_mark = "【寄】" if data.get('parasite') else ""
                ranking.append(
                    f"{idx}. {data['nickname']}{parasite_mark} ➜ {self.format_length(data['length'])} 💪{hardness}"
                )

        yield event.plain_result("\n".join(ranking))
    async def _show_menu(self, event):
        """显示菜单"""
        yield event.plain_result(self.niuniu_texts['menu']['default'])
    # endregion
