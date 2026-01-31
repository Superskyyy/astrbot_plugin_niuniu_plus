# Proposal: cross-group-alliance (简化版)

## Summary
实现最简跨群联盟系统：多个群共享数据，解散后各自保留完整副本。

## 核心简化原则

1. **不做数据清理**：解散后每个群保留完整数据副本
2. **不要别名**：直接显示群号
3. **最简命令**：只有创建、查看、解散
4. **统一合并策略**：大部分字段用 max()
5. **暂不广播**：先实现核心功能

## 数据结构

### 联盟配置 (`data/niuniu_alliances.yml`)

```yaml
alliances:
  "12345678":  # alliance_id
    groups:
      - "12345678"
      - "87654321"
    created_at: 1706745600

group_to_alliance:
  "12345678": "12345678"
  "87654321": "12345678"
```

**删除的字段**：
- ❌ `name` (不需要命名)
- ❌ `group_aliases` (不要别名)
- ❌ `original_users` (不做数据分叉)
- ❌ `created_by` (不需要记录)
- ❌ `leader_group` (没有盟主)

### 用户数据合并策略（简化）

| 字段 | 合并策略 |
|------|---------|
| `length` | `max()` |
| `hardness` | `max()` |
| `coins` | `sum()` ⚠️ 唯一的求和 |
| `items` | 数量累加 |
| **其他所有字段** | `max()` 或取第一个非空值 |

**简化要点**：
- 除了金币和道具，其他都取最大值
- 不区分连胜/连败/冷却时间的特殊逻辑
- nickname 取第一个非空值即可

## 命令设计（仅3个）

| 命令 | 权限 | 功能 |
|------|------|------|
| `牛牛联盟 <群号1> <群号2> ...` | 管理员 | 创建联盟 |
| `牛牛联盟查看` | 所有人 | 查看联盟 |
| `牛牛联盟解散` | 管理员 | 解散联盟 |

**删除的命令**：
- ❌ `牛牛联盟创建` (改为 `牛牛联盟`)
- ❌ `牛牛联盟退出` (合并到解散)

## 核心实现

### 1. 创建联盟

```python
async def _alliance_create(self, event):
    """牛牛联盟 <群号...>"""
    group_id = str(event.message_obj.group_id)
    user_id = str(event.get_sender_id())

    if not self.is_admin(user_id):
        return

    parts = event.message_str.strip().split()
    group_ids = [p for p in parts[1:] if p.isdigit()]

    if len(group_ids) < 2:
        yield event.plain_result("至少需要2个群")
        return

    # 冲突检查
    alliances = self._load_alliances()
    for gid in group_ids:
        if gid in alliances.get('group_to_alliance', {}):
            yield event.plain_result(f"群 {gid} 已在联盟中")
            return

    # 创建联盟
    alliance_id = group_ids[0]
    alliances.setdefault('alliances', {})[alliance_id] = {
        'groups': group_ids,
        'created_at': time.time()
    }

    for gid in group_ids:
        alliances.setdefault('group_to_alliance', {})[gid] = alliance_id

    self._save_alliances(alliances)
    self._initial_merge_alliance_data(alliance_id)

    yield event.plain_result(f"✅ 联盟创建成功\n成员群: {', '.join(group_ids)}")
```

### 2. 查看联盟

```python
async def _alliance_view(self, event):
    """牛牛联盟查看"""
    group_id = str(event.message_obj.group_id)
    alliance_id = self._get_alliance_id(group_id)

    if not alliance_id:
        yield event.plain_result("当前群未加入联盟")
        return

    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]

    groups_str = '\n'.join([f"- {gid}" for gid in alliance['groups']])

    yield event.plain_result(
        f"📋 联盟信息\n"
        f"成员群: {len(alliance['groups'])}个\n\n"
        f"{groups_str}"
    )
```

### 3. 解散联盟

```python
async def _alliance_dissolve(self, event):
    """牛牛联盟解散"""
    group_id = str(event.message_obj.group_id)
    user_id = str(event.get_sender_id())

    if not self.is_admin(user_id):
        return

    alliance_id = self._get_alliance_id(group_id)
    if not alliance_id:
        yield event.plain_result("当前群未加入联盟")
        return

    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]
    groups = alliance['groups']

    # 删除联盟配置（数据保留不动）
    for gid in groups:
        del alliances['group_to_alliance'][gid]
    del alliances['alliances'][alliance_id]

    self._save_alliances(alliances)

    yield event.plain_result("✅ 联盟已解散\n各群数据已保留")
```

**关键简化**：
- 不做数据分叉，直接删除联盟配置
- 每个群保留联盟时的完整数据副本

### 4. 数据合并（简化版）

```python
def _merge_user_data_across_groups(self, user_id: str, alliance_id: str) -> Dict:
    """合并联盟内所有群的用户数据（简化版）"""
    groups = self._get_alliance_groups(alliance_id)
    all_data = self._load_niuniu_lengths()

    merged = {}

    for gid in groups:
        user_data = all_data.get(gid, {}).get(user_id)
        if not user_data:
            continue

        for key, value in user_data.items():
            if key == 'coins' or key.startswith('items'):
                # 金币和道具求和
                merged[key] = merged.get(key, 0) + value
            elif key not in merged:
                # 其他字段取第一个值
                merged[key] = value
            else:
                # 取最大值
                merged[key] = max(merged[key], value)

    return merged
```

## 广播系统（暂不实现）

先不实现跨群广播，等基础功能稳定后再考虑。

事件通知只在触发事件的群发送，其他群不发送。

## 实施计划（进一步简化）

### Phase 1: 核心功能 (1-2天)
- [ ] 联盟配置文件操作
- [ ] 数据合并逻辑（简化版）
- [ ] 改造核心数据访问层
- [ ] 三个命令实现

### Phase 2: 股市改造 (半天)
- [ ] 改造股市数据访问
- [ ] 验证跨群共享

### Phase 3: 测试 (半天)
- [ ] 创建联盟测试
- [ ] 跨群操作测试
- [ ] 解散联盟测试

**总计**: 2-3天

## 风险

### 1. 解散后数据冗余

**问题**: 每个群都保留全部用户数据，可能有冗余

**回应**:
- 数据量不大，可接受
- 避免了复杂的分叉逻辑
- 用户不会丢失数据

### 2. 没有广播通知

**问题**: 股市事件只在一个群通知

**回应**:
- 先实现核心功能
- 后续可以加广播

## 对比原方案

| 项目 | 原方案 | 简化方案 |
|------|-------|---------|
| 配置字段 | 7个 | 2个 |
| 命令数量 | 4个 | 3个 |
| 数据分叉 | ✅ 智能清理 | ❌ 全部保留 |
| 群别名 | ✅ 支持 | ❌ 直接显示群号 |
| 广播系统 | ✅ 完整实现 | ❌ 暂不实现 |
| 合并策略 | 7种 | 2种（max/sum）|
| 实施时间 | 3-5天 | 2-3天 |

## 总结

**简化后的核心逻辑**：
1. 创建联盟 = 记录群号列表
2. 合并数据 = max() + sum(金币)
3. 解散联盟 = 删除配置，数据保留

**牺牲的功能**：
- 数据分叉清理（用户可能看到其他群的用户）
- 群别名（直接显示群号）
- 广播通知（暂时没有）
- 盟主权限（任何管理员都能操作）

**收益**：
- 代码量减少 50%
- 实施时间减少 40%
- 维护成本大幅降低
- 不易出bug
