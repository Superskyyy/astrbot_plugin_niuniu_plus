import random
import time
import yaml
from astrbot.api.all import AstrMessageEvent
import pytz
from datetime import datetime
import os
from typing import Dict, Any
from niuniu_config import (
    TIMEZONE, NIUNIU_LENGTHS_FILE, Cooldowns, FLY_PLANE_EVENTS, RushConfig
)

class NiuniuGames:
    def __init__(self, main_plugin):
        self.main = main_plugin  # 主插件实例
        self.shanghai_tz = pytz.timezone(TIMEZONE)
        self.data_file = NIUNIU_LENGTHS_FILE
    
    def _load_data(self) -> Dict[str, Any]:
        """加载YAML数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            return {}
        except Exception as e:
            self.main.context.logger.error(f"加载数据失败: {str(e)}")
            return {}
    
    def _save_data(self, data: Dict[str, Any]):
        """保存YAML数据"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            self.main.context.logger.error(f"保存数据失败: {str(e)}")
    
    async def start_rush(self, event: AstrMessageEvent):
        """冲(咖啡)游戏"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        
        # 从文件加载数据
        data = self._load_data()
        group_data = data.get(group_id, {})
        
        # 检查插件是否启用
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return
        
        # 从文件获取用户数据
        user_data = group_data.get(user_id, {})
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return
        
        # 获取当前日期（基于开冲时间）
        current_time = time.time()
        current_date = datetime.fromtimestamp(current_time, self.shanghai_tz).strftime("%Y-%m-%d")
        
        # 检查是否需要重置今日次数
        if user_data.get('last_rush_start_date') != current_date:
            user_data['today_rush_count'] = 0
            user_data['last_rush_start_date'] = current_date
        
        # 检查今日已冲次数
        if user_data.get('today_rush_count', 0) >= Cooldowns.RUSH_DAILY_LIMIT:
            yield event.plain_result(f" {nickname} 你冲得到处都是，明天再来吧")
            return

        # 检查冷却时间
        last_rush_end_time = user_data.get('last_rush_end_time', 0)
        if current_time - last_rush_end_time < Cooldowns.RUSH_COOLDOWN:
            remaining = Cooldowns.RUSH_COOLDOWN - (current_time - last_rush_end_time)
            yield event.plain_result(f"⏳ {nickname} 牛牛冲累了，休息{int(remaining//60)+1}分钟再冲吧")
            return

        # 检查是否已经在冲
        if user_data.get('is_rushing', False):
            remaining = user_data.get('rush_start_time', 0) + Cooldowns.RUSH_MAX_TIME - current_time
            if remaining > 0:
                yield event.plain_result(f"⏳ {nickname} 你已经在冲了（剩余{int(remaining//60)+1}分钟）")
                return
        
        # 更新开冲状态
        user_data['is_rushing'] = True
        user_data['rush_start_time'] = current_time
        user_data['today_rush_count'] = user_data.get('today_rush_count', 0) + 1
        
        # 保存到文件
        data.setdefault(group_id, {})[user_id] = user_data
        self._save_data(data)
        
        rush_msgs = [
            f"💪 {nickname} 芜湖！开冲！\n⏱️ 后台计时中，你可以继续打胶、比划~\n📝 输入「停止开冲」来结算金币",
            f"🚀 {nickname} 开始后台冲刺！\n🎮 放心玩其他的，冲的金币照算~\n📝 输入「停止开冲」来收菜",
            f"⚡ {nickname} 的牛牛开始疯狂输出！\n🎯 不影响其他操作，后台自动计时\n📝 想停就喊「停止开冲」",
        ]
        yield event.plain_result(random.choice(rush_msgs))
    
    async def stop_rush(self, event: AstrMessageEvent):
        """停止开冲并结算金币"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        
        # 从文件加载数据
        data = self._load_data()
        user_data = data.get(group_id, {}).get(user_id, {})
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return
        
        # 检查是否在冲
        if not user_data.get('is_rushing', False):
            yield event.plain_result(f"❌ {nickname} 你当前没有在冲")
            return
        
        # 计算冲的时间
        work_time = time.time() - user_data.get('rush_start_time', 0)

        # 时间不足最小时间无奖励
        if work_time < Cooldowns.RUSH_MIN_TIME:
            yield event.plain_result(f"❌ {nickname} 至少冲够{Cooldowns.RUSH_MIN_TIME // 60}分钟才能停")
            return

        # 超过最大时间按最大时间计算
        work_time = min(work_time, Cooldowns.RUSH_MAX_TIME)

        # 计算金币（基础收益有上限）
        base_coins = min(int(work_time / 60 * RushConfig.COINS_PER_MINUTE), RushConfig.MAX_COINS)
        bonus_coins = 0
        bonus_msg = ""

        # 时长奖励机制
        minutes = int(work_time / 60)
        hours = minutes // 60

        # 超过30分钟有概率触发奖励事件
        if minutes >= 30 and random.random() < 0.2:  # 20%概率
            bonus_events = [
                ("🎰 冲到一半捡到了神秘红包！", random.randint(10, 30)),
                ("⭐ 触发了冲刺暴击！", random.randint(20, 50)),
                ("🍀 幸运加成！", random.randint(15, 40)),
                ("🎁 隐藏成就「持久战士」！", 25),
            ]
            event_msg, bonus = random.choice(bonus_events)
            bonus_coins = bonus
            bonus_msg = f"\n{event_msg} +{bonus}金币"

        # 每小时额外奖励（固定）
        if hours >= 1:
            hour_bonus = hours * 5  # 每小时+5金币
            bonus_coins += hour_bonus
            bonus_msg += f"\n🏆 坚持{hours}小时！额外 +{hour_bonus}金币"

        # 里程碑奖励
        if hours >= 3:
            bonus_coins += 25
            bonus_msg += f"\n🎖️ 3小时里程碑！+25金币"
        if hours >= 6:
            bonus_coins += 50
            bonus_msg += f"\n🏅 6小时里程碑！+50金币"
        if hours >= 9:
            bonus_coins += 75
            bonus_msg += f"\n🥇 9小时里程碑！+75金币"
        if hours >= 12:
            bonus_coins += 100
            bonus_msg += f"\n👑 12小时满冲成就！+100金币"

        # 超过2小时有小概率触发超级奖励
        if hours >= 2 and random.random() < 0.1:  # 10%概率
            super_bonus = random.randint(20, 50)
            bonus_coins += super_bonus
            bonus_msg += f"\n🌟 【超级冲刺王】触发！+{super_bonus}金币！"

        total_coins = base_coins + bonus_coins
        user_data['coins'] = user_data.get('coins', 0) + total_coins

        # 保存到文件
        data.setdefault(group_id, {})[user_id] = user_data
        self._save_data(data)

        # 结算消息
        result_lines = [
            f"🎉 {nickname} 冲刺结束！",
            f"⏱️ 冲了 {minutes} 分钟",
            f"💰 基础收益：{base_coins} 金币",
        ]
        if bonus_msg:
            result_lines.append(bonus_msg)
        result_lines.append(f"📊 总计：{total_coins} 金币")

        yield event.plain_result("\n".join(result_lines))
        
        # 重置状态
        user_data['is_rushing'] = False
        user_data['last_rush_end_time'] = time.time()
        
        # 再次保存到文件
        data.setdefault(group_id, {})[user_id] = user_data
        self._save_data(data)
    
    async def fly_plane(self, event: AstrMessageEvent):
        """飞机游戏"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        
        #从文件加载数据
        data = self._load_data()
        group_data = data.get(group_id, {})
        
        # 检查插件是否启用
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return
        
        #从文件获取用户数据
        user_data = group_data.get(user_id, {})
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return
        
        # 检查冷却时间
        last_fly_time = user_data.get('last_fly_time', 0)
        if time.time() - last_fly_time < Cooldowns.FLY_PLANE_COOLDOWN:
            remaining = Cooldowns.FLY_PLANE_COOLDOWN - (time.time() - last_fly_time)
            yield event.plain_result(f"✈️ 油箱空了，{nickname} {int(remaining//60)+1}分钟后可再起飞")
            return

        # 飞行事件
        event_template = random.choice(FLY_PLANE_EVENTS)
        event_coins = random.randint(event_template["coins_min"], event_template["coins_max"])

        # 更新金币和时间
        user_data['coins'] = user_data.get('coins', 0) + event_coins
        user_data['last_fly_time'] = time.time()
        
        # 保存到文件
        data.setdefault(group_id, {})[user_id] = user_data
        self._save_data(data)

        if event_coins >= 0:
            yield event.plain_result(f"✈️ {nickname} {event_template['desc']}\n💰 获得 {event_coins} 金币！")
        else:
            yield event.plain_result(f"✈️ {nickname} {event_template['desc']}\n💸 损失 {abs(event_coins)} 金币！")
    
    def update_user_coins(self, group_id: str, user_id: str, coins: float):
        """更新用户金币"""
        data = self._load_data()
        user_data = data.setdefault(str(group_id), {}).setdefault(str(user_id), {})
        user_data['coins'] = user_data.get('coins', 0) + coins
        data[str(group_id)][str(user_id)] = user_data
        self._save_data(data)
    
    def get_user_coins(self, group_id: str, user_id: str) -> float:
        """获取用户金币"""
        data = self._load_data()
        user_data = data.get(str(group_id), {}).get(str(user_id), {})
        return user_data.get('coins', 0)
