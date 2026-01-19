import random
import yaml
import os
import re
import time
import json
import sys
from astrbot.api.all import *
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from niuniu_shop import NiuniuShop
from niuniu_games import NiuniuGames
from niuniu_effects import create_effect_manager, EffectTrigger, EffectContext
from niuniu_config import (
    PLUGIN_DIR, NIUNIU_LENGTHS_FILE, GAME_TEXTS_FILE, LAST_ACTION_FILE
)

# 确保目录存在
os.makedirs(PLUGIN_DIR, exist_ok=True)

@register("niuniu_plugin", "长安某", "牛牛插件，包含注册牛牛、打胶、我的牛牛、比划比划、牛牛排行等功能", "4.7.2")
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
        self.effects.set_shop(self.shop)  # 设置商城引用
    
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
        except:
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
        if length <= -100:
            return f"{length/100:.2f}m (凹)"
        elif length < 0:
            return f"{length}cm (凹)"
        elif length == 0:
            return "0cm (无)"
        elif length >= 100:
            return f"{length/100:.2f}m"
        return f"{length}cm"

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
    niuniu_commands = ["牛牛菜单", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛", "比划比划", "牛牛排行"]

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
        elif msg.startswith("牛牛菜单"):
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

        # 处理其他命令
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
            if is_rushing:
                yield event.plain_result("❌ 牛牛快冲晕了，还做不了其他事情，要不先停止开冲？")
                return
            async for result in self.games.fly_plane(event):
                yield result
        else:
            # 处理其他命令
            handler_map = {
                "注册牛牛": self._register,
                "打胶": self._dajiao,
                "我的牛牛": self._show_status,
                "比划比划": self._compare,
                "牛牛排行": self._show_ranking,
                "牛牛商城": self.shop.show_shop,
                "牛牛购买": self.shop.handle_buy,
                "牛牛背包": self.shop.show_items
            }

            for cmd, handler in handler_map.items():
                if msg.startswith(cmd):
                    if is_rushing:
                        yield event.plain_result("❌ 牛牛快冲晕了，还做不了其他事情，要不先停止开冲？")
                        return
                    async for result in handler(event):
                        yield result
                    return
    @event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """私聊消息处理器"""
        msg = event.message_str.strip()
        niuniu_commands = [
            "牛牛菜单", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛",
            "比划比划", "牛牛排行", "牛牛商城", "牛牛购买", "牛牛背包",
            "开冲", "停止开冲", "飞飞机"  
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
        """打胶功能"""
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

        # 计算变化
        change = 0
        current_time = time.time()
        hardness_updated = False
        old_hardness = user_data['hardness']

        if elapsed < self.COOLDOWN_30_MIN:  # 10-30分钟
            rand = random.random()
            if rand < 0.4:   # 40% 增加
                change = random.randint(2, 5)
            elif rand < 0.7:  # 30% 减少
                change = -random.randint(1, 3)
                template = random.choice(self.niuniu_texts['dajiao']['decrease'])
        else:  # 30分钟后
            rand = random.random()
            if rand < 0.7:  # 70% 增加
                change = random.randint(3, 6)
                user_data['hardness'] = min(user_data['hardness'] + 1, 10)
                if user_data['hardness'] > old_hardness:
                    hardness_updated = True
            elif rand < 0.9:  # 20% 减少
                change = -random.randint(1, 2)
                template = random.choice(self.niuniu_texts['dajiao']['decrease_30min'])

        # 应用变化并保存到文件
        updated_data = {
            'length': user_data['length'] + change
        }
        if hardness_updated:
            updated_data['hardness'] = user_data['hardness']
        self.update_user_data(group_id, user_id, updated_data)

        # 更新冷却时间
        last_actions = self._load_last_actions()
        last_actions.setdefault(group_id, {}).setdefault(user_id, {})['dajiao'] = current_time
        self.update_last_actions(last_actions)

        # 生成消息
        if change > 0:
            template = random.choice(self.niuniu_texts['dajiao']['increase'])
        elif change < 0:
            template = template
        else:
            template = random.choice(self.niuniu_texts['dajiao']['no_effect'])

        text = template.format(nickname=nickname, change=abs(change))

        # 合并效果消息
        if ctx.messages:
            final_text = "\n".join(ctx.messages + [text])
        else:
            final_text = text

        # 重新获取最新数据以显示
        user_data = self.get_user_data(group_id, user_id)
        result_text = f"{final_text}\n当前长度：{self.format_length(user_data['length'])}"
        if hardness_updated:
            result_text += f"\n💪 硬度提升: {old_hardness} → {user_data['hardness']}"
        else:
            result_text += f"\n当前硬度：{user_data['hardness']}"
        yield event.plain_result(result_text)

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

        # 创建效果上下文
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

        # 触发 BEFORE_COMPARE 效果（如夺心魔）
        ctx = self.effects.trigger(EffectTrigger.BEFORE_COMPARE, ctx, user_items, target_items)

        # 消耗触发的道具
        self.effects.consume_items(group_id, user_id, ctx.items_to_consume)

        # 如果被拦截（如夺心魔触发），直接返回结果
        if ctx.intercept:
            # 应用长度变化
            if ctx.length_change != 0:
                new_user_len = user_data['length'] + ctx.length_change
                self.update_user_data(group_id, user_id, {'length': new_user_len})
            if ctx.target_length_change != 0:
                new_target_len = target_data['length'] + ctx.target_length_change
                self.update_user_data(group_id, target_id, {'length': new_target_len})

            # 添加长度变化显示
            user_data = self.get_user_data(group_id, user_id)
            target_data = self.get_user_data(group_id, target_id)
            ctx.messages.append(f"🗡️ {nickname}: {self.format_length(old_u_len)} → {self.format_length(user_data['length'])}")
            ctx.messages.append(f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} → {self.format_length(target_data['length'])}")

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
        hardness_factor = (u_hardness - t_hardness) * 0.08
        win_prob = min(max(base_win + length_factor + hardness_factor, 0.15), 0.85)

        # 执行判定
        is_win = random.random() < win_prob
        base_gain = random.randint(0, 3)
        base_loss = random.randint(1, 2)

        if is_win:
            # 硬度影响伤害：赢家(user)硬度加成攻击，输家(target)硬度减少损失
            hardness_bonus = max(0, int((u_hardness - 5) * 0.3))
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

            # 负数特殊文案
            if u_len <= 0 and t_len <= 0:
                text += f"\n🕳️ 两个凹牛牛之间的较量！{nickname} 凹得更有型！"
            elif u_len <= 0:
                text += f"\n🎊 逆天改命！{nickname} 凹着都能赢！"
            elif t_len <= 0:
                text += f"\n💀 {target_data['nickname']} 的凹牛牛毫无还手之力..."

            # 添加效果消息
            for msg in ctx.messages:
                text += f"\n{msg}"

            # 额外逻辑：极大劣势但硬度优势获胜奖励
            if u_len < t_len and abs(u_len - t_len) >= 20 and u_hardness > t_hardness:
                extra_gain = random.randint(0, 5)
                self.update_user_data(group_id, user_id, {'length': user_data['length'] + total_gain + extra_gain})
                total_gain += extra_gain
                text += f"\n🎁 由于极大劣势获胜，额外增加 {extra_gain}cm！"

            # 额外逻辑：掠夺（非道具触发，仅当目标长度为正时）
            if abs(u_len - t_len) > 10 and u_len < t_len and t_len > 0:
                stolen_length = int(target_data['length'] * 0.2)
                current_user = self.get_user_data(group_id, user_id)
                current_target = self.get_user_data(group_id, target_id)
                self.update_user_data(group_id, user_id, {'length': current_user['length'] + stolen_length})
                self.update_user_data(group_id, target_id, {'length': current_target['length'] - stolen_length})
                text += f"\n🎉 {nickname} 掠夺了 {stolen_length}cm！"

            # 硬度优势获胜提示
            if abs(u_len - t_len) <= 5 and u_hardness > t_hardness:
                text += f"\n🎉 {nickname} 因硬度优势获胜！"

            if total_gain == 0:
                text += f"\n{self.niuniu_texts['compare']['user_no_increase'].format(nickname=nickname)}"
        else:
            # 硬度影响伤害：赢家(target)硬度加成攻击，输家(user)硬度减少损失
            hardness_bonus = max(0, int((t_hardness - 5) * 0.3))
            hardness_defense = max(0, int((u_hardness - 5) * 0.2))
            gain = base_gain + hardness_bonus
            loss = max(1, base_loss - hardness_defense)

            # 触发 ON_COMPARE_LOSE 效果
            ctx = self.effects.trigger(EffectTrigger.ON_COMPARE_LOSE, ctx, user_items, target_items)
            self.effects.consume_items(group_id, user_id, ctx.items_to_consume)

            # 更新目标数据
            self.update_user_data(group_id, target_id, {'length': target_data['length'] + gain})

            # 检查是否防止损失
            if ctx.prevent_loss:
                # 不减少长度
                pass
            else:
                self.update_user_data(group_id, user_id, {'length': user_data['length'] - loss})

            text = random.choice(self.niuniu_texts['compare']['lose']).format(
                loser=nickname,
                winner=target_data['nickname'],
                loss=loss if not ctx.prevent_loss else 0
            )

            # 负数特殊文案
            if u_len <= 0 and t_len <= 0:
                text += f"\n🕳️ 凹牛牛对决！{nickname} 凹得不够深..."
            elif u_len <= 0:
                text += f"\n😭 {nickname} 凹着牛牛还敢挑战，真是勇气可嘉..."
            elif t_len <= 0:
                text += f"\n😱 居然输给了凹牛牛！{nickname} 羞愧难当！"

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

        result_msg = [
            "⚔️ 【牛牛对决结果】 ⚔️",
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

        # 硬度过低触发缠绕
        if not special_event_triggered and (user_data['hardness'] <= 2 or target_data['hardness'] <= 2) and random.random() < 0.05:
            async for msg in self._handle_halving_event(group_id, user_id, target_id, nickname, target_data['nickname'], user_items, target_items, result_msg):
                pass
            tangle_text = random.choice(self.niuniu_texts['compare']['tangle']).format(
                nickname1=nickname, nickname2=target_data['nickname']
            )
            result_msg.append(tangle_text)
            special_event_triggered = True

        # 长度相近触发减半
        if not special_event_triggered and abs(u_len - t_len) < 10 and random.random() < 0.025:
            async for msg in self._handle_halving_event(group_id, user_id, target_id, nickname, target_data['nickname'], user_items, target_items, result_msg):
                pass
            halving_text = random.choice(self.niuniu_texts['compare']['halving']).format(
                nickname1=nickname, nickname2=target_data['nickname']
            )
            result_msg.append(halving_text)
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
            new_hardness = min(10, winner_data['hardness'] + 2)
            self.update_user_data(group_id, winner_id, {'hardness': new_hardness})
            awakening_text = random.choice(self.niuniu_texts['compare'].get('hardness_awakening', ['💪 【硬度觉醒】硬度+2！'])).format(nickname=winner_name)
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
            self.update_user_data(group_id, loser_id, {'length': loser_data['length'] + 5})
            lucky_text = random.choice(self.niuniu_texts['compare'].get('lucky_strike', ['🍀 【幸运一击】+5cm！'])).format(loser=loser_name)
            result_msg.append(lucky_text)
            special_event_triggered = True

        # 更新最终显示的长度
        final_user = self.get_user_data(group_id, user_id)
        final_target = self.get_user_data(group_id, target_id)
        result_msg[1] = f"🗡️ {nickname}: {self.format_length(old_u_len)} → {self.format_length(final_user['length'])}"
        result_msg[2] = f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} → {self.format_length(final_target['length'])}"

        yield event.plain_result("\n".join(result_msg))

    async def _handle_halving_event(self, group_id, user_id, target_id, nickname, target_nickname, user_items, target_items, result_msg):
        """处理减半事件，使用效果系统"""
        user_data = self.get_user_data(group_id, user_id)
        target_data = self.get_user_data(group_id, target_id)
        original_user_len = user_data['length']
        original_target_len = target_data['length']

        # 先执行减半
        self.update_user_data(group_id, user_id, {'length': original_user_len // 2})
        self.update_user_data(group_id, target_id, {'length': original_target_len // 2})

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
        yield event.plain_result(text)

    async def _show_ranking(self, event):
        """显示排行榜（从文件读取数据）"""
        group_id = str(event.message_obj.group_id)
        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 过滤有效用户数据
        data = self._load_niuniu_lengths()
        group_data = data.get(group_id, {'plugin_enabled': False})
        valid_users = [
            (uid, data) for uid, data in group_data.items()
            if isinstance(data, dict) and 'length' in data
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
            ranking.append(
                f"{idx}. {data['nickname']} ➜ {self.format_length(data['length'])} 💪{hardness}"
            )

        # 如果总人数超过10，显示...和后3名
        if total_users > 10:
            ranking.append("...")
            # 取后3名（避免与前10重复）
            bottom_start = max(10, total_users - 3)
            bottom_users = sorted_users[bottom_start:]
            for idx, (uid, data) in enumerate(bottom_users, bottom_start + 1):
                hardness = data.get('hardness', 1)
                ranking.append(
                    f"{idx}. {data['nickname']} ➜ {self.format_length(data['length'])} 💪{hardness}"
                )

        yield event.plain_result("\n".join(ranking))
    async def _show_menu(self, event):
        """显示菜单"""
        yield event.plain_result(self.niuniu_texts['menu']['default'])
    # endregion
