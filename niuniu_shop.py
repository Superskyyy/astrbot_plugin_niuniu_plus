import os
import yaml
import copy
import random
from typing import Dict, Any, List
from astrbot.api.all import Context, AstrMessageEvent
from niuniu_config import (
    PLUGIN_DIR, NIUNIU_LENGTHS_FILE, SIGN_DATA_FILE, SHOP_CONFIG_FILE,
    DEFAULT_SHOP_ITEMS
)
from niuniu_effects import EffectTrigger, EffectContext

class NiuniuShop:
    def __init__(self, main_plugin):
        self.main = main_plugin  # 主插件实例
        self.shop_config_path = SHOP_CONFIG_FILE
        os.makedirs(PLUGIN_DIR, exist_ok=True)
        self._create_default_shop_config()  # 确保配置文件存在

    def _create_default_shop_config(self):
        """创建/更新默认商城配置文件，始终同步最新道具"""
        # 始终用最新的 DEFAULT_SHOP_ITEMS 覆盖，确保新道具能加入商城
        with open(self.shop_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(DEFAULT_SHOP_ITEMS, f, allow_unicode=True)

    def _load_shop_config(self) -> List[Dict[str, Any]]:
        """加载商城配置"""
        try:
            if os.path.exists(self.shop_config_path):
                with open(self.shop_config_path, 'r', encoding='utf-8') as f:
                    custom_config = yaml.safe_load(f) or []
                    return self._merge_config(copy.deepcopy(DEFAULT_SHOP_ITEMS), custom_config)
            return copy.deepcopy(DEFAULT_SHOP_ITEMS)
        except Exception as e:
            return copy.deepcopy(DEFAULT_SHOP_ITEMS)

    def _merge_config(self, base: List[Dict[str, Any]], custom: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并默认配置和自定义配置"""
        config_map = {item['id']: item for item in base}
        for custom_item in custom:
            if custom_item['id'] in config_map:
                config_map[custom_item['id']].update(custom_item)
            else:
                config_map[custom_item['id']] = custom_item
        return list(config_map.values())

    def get_shop_items(self) -> List[Dict[str, Any]]:
        """获取商城商品列表"""
        return self._load_shop_config()

    async def show_shop(self, event: AstrMessageEvent):
        """显示商城"""
        shop_list = ["🛒 牛牛商城（使用 牛牛购买+编号）"]
        for item in self.get_shop_items():
            shop_list.append(f"{item['id']}. {item['name']} - {item['desc']} (价格: {item['price']} 金币)")
        yield event.plain_result("\n".join(shop_list))

    def _load_niuniu_data(self) -> Dict[str, Any]:
        """加载牛牛核心数据"""
        if not os.path.exists(NIUNIU_LENGTHS_FILE):
            with open(NIUNIU_LENGTHS_FILE, 'w', encoding='utf-8') as f:
                yaml.dump({}, f)
        with open(NIUNIU_LENGTHS_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _save_niuniu_data(self, data: Dict[str, Any]):
        """保存牛牛核心数据"""
        with open(NIUNIU_LENGTHS_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)

    def _load_sign_data(self) -> Dict[str, Any]:
        """加载签到数据"""
        if not os.path.exists(SIGN_DATA_FILE):
            with open(SIGN_DATA_FILE, 'w', encoding='utf-8') as f:
                yaml.dump({}, f)
        with open(SIGN_DATA_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _save_sign_data(self, data: Dict[str, Any]):
        """保存签到数据"""
        with open(SIGN_DATA_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True)

    def get_sign_coins(self, group_id: str, user_id: str) -> float:
        """获取签到插件的金币"""
        sign_data = self._load_sign_data()
        return sign_data.get(group_id, {}).get(user_id, {}).get('coins', 0.0)

    def update_sign_coins(self, group_id: str, user_id: str, coins: float):
        """更新签到插件的金币"""
        sign_data = self._load_sign_data()
        user_data = sign_data.setdefault(group_id, {}).setdefault(user_id, {})
        user_data['coins'] = coins
        self._save_sign_data(sign_data)

    def _get_new_game_coins(self, group_id: str, user_id: str) -> float:
        """获取牛牛游戏的金币"""
        niuniu_data = self._load_niuniu_data()
        return niuniu_data.get(group_id, {}).get(user_id, {}).get('coins', 0.0)

    def _update_new_game_coins(self, group_id: str, user_id: str, coins: float):
        """更新牛牛游戏的金币"""
        niuniu_data = self._load_niuniu_data()
        group_data = niuniu_data.setdefault(group_id, {})
        user_info = group_data.setdefault(user_id, {})
        user_info['coins'] = coins
        self._save_niuniu_data(niuniu_data)

    def get_user_coins(self, group_id: str, user_id: str) -> float:
        """获取总金币"""
        sign_coins = self.get_sign_coins(group_id, user_id)
        game_coins = self._get_new_game_coins(group_id, user_id)
        return sign_coins + game_coins

    def update_user_coins(self, group_id: str, user_id: str, coins: float):
        """更新总金币"""
        current_coins = self.get_user_coins(group_id, user_id)
        delta = current_coins - coins  # 需要扣除的金币数量
        
        game_coins = self._get_new_game_coins(group_id, user_id)
        if game_coins >= delta:
            self._update_new_game_coins(group_id, user_id, game_coins - delta)
        else:
            remaining = delta - game_coins
            self._update_new_game_coins(group_id, user_id, 0)
            sign_coins = self.get_sign_coins(group_id, user_id)
            self.update_sign_coins(group_id, user_id, sign_coins - remaining)

    def _get_user_data(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """获取用户数据"""
        niuniu_data = self._load_niuniu_data()
        group_data = niuniu_data.get(group_id, {})
        return group_data.get(user_id, {})

    def _save_user_data(self, group_id: str, user_id: str, user_data: Dict[str, Any]):
        """保存用户数据"""
        niuniu_data = self._load_niuniu_data()
        group_data = niuniu_data.setdefault(group_id, {})
        group_data[user_id] = user_data
        self._save_niuniu_data(niuniu_data)

    def get_user_items(self, group_id: str, user_id: str) -> Dict[str, int]:
        """获取用户道具"""
        user_data = self._get_user_data(group_id, user_id)
        return user_data.get('items', {})

    def consume_item(self, group_id: str, user_id: str, item_name: str) -> bool:
        """消耗道具返回是否成功"""
        user_data = self._get_user_data(group_id, user_id)
        items = user_data.get('items', {})

        if items.get(item_name, 0) > 0:
            items[item_name] -= 1
            if items[item_name] == 0:
                del items[item_name]
            user_data['items'] = items
            self._save_user_data(group_id, user_id, user_data)
            return True
        return False

    def _check_victim_insurance(self, group_id: str, group_data: Dict[str, Any],
                                victim_id: str, length_damage: int, hardness_damage: int = 0) -> Dict[str, Any]:
        """
        检查被动受害者的保险理赔

        Args:
            group_id: 群组ID
            group_data: 群组数据
            victim_id: 受害者ID
            length_damage: 长度伤害
            hardness_damage: 硬度伤害

        Returns:
            保险信息字典，包含:
            - triggered: 是否触发保险
            - payout: 赔付金额
            - charges_remaining: 剩余保险次数
            - message: 保险消息
        """
        from niuniu_config import ShangbaoxianConfig

        victim_data = group_data.get(victim_id, {})
        if not isinstance(victim_data, dict):
            return {'triggered': False}

        # 检查保险次数
        insurance_charges = victim_data.get('insurance_charges', 0)
        if insurance_charges <= 0:
            return {'triggered': False}

        # 检查是否达到阈值（长度>=50 或 硬度>=10）
        length_triggered = length_damage >= ShangbaoxianConfig.LENGTH_THRESHOLD
        hardness_triggered = hardness_damage >= ShangbaoxianConfig.HARDNESS_THRESHOLD

        if not length_triggered and not hardness_triggered:
            return {'triggered': False}

        # 触发保险理赔
        victim_name = victim_data.get('nickname', victim_id)
        new_charges = insurance_charges - 1

        # 消耗保险次数
        group_data[victim_id]['insurance_charges'] = new_charges

        # 赔付金币
        self._update_new_game_coins(group_id, victim_id,
            self._get_new_game_coins(group_id, victim_id) + ShangbaoxianConfig.PAYOUT)

        # 构建消息
        damage_parts = []
        if length_damage > 0:
            damage_parts.append(f"{length_damage}cm长度")
        if hardness_damage > 0:
            damage_parts.append(f"{hardness_damage}硬度")
        damage_str = "、".join(damage_parts)

        return {
            'triggered': True,
            'payout': ShangbaoxianConfig.PAYOUT,
            'charges_remaining': new_charges,
            'message': f"📋 {victim_name} 触发保险！损失{damage_str}，赔付{ShangbaoxianConfig.PAYOUT}金币（剩余{new_charges}次）"
        }

    def _check_risk_transfer(self, group_data: Dict[str, Any], victim_id: str,
                             length_damage: int, hardness_damage: int,
                             excluded_ids: List[str], is_robin_hood: bool = False) -> Dict[str, Any]:
        """
        检查是否触发祸水东引转嫁

        Args:
            group_data: 群组数据
            victim_id: 受害者ID
            length_damage: 长度伤害（用于阈值判断）
            hardness_damage: 硬度伤害（一起转嫁但不计入阈值）
            excluded_ids: 排除的用户ID列表（不能被转嫁到的用户）
            is_robin_hood: 是否来自劫富济贫（特殊效果：转嫁给第二富有的人）

        Returns:
            转嫁信息字典，包含:
            - transferred: 是否转嫁成功
            - new_victim_id: 新受害者ID
            - new_victim_name: 新受害者昵称
            - original_victim_name: 原受害者昵称
            - message: 转嫁消息
        """
        from niuniu_config import HuoshuiDongyinConfig

        victim_data = group_data.get(victim_id, {})
        if not isinstance(victim_data, dict):
            return {'transferred': False}

        # 检查转嫁次数
        risk_transfer_charges = victim_data.get('risk_transfer_charges', 0)
        if risk_transfer_charges <= 0:
            return {'transferred': False}

        # 检查长度伤害是否达到阈值（只看长度，不看硬度）
        if length_damage < HuoshuiDongyinConfig.DAMAGE_THRESHOLD:
            return {'transferred': False}

        # 寻找新的受害者（排除指定用户）
        valid_targets = [
            (uid, data) for uid, data in group_data.items()
            if isinstance(data, dict) and 'length' in data
            and uid not in excluded_ids and uid != victim_id
        ]

        if not valid_targets:
            return {'transferred': False}

        original_victim_name = victim_data.get('nickname', victim_id)

        if is_robin_hood:
            # 劫富济贫特殊效果：转嫁给第二富有的人
            sorted_targets = sorted(valid_targets, key=lambda x: x[1].get('length', 0), reverse=True)
            new_victim_id, new_victim_data = sorted_targets[0]  # 第二富有（首富已被排除）
            new_victim_name = new_victim_data.get('nickname', new_victim_id)
            message = f"🔄💰 {original_victim_name} 触发祸水东引！首富把祸水引向了第二富有的 {new_victim_name}！{length_damage}cm伤害转嫁！（剩余{risk_transfer_charges - 1}次）"
        else:
            # 随机选择新受害者
            new_victim_id, new_victim_data = random.choice(valid_targets)
            new_victim_name = new_victim_data.get('nickname', new_victim_id)
            message = f"🔄 {original_victim_name} 触发祸水东引！{length_damage}cm伤害转嫁给 {new_victim_name}！（剩余{risk_transfer_charges - 1}次）"

        return {
            'transferred': True,
            'new_victim_id': new_victim_id,
            'new_victim_name': new_victim_name,
            'original_victim_id': victim_id,
            'original_victim_name': original_victim_name,
            'length_damage': length_damage,
            'hardness_damage': hardness_damage,
            'charges_remaining': risk_transfer_charges - 1,
            'message': message
        }

    async def handle_buy(self, event: AstrMessageEvent):
        """处理购买命令"""
        msg_parts = event.message_str.split()
        if len(msg_parts) < 2 or not msg_parts[1].isdigit():
            yield event.plain_result("❌ 格式：牛牛购买 商品编号\n例：牛牛购买 1")
            return

        item_id = int(msg_parts[1])
        shop_items = self.get_shop_items()
        selected_item = next((i for i in shop_items if i['id'] == item_id), None)

        if not selected_item:
            yield event.plain_result("❌ 无效的商品编号")
            return

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        # 获取用户金币
        user_coins = self.get_user_coins(group_id, user_id)

        # 检查用户是否有足够的金币（动态定价道具跳过，在效果中检查）
        if not selected_item.get('dynamic_price') and user_coins < selected_item['price']:
            yield event.plain_result("❌ 金币不足，无法购买")
            return

        try:
            result_msg = []
            user_data = self._get_user_data(group_id, user_id)
            final_price = selected_item['price']  # 默认价格，动态定价道具会在效果中更新

            if selected_item['type'] == 'passive':
                # Passive items go to inventory
                user_data.setdefault('items', {})
                current = user_data['items'].get(selected_item['name'], 0)
                quantity = selected_item.get('quantity', 1)
                max_count = selected_item.get('max', 3)

                # 检查是否会超过上限
                if current + quantity > max_count:
                    if current >= max_count:
                        yield event.plain_result(f"⚠️ 已达到最大持有量（当前{current}个，最大{max_count}个）")
                    else:
                        yield event.plain_result(f"⚠️ 购买后会超过上限（当前{current}个，购买+{quantity}个，最大{max_count}个）")
                    return

                user_data['items'][selected_item['name']] = current + quantity
                result_msg.append(f"📦 获得 {selected_item['name']}x{quantity}")
                self._save_user_data(group_id, user_id, user_data)

            elif selected_item['type'] == 'active':
                # Active items use effect system
                extra_data = {'item_name': selected_item['name'], 'user_coins': user_coins}

                # 需要群组数据的道具
                if selected_item['name'] in ['劫富济贫', '混沌风暴', '月牙天冲', '牛牛大自爆']:
                    niuniu_data = self._load_niuniu_data()
                    extra_data['group_data'] = niuniu_data.get(group_id, {})

                ctx = EffectContext(
                    group_id=group_id,
                    user_id=user_id,
                    nickname=nickname,
                    user_data=user_data,
                    user_length=user_data.get('length', 0),
                    user_hardness=user_data.get('hardness', 1),
                    extra=extra_data
                )

                # Trigger ON_PURCHASE for this specific item
                effect = self.main.effects.effects.get(selected_item['name'])
                if effect and EffectTrigger.ON_PURCHASE in effect.triggers:
                    ctx = effect.on_trigger(EffectTrigger.ON_PURCHASE, ctx)

                    # 检查是否需要退款（操作失败）
                    if ctx.extra.get('refund'):
                        yield event.plain_result("\n".join(ctx.messages))
                        return

                    # 动态定价道具更新最终价格
                    if ctx.extra.get('dynamic_price') is not None:
                        final_price = ctx.extra['dynamic_price']

                    # 处理劫富济贫的特殊逻辑（合并护盾消耗+祸水东引）
                    if ctx.extra.get('robin_hood'):
                        robin_hood = ctx.extra['robin_hood']
                        niuniu_data = self._load_niuniu_data()
                        group_data = niuniu_data.setdefault(group_id, {})

                        # 扣除首富的长度（考虑祸水东引）
                        richest_id = robin_hood['richest_id']
                        steal_amount = robin_hood['steal_amount']

                        if steal_amount > 0 and richest_id in group_data:
                            # 检查祸水东引（护盾已在效果中检查，这里检查转嫁）
                            if not ctx.extra.get('consume_shield'):  # 护盾优先于转嫁
                                transfer_info = self._check_risk_transfer(
                                    group_data, richest_id, steal_amount, 0, [user_id],
                                    is_robin_hood=True  # 劫富济贫特殊：转嫁给第二富有的人
                                )
                                if transfer_info['transferred']:
                                    # 转嫁成功，扣新受害者
                                    new_victim_id = transfer_info['new_victim_id']
                                    group_data[new_victim_id]['length'] = group_data[new_victim_id].get('length', 0) - steal_amount
                                    # 消耗转嫁次数
                                    group_data[richest_id]['risk_transfer_charges'] = transfer_info['charges_remaining']
                                    result_msg.append(transfer_info['message'])
                                    # 检查新受害者的保险
                                    insurance_info = self._check_victim_insurance(group_id, group_data, new_victim_id, steal_amount)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                                else:
                                    # 正常扣除首富
                                    group_data[richest_id]['length'] = group_data[richest_id].get('length', 0) - steal_amount
                                    # 检查首富的保险
                                    insurance_info = self._check_victim_insurance(group_id, group_data, richest_id, steal_amount)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                            else:
                                # 有护盾，不扣（已在效果中处理）
                                pass

                        # 给穷人加长度
                        for beneficiary in robin_hood['beneficiaries']:
                            uid = beneficiary['user_id']
                            if uid in group_data:
                                group_data[uid]['length'] = group_data[uid].get('length', 0) + beneficiary['amount']

                        # 同时处理护盾消耗（劫富济贫单人）
                        if ctx.extra.get('consume_shield'):
                            shield_info = ctx.extra['consume_shield']
                            target_id = shield_info['user_id']
                            if target_id in group_data:
                                current = group_data[target_id].get('shield_charges', 0)
                                group_data[target_id]['shield_charges'] = max(0, current - shield_info['amount'])

                        self._save_niuniu_data(niuniu_data)

                    # 处理混沌风暴的特殊逻辑（合并护盾消耗+祸水东引）
                    if ctx.extra.get('chaos_storm'):
                        chaos_storm = ctx.extra['chaos_storm']
                        niuniu_data = self._load_niuniu_data()
                        group_data = niuniu_data.setdefault(group_id, {})

                        # 记录被护盾保护的用户ID
                        shielded_ids = set(s['user_id'] for s in ctx.extra.get('consume_shields', []))

                        # 应用所有人的长度和硬度变化（考虑祸水东引）
                        for change in chaos_storm.get('changes', []):
                            uid = change['user_id']
                            if uid not in group_data:
                                continue

                            length_change = change.get('change', 0)
                            hardness_change = change.get('hardness_change', 0)

                            # 如果是负长度变化且没有护盾，检查祸水东引
                            if length_change < 0 and uid not in shielded_ids:
                                length_damage = abs(length_change)
                                transfer_info = self._check_risk_transfer(
                                    group_data, uid, length_damage, 0, [user_id]
                                )
                                if transfer_info['transferred']:
                                    # 转嫁成功，扣新受害者
                                    new_victim_id = transfer_info['new_victim_id']
                                    group_data[new_victim_id]['length'] = group_data[new_victim_id].get('length', 0) - length_damage
                                    # 消耗转嫁次数
                                    group_data[uid]['risk_transfer_charges'] = transfer_info['charges_remaining']
                                    result_msg.append(transfer_info['message'])
                                    # 检查新受害者的保险
                                    insurance_info = self._check_victim_insurance(group_id, group_data, new_victim_id, length_damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                                else:
                                    # 正常扣除长度
                                    group_data[uid]['length'] = group_data[uid].get('length', 0) + length_change
                                    # 检查受害者的保险
                                    insurance_info = self._check_victim_insurance(group_id, group_data, uid, length_damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                            else:
                                # 正数变化或有护盾，直接应用长度
                                group_data[uid]['length'] = group_data[uid].get('length', 0) + length_change

                            # 应用硬度变化（不受祸水东引影响）
                            if hardness_change != 0:
                                old_hardness = group_data[uid].get('hardness', 1)
                                group_data[uid]['hardness'] = max(1, min(100, old_hardness + hardness_change))

                        # 处理交换事件（交换如果亏了也触发保险）
                        for swap in chaos_storm.get('swaps', []):
                            u1_id = swap['user1_id']
                            u2_id = swap['user2_id']
                            if u1_id in group_data and u2_id in group_data:
                                u1_old = swap['user1_old']
                                u2_old = swap['user2_old']
                                group_data[u1_id]['length'] = u2_old
                                group_data[u2_id]['length'] = u1_old

                                # 检查u1是否亏了
                                u1_loss = u1_old - u2_old
                                if u1_loss > 0:
                                    insurance_info = self._check_victim_insurance(group_id, group_data, u1_id, u1_loss)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])

                                # 检查u2是否亏了
                                u2_loss = u2_old - u1_old
                                if u2_loss > 0:
                                    insurance_info = self._check_victim_insurance(group_id, group_data, u2_id, u2_loss)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])

                        # 处理金币变化
                        for coin_change in chaos_storm.get('coin_changes', []):
                            uid = coin_change['user_id']
                            amount = coin_change['amount']
                            current_coins = self._get_new_game_coins(group_id, uid)
                            self._update_new_game_coins(group_id, uid, current_coins + amount)

                        # 同时处理护盾消耗（混沌风暴多人）
                        for shield_info in ctx.extra.get('consume_shields', []):
                            target_id = shield_info['user_id']
                            if target_id in group_data:
                                current = group_data[target_id].get('shield_charges', 0)
                                group_data[target_id]['shield_charges'] = max(0, current - shield_info['amount'])

                        self._save_niuniu_data(niuniu_data)

                    # 处理月牙天冲的特殊逻辑（合并护盾消耗+祸水东引）
                    if ctx.extra.get('yueya_tianchong'):
                        yueya = ctx.extra['yueya_tianchong']
                        niuniu_data = self._load_niuniu_data()
                        group_data = niuniu_data.setdefault(group_id, {})

                        target_id = yueya['target_id']
                        damage = yueya['damage']

                        # 扣除目标的长度（考虑祸水东引）
                        if target_id in group_data and damage > 0:
                            # 检查是否有护盾（护盾优先于转嫁）
                            if not ctx.extra.get('consume_shield'):
                                transfer_info = self._check_risk_transfer(
                                    group_data, target_id, damage, 0, [user_id]
                                )
                                if transfer_info['transferred']:
                                    # 转嫁成功，扣新受害者
                                    new_victim_id = transfer_info['new_victim_id']
                                    group_data[new_victim_id]['length'] = group_data[new_victim_id].get('length', 0) - damage
                                    # 消耗转嫁次数
                                    group_data[target_id]['risk_transfer_charges'] = transfer_info['charges_remaining']
                                    result_msg.append(transfer_info['message'])
                                    # 检查新受害者的保险
                                    insurance_info = self._check_victim_insurance(group_id, group_data, new_victim_id, damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                                else:
                                    # 正常扣除
                                    group_data[target_id]['length'] = group_data[target_id].get('length', 0) - damage
                                    # 检查目标的保险
                                    insurance_info = self._check_victim_insurance(group_id, group_data, target_id, damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                            # 有护盾则不扣（已在效果中处理）

                        # 处理护盾消耗
                        if ctx.extra.get('consume_shield'):
                            shield_info = ctx.extra['consume_shield']
                            shield_target_id = shield_info['user_id']
                            if shield_target_id in group_data:
                                current = group_data[shield_target_id].get('shield_charges', 0)
                                group_data[shield_target_id]['shield_charges'] = max(0, current - shield_info['amount'])

                        self._save_niuniu_data(niuniu_data)

                    # 处理牛牛大自爆的特殊逻辑（合并护盾消耗+祸水东引）
                    if ctx.extra.get('dazibao'):
                        dazibao = ctx.extra['dazibao']
                        niuniu_data = self._load_niuniu_data()
                        group_data = niuniu_data.setdefault(group_id, {})

                        # 记录被护盾保护的用户ID
                        shielded_ids = set(s['user_id'] for s in ctx.extra.get('consume_shields', []))

                        # 扣除受害者的长度和硬度（考虑祸水东引）
                        for victim in dazibao.get('victims', []):
                            uid = victim['user_id']
                            if uid not in group_data or victim.get('shielded', False):
                                continue

                            length_damage = victim['length_damage']
                            hardness_damage = victim['hardness_damage']

                            # 检查祸水东引（只看长度是否达到阈值）
                            if length_damage > 0 and uid not in shielded_ids:
                                transfer_info = self._check_risk_transfer(
                                    group_data, uid, length_damage, hardness_damage, [user_id]
                                )
                                if transfer_info['transferred']:
                                    # 转嫁成功，扣新受害者（长度和硬度都转）
                                    new_victim_id = transfer_info['new_victim_id']
                                    group_data[new_victim_id]['length'] = group_data[new_victim_id].get('length', 0) - length_damage
                                    group_data[new_victim_id]['hardness'] = max(1, group_data[new_victim_id].get('hardness', 1) - hardness_damage)
                                    # 消耗转嫁次数
                                    group_data[uid]['risk_transfer_charges'] = transfer_info['charges_remaining']
                                    result_msg.append(transfer_info['message'])
                                    # 检查新受害者的保险（长度>=50或硬度>=10触发）
                                    insurance_info = self._check_victim_insurance(group_id, group_data, new_victim_id, length_damage, hardness_damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                                else:
                                    # 正常扣除
                                    group_data[uid]['length'] = group_data[uid].get('length', 0) - length_damage
                                    group_data[uid]['hardness'] = max(1, group_data[uid].get('hardness', 1) - hardness_damage)
                                    # 检查受害者的保险（长度>=50或硬度>=10触发）
                                    insurance_info = self._check_victim_insurance(group_id, group_data, uid, length_damage, hardness_damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])
                            else:
                                # 只有硬度伤害或被护盾保护
                                group_data[uid]['length'] = group_data[uid].get('length', 0) - length_damage
                                group_data[uid]['hardness'] = max(1, group_data[uid].get('hardness', 1) - hardness_damage)
                                # 检查保险（硬度>=10也可触发）
                                if uid not in shielded_ids:
                                    insurance_info = self._check_victim_insurance(group_id, group_data, uid, length_damage, hardness_damage)
                                    if insurance_info['triggered']:
                                        result_msg.append(insurance_info['message'])

                        # 处理护盾消耗（多人）
                        for shield_info in ctx.extra.get('consume_shields', []):
                            target_id = shield_info['user_id']
                            if target_id in group_data:
                                current = group_data[target_id].get('shield_charges', 0)
                                group_data[target_id]['shield_charges'] = max(0, current - shield_info['amount'])

                        self._save_niuniu_data(niuniu_data)

                    # 记录劫富济贫使用时间
                    if ctx.extra.get('record_jiefu_time'):
                        import time
                        user_data['last_jiefu_time'] = time.time()

                    # 处理牛牛盾牌护盾增加
                    if ctx.extra.get('add_shield_charges'):
                        add_charges = ctx.extra['add_shield_charges']
                        user_data['shield_charges'] = user_data.get('shield_charges', 0) + add_charges

                    # 处理祸水东引转嫁次数增加
                    if ctx.extra.get('add_risk_transfer_charges'):
                        add_charges = ctx.extra['add_risk_transfer_charges']
                        user_data['risk_transfer_charges'] = user_data.get('risk_transfer_charges', 0) + add_charges

                    # 处理上保险次数增加
                    if ctx.extra.get('add_insurance_charges'):
                        add_charges = ctx.extra['add_insurance_charges']
                        user_data['insurance_charges'] = user_data.get('insurance_charges', 0) + add_charges

                    # Apply changes to current user
                    old_length = user_data.get('length', 0)
                    old_hardness = user_data.get('hardness', 1)
                    if ctx.length_change != 0:
                        user_data['length'] = old_length + ctx.length_change
                    if ctx.hardness_change != 0:
                        # 主动自残允许硬度归0，其他情况最小为1，上限100
                        from niuniu_config import ShangbaoxianConfig
                        item_name = ctx.extra.get('item_name', '')
                        if item_name in ShangbaoxianConfig.INTENTIONAL_SELF_HURT_ITEMS:
                            user_data['hardness'] = min(100, max(0, old_hardness + ctx.hardness_change))
                        else:
                            user_data['hardness'] = min(100, max(1, old_hardness + ctx.hardness_change))

                    # 计算实际损失
                    length_loss = max(0, old_length - user_data.get('length', 0))
                    hardness_loss = max(0, old_hardness - user_data.get('hardness', 1))

                    # 检查保险理赔（长度>=50或硬度>=10，且不是主动自残类道具）
                    from niuniu_config import ShangbaoxianConfig
                    item_name = ctx.extra.get('item_name', '')
                    is_intentional_self_hurt = item_name in ShangbaoxianConfig.INTENTIONAL_SELF_HURT_ITEMS
                    if user_data.get('insurance_charges', 0) > 0 and not is_intentional_self_hurt:
                        length_triggered = length_loss >= ShangbaoxianConfig.LENGTH_THRESHOLD
                        hardness_triggered = hardness_loss >= ShangbaoxianConfig.HARDNESS_THRESHOLD
                        if length_triggered or hardness_triggered:
                            user_data['insurance_charges'] -= 1
                            # 赔付金币
                            self._update_new_game_coins(group_id, user_id,
                                self._get_new_game_coins(group_id, user_id) + ShangbaoxianConfig.PAYOUT)
                            # 构建消息
                            damage_parts = []
                            if length_loss > 0:
                                damage_parts.append(f"{length_loss}cm长度")
                            if hardness_loss > 0:
                                damage_parts.append(f"{hardness_loss}硬度")
                            damage_str = "、".join(damage_parts)
                            result_msg.append(f"📋 保险理赔！损失{damage_str}，赔付{ShangbaoxianConfig.PAYOUT}金币（剩余{user_data['insurance_charges']}次）")

                    self._save_user_data(group_id, user_id, user_data)
                    result_msg.extend(ctx.messages)
                else:
                    self.main.context.logger.error(f"未找到道具效果类: {selected_item['name']}")
                    yield event.plain_result("⚠️ 道具配置错误，请联系管理员")
                    return

            # 扣除金币（动态定价道具使用效果返回的价格）
            self.update_user_coins(group_id, user_id, user_coins - final_price)

            yield event.plain_result("✅ 购买成功\n" + "\n".join(result_msg))

        except Exception as e:
            self.main.context.logger.error(f"购买错误: {str(e)}")
            yield event.plain_result("⚠️ 购买过程中出现错误，请稍后再试")

    async def show_items(self, event: AstrMessageEvent):
        """显示用户道具及金币总额"""
        from niuniu_config import DELETED_ITEM_REFUND

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        items = self.get_user_items(group_id, user_id)
        user_data = self._get_user_data(group_id, user_id)

        result_list = ["📦 你的道具背包："]
        refund_msgs = []

        # 检查并处理已删除的道具（统一退款）
        if items:
            shop_items = self.get_shop_items()
            shop_names = {i['name'] for i in shop_items}
            items_to_remove = []

            for name, count in list(items.items()):
                if name not in shop_names:
                    # 道具已从商店删除，统一退款
                    total_refund = DELETED_ITEM_REFUND * count
                    self._update_new_game_coins(group_id, user_id,
                        self._get_new_game_coins(group_id, user_id) + total_refund)
                    items_to_remove.append(name)
                    refund_msgs.append(f"🔄 道具「{name}」已下架，退款 {total_refund} 金币")

            # 移除已退款的道具
            if items_to_remove:
                for name in items_to_remove:
                    del items[name]
                user_data['items'] = items
                self._save_user_data(group_id, user_id, user_data)

        # 显示退款信息
        if refund_msgs:
            result_list.extend(refund_msgs)
            result_list.append("")

        # 显示道具信息
        if items:
            shop_items = self.get_shop_items()
            for name, count in items.items():
                item_info = next((i for i in shop_items if i['name'] == name), None)
                if item_info:
                    result_list.append(f"🔹 {name}x{count} - {item_info['desc']}")

        # 显示护盾次数
        shield_charges = user_data.get('shield_charges', 0)
        if shield_charges > 0:
            result_list.append(f"🛡️ 牛牛盾牌护盾：{shield_charges}次")

        # 显示转嫁次数
        risk_transfer_charges = user_data.get('risk_transfer_charges', 0)
        if risk_transfer_charges > 0:
            result_list.append(f"🔄 祸水东引：{risk_transfer_charges}次")

        # 显示保险次数
        insurance_charges = user_data.get('insurance_charges', 0)
        if insurance_charges > 0:
            result_list.append(f"📋 上保险：{insurance_charges}次")

        if not items and shield_charges == 0 and risk_transfer_charges == 0 and insurance_charges == 0:
            result_list.append("🛍️ 你的背包里还没有道具哦~")

        # 显示金币总额
        total_coins = self.get_user_coins(group_id, user_id)
        if total_coins < 0:
            debt_msgs = [
                f"💸 你的金币：{total_coins} (欠债中，要打工还钱了！)",
                f"📉 你的金币：{total_coins} (负债累累，牛牛都要被抵押了！)",
                f"💀 你的金币：{total_coins} (破产警告！快去搬砖！)",
                f"🚨 你的金币：{total_coins} (已被列入老赖名单！)",
                f"😭 你的金币：{total_coins} (穷得只剩牛牛了...)"
            ]
            result_list.append(random.choice(debt_msgs))
        else:
            result_list.append(f"💰 你的金币：{total_coins}")

        yield event.plain_result("\n".join(result_list))
