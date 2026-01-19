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
    {"desc": "牛牛没赶上飞机，不过也算出来透了口气", "coins_min": 20, "coins_max": 40},
    {"desc": "竟然赶上了国际航班，遇到了兴奋的大母猴", "coins_min": 80, "coins_max": 100},
    {"desc": "无惊无险，牛牛顺利抵达目的地", "coins_min": 70, "coins_max": 80},
    {"desc": "牛牛刚出来就遇到了冷空气，冻得像个鹌鹑似的", "coins_min": 40, "coins_max": 60},
    {"desc": "牛牛好像到奇怪的地方，不过也算是完成了目标", "coins_min": 60, "coins_max": 80}
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
    }
]

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
