# Niuniu Plugin Configuration
# All hardcoded values extracted here for easy modification

# =============================================================================
# File Paths
# =============================================================================
PLUGIN_DIR = 'data/plugins/astrbot_plugin_niuniu'
NIUNIU_LENGTHS_FILE = 'data/niuniu_lengths.yml'
SIGN_DATA_FILE = 'data/sign_data.yml'
SHOP_CONFIG_FILE = f'{PLUGIN_DIR}/niuniu_shop.yml'
LAST_ACTION_FILE = f'{PLUGIN_DIR}/last_actions.yml'

# 文本配置文件（项目根目录）
import os as _os
_PLUGIN_ROOT = _os.path.dirname(_os.path.abspath(__file__))
GAME_TEXTS_FILE = _os.path.join(_PLUGIN_ROOT, 'niuniu_game_texts.yml')

# =============================================================================
# General Settings
# =============================================================================
TIMEZONE = 'Asia/Shanghai'

# =============================================================================
# Cooldowns (in seconds)
# =============================================================================
class Cooldowns:
    DAJIAO_COOLDOWN = 600          # 10 minutes - dajiao cooldown
    DAJIAO_BONUS_THRESHOLD = 1200  # 20 minutes - after this, better rewards
    COMPARE_COOLDOWN = 600         # 10 minutes - compare cooldown per target
    COMPARE_LIMIT_WINDOW = 600     # 10 minutes - window for compare count limit
    COMPARE_LIMIT_COUNT = 3        # Max compares within window

    RUSH_COOLDOWN = 1800           # 30 minutes - cooldown between rushes
    RUSH_MIN_TIME = 600            # 10 minutes - minimum time to get reward
    RUSH_MAX_TIME = 43200          # 12 hours - maximum counted time
    RUSH_DAILY_LIMIT = 3           # Max rushes per day

    FLY_PLANE_COOLDOWN = 7200      # 2 hours - fly plane cooldown

# =============================================================================
# Dajiao (打胶) Configuration
# =============================================================================
class DajiaoConfig:
    # 10-30 minute window probabilities and ranges
    EARLY_INCREASE_CHANCE = 0.4    # 40% chance to increase
    EARLY_DECREASE_CHANCE = 0.3    # 30% chance to decrease (0.4 + 0.3 = 0.7)
    EARLY_INCREASE_MIN = 2
    EARLY_INCREASE_MAX = 10
    EARLY_DECREASE_MIN = 1
    EARLY_DECREASE_MAX = 3

    # After 30 minute probabilities and ranges
    LATE_INCREASE_CHANCE = 0.7     # 70% chance to increase
    LATE_DECREASE_CHANCE = 0.2     # 20% chance to decrease (0.7 + 0.2 = 0.9)
    LATE_INCREASE_MIN = 4
    LATE_INCREASE_MAX = 12
    LATE_DECREASE_MIN = 1
    LATE_DECREASE_MAX = 2
    LATE_HARDNESS_INCREASE = 1     # Hardness increase on success
    MAX_HARDNESS = 100             # Maximum hardness cap

# =============================================================================
# Dajiao Random Events Configuration
# =============================================================================
class DajiaoEvents:
    # 随机事件概率
    CRITICAL_CHANCE = 0.03         # 3% 暴击 - 增长x3
    FUMBLE_CHANCE = 0.02           # 2% 失手 - 损失x2
    HARDNESS_AWAKENING_CHANCE = 0.05  # 5% 硬度觉醒 - +1~2硬度
    COIN_DROP_CHANCE = 0.08        # 8% 金币掉落 - 10-30金币
    TIME_WARP_CHANCE = 0.02        # 2% 时间扭曲 - 重置冷却
    INSPIRATION_CHANCE = 0.03      # 3% 灵感迸发 - 下次必成功
    AUDIENCE_EFFECT_CHANCE = 0.05  # 5% 观众效应 - 双方+1cm
    MYSTERIOUS_FORCE_CHANCE = 0.02 # 2% 神秘力量 - 随机±5~15cm

    # 事件参数
    COIN_DROP_MIN = 10
    COIN_DROP_MAX = 30
    HARDNESS_AWAKENING_MIN = 1
    HARDNESS_AWAKENING_MAX = 2
    MYSTERIOUS_FORCE_MIN = 5
    MYSTERIOUS_FORCE_MAX = 15
    AUDIENCE_EFFECT_WINDOW = 300   # 5分钟内有人打胶才触发

# =============================================================================
# Dajiao Combo Configuration
# =============================================================================
class DajiaoCombo:
    # 连击奖励阈值和奖励
    COMBO_3_THRESHOLD = 3
    COMBO_3_LENGTH_BONUS = 1

    COMBO_5_THRESHOLD = 5
    COMBO_5_LENGTH_BONUS = 2
    COMBO_5_COIN_BONUS = 5

    COMBO_10_THRESHOLD = 10
    COMBO_10_LENGTH_BONUS = 5
    COMBO_10_COIN_BONUS = 20
    COMBO_10_HARDNESS_BONUS = 1

# =============================================================================
# Dajiao Daily Bonus Configuration
# =============================================================================
class DailyBonus:
    FIRST_DAJIAO_LENGTH_BONUS = 2  # 每日首次打胶额外+2cm

# =============================================================================
# Dajiao Time Period Configuration (24小时时段感知)
# =============================================================================
class TimePeriod:
    # 时段定义 (小时范围, 时段名称, 增益概率加成, 额外长度加成)
    PERIODS = {
        'morning_glory': {  # 早间时间
            'hours': (6, 9),
            'name': '早间时间',
            'success_bonus': 0.15,    # +15% 成功率
            'length_bonus': 1,        # 额外+1cm
        },
        'work_time': {  # 上班摸鱼
            'hours': (9, 12),
            'name': '摸鱼时间',
            'success_bonus': 0,
            'length_bonus': 0,
        },
        'lunch_sleepy': {  # 午后犯困
            'hours': (12, 14),
            'name': '午后犯困',
            'success_bonus': -0.05,   # -5% 成功率
            'length_bonus': 0,
        },
        'afternoon': {  # 下午
            'hours': (14, 18),
            'name': '下午时光',
            'success_bonus': 0,
            'length_bonus': 0,
        },
        'evening_vigor': {  # 晚间精力旺盛
            'hours': (18, 22),
            'name': '精力旺盛',
            'success_bonus': 0.1,     # +10% 成功率
            'length_bonus': 0,
        },
        'late_night': {  # 深夜
            'hours': (22, 24),
            'name': '夜深人静',
            'success_bonus': 0.05,    # +5% 成功率
            'length_bonus': 0,
            'special_chance': 0.1,    # 10% 触发深夜特殊事件
        },
        'midnight': {  # 凌晨
            'hours': (0, 6),
            'name': '熬夜时间',
            'success_bonus': -0.05,   # -5% 成功率
            'length_bonus': 0,
            'special_chance': 0.15,   # 15% 触发凌晨特殊事件
        },
    }

# =============================================================================
# Compare (比划) Configuration
# =============================================================================
class CompareConfig:
    BASE_WIN_PROBABILITY = 0.5     # Base 50% win chance
    LENGTH_FACTOR_MAX = 0.2        # Length can affect up to 20% of win rate
    HARDNESS_FACTOR_PER_POINT = 0.05  # Each hardness point = 5% win rate
    MIN_WIN_PROBABILITY = 0.2      # Minimum win probability
    MAX_WIN_PROBABILITY = 0.8      # Maximum win probability

    WIN_GAIN_MIN = 0
    WIN_GAIN_MAX = 3
    WIN_LOSS_MIN = 1
    WIN_LOSS_MAX = 2

    LOSE_GAIN_MIN = 0
    LOSE_GAIN_MAX = 3
    LOSE_LOSS_MIN = 1
    LOSE_LOSS_MAX = 2

    HARDNESS_DECAY_CHANCE = 0.3    # 30% chance to lose hardness after compare

    # Special events
    DRAW_CHANCE = 0.075            # 7.5% chance for draw when lengths close
    DRAW_LENGTH_THRESHOLD = 5      # Length difference for draw chance

    TANGLE_CHANCE = 0.05           # 5% chance for tangle when hardness low
    TANGLE_HARDNESS_THRESHOLD = 2  # Hardness threshold for tangle

    HALVING_CHANCE = 0.025         # 2.5% chance for halving when lengths close
    HALVING_LENGTH_THRESHOLD = 10  # Length difference for halving chance

    # Underdog bonus
    UNDERDOG_LENGTH_THRESHOLD = 20
    UNDERDOG_EXTRA_GAIN_MIN = 0
    UNDERDOG_EXTRA_GAIN_MAX = 5

    # Plunder mechanics
    PLUNDER_LENGTH_THRESHOLD = 10
    PLUNDER_PERCENT = 0.2          # 20% plunder

    # Cuihuo item bonus
    CUIHUO_LENGTH_THRESHOLD = 10
    CUIHUO_PLUNDER_PERCENT = 0.1   # 10% extra plunder

# =============================================================================
# Compare Streak Configuration (连胜/连败系统)
# =============================================================================
class CompareStreak:
    # 连胜奖励
    WIN_STREAK_THRESHOLD = 3       # 3连胜触发
    WIN_STREAK_BONUS = 0.05        # +5% 胜率

    # 连败保护
    LOSE_STREAK_THRESHOLD = 3      # 3连败触发
    LOSE_STREAK_BONUS = 0.10       # +10% 胜率
    LOSE_STREAK_PROTECTION = True  # 连败时输了不扣长度

# =============================================================================
# Compare Bet Configuration (赌注系统)
# =============================================================================
class CompareBet:
    MIN_BET = 10                   # 最小赌注
    MAX_BET = 10000                # 最大赌注
    WINNER_MULTIPLIER = 1.8        # 赢家获得1.8倍赌注
    LOSER_REFUND = 0               # 输家不退还

# =============================================================================
# Compare Audience Configuration (围观效应)
# =============================================================================
class CompareAudience:
    TIME_WINDOW = 300              # 5分钟内
    MIN_COMPARES = 3               # 至少3次比划
    TRIGGER_CHANCE = 0.3           # 30% 触发概率

    # 效果类型及权重
    EFFECT_WEIGHTS = {
        'bonus_length': 40,        # 40% 加长度（双方）
        'penalty_length': 15,      # 15% 减长度（双方，副作用）
        'bonus_coins': 20,         # 20% 奖励金币（双方）
        'group_bonus': 15,         # 15% 群友福利（全群加金币）
        'group_penalty': 10,       # 10% 群友惩罚（全群减长度）
    }

    # 加长度配置（双方）
    BONUS_LENGTH_MIN = 1
    BONUS_LENGTH_MAX = 3

    # 副作用：减长度配置（双方）
    PENALTY_LENGTH_MIN = 1
    PENALTY_LENGTH_MAX = 2

    # 金币奖励配置（双方）
    BONUS_COINS_MIN = 20
    BONUS_COINS_MAX = 80

    # 群友福利配置（全群注册用户）
    GROUP_BONUS_COINS_MIN = 10
    GROUP_BONUS_COINS_MAX = 30

    # 群友惩罚配置（全群减长度）
    GROUP_PENALTY_LENGTH_MIN = 1
    GROUP_PENALTY_LENGTH_MAX = 3

# =============================================================================
# Registration Configuration
# =============================================================================
class RegisterConfig:
    MIN_LENGTH = 3
    MAX_LENGTH = 10
    INITIAL_HARDNESS = 1
    INITIAL_COINS = 0

# =============================================================================
# Fly Plane (飞飞机) Configuration
# =============================================================================
FLY_PLANE_EVENTS = [
    # 低收益 (20-50)
    {"desc": "牛牛没赶上飞机，不过也算出来透了口气", "coins_min": 20, "coins_max": 40},
    {"desc": "牛牛刚出来就遇到了冷空气，冻得像个鹌鹑似的", "coins_min": 30, "coins_max": 50},
    {"desc": "飞机延误了，牛牛在候机厅睡着了", "coins_min": 20, "coins_max": 35},
    {"desc": "牛牛坐的是廉价航空，腿都伸不开", "coins_min": 25, "coins_max": 40},
    {"desc": "牛牛被安检拦下来检查了半天", "coins_min": 20, "coins_max": 30},
    {"desc": "牛牛的行李丢了，只能空手而归", "coins_min": 15, "coins_max": 25},
    # 中等收益 (50-80)
    {"desc": "无惊无险，牛牛顺利抵达目的地", "coins_min": 60, "coins_max": 75},
    {"desc": "牛牛好像到奇怪的地方，不过也算是完成了目标", "coins_min": 55, "coins_max": 70},
    {"desc": "牛牛在飞机上认识了新朋友，收获颇丰", "coins_min": 60, "coins_max": 80},
    {"desc": "飞行途中牛牛看了三部电影，心情愉悦", "coins_min": 50, "coins_max": 65},
    {"desc": "牛牛幸运地被升舱到商务舱", "coins_min": 65, "coins_max": 80},
    {"desc": "牛牛在免税店血拼了一番", "coins_min": 55, "coins_max": 75},
    {"desc": "空姐对牛牛特别照顾，全程VIP待遇", "coins_min": 60, "coins_max": 80},
    # 高收益 (80-120)
    {"desc": "竟然赶上了国际航班，遇到了兴奋的大母牛", "coins_min": 85, "coins_max": 110},
    {"desc": "竟然赶上了本地航班，遇到了兴奋的大公牛", "coins_min": 85, "coins_max": 110},
    {"desc": "牛牛意外发现飞机上有隐藏任务，奖励丰厚", "coins_min": 90, "coins_max": 120},
    {"desc": "牛牛被选中参加机上抽奖，中了大奖！", "coins_min": 100, "coins_max": 130},
    {"desc": "牛牛帮助空乘解决了紧急情况，获得感谢奖励", "coins_min": 85, "coins_max": 105},
    {"desc": "牛牛在头等舱偶遇神秘富婆，收获满满", "coins_min": 95, "coins_max": 120},
    {"desc": "飞机经过百慕大三角，牛牛获得了神秘力量加持", "coins_min": 80, "coins_max": 100},
    # 特殊事件 (极端)
    {"desc": "牛牛的飞机迫降在无人岛，意外发现宝藏！", "coins_min": 120, "coins_max": 150},
    {"desc": "牛牛成功阻止了一场劫机，成为英雄！", "coins_min": 130, "coins_max": 160},
    {"desc": "牛牛买的机票中了航空公司年度大奖！", "coins_min": 150, "coins_max": 200},
    {"desc": "牛牛不小心走进了驾驶舱，被机长收为徒弟", "coins_min": 100, "coins_max": 140},
    {"desc": "牛牛的座位下面发现了前乘客遗落的金条", "coins_min": 140, "coins_max": 180},
    # 搞笑事件
    {"desc": "牛牛把花生米当成了安眠药，睡了一路", "coins_min": 40, "coins_max": 55},
    {"desc": "牛牛和邻座大妈聊了一路，耳朵都快聋了", "coins_min": 35, "coins_max": 50},
    {"desc": "牛牛在飞机上拉肚子，厕所排了半小时队", "coins_min": 25, "coins_max": 40},
    {"desc": "牛牛被小孩踢了一路椅背，精神损失惨重", "coins_min": 30, "coins_max": 45},
    {"desc": "牛牛旁边坐了个打呼噜的，一路没睡着", "coins_min": 35, "coins_max": 50},
    {"desc": "牛牛手机没电了，整趟航班只能发呆", "coins_min": 30, "coins_max": 45},
    # 终极事件 (超高收益)
    {"desc": "✈️ 牛牛的飞机穿越到了平行宇宙，带回了另一个世界的财富！", "coins_min": 250, "coins_max": 350},
    {"desc": "👑 牛牛意外成为航空公司第一亿名乘客，获得终身免费机票+巨额奖金！", "coins_min": 300, "coins_max": 400},
    # 负面事件 (扣钱)
    {"desc": "💸 牛牛在飞机上打翻了红酒，赔了一大笔清洁费", "coins_min": -80, "coins_max": -50},
    {"desc": "🚨 牛牛被发现超重行李，被罚款了", "coins_min": -60, "coins_max": -30},
    {"desc": "💀 牛牛不小心损坏了座椅屏幕，要赔偿！", "coins_min": -100, "coins_max": -60},
    {"desc": "🎰 牛牛在飞机上玩牌输了，输给别牛一条裤子", "coins_min": -120, "coins_max": -70},
    {"desc": "🤮 牛牛晕机吐在了邻座身上，被索赔干洗费", "coins_min": -50, "coins_max": -20},
    {"desc": "📱 牛牛的手机掉进马桶里了，损失惨重", "coins_min": -70, "coins_max": -40},
    {"desc": "🚔 牛牛下飞机时被税务局拦住，补交了一大笔税", "coins_min": -150, "coins_max": -80},
    {"desc": "💔 牛牛被空姐发了好牛卡，精神和金钱双重损失", "coins_min": -40, "coins_max": -20},
    {"desc": "🦠 牛牛在飞机上感染了牛感，医药费花光了积蓄", "coins_min": -100, "coins_max": -50},
    {"desc": "⚠️ 牛牛误触紧急出口，被罚了巨款！", "coins_min": -200, "coins_max": -100},
    # === 新增搞怪事件 ===
    # 奇遇正面
    {"desc": "🎭 牛牛被误认为是某明星，收到粉丝送的礼物", "coins_min": 70, "coins_max": 95},
    {"desc": "🎪 牛牛在飞机上表演了一段才艺，乘客们纷纷打赏", "coins_min": 60, "coins_max": 85},
    {"desc": "🧲 牛牛在座位缝里发现了别牛落下的钱包（已归还，失主给了感谢费）", "coins_min": 80, "coins_max": 110},
    {"desc": "🎮 牛牛和邻座打赌猜飞行时间，赢了！", "coins_min": 50, "coins_max": 70},
    {"desc": "🌈 牛牛在高空看到了极光，拍照发朋友圈收获无数点赞和打赏", "coins_min": 55, "coins_max": 75},
    {"desc": "🎁 牛牛是今天第888位乘客，获得幸运礼包", "coins_min": 88, "coins_max": 128},
    {"desc": "🐾 牛牛帮一位老奶奶找到了走丢的小狗，获得丰厚酬谢", "coins_min": 65, "coins_max": 90},
    {"desc": "🎤 机长竟然是牛牛的老同学，直接安排头等舱待遇", "coins_min": 90, "coins_max": 120},
    {"desc": "🍀 牛牛发现座椅口袋里有上一位乘客忘记领的刮刮乐，中了！", "coins_min": 100, "coins_max": 150},
    {"desc": "🎯 牛牛精准预测了航班到达时间，航空公司奖励积分兑换现金", "coins_min": 45, "coins_max": 65},
    {"desc": "🦸 牛牛帮空姐制服了一个闹事乘客，获得英雄奖励", "coins_min": 110, "coins_max": 140},
    {"desc": "📺 航班娱乐系统故障，牛牛用手机给大家放电影，收到感谢费", "coins_min": 40, "coins_max": 60},
    {"desc": "🧩 牛牛在飞机上完成了一个超难拼图，邻座土豪觉得有趣买下了它", "coins_min": 75, "coins_max": 100},
    {"desc": "🎂 今天是牛牛生日，机组送上惊喜蛋糕和生日礼金", "coins_min": 80, "coins_max": 110},
    {"desc": "💤 牛牛睡着后说梦话，竟然说中了彩票号码！（邻座分红）", "coins_min": 120, "coins_max": 160},
    # 搞笑中性偏正
    {"desc": "🐔 牛牛的飞机餐居然是满汉全席？原来是厨师搞错了", "coins_min": 50, "coins_max": 70},
    {"desc": "👻 牛牛假装睡着躲过了推销信用卡的空姐，省下时间刷副业", "coins_min": 35, "coins_max": 55},
    {"desc": "🎵 牛牛耳机坏了，只能听飞机引擎声，竟然悟出了新的赚钱思路", "coins_min": 60, "coins_max": 85},
    {"desc": "🤡 牛牛把安全演示看成了喜剧表演，笑出了腹肌", "coins_min": 30, "coins_max": 50},
    {"desc": "🌙 牛牛在飞机上做了个发财梦，醒来发现真的有人给自己转账了", "coins_min": 70, "coins_max": 100},
    {"desc": "📖 牛牛看完了一本理财书，下飞机立刻赚到了第一桶金", "coins_min": 55, "coins_max": 80},
    {"desc": "🎲 牛牛和空少玩石头剪刀布，连赢十局获得神秘奖品", "coins_min": 65, "coins_max": 90},
    {"desc": "🧘 牛牛在飞机上冥想，悟到了人生的真谛（顺便接了个私单）", "coins_min": 45, "coins_max": 70},
    # 搞笑负面
    {"desc": "🦷 牛牛吃飞机餐太猛，把假牙吞下去了，医疗费爆表", "coins_min": -90, "coins_max": -50},
    {"desc": "🎪 牛牛在飞机上放了个响屁，被要求换座+精神损失费", "coins_min": -30, "coins_max": -10},
    {"desc": "👔 牛牛西装被邻座小孩画满了蜡笔画，干洗费感人", "coins_min": -45, "coins_max": -25},
    {"desc": "🍷 牛牛喝多了在飞机上唱歌，被罚款扰民费", "coins_min": -55, "coins_max": -30},
    {"desc": "🎭 牛牛模仿机长广播被投诉，赔礼道歉+罚款", "coins_min": -70, "coins_max": -40},
    # 神秘事件
    {"desc": "👽 牛牛声称看到了UFO，虽然没人信但直播间涨了不少粉", "coins_min": 85, "coins_max": 115},
    {"desc": "🔮 飞机上的算命先生说牛牛有财运，果然下机就捡到钱", "coins_min": 40, "coins_max": 60},
    {"desc": "🌀 牛牛的飞机穿过神秘云层，牛牛感觉时间变慢了，多赚了几小时工资", "coins_min": 95, "coins_max": 130},
    {"desc": "🎰 牛牛在飞机上刮彩票，三等奖！", "coins_min": 150, "coins_max": 200},
    {"desc": "🗝️ 牛牛在洗手间捡到一把神秘钥匙，后来发现是某个寄存柜的", "coins_min": 180, "coins_max": 250}
]

# =============================================================================
# Rush (开冲) Configuration
# =============================================================================
class RushConfig:
    COINS_PER_MINUTE = 1           # Coins earned per minute
    MAX_COINS = 600                # Maximum base coins per rush (before bonus)

# =============================================================================
# Shop Items Configuration
# =============================================================================
DEFAULT_SHOP_ITEMS = [
    {
        'id': 1,
        'name': "巴黎牛家",
        'type': 'active',
        'desc': "立即增加10点硬度，但会随机缩短1-10%长度",
        'price': 200
    },
    {
        'id': 2,
        'name': "妙脆角",
        'type': 'passive',
        'max': 3,
        'desc': "防止一次长度减半",
        'price': 70
    },
    {
        'id': 3,
        'name': "淬火爪刀",
        'type': 'passive',
        'max': 3,
        'desc': "触发掠夺时，额外掠夺10%长度和10%硬度",
        'price': 100
    },
    {
        'id': 4,
        'name': "致命节奏",
        'type': 'passive',
        'max': 20,
        'quantity': 5,
        'desc': "短时间内多次打胶或比划，同时不受20分钟内连续打胶的debuff",
        'price': 100
    },
    {
        'id': 5,
        'name': "夺牛魔蝌蚪罐头",
        'type': 'passive',
        'max': 1,
        'desc': "比划时触发：50%夺取全部长度+硬度｜20%混沌风暴｜20%大自爆｜10%自爆归零",
        'price': 600
    },
    {
        'id': 6,
        'name': "赌徒硬币",
        'type': 'active',
        'desc': "抛硬币！50%翻倍/48%减半/1%头等奖(变4倍)/1%霉运(变负2倍)",
        'price': 50
    },
    {
        'id': 7,
        'name': "劫富济贫",
        'type': 'active',
        'desc': "从排名第一的牛牛手中抢50%长度和20%硬度，平分给随机3人（可能包括自己，但不会给首富）",
        'price': 600
    },
    {
        'id': 8,
        'name': "混沌风暴",
        'type': 'active',
        'desc': "随机选10人，每人触发一个奇怪事件！",
        'price': 500
    },
    {
        'id': 9,
        'name': "牛牛盾牌",
        'type': 'active',
        'desc': "⚠️购买后会扣除当前50%长度和硬度！获得3层盾牌：每层消耗后完全免疫劫富济贫/混沌风暴/月牙天冲/被别人大自爆；每层消耗后减免夺牛魔10%伤害",
        'price': 500
    },
    {
        'id': 10,
        'name': "穷牛一生",
        'type': 'active',
        'desc': "便宜的盲盒！随机改变长度和硬度",
        'price': 25
    },
    {
        'id': 11,
        'name': "月牙天冲",
        'type': 'active',
        'desc': "随机选一位群友，双方同时损失发起人50%的长度！可把人冲成负数！",
        'price': 300
    },
    {
        'id': 12,
        'name': "牛牛大自爆",
        'type': 'active',
        'desc': "自己归零，损失的长度/硬度随机扣到top3头上！同归于尽！",
        'price': 250
    },
    {
        'id': 13,
        'name': "祸水东引",
        'type': 'active',
        'desc': "获得1次转嫁，受到>=50cm长度伤害时转给随机群友！（无法转移夺牛魔）",
        'price': 125
    },
    {
        'id': 14,
        'name': "上保险",
        'type': 'active',
        'desc': "获得10次理赔机会，损失>=50cm或硬度>=10时赔付200金币！自残类不赔",
        'price': 1000
    },
    {
        'id': 15,
        'name': "绝对值！",
        'type': 'active',
        'desc': "仅限负数牛牛！花费=|长度|×0.1金币，把负数取绝对值翻身！",
        'price': 0,  # 动态定价，实际价格在效果中计算
        'dynamic_price': True
    },
    {
        'id': 16,
        'name': "小蓝片",
        'type': 'passive',
        'max': 5,
        'desc': "下一次比划时硬度视为100",
        'price': 200
    },
    {
        'id': 17,
        'name': "牛牛黑洞",
        'type': 'active',
        'desc': "召唤黑洞吸取5-15人各3-10%长度！40%归你/30%喷射路人/20%反噬自己/10%吃撑反喷",
        'price': 300
    },
    {
        'id': 18,
        'name': "牛牛寄生",
        'type': 'active',
        'desc': "在指定群友身上种下寄生牛牛！宿主每次增长>5%时，抽取5%长度和硬度给你！用法：牛牛购买 18 @目标",
        'price': 150
    },
    {
        'id': 19,
        'name': "驱牛药",
        'type': 'active',
        'desc': "清除寄生在自己身上的寄生牛牛，重获自由！",
        'price': 75
    },
    {
        'id': 20,
        'name': "牛牛均富/负卡",
        'type': 'active',
        'desc': "发动！全群所有牛牛长度和硬度取平均值！大牛哭晕，小牛狂喜！价格随群内贫富差距浮动",
        'price': 0,  # 动态定价
        'dynamic_price': True
    },
    {
        'id': 21,
        'name': "牛牛反弹",
        'type': 'active',
        'desc': "获得1次反弹，受到>=50cm长度伤害时反弹给攻击者！以彼之道还施彼身！（无法反弹夺牛魔）",
        'price': 125
    }
]

# 下架道具统一退款金额
DELETED_ITEM_REFUND = 50

# =============================================================================
# 祸水东引 Configuration
# =============================================================================
class HuoshuiDongyinConfig:
    DAMAGE_THRESHOLD = 50              # 长度伤害>=50cm才触发转嫁

# =============================================================================
# 牛牛反弹 Configuration
# =============================================================================
class FantanConfig:
    DAMAGE_THRESHOLD = 50              # 长度伤害>=50cm才触发反弹

# =============================================================================
# 上保险 Configuration
# =============================================================================
class ShangbaoxianConfig:
    CHARGES = 10                       # 10次保险
    LENGTH_THRESHOLD = 50              # 长度损失>=50cm触发
    HARDNESS_THRESHOLD = 10            # 硬度损失>=10触发
    PAYOUT = 200                       # 赔付200金币
    # 主动自残类道具，不触发保险理赔
    INTENTIONAL_SELF_HURT_ITEMS = [
        "牛牛大自爆",
        "月牙天冲",
    ]

# =============================================================================
# 牛牛大自爆 Configuration
# =============================================================================
class DazibaoConfig:
    TOP_N = 3                          # 影响top3
    MIN_PLAYERS = 2                    # 最少需要2人

# =============================================================================
# 月牙天冲 Configuration
# =============================================================================
class YueyaTianchongConfig:
    DAMAGE_PERCENT_MIN = 0.50          # 最小伤害 50%
    DAMAGE_PERCENT_MAX = 0.50          # 最大伤害 50%
    MIN_PLAYERS = 2                    # 最少需要2人（自己+1个目标）

# =============================================================================
# 牛牛盾牌 Configuration
# =============================================================================
class NiuniuDunpaiConfig:
    SHIELD_CHARGES = 3                 # 每个牛牛盾牌提供3次护盾

# =============================================================================
# 穷牛一生 Configuration (期望值略正的赌博道具)
# =============================================================================
class QiongniuYishengConfig:
    # 结果概率分布 (总和=1.0)
    # 期望长度: 0.45*(-4) + 0.30*(+4.5) + 0.20*(+9) + 0.05*(+20) ≈ +1.55cm
    # 期望硬度: 0.45*(-0.5) + 0.30*(0) + 0.20*(+1) + 0.05*(+2) ≈ -0.025
    OUTCOMES = [
        {
            'name': 'bad',
            'chance': 0.45,           # 45% 倒霉
            'length_min': -6,
            'length_max': -2,
            'hardness_min': -1,
            'hardness_max': 0,
        },
        {
            'name': 'neutral',
            'chance': 0.30,           # 30% 小赚
            'length_min': 3,
            'length_max': 6,
            'hardness_min': 0,
            'hardness_max': 0,
        },
        {
            'name': 'good',
            'chance': 0.20,           # 20% 不错
            'length_min': 6,
            'length_max': 12,
            'hardness_min': 1,
            'hardness_max': 1,
        },
        {
            'name': 'jackpot',
            'chance': 0.05,           # 5% 大奖
            'length_min': 15,
            'length_max': 25,
            'hardness_min': 2,
            'hardness_max': 2,
        },
    ]

# =============================================================================
# 混沌风暴 Configuration
# =============================================================================
class HundunFengbaoConfig:
    MAX_TARGETS = 10               # 最多影响10人
    MIN_PLAYERS = 3                # 最少需要3人才能触发
    # 混沌事件列表 (权重, 事件ID, 事件描述模板, 参数)
    CHAOS_EVENTS = [
        # 基础事件
        (15, 'length_up', '长度+{value}cm', {'min': 5, 'max': 20}),
        (15, 'length_down', '长度-{value}cm', {'min': 3, 'max': 15}),
        (10, 'hardness_up', '硬度+{value}', {'min': 1, 'max': 2}),
        (10, 'hardness_down', '硬度-{value}', {'min': 1, 'max': 2}),
        (8, 'coin_gain', '捡到{value}金币', {'min': 20, 'max': 80}),
        (8, 'coin_lose', '丢失{value}金币', {'min': 10, 'max': 50}),
        (5, 'length_percent_up', '长度+{value}%', {'min': 10, 'max': 25}),
        (5, 'length_percent_down', '长度-{value}%', {'min': 5, 'max': 20}),
        (4, 'swap_random', '与{target}交换了长度！', {}),
        (3, 'double_or_nothing', '长度翻倍！+{value}cm', {}),
        (3, 'halve', '长度减半！-{value}cm', {}),
        (3, 'hardness_reset', '硬度重置为{value}', {'min': 1, 'max': 10}),
        (2, 'steal_from_random', '偷走{target}的{value}cm', {'min': 5, 'max': 15}),
        (2, 'give_to_random', '送给{target} {value}cm', {'min': 3, 'max': 10}),
        (5, 'nothing', '啥也没发生...', {}),
        (2, 'reverse_sign', '长度正负反转！{old}→{new}cm', {}),
        # 新增事件
        (3, 'full_swap', '与{target}交换了全部属性！', {}),  # 长度+硬度互换
        (2, 'cooldown_reset', '打胶冷却清零！', {}),  # 重置打胶CD
        (2, 'chaos_chain', '混沌连锁！触发双重事件！', {}),  # 触发2个事件
        (3, 'hardness_to_length', '硬度转化为长度！{h}硬度→{l}cm', {}),  # 硬度变长度
        (3, 'length_to_hardness', '长度转化为硬度！{l}cm→{h}硬度', {}),  # 长度变硬度
        (1, 'chaos_tax', '被混沌收税！-5%长度', {}),  # 交5%给使用者
        (2, 'clone_length', '克隆了{target}的长度！', {}),  # 复制别人长度
        (2, 'lucky_buff', '获得幸运祝福！下次打胶必增长！', {}),  # 下次打胶必成功
        (3, 'length_quake', '长度震荡！{change}cm', {'min': -30, 'max': 30}),  # 大幅随机波动
        # 更有趣的事件
        (2, 'quantum_entangle', '与{target}量子纠缠！双方长度平均化！', {}),  # 双方取平均
        (2, 'dark_sacrifice', '黑暗献祭！牺牲{loss}cm，{target}获得{gain}cm！', {}),  # 牺牲自己给别人×3
        (3, 'resurrection', '牛牛复活！', {'min': 20, 'max': 50}),  # 负数变正数
        (1, 'doomsday', '【末日审判】最短归零，最长翻倍！', {}),  # 全局事件
        (1, 'roulette', '【轮盘重置】所有人长度重新洗牌！', {}),  # 全局事件
        (1, 'reverse_talent', '【反向天赋】最长和最短互换！', {}),  # 全局事件
        (1, 'lottery_bomb', '【团灭彩票】5%全体翻倍，95%全体-50%长度和硬度！', {}),  # 全局事件
        (2, 'parasite', '在{target}身上种下寄生虫！他下次打胶你也+同等！', {}),  # 持久效果
    ]

# =============================================================================
# 劫富济贫 Configuration
# =============================================================================
class JiefuJipinConfig:
    STEAL_LENGTH_PERCENT = 0.50    # 50% length from richest
    STEAL_HARDNESS_PERCENT = 0.20  # 20% hardness from richest
    BENEFICIARY_COUNT = 3          # Give to random 3 (excluding richest)

# =============================================================================
# Duoxinmo Item Probabilities
# =============================================================================
class DuoxinmoConfig:
    STEAL_ALL_CHANCE = 0.5         # 50% chance to steal all length + hardness
    CHAOS_STORM_CHANCE = 0.2       # 20% chance to trigger chaos storm (0.5 + 0.2 = 0.7)
    DAZIBAO_CHANCE = 0.2           # 20% chance to trigger dazibao (0.7 + 0.2 = 0.9)
    SELF_CLEAR_CHANCE = 0.1        # 10% chance to clear self (0.9 + 0.1 = 1.0)

# =============================================================================
# 牛牛黑洞 Configuration
# =============================================================================
class HeidongConfig:
    MIN_TARGETS = 5                # 最少吸取5人
    MAX_TARGETS = 15               # 最多吸取15人
    STEAL_PERCENT_MIN = 0.03       # 每人最少吸3%
    STEAL_PERCENT_MAX = 0.10       # 每人最多吸10%
    MIN_PLAYERS = 3                # 最少需要3人才能使用

    # 结果概率
    RESULT_ALL_TO_USER = 0.40      # 40% 全归使用者
    RESULT_HALF_SPRAY = 0.30       # 30% 一半喷给路人
    RESULT_BACKFIRE = 0.20         # 20% 反噬自己
    RESULT_REVERSE = 0.10          # 10% 吃撑反喷（所有人反而变长）

    BACKFIRE_PERCENT = 0.15        # 反噬损失自身15%长度

# =============================================================================
# 牛牛寄生 Configuration
# =============================================================================
class NiuniuJishengConfig:
    MIN_PLAYERS = 2                    # 最少需要2人（自己+1个宿主）
    TRIGGER_THRESHOLD = 0.05           # 5% - 宿主增长超过自身绝对值5%时触发
    DRAIN_LENGTH_PERCENT = 0.05        # 抽取宿主5%绝对值长度
    DRAIN_HARDNESS_PERCENT = 0.05      # 抽取宿主5%硬度

    # 成功种植文案
    PARASITE_TEXTS = [
        "🎯 你在 {host_name} 身上种下了寄生牛牛！每当他增长>5%时，你将吸取他的精华！",
        "😈 寄生牛牛已潜入 {host_name} 体内！他的每一次成长都将反哺于你！",
        "🌱 {host_name} 成为了你的宿主！当他茁壮成长时，你也会分一杯羹！",
        "🔗 你与 {host_name} 建立了寄生连接！他的努力，你的收获！",
    ]

    # 覆盖旧寄生的文案（把旧寄生牛牛踢走）
    OVERRIDE_TEXTS = [
        "⚔️ 你的寄生牛牛把 {old_beneficiary_name} 的寄生牛牛从 {host_name} 身上踢了出去！",
        "👊 {old_beneficiary_name} 的寄生牛牛被你的寄生牛牛驱逐了！{host_name} 现在是你的宿主！",
        "🥊 寄生牛牛大战！你成功霸占了 {host_name}，{old_beneficiary_name} 被扫地出门！",
    ]

    # 抽取触发文案
    DRAIN_TEXTS = [
        "🩸 {host_name} 增长了{gain}cm，寄生牛牛生效！{beneficiary_name} 吸取了 {drain_length}cm长度 和 {drain_hardness}硬度！",
        "😋 {beneficiary_name} 的寄生牛牛从 {host_name} 身上吸取了 {drain_length}cm 和 {drain_hardness}硬度！",
        "🔋 寄生牛牛充能！{host_name} 被抽取 {drain_length}cm长度、{drain_hardness}硬度 → {beneficiary_name}！",
    ]

    # 驱牛药成功文案
    CURE_TEXTS = [
        "💊 驱牛药生效！寄生在你身上的寄生牛牛被清除了！",
        "🎉 你成功驱除了寄生牛牛！重获自由！",
        "✨ 寄生牛牛已被药物清除，你的牛牛恢复了独立！",
    ]

    # 没有寄生牛牛时使用驱牛药
    NO_PARASITE_TEXTS = [
        "❓ 你身上并没有寄生牛牛，不需要使用驱牛药！",
        "🤷 浪费了！你身上根本没有寄生牛牛！",
        "💸 钱白花了...你本来就是自由的！",
    ]

# =============================================================================
# 牛牛均富/负卡 Configuration
# =============================================================================
class JunfukaConfig:
    MIN_PLAYERS = 3                    # 最少需要3人才能触发

    # 动态定价配置
    BASE_PRICE = 1888                  # 基础价格
    TOTAL_DIFF_COEFFICIENT = 0.0005   # 总差异系数：价格 = 基础价格 + Σ|长度 - 平均长度| × 系数
    MIN_PRICE = 1888                   # 最低价格（分布极小时）

    # 开场文案
    OPENING_TEXTS = [
        "☭ ══ 牛牛均富/负卡 ══ ☭",
        "🚩 「不患寡而患不均！」",
        "📢 全群牛牛长度即将重新分配！",
    ]

    # 大佬受损文案
    LOSER_TEXTS = [
        "😭 {name} 从 {old}→{new}，血亏 {diff}！大佬哭晕在厕所！",
        "💔 {name} 痛失 {diff}！从 {old} 跌落到 {new}！",
        "🔻 {name} 被均富！{old}→{new}，贡献了 {diff}！",
        "😱 {name} 哭了！{diff} 的长度被充公！{old}→{new}",
    ]

    # 负数/小号受益文案
    WINNER_TEXTS = [
        "🎉 {name} 从 {old}→{new}，白嫖 {diff}！负数狂喜！",
        "🚀 {name} 逆袭！从 {old} 飞升到 {new}！+{diff}！",
        "🔺 {name} 躺赢！{old}→{new}，喜提 {diff}！",
        "🥳 {name} 笑了！均富后喜获 {diff}！{old}→{new}",
    ]

    # 不变文案
    NEUTRAL_TEXTS = [
        "😐 {name} 纹丝不动...刚好是平均值？",
        "🤷 {name} 不亏不赚，{old}→{new}",
    ]

    # 结尾文案
    ENDING_TEXTS = [
        "═══════════════════",
        "☭ 均富完成！今天，牛牛平等！",
    ]

# =============================================================================
# 股票收益税配置
# =============================================================================
class StockTaxConfig:
    """股票卖出收益阶梯税率配置

    税率基于收益与群内金币平均值的比例：
    - 收益 <= 1倍平均值：免税
    - 超出部分按阶梯累进征税
    """
    # 阶梯税率：(倍数上限, 税率)，按顺序累进
    TAX_BRACKETS = [
        (1, 0.00),    # 0-1倍平均：0%
        (2, 0.10),    # 1-2倍：10%
        (3, 0.20),    # 2-3倍：20%
        (5, 0.30),    # 3-5倍：30%
        (10, 0.50),   # 5-10倍：50%
        (float('inf'), 0.75),  # 10倍以上：75%
    ]

    # 税收文案
    TAX_TEXTS = [
        "🏛️ 妖牛税务局温馨提示：赚太多要交税哦~",
        "💸 恭喜发财！但税务局也要恭喜一下自己~",
        "📜 根据《妖牛股市税法》，您需缴纳收益税",
        "🎩 绅士交税，股市长治久安",
        "💰 取之于牛，用之于牛~",
    ]

    # 免税文案
    NO_TAX_TEXTS = [
        "✨ 收益未超过群平均，免税！",
        "🎉 小赚怡情，税务局放你一马~",
        "📊 收益在免税额度内，恭喜！",
    ]

    # 高税率文案（税率>=30%时）
    HIGH_TAX_TEXTS = [
        "💀 血税！税务局笑得合不拢嘴！",
        "🩸 这税交得肉疼吧？",
        "😱 税务局：谢谢大佬的慷慨解囊！",
        "🏦 恭喜成为纳税大户！",
    ]

    # 超高税率文案（税率>=50%时）
    EXTREME_TAX_TEXTS = [
        "💸💸💸 税务局狂喜！半数收益充公！",
        "🎰 赌赢了？一半归税务局！",
        "👑 股神也要给税务局打工！",
        "🏛️ 税务局：这波血赚！",
    ]

# =============================================================================
# Length Display Thresholds
# =============================================================================
LENGTH_METER_THRESHOLD = 100       # Display in meters when >= 100cm

# =============================================================================
# Evaluation Thresholds
# =============================================================================
class EvaluationThresholds:
    SHORT = 12
    MEDIUM = 25
    LONG = 50
    VERY_LONG = 100
    SUPER_LONG = 200
    # >= SUPER_LONG = ultra_long


# =============================================================================
# Length Formatting Utility
# =============================================================================
def format_length(length: float, show_sign: bool = False) -> str:
    """
    格式化长度显示，自动转换单位

    Args:
        length: 长度值（cm）
        show_sign: 是否显示正号（用于变化量）

    Returns:
        格式化后的字符串，如 "15cm", "1.50m", "2.30km", "-500m (凹)"
    """
    abs_length = abs(length)
    is_negative = length < 0

    # 确定单位和数值
    if abs_length >= 100000:  # >= 1km
        value = abs_length / 100000
        unit = "km"
    elif abs_length >= 100:  # >= 1m
        value = abs_length / 100
        unit = "m"
    else:
        value = abs_length
        unit = "cm"

    # 格式化数值
    if unit == "cm":
        # cm 保持整数或一位小数
        if value == int(value):
            num_str = f"{int(value)}"
        else:
            num_str = f"{value:.1f}"
    else:
        # m/km 保持两位小数
        num_str = f"{value:.2f}"

    # 构建结果
    if is_negative:
        result = f"-{num_str}{unit} (凹)"
    elif length == 0:
        result = "0cm (无)"
    else:
        if show_sign:
            result = f"+{num_str}{unit}"
        else:
            result = f"{num_str}{unit}"

    return result


def format_length_change(change: float) -> str:
    """
    格式化长度变化量（总是显示正负号）

    Args:
        change: 变化量（cm）

    Returns:
        格式化后的字符串，如 "+15cm", "-1.50m"
    """
    if change >= 0:
        return format_length(change, show_sign=True)
    else:
        # 负数变化，format_length会加(凹)，这里我们不需要
        abs_change = abs(change)
        if abs_change >= 100000:
            return f"-{abs_change/100000:.2f}km"
        elif abs_change >= 100:
            return f"-{abs_change/100:.2f}m"
        else:
            if abs_change == int(abs_change):
                return f"-{int(abs_change)}cm"
            return f"-{abs_change:.1f}cm"
