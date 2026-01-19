import os
import yaml
import copy
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
        """创建默认商城配置文件"""
        if not os.path.exists(self.shop_config_path):
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

        # 检查用户是否有足够的金币
        if user_coins < selected_item['price']:
            yield event.plain_result("❌ 金币不足，无法购买")
            return

        try:
            result_msg = []
            user_data = self._get_user_data(group_id, user_id)

            if selected_item['type'] == 'passive':
                # Passive items go to inventory
                user_data.setdefault('items', {})
                current = user_data['items'].get(selected_item['name'], 0)
                if current >= selected_item.get('max', 3):
                    yield event.plain_result(f"⚠️ 已达到最大持有量（最大{selected_item['max']}个）")
                    return
                user_data['items'][selected_item['name']] = current + 1
                result_msg.append(f"📦 获得 {selected_item['name']}x1")
                self._save_user_data(group_id, user_id, user_data)

            elif selected_item['type'] == 'active':
                # Active items use effect system
                ctx = EffectContext(
                    group_id=group_id,
                    user_id=user_id,
                    nickname=nickname,
                    user_data=user_data,
                    user_length=user_data.get('length', 0),
                    user_hardness=user_data.get('hardness', 1),
                    extra={'item_name': selected_item['name']}
                )

                # Trigger ON_PURCHASE for this specific item
                effect = self.main.effects.effects.get(selected_item['name'])
                if effect and EffectTrigger.ON_PURCHASE in effect.triggers:
                    ctx = effect.on_trigger(EffectTrigger.ON_PURCHASE, ctx)

                    # Apply changes
                    if ctx.length_change != 0:
                        user_data['length'] = user_data.get('length', 0) + ctx.length_change
                    if ctx.hardness_change != 0:
                        user_data['hardness'] = max(1, user_data.get('hardness', 1) + ctx.hardness_change)

                    self._save_user_data(group_id, user_id, user_data)
                    result_msg.extend(ctx.messages)
                else:
                    self.main.context.logger.error(f"未找到道具效果类: {selected_item['name']}")
                    yield event.plain_result("⚠️ 道具配置错误，请联系管理员")
                    return

            # 扣除金币
            self.update_user_coins(group_id, user_id, user_coins - selected_item['price'])

            yield event.plain_result("✅ 购买成功\n" + "\n".join(result_msg))

        except Exception as e:
            self.main.context.logger.error(f"购买错误: {str(e)}")
            yield event.plain_result("⚠️ 购买过程中出现错误，请稍后再试")

    async def show_items(self, event: AstrMessageEvent):
        """显示用户道具及金币总额"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        items = self.get_user_items(group_id, user_id)
        
        result_list = ["📦 你的道具背包："]

        # 显示道具信息
        if items:
            shop_items = self.get_shop_items()
            for name, count in items.items():
                item_info = next((i for i in shop_items if i['name'] == name), None)
                if item_info:
                    result_list.append(f"🔹 {name}x{count} - {item_info['desc']}")

        else:
            result_list.append("🛍️ 你的背包里还没有道具哦~")
        
        # 显示金币总额
        total_coins = self.get_user_coins(group_id, user_id)
        result_list.append(f"💰 你的金币：{total_coins}")

        yield event.plain_result("\n".join(result_list))
