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
    DAJIAO_BONUS_THRESHOLD = 1800  # 30 minutes - after this, better rewards
    COMPARE_COOLDOWN = 600         # 10 minutes - compare cooldown per target
    COMPARE_LIMIT_WINDOW = 600     # 10 minutes - window for compare count limit
    COMPARE_LIMIT_COUNT = 3        # Max compares within window

    RUSH_COOLDOWN = 1800           # 30 minutes - cooldown between rushes
    RUSH_MIN_TIME = 600            # 10 minutes - minimum time to get reward
    RUSH_MAX_TIME = 14400          # 4 hours - maximum counted time
    RUSH_DAILY_LIMIT = 3           # Max rushes per day

    FLY_PLANE_COOLDOWN = 14400     # 4 hours - fly plane cooldown

# =============================================================================
# Dajiao (打胶) Configuration
# =============================================================================
class DajiaoConfig:
    # 10-30 minute window probabilities and ranges
    EARLY_INCREASE_CHANCE = 0.4    # 40% chance to increase
    EARLY_DECREASE_CHANCE = 0.3    # 30% chance to decrease (0.4 + 0.3 = 0.7)
    EARLY_INCREASE_MIN = 2
    EARLY_INCREASE_MAX = 5
    EARLY_DECREASE_MIN = 1
    EARLY_DECREASE_MAX = 3

    # After 30 minute probabilities and ranges
    LATE_INCREASE_CHANCE = 0.7     # 70% chance to increase
    LATE_DECREASE_CHANCE = 0.2     # 20% chance to decrease (0.7 + 0.2 = 0.9)
    LATE_INCREASE_MIN = 3
    LATE_INCREASE_MAX = 6
    LATE_DECREASE_MIN = 1
    LATE_DECREASE_MAX = 2
    LATE_HARDNESS_INCREASE = 1     # Hardness increase on success
    MAX_HARDNESS = 10              # Maximum hardness cap

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
    {"desc": "竟然赶上了国际航班，遇到了兴奋的大母猴", "coins_min": 85, "coins_max": 110},
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
    {"desc": "🎰 牛牛在飞机上玩骰子输了（不要问为什么飞机上有赌场）", "coins_min": -120, "coins_max": -70},
    {"desc": "🤮 牛牛晕机吐在了邻座身上，被索赔干洗费", "coins_min": -50, "coins_max": -20},
    {"desc": "📱 牛牛的手机掉进马桶里了，损失惨重", "coins_min": -70, "coins_max": -40},
    {"desc": "🚔 牛牛下飞机时被税务局拦住，补交了一大笔税", "coins_min": -150, "coins_max": -80},
    {"desc": "💔 牛牛被空姐发了好牛卡，精神和金钱双重损失", "coins_min": -40, "coins_max": -20},
    {"desc": "🦠 牛牛在飞机上感染了牛感，医药费花光了积蓄", "coins_min": -100, "coins_max": -50},
    {"desc": "⚠️ 牛牛误触紧急出口，被罚了巨款！", "coins_min": -200, "coins_max": -100}
]

# =============================================================================
# Rush (开冲) Configuration
# =============================================================================
class RushConfig:
    COINS_PER_MINUTE = 1           # Coins earned per minute

# =============================================================================
# Shop Items Configuration
# =============================================================================
DEFAULT_SHOP_ITEMS = [
    {
        'id': 1,
        'name': "巴黎世家",
        'type': 'active',
        'desc': "立即增加3点硬度",
        'price': 50
    },
    {
        'id': 2,
        'name': "巴适得板生长素",
        'type': 'active',
        'desc': "立即增加20cm长度，但会减少2点硬度",
        'price': 50
    },
    {
        'id': 3,
        'name': "妙脆角",
        'type': 'passive',
        'max': 3,
        'desc': "防止一次长度减半",
        'price': 70
    },
    {
        'id': 4,
        'name': "淬火爪刀",
        'type': 'passive',
        'max': 2,
        'desc': "触发掠夺时，额外掠夺10%长度",
        'price': 70
    },
    {
        'id': 5,
        'name': "余震",
        'type': 'passive',
        'max': 3,
        'desc': "被比划时，如果失败，不扣长度",
        'price': 80
    },
    {
        'id': 6,
        'name': "不灭之握",
        'type': 'active',
        'desc': "直接增加30cm长度",
        'price': 100
    },
    {
        'id': 7,
        'name': "致命节奏",
        'type': 'passive',
        'max': 20,
        'quantity': 5,
        'desc': "短时间内多次打胶或比划，同时不受30分钟内连续打胶的debuff",
        'price': 100
    },
    {
        'id': 8,
        'name': "阿姆斯特朗旋风喷射炮",
        'type': 'active',
        'desc': "长度直接+1m，硬度+10",
        'price': 500
    },
    {
        'id': 9,
        'name': "夺心魔蝌蚪罐头",
        'type': 'passive',
        'max': 1,
        'desc': "在比划时，有50%的概率夺取对方全部长度，10%的概率清空自己的长度，40%的概率无效",
        'price': 600
    },
    {
        'id': 10,
        'name': "赌徒硬币",
        'type': 'active',
        'desc': "抛硬币！50%概率长度翻倍，50%概率长度减半",
        'price': 30
    },
    {
        'id': 11,
        'name': "劫富济贫",
        'type': 'active',
        'desc': "从群首富抢15%长度，平分给最穷的3人（每天限1次）",
        'price': 60
    }
]

# =============================================================================
# 劫富济贫 Configuration
# =============================================================================
class JiefuJipinConfig:
    STEAL_PERCENT = 0.15           # 15% from richest
    BENEFICIARY_COUNT = 3          # Give to bottom 3
    DAILY_LIMIT = 1                # Once per day

# =============================================================================
# Duoxinmo Item Probabilities
# =============================================================================
class DuoxinmoConfig:
    STEAL_ALL_CHANCE = 0.5         # 50% chance to steal all
    SELF_CLEAR_CHANCE = 0.2        # 20% chance to clear self (0.5 + 0.2 = 0.7)
    # Remaining 30% = no effect

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
