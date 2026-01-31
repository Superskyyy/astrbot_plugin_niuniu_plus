# Proposal: cross-group-alliance

## Summary
实现跨群联盟系统，允许多个QQ群组成联盟，完全共享用户数据、股市、游戏功能和通知系统。

## Motivation
用户希望在多个QQ群之间实现数据互通，让玩家在不同群中使用同一账号，共享游戏进度和资源。同时，群体事件（如股市波动、全局BUFF）需要在所有联盟群同步通知，增强跨群互动体验。

## Design Principles

### 1. 完全共享原则
联盟内所有内容完全共享，包括但不限于：
- 用户数据（牛牛长度、硬度、金币、道具、连胜等）
- 股市系统（股价、持仓、历史事件）
- 游戏状态（寄生关系、BUFF状态、冷却时间）
- 排行榜（跨群聚合显示）

### 2. 广播通知原则
所有群体事件在联盟内每个群都发送通知：
- 股市崩盘/暴涨事件 → 所有群收到通知
- 全局BUFF触发 → 所有群广播
- 订阅扣费/补贴发放 → 每个群都通知
- 牛牛救市 → 所有群同步消息

### 3. 向后兼容原则
- 非联盟群保持完全独立，不受任何影响
- 联盟功能对非联盟群透明（代码内部判断）
- 退出联盟后恢复独立模式，数据保留退出时状态

## Architecture

### 数据结构

#### 联盟配置文件 (`data/niuniu_alliances.yml`)

```yaml
alliances:
  "12345678":  # alliance_id（使用盟主群号）
    alliance_id: "12345678"
    name: "跨服牛牛联盟"
    groups:
      - "12345678"  # 盟主群
      - "87654321"
      - "11111111"
    group_aliases:  # 群别名配置
      "12345678": "牛牛总部"
      "87654321": "牛牛分部"
      "11111111": "牛牛三群"
    original_users:  # 联盟创建前各群的原始用户列表（用于解散时分叉）
      "12345678": ["user1", "user2"]
      "87654321": ["user2", "user3"]
      "11111111": ["user3", "user4"]
    created_at: 1706745600
    created_by: "999999999"  # 创建者QQ号
    leader_group: "12345678"

group_to_alliance:
  "12345678": "12345678"
  "87654321": "12345678"
  "11111111": "12345678"
```

#### 用户数据合并策略

| 字段 | 合并策略 | 说明 |
|------|---------|------|
| `length` | `max()` | 保留最长的牛牛 |
| `hardness` | `max()` | 保留最硬的数据 |
| `coins` | `sum()` | 累加所有群的金币 |
| `items` | 数量累加 | 道具数量求和 |
| `compare_win_streak` | `max()` | 保留最佳连胜 |
| `compare_lose_streak` | `min()` | 取最优（最少连败）|
| `nickname` | 最近活跃 | 使用最近操作群的昵称 |
| `parasite` | 特殊处理 | 保留最近的寄生状态 |
| `last_dajiao` | `min()` | 取最早的冷却时间（允许更早操作）|
| `last_compare` | `min()` | 取最早的冷却时间 |
| `subscription_expire` | `max()` | 保留最晚的过期时间 |

#### 股市数据共享

**改造前**（独立群）:
```json
{
  "12345678": {  // 群号作为key
    "price": 150.5,
    "holdings": {"user1": 100},
    "events": [...]
  }
}
```

**改造后**（联盟共享）:
```json
{
  "12345678": {  // alliance_id作为key
    "price": 150.5,
    "holdings": {
      "user1": 100,  // 来自联盟内所有群的持仓
      "user2": 50
    },
    "events": [...]
  }
}
```

### 核心组件

#### 1. 联盟解析层 (Alliance Resolver)

**职责**: 透明地处理联盟/独立模式切换

```python
def _get_alliance_id(self, group_id: str) -> Optional[str]:
    """获取群组所属的联盟ID，返回None表示独立群"""
    alliances = self._load_alliances()
    return alliances.get('group_to_alliance', {}).get(group_id)

def _get_effective_group_id(self, group_id: str) -> str:
    """
    获取有效的group_id用于数据访问
    - 联盟群: 返回alliance_id
    - 独立群: 返回原group_id
    """
    alliance_id = self._get_alliance_id(group_id)
    return alliance_id if alliance_id else group_id
```

#### 2. 数据合并引擎 (Data Merger)

**职责**: 合并联盟内所有群的用户数据

```python
def _merge_user_data_across_groups(self, user_id: str, alliance_id: str) -> Dict:
    """
    合并联盟内所有群的用户数据
    返回合并后的虚拟数据（不直接写入文件）
    """
    groups = self._get_alliance_groups(alliance_id)
    all_data = self._load_niuniu_lengths()

    merged = {
        'nickname': '',
        'length': 0,
        'hardness': 1,
        'coins': 0,
        'items': {},
        'compare_win_streak': 0,
        'compare_lose_streak': 0,
        'last_dajiao': 0,
        'last_compare': 0,
        'subscription_expire': 0,
        'parasite': None,
        # ... 初始化所有字段
    }

    last_active_time = 0
    last_active_nickname = ''

    for gid in groups:
        user_data = all_data.get(gid, {}).get(user_id)
        if not user_data:
            continue

        # 最大值字段
        merged['length'] = max(merged['length'], user_data.get('length', 0))
        merged['hardness'] = max(merged['hardness'], user_data.get('hardness', 1))
        merged['compare_win_streak'] = max(
            merged['compare_win_streak'],
            user_data.get('compare_win_streak', 0)
        )
        merged['subscription_expire'] = max(
            merged['subscription_expire'],
            user_data.get('subscription_expire', 0)
        )

        # 最小值字段（最优）
        if 'compare_lose_streak' in user_data:
            if merged['compare_lose_streak'] == 0:
                merged['compare_lose_streak'] = user_data['compare_lose_streak']
            else:
                merged['compare_lose_streak'] = min(
                    merged['compare_lose_streak'],
                    user_data['compare_lose_streak']
                )

        # 冷却时间取最小（允许更早操作）
        if 'last_dajiao' in user_data:
            if merged['last_dajiao'] == 0:
                merged['last_dajiao'] = user_data['last_dajiao']
            else:
                merged['last_dajiao'] = min(merged['last_dajiao'], user_data['last_dajiao'])

        if 'last_compare' in user_data:
            if merged['last_compare'] == 0:
                merged['last_compare'] = user_data['last_compare']
            else:
                merged['last_compare'] = min(merged['last_compare'], user_data['last_compare'])

        # 求和字段
        merged['coins'] += user_data.get('coins', 0)

        # 道具累加
        for item, count in user_data.get('items', {}).items():
            merged['items'][item] = merged['items'].get(item, 0) + count

        # 追踪最近活跃的昵称
        user_last_action = max(
            user_data.get('last_dajiao', 0),
            user_data.get('last_compare', 0)
        )
        if user_last_action > last_active_time:
            last_active_time = user_last_action
            last_active_nickname = user_data.get('nickname', '')

        # 寄生状态（保留最近的）
        if 'parasite' in user_data and user_data['parasite']:
            merged['parasite'] = user_data['parasite']

    merged['nickname'] = last_active_nickname or f"用户{user_id}"

    return merged
```

#### 3. 数据同步器 (Data Synchronizer)

**职责**: 将更新同步到联盟内所有群

```python
def _sync_user_data_to_alliance(self, user_id: str, alliance_id: str, updates: Dict):
    """
    将数据更新同步到联盟内所有群

    策略：
    - 设置类操作（set）: 直接覆盖所有群的值
    - 增量类操作（delta）: 只在当前群应用增量

    updates 格式：
    {
        'set': {'nickname': 'xxx', 'hardness': 5},  # 直接设置
        'delta': {'coins': -100, 'length': 2.5}      # 增量变化
    }
    """
    groups = self._get_alliance_groups(alliance_id)
    all_data = self._load_niuniu_lengths()

    for gid in groups:
        group_data = all_data.setdefault(gid, {})
        user_data = group_data.setdefault(user_id, {})

        # 应用设置类更新（所有群同步）
        if 'set' in updates:
            user_data.update(updates['set'])

        # 应用增量更新（仅当前操作群）
        # 注意：delta操作需要在调用方特殊处理，
        # 通常直接修改当前群，然后重新合并

    self._save_niuniu_lengths(all_data)
```

#### 4. 广播系统 (Broadcast System)

**职责**: 向联盟内所有群发送通知

```python
async def _broadcast_to_alliance(self, group_id: str, message: str, exclude_current: bool = False):
    """
    向联盟内所有群广播消息

    Args:
        group_id: 当前操作的群号
        message: 要广播的消息
        exclude_current: 是否排除当前群（避免重复通知）
    """
    alliance_id = self._get_alliance_id(group_id)

    if not alliance_id:
        # 独立群，无需广播
        return

    groups = self._get_alliance_groups(alliance_id)

    for gid in groups:
        if exclude_current and gid == group_id:
            continue

        try:
            # 发送群消息
            await self.send_group_message(gid, message)
        except Exception as e:
            logger.error(f"广播到群 {gid} 失败: {e}")

async def send_group_message(self, group_id: str, message: str):
    """发送群消息的底层方法（需要实现）"""
    # TODO: 调用 AstrBot 的 API 发送群消息
    # 这需要了解 AstrBot 的消息发送机制
    pass
```

**广播场景举例**:

```python
# 场景1: 股市崩盘事件
async def _trigger_stock_crash(self, group_id: str):
    # ... 执行崩盘逻辑
    message = "📉 股市崩盘！所有持仓清零！"
    await self._broadcast_to_alliance(group_id, message, exclude_current=False)

# 场景2: 订阅扣费通知
async def _charge_subscription_fee(self, group_id: str, user_id: str, fee: int):
    # ... 扣费逻辑
    message = f"💳 订阅扣费：{fee}金币已从账户扣除"
    # 只通知当前用户所在的群（不跨群广播个人通知）
    yield event.plain_result(message)

# 场景3: 全局BUFF事件
async def _apply_global_buff(self, group_id: str, buff_name: str):
    # ... 应用BUFF
    message = f"⭐ 全局BUFF【{buff_name}】已激活！持续1小时"
    await self._broadcast_to_alliance(group_id, message, exclude_current=False)
```

## Changes

### Phase 1: 基础设施 (P0 - 必须实现)

#### 1.1 联盟配置管理

**新增文件**: `data/niuniu_alliances.yml`

**新增方法** (在 `main.py`):
- `_load_alliances() -> Dict`: 加载联盟配置
- `_save_alliances(data: Dict)`: 保存联盟配置
- `_get_alliance_id(group_id: str) -> Optional[str]`: 获取联盟ID
- `_get_alliance_groups(alliance_id: str) -> List[str]`: 获取联盟群列表

#### 1.2 数据合并逻辑

**新增方法** (在 `main.py`):
- `_merge_user_data_across_groups(user_id: str, alliance_id: str) -> Dict`
- `_sync_user_data_to_alliance(user_id: str, alliance_id: str, updates: Dict)`
- `_initial_merge_alliance_data(alliance_id: str)`: 首次创建联盟时的数据合并

#### 1.3 核心数据访问改造

**修改方法** (在 `main.py`):

```python
# 改造前
def get_user_data(self, group_id, user_id):
    data = self._load_niuniu_lengths()
    return data.get(group_id, {}).get(user_id)

# 改造后
def get_user_data(self, group_id, user_id):
    group_id = str(group_id)
    user_id = str(user_id)

    alliance_id = self._get_alliance_id(group_id)

    if alliance_id:
        # 联盟模式：合并数据
        return self._merge_user_data_across_groups(user_id, alliance_id)
    else:
        # 独立模式：原逻辑
        data = self._load_niuniu_lengths()
        return data.get(group_id, {}).get(user_id)
```

**类似改造**:
- `update_user_data()`: 增加联盟判断 + 同步逻辑
- `get_group_data()`: 使用 `_get_effective_group_id()`
- `_save_user_data()`: 联盟模式下同步到所有群

### Phase 2: 联盟管理命令 (P0)

#### 2.1 命令列表

| 命令 | 权限 | 功能 | 示例 |
|------|------|------|------|
| `牛牛联盟创建 <群号...>` | 管理员 | 创建新联盟 | `牛牛联盟创建 12345678 87654321` |
| `牛牛联盟查看` | 所有人 | 查看当前联盟信息 | `牛牛联盟查看` |
| `牛牛联盟退出` | 管理员 | 退出联盟（保留数据） | `牛牛联盟退出` |
| `牛牛联盟解散` | 盟主管理员 | 解散整个联盟 | `牛牛联盟解散` |

#### 2.2 创建联盟流程

```
用户输入: 牛牛联盟创建 12345678 87654321 11111111
    ↓
权限检查: 是否为管理员
    ↓
冲突检查: 所有群是否已加入其他联盟
    ↓
创建联盟: alliance_id = 第一个群号
    ↓
数据合并: 调用 _initial_merge_alliance_data()
    ↓
保存配置: 写入 alliances.yml
    ↓
返回结果: 显示联盟信息 + 成员群数量
```

**实现** (在 `main.py`):

```python
async def _alliance_create(self, event):
    """创建跨群联盟"""
    group_id = str(event.message_obj.group_id)
    user_id = str(event.get_sender_id())

    if not self.is_admin(user_id):
        yield event.plain_result("只有管理员才能创建联盟")
        return

    parts = event.message_str.strip().split()
    group_ids = [p for p in parts[1:] if p.isdigit()]

    if len(group_ids) < 2:
        yield event.plain_result("至少需要2个群才能创建联盟")
        return

    # 冲突检查
    alliances = self._load_alliances()
    for gid in group_ids:
        if gid in alliances.get('group_to_alliance', {}):
            yield event.plain_result(f"群 {gid} 已加入其他联盟")
            return

    # 记录各群的原始用户列表（用于解散时分叉）
    all_data = self._load_niuniu_lengths()
    original_users = {}
    for gid in group_ids:
        group_data = all_data.get(gid, {})
        # 排除 plugin_enabled 等非用户字段
        users = [uid for uid in group_data.keys() if uid != 'plugin_enabled']
        original_users[gid] = users

    # 创建联盟
    alliance_id = group_ids[0]
    alliances.setdefault('alliances', {})[alliance_id] = {
        'alliance_id': alliance_id,
        'name': f"联盟-{alliance_id[:6]}",
        'groups': group_ids,
        'group_aliases': {},  # 可后续通过命令配置
        'original_users': original_users,
        'created_at': time.time(),
        'created_by': user_id,
        'leader_group': group_id
    }

    for gid in group_ids:
        alliances.setdefault('group_to_alliance', {})[gid] = alliance_id

    self._save_alliances(alliances)
    self._initial_merge_alliance_data(alliance_id)

    # 广播通知
    message = (
        f"联盟创建成功！\n"
        f"联盟ID: {alliance_id}\n"
        f"成员群: {len(group_ids)}个\n"
        f"所有成员群现已共享用户数据和股市！"
    )
    await self._broadcast_to_alliance(group_id, message, exclude_current=False)
```

#### 2.3 查看联盟信息

```python
async def _alliance_view(self, event):
    """查看当前联盟信息"""
    group_id = str(event.message_obj.group_id)
    alliance_id = self._get_alliance_id(group_id)

    if not alliance_id:
        yield event.plain_result("当前群未加入任何联盟")
        return

    alliances = self._load_alliances()
    alliance = alliances['alliances'].get(alliance_id, {})
    group_aliases = alliance.get('group_aliases', {})

    # 显示群别名（如有）+ 群号
    groups_list = []
    for gid in alliance['groups']:
        alias = group_aliases.get(gid, '')
        if alias:
            groups_list.append(f"- {alias} ({gid})")
        else:
            groups_list.append(f"- {gid}")
    groups_str = '\n'.join(groups_list)

    yield event.plain_result(
        f"联盟信息\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"联盟ID: {alliance_id}\n"
        f"名称: {alliance['name']}\n"
        f"成员群数: {len(alliance['groups'])}\n"
        f"创建时间: {time.strftime('%Y-%m-%d', time.localtime(alliance['created_at']))}\n"
        f"\n成员群:\n{groups_str}"
    )
```

#### 2.4 退出联盟

```python
async def _alliance_leave(self, event):
    """当前群退出联盟"""
    group_id = str(event.message_obj.group_id)
    user_id = str(event.get_sender_id())

    if not self.is_admin(user_id):
        yield event.plain_result("只有管理员才能退出联盟")
        return

    alliance_id = self._get_alliance_id(group_id)
    if not alliance_id:
        yield event.plain_result("当前群未加入任何联盟")
        return

    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]

    # 如果是盟主群退出，解散整个联盟
    if alliance['leader_group'] == group_id:
        yield event.plain_result("盟主群不能单独退出，请使用【牛牛联盟解散】命令")
        return

    # 从联盟中移除该群
    alliance['groups'].remove(group_id)
    del alliances['group_to_alliance'][group_id]

    # 如果联盟只剩1个群，自动解散
    if len(alliance['groups']) < 2:
        yield event.plain_result("联盟成员不足，自动解散")
        await self._dissolve_alliance(alliance_id)
        return

    self._save_alliances(alliances)

    # 执行数据分叉
    self._fork_alliance_data_for_group(group_id, alliance_id)

    yield event.plain_result(
        f"已退出联盟\n"
        f"当前群已恢复独立模式\n"
        f"数据已分叉，仅保留本群用户"
    )
```

#### 2.5 解散联盟

```python
async def _alliance_dissolve(self, event):
    """解散联盟（仅盟主可用）"""
    group_id = str(event.message_obj.group_id)
    user_id = str(event.get_sender_id())

    if not self.is_admin(user_id):
        yield event.plain_result("只有管理员才能解散联盟")
        return

    alliance_id = self._get_alliance_id(group_id)
    if not alliance_id:
        yield event.plain_result("当前群未加入任何联盟")
        return

    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]

    # 验证是否为盟主群
    if alliance['leader_group'] != group_id:
        yield event.plain_result("只有盟主群的管理员才能解散联盟")
        return

    # 广播解散通知
    await self._broadcast_to_alliance(
        group_id,
        "联盟已解散\n所有群恢复独立模式\n数据已分叉",
        exclude_current=False
    )

    # 执行解散逻辑
    await self._dissolve_alliance(alliance_id)

    yield event.plain_result("联盟解散成功")

async def _dissolve_alliance(self, alliance_id: str):
    """解散联盟的内部实现"""
    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]
    groups = alliance['groups']

    # 为每个群执行数据分叉
    for gid in groups:
        self._fork_alliance_data_for_group(gid, alliance_id)

    # 从配置中删除联盟
    for gid in groups:
        del alliances['group_to_alliance'][gid]
    del alliances['alliances'][alliance_id]

    self._save_alliances(alliances)

def _fork_alliance_data_for_group(self, group_id: str, alliance_id: str):
    """
    为单个群分叉数据
    只保留该群原本就有的用户数据
    """
    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]

    # 获取联盟创建时记录的原始用户列表
    original_users = set(alliance.get('original_users', {}).get(group_id, []))

    all_data = self._load_niuniu_lengths()
    group_data = all_data.get(group_id, {})

    # 清理：删除不属于本群原始用户的数据
    users_to_remove = []
    for user_id in group_data.keys():
        if user_id == 'plugin_enabled':
            continue
        # 如果用户不在原始用户列表中，删除
        if user_id not in original_users:
            users_to_remove.append(user_id)

    for user_id in users_to_remove:
        del group_data[user_id]

    self._save_niuniu_lengths(all_data)
```

### Phase 3: 股市系统改造 (P0)

#### 3.1 改造文件: `niuniu_stock.py`

**新增方法**:
```python
def _get_alliance_id(self, group_id: str) -> Optional[str]:
    """获取群组所属的联盟ID"""
    try:
        alliance_file = os.path.join(self.data_dir, 'niuniu_alliances.yml')
        if os.path.exists(alliance_file):
            with open(alliance_file, 'r', encoding='utf-8') as f:
                alliances = yaml.safe_load(f) or {}
                return alliances.get('group_to_alliance', {}).get(group_id)
    except Exception as e:
        logger.error(f"读取联盟配置失败: {e}")
    return None
```

**修改方法**:
```python
# 改造前
def _get_group_data(self, group_id: str) -> Dict[str, Any]:
    group_id = str(group_id)
    if group_id not in self._data:
        self._data[group_id] = {...}
    return self._data[group_id]

# 改造后
def _get_group_data(self, group_id: str) -> Dict[str, Any]:
    group_id = str(group_id)

    # 检查是否在联盟
    alliance_id = self._get_alliance_id(group_id)
    effective_gid = alliance_id if alliance_id else group_id

    if effective_gid not in self._data:
        self._data[effective_gid] = {
            'price': 100.0,
            'holdings': {},
            'events': [],
            # ...
        }
    return self._data[effective_gid]
```

#### 3.2 股市事件广播

**修改**:
```python
# 在股市事件触发时，广播到联盟
async def trigger_market_crash(self, group_id: str):
    # ... 执行崩盘逻辑
    message = "股市崩盘！所有持仓清零！"

    # 广播到联盟（需要主插件支持）
    # 方案1: 返回需要广播的消息，由主插件处理
    # 方案2: 股市模块持有主插件引用，直接调用广播
    return {'broadcast': True, 'message': message}
```

### Phase 4: 广播系统实现 (P0)

#### 4.1 消息发送机制调研

需要了解 AstrBot 的消息发送API：
- 如何主动发送群消息
- 是否支持异步发送
- 是否有频率限制

#### 4.2 广播方法实现

```python
async def send_group_message(self, group_id: str, message: str):
    """
    发送群消息的底层方法
    需要调用 AstrBot 的 API
    """
    # TODO: 实现方案待定
    # 可能需要使用 self.context 的某个方法
    pass

async def _broadcast_to_alliance(self, group_id: str, message: str, exclude_current: bool = False):
    """向联盟内所有群广播消息"""
    alliance_id = self._get_alliance_id(group_id)
    if not alliance_id:
        return

    groups = self._get_alliance_groups(alliance_id)

    for gid in groups:
        if exclude_current and gid == group_id:
            continue

        try:
            await self.send_group_message(gid, message)
        except Exception as e:
            logger.error(f"广播到群 {gid} 失败: {e}")
```

#### 4.3 广播集成点

**需要集成广播的功能**:

| 功能 | 触发时机 | 广播消息 | 是否排除当前群 |
|------|---------|---------|---------------|
| 股市崩盘 | 随机触发 | "股市崩盘！" | ❌ 全部广播 |
| 股市暴涨 | 随机触发 | "股市暴涨！" | ❌ 全部广播 |
| 全局BUFF | 道具使用 | "BUFF已激活" | ❌ 全部广播 |
| 订阅扣费 | 用户操作时检查 | "已扣费XX金币" | ❌ 全部广播 |
| 牛牛救市 | 管理员命令 | "救市成功" | ❌ 全部广播 |
| 联盟创建 | 管理员命令 | "联盟创建成功" | ❌ 全部广播 |
| 联盟解散 | 管理员命令 | "联盟已解散" | ❌ 全部广播 |

### Phase 5: 功能适配 (P1)

#### 5.1 排行榜跨群聚合

**修改**: `_show_ranking()` 在 `main.py`

```python
async def _show_ranking(self, event):
    group_id = str(event.message_obj.group_id)
    alliance_id = self._get_alliance_id(group_id)

    if alliance_id:
        # 联盟模式：聚合所有用户（去重）
        all_users = {}  # {user_id: merged_data}
        groups = self._get_alliance_groups(alliance_id)

        for gid in groups:
            group_data = self._load_niuniu_lengths().get(gid, {})
            for uid in group_data.keys():
                if uid == 'plugin_enabled':
                    continue
                if uid not in all_users:
                    all_users[uid] = self._merge_user_data_across_groups(uid, alliance_id)

        sorted_users = sorted(
            all_users.items(),
            key=lambda x: x[1].get('length', 0),
            reverse=True
        )[:10]

        # 显示榜单（标注联盟）
        title = f"【联盟排行榜】{len(groups)}个群"
    else:
        # 独立模式（原逻辑）
        # ...
```

#### 5.2 效果系统适配

**修改**: `niuniu_effects.py` 的 `EffectContext`

```python
@dataclass
class EffectContext:
    group_id: str
    user_id: str
    alliance_id: Optional[str] = None  # 新增
    # ... 其他字段
```

在创建 `EffectContext` 时传递 `alliance_id`:
```python
ctx = EffectContext(
    group_id=group_id,
    user_id=user_id,
    alliance_id=self._get_alliance_id(group_id),
    # ...
)
```

#### 5.3 商城系统适配

**修改**: `niuniu_shop.py`

商城模块已经通过 `main_plugin.get_user_data()` 获取数据，理论上无需改动。但需要验证：
- 购买道具后，是否正确同步到联盟所有群
- 金币扣除是否正确反映在合并后的数据中

## Files Modified

### 核心文件 (P0)

| 文件 | 改动类型 | 主要变更 |
|------|---------|---------|
| `main.py` | 大量修改 | 新增联盟管理方法、改造数据访问层、实现广播系统 |
| `niuniu_stock.py` | 中等修改 | 改造 `_get_group_data()` 使用 alliance_id |
| `data/niuniu_alliances.yml` | 新增 | 联盟配置文件 |

### 功能文件 (P1)

| 文件 | 改动类型 | 主要变更 |
|------|---------|---------|
| `niuniu_effects.py` | 小修改 | `EffectContext` 增加 `alliance_id` 字段 |
| `niuniu_shop.py` | 可能无需修改 | 验证使用合并后的数据 |
| `niuniu_games.py` | 可能无需修改 | 验证跨群游戏逻辑 |

### 文档 (P0)

| 文件 | 改动类型 | 主要变更 |
|------|---------|---------|
| `README.md` | 新增章节 | 添加"跨群联盟"功能说明 |
| `CHANGELOG.md` | 新增条目 | 记录联盟系统上线 |

## Implementation Plan

### Phase 1: 基础设施 (1-2天)
- [ ] 创建联盟配置文件操作方法（含群别名）
- [ ] 实现数据合并逻辑
- [ ] 改造核心数据访问层
- [ ] 单元测试

### Phase 2: 联盟管理 (1天)
- [ ] 实现创建/查看/退出/解散命令
- [ ] 命令注册和权限控制
- [ ] 集成测试

### Phase 3: 股市改造 (半天)
- [ ] 改造股市数据访问
- [ ] 验证跨群共享

### Phase 4: 广播系统 (半天-1天)
- [ ] 调研 AstrBot 消息API
- [ ] 实现广播方法
- [ ] 集成到关键功能点

### Phase 5: 功能适配 (半天-1天)
- [ ] 排行榜跨群聚合（显示群别名）
- [ ] 效果系统传递联盟信息
- [ ] 验证商城/道具/游戏逻辑

**总计**: 3-5天（单人开发）

## Testing Plan

### 功能测试

- [ ] **联盟管理**
  - [ ] 创建联盟（2个群）
  - [ ] 创建联盟（3个群）
  - [ ] 查看联盟信息
  - [ ] 退出联盟
  - [ ] 解散联盟

- [ ] **跨群数据共享**
  - [ ] 用户在群A打胶，数据同步到群B
  - [ ] 用户在群B购买道具，金币扣除在群A可见
  - [ ] 排行榜显示联盟所有用户

- [ ] **跨群股市**
  - [ ] 群A购买股票，群B查询持仓可见
  - [ ] 股价在所有群同步
  - [ ] 股市事件在所有群广播

- [ ] **跨群通知**
  - [ ] 股市崩盘在所有群收到通知
  - [ ] 全局BUFF在所有群广播
  - [ ] 订阅扣费在所有群提醒

### 边界测试

- [ ] 群已在联盟中，不能重复加入
- [ ] 非管理员无法创建联盟
- [ ] 只有1个群时无法创建联盟
- [ ] 盟主群退出，联盟自动解散
- [ ] 独立群不受联盟影响
- [ ] 退出联盟后数据保留

## Risks

### 1. 数据一致性风险

**问题**: 多群同时修改同一用户数据可能导致数据不一致

**缓解**: 使用文件锁（`fcntl.flock`）或在写入时加锁

### 2. 广播消息风险

**问题**: 频繁广播可能触发QQ风控

**缓解**:
- 限制广播频率（例如每分钟最多5次）
- 合并相似消息（例如多个股市事件合并为一条）
- 错开发送时间（不同群延迟100-500ms）

### 3. 退出/解散联盟后的数据分叉

**策略**: 智能分叉，只保留有归属的用户数据

联盟解散后，每个群会获得一份独立的数据副本：
- 保留：在该群有过活动记录的用户
- 删除：从未在该群活动过的用户

**示例**:
```
联盟时（群A+群B）:
- 用户1: 在群A有记录
- 用户2: 在群A和群B都有记录
- 用户3: 在群B有记录

解散后:
- 群A保留: 用户1, 用户2
- 群B保留: 用户2, 用户3
```

**实现**: 解散时检查原始数据文件，只保留该群原本就有的用户

### 4. 恶意创建联盟

**问题**: 用户可能恶意将其他群加入联盟

**缓解**:
- 方案1：验证创建者是否为所有群的管理员（需要跨群权限查询）
- 方案2：采用"邀请-确认"机制（其他群管理员需确认加入）
- 方案3：仅允许盟主群管理员创建，其他群通过申请加入

**推荐**: 方案3（最简单且安全）

## Compatibility

### 向后兼容

- 非联盟群完全不受影响，所有逻辑保持原样
- 联盟功能对非联盟群透明（通过 `_get_alliance_id()` 判断）
- 退出联盟后立即恢复独立模式

### 数据迁移

无需数据迁移，联盟配置文件独立存储。

## Open Questions

1. **AstrBot 消息发送API**: 如何主动向指定群发送消息？
   - 需要查阅 AstrBot 文档或代码
   - 可能需要使用 `self.context` 的某个方法

2. **权限验证**: 如何验证用户是否为其他群的管理员？
   - 跨群权限查询可能不可行
   - 建议采用"邀请-确认"机制或仅允许盟主群管理员创建

3. **联盟解散后的数据分叉**: 如何判断用户"在某个群有活动"？
   - 方案1: 检查原始数据文件中该群是否有该用户的条目
   - 方案2: 联盟创建时记录每个用户的"原始归属群"
   - 需要确认具体实现方式

4. **联盟解散后**: 是否保留历史数据？
   - 建议：保留联盟配置但标记为"已解散"
   - 不删除数据，仅停止同步

## References

- 原始设计文档：跨群战斗系统 - 架构设计文档
- 用户需求：所有东西都是跨群共享的，包括通知系统
