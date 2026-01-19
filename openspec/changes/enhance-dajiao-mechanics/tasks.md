# Tasks: enhance-dajiao-mechanics

## Implementation Order

1. [x] 添加配置常量到 `niuniu_config.py`
   - DajiaoEvents 类：事件概率
   - DajiaoCombo 类：连击奖励配置
   - DailyBonus：每日首次奖励

2. [x] 添加事件文本到 `niuniu_game_texts.yml`
   - critical, fumble, hardness_awakening
   - coin_drop, time_warp, inspiration
   - audience_effect, mysterious_force
   - combo_bonus, daily_first

3. [x] 修改 `main.py` 打胶逻辑
   - 添加用户数据字段：combo_count, last_dajiao_date, inspiration_active
   - 实现每日首次检测
   - 实现连击追踪和奖励
   - 实现8种随机事件
   - 实现观众效应（查找最近5分钟打胶的用户）

4. [x] 语法验证通过
