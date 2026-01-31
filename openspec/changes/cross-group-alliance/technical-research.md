# 跨群联盟系统 - 技术调研报告

## 调研时间
2026-01-31

## 调研目标
解决 `proposal.md` 中的所有待确认技术问题（Open Questions）

---

## 1. AstrBot 消息发送API ✅

### 问题
如何主动向指定群发送消息（用于跨群广播）？

### 调研结果

#### 方法：Context.send_message()

```python
await self.context.send_message(target, message_chain)
```

**参数说明**：
- `target` (str): 会话标识符 `unified_msg_origin`
- `message_chain` (MessageChain): 消息内容

#### Target 格式构造

**格式模板**：
```python
target = f"{platform_name}:MessageType:{session_id}"
```

**QQ群示例**：
```python
# aiocqhttp 平台（go-cqhttp）
target = "aiocqhttp:GroupMessage:123456789"

# QQ官方API平台
target = "qqofficial:GroupMessage:123456789@chatroom"
```

**获取平台名称**：
```python
# 方案1: 从 event 中提取
platform_name = event.unified_msg_origin.split(':')[0]

# 方案2: 在联盟配置中存储完整的 unified_msg_origin
# 推荐：创建联盟时记录 event.unified_msg_origin
```

#### MessageChain 构建

```python
from astrbot.api.message_components import Plain, At, Image, MessageChain

# 纯文本消息
chain = MessageChain().message("Hello!")

# 复杂消息
chain = MessageChain()
chain.chain.append(At(qq="123456789"))
chain.chain.append(Plain(" 你好！"))
chain.chain.append(Image.fromFileSystem("/path/to/image.jpg"))
```

### 实现方案

#### 方案A：存储完整的 unified_msg_origin（推荐）

**优点**：
- 平台无关，支持所有协议
- 不需要手动构造格式

**缺点**：
- 需要至少一次消息交互才能获取

**联盟配置修改**：
```yaml
alliances:
  "12345678":
    groups:
      - "12345678"
      - "87654321"
    unified_origins:  # 新增：存储每个群的会话ID
      "12345678": "aiocqhttp:GroupMessage:12345678"
      "87654321": "aiocqhttp:GroupMessage:87654321"
```

**获取方法**：
```python
# 在任意命令处理时记录
def _record_group_origin(self, group_id: str, unified_msg_origin: str):
    """记录群的 unified_msg_origin"""
    # 存储到配置文件或内存缓存
    pass
```

#### 方案B：手动构造（备选）

**假设用户使用 aiocqhttp**：
```python
target = f"aiocqhttp:GroupMessage:{group_id}"
```

**风险**：不同平台格式不同，可能失败

### 广播实现代码

```python
async def _broadcast_to_alliance(
    self,
    group_id: str,
    message: str,
    exclude_current: bool = False
):
    """向联盟内所有群广播消息"""
    alliance_id = self._get_alliance_id(group_id)
    if not alliance_id:
        return

    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]
    unified_origins = alliance.get('unified_origins', {})

    for gid, origin in unified_origins.items():
        if exclude_current and gid == group_id:
            continue

        try:
            # 构建消息链
            chain = MessageChain().message(message)

            # 发送消息
            await self.context.send_message(origin, chain)

            self.context.logger.info(f"✅ 广播到群 {gid} 成功")

        except Exception as e:
            self.context.logger.error(f"❌ 广播到群 {gid} 失败: {e}")
```

### 参考资料
- [AstrBot 消息发送文档](https://docs.astrbot.app/dev/star/guides/send-message.html)
- [AstrBot 会话控制文档](https://docs.astrbot.app/dev/star/guides/session-control.html)
- [GitHub 插件示例](https://github.com/memoriass/astrbot_plugin_media_webhook/blob/main/main.py)

---

## 2. 权限验证 ✅

### 问题
如何验证用户是否为管理员？是否能跨群验证？

### 调研结果

#### 现有实现

**代码位置**：`main.py` 第144-146行

```python
def is_admin(self, user_id):
    """检查用户是否为管理员"""
    return str(user_id) in self.admins
```

**管理员列表加载**：
```python
def _load_admins(self):
    """加载管理员列表"""
    try:
        with open(os.path.join('data', 'cmd_config.json'), 'r', encoding='utf-8-sig') as f:
            config = json.load(f)
            return config.get('admins_id', [])
    except Exception as e:
        self.context.logger.error(f"加载管理员列表失败: {str(e)}")
        return []
```

**配置文件**：`data/cmd_config.json`
```json
{
  "admins_id": ["123456789", "987654321"]
}
```

#### 跨群权限验证

**问题**：
- AstrBot 的管理员是全局配置，不区分群
- 无法验证"用户是否为某个特定群的管理员"

**结论**：
- ❌ 不支持跨群权限验证
- ✅ 只能验证是否为插件全局管理员

### 实现方案

#### 方案A：仅验证当前操作者（推荐）

**逻辑**：
```python
async def _alliance_create(self, event):
    user_id = str(event.get_sender_id())

    # 只验证创建者是否为管理员
    if not self.is_admin(user_id):
        yield event.plain_result("只有管理员才能创建联盟")
        return

    # 不验证其他群的管理员权限
    # 信任创建者有权限将其他群加入联盟
```

**优点**：实现简单，避免复杂权限验证

**缺点**：可能被滥用（管理员恶意将他人的群加入联盟）

#### 方案B："邀请-确认"机制（备选）

**流程**：
1. 盟主群管理员创建联盟（只包含本群）
2. 其他群管理员收到邀请通知
3. 其他群管理员输入"牛牛联盟接受邀请"确认加入

**优点**：安全，其他群需要主动确认

**缺点**：
- 实现复杂（需要邀请状态管理）
- 用户体验较差（需要多次操作）

#### 方案C：要求管理员手动配置（最简）

**说明**：
```
管理员需要在所有要加入联盟的群中都拥有管理员权限，
然后手动输入命令：牛牛联盟 <群号1> <群号2>
```

**信任模型**：
- 信任配置的管理员不会恶意操作
- 如果被滥用，受害群管理员可使用"牛牛联盟解散"退出

### 推荐方案

**采用方案A + 方案C**：
- 只验证操作者是否为管理员
- 在文档中说明：管理员需对所有加入联盟的群负责
- 提供解散命令作为退出机制

---

## 3. 联盟解散后的数据分叉 ✅

### 问题
如何判断用户"在某个群有活动"？

### 调研结果

**已采用方案**：联盟创建时记录原始归属

#### 实现逻辑

**联盟创建时**（`_alliance_create`）：
```python
# 记录各群的原始用户列表
all_data = self._load_niuniu_lengths()
original_users = {}

for gid in group_ids:
    group_data = all_data.get(gid, {})
    # 排除非用户字段
    users = [uid for uid in group_data.keys() if uid != 'plugin_enabled']
    original_users[gid] = users

# 保存到联盟配置
alliance['original_users'] = original_users
```

**联盟解散时**（`_fork_alliance_data_for_group`）：
```python
def _fork_alliance_data_for_group(self, group_id: str, alliance_id: str):
    """为单个群分叉数据，只保留原始用户"""
    alliances = self._load_alliances()
    alliance = alliances['alliances'][alliance_id]

    # 获取该群的原始用户列表
    original_users = set(alliance.get('original_users', {}).get(group_id, []))

    all_data = self._load_niuniu_lengths()
    group_data = all_data.get(group_id, {})

    # 删除非原始用户
    users_to_remove = []
    for user_id in group_data.keys():
        if user_id == 'plugin_enabled':
            continue
        if user_id not in original_users:
            users_to_remove.append(user_id)

    for user_id in users_to_remove:
        del group_data[user_id]

    self._save_niuniu_lengths(all_data)
```

### 配置文件示例

```yaml
alliances:
  "12345678":
    groups:
      - "12345678"
      - "87654321"
    original_users:  # 联盟创建前的用户归属
      "12345678": ["user1", "user2", "user3"]
      "87654321": ["user2", "user4", "user5"]
```

**解散后结果**：
- 群 `12345678` 保留：user1, user2, user3
- 群 `87654321` 保留：user2, user4, user5
- user2 在两个群都保留（交叉用户）

### 结论

✅ 已确定使用"记录原始归属"方案，无需进一步调研

---

## 4. 联盟解散后的历史数据 ✅

### 问题
是否保留历史数据？

### 决策

**策略**：保留联盟配置，标记为已解散（可选）

#### 方案A：完全删除（当前采用）

```python
# 删除联盟配置
for gid in groups:
    del alliances['group_to_alliance'][gid]
del alliances['alliances'][alliance_id]
```

**优点**：配置文件干净

**缺点**：无法查看历史联盟信息

#### 方案B：标记为已解散（备选）

```python
# 标记为已解散
alliance['status'] = 'dissolved'
alliance['dissolved_at'] = time.time()

# 从 group_to_alliance 中移除
for gid in groups:
    del alliances['group_to_alliance'][gid]
```

**优点**：可查看历史记录

**缺点**：配置文件会积累历史数据

### 推荐

**采用方案A**（完全删除）：
- 联盟解散后不保留配置
- 用户数据已分叉到各群，无需保留联盟信息

---

## 总结

### 所有问题解决状态

| # | 问题 | 状态 | 方案 |
|---|------|------|------|
| 1 | AstrBot 消息发送API | ✅ | 存储 unified_msg_origin |
| 2 | 权限验证 | ✅ | 只验证操作者 + 信任模型 |
| 3 | 数据分叉判断 | ✅ | 记录 original_users |
| 4 | 历史数据保留 | ✅ | 完全删除 |

### Proposal 需要更新的部分

#### 1. 联盟配置结构（新增 unified_origins）

```yaml
alliances:
  "12345678":
    groups: [...]
    group_aliases: {...}
    original_users: {...}
    unified_origins:  # ⬅️ 新增
      "12345678": "aiocqhttp:GroupMessage:12345678"
      "87654321": "aiocqhttp:GroupMessage:87654321"
```

#### 2. 创建联盟时记录 unified_msg_origin

```python
# 在 _alliance_create 中添加
unified_origins = {}
for gid in group_ids:
    # TODO: 如何获取其他群的 unified_msg_origin？
    # 方案1: 要求管理员在每个群都执行一次命令来记录
    # 方案2: 假设平台名称，手动构造
    pass
```

#### 3. 广播系统实现

使用调研中的 `_broadcast_to_alliance()` 代码

#### 4. 权限验证说明

在文档中明确：
- 只验证操作者是否为管理员
- 管理员需对所有加入联盟的群负责
- 提供解散命令作为退出机制

### 剩余问题

#### ⚠️ 如何获取其他群的 unified_msg_origin？

**问题**：
创建联盟时，只能获取当前群的 `event.unified_msg_origin`，无法直接获取其他群的。

**可行方案**：

**方案1**：两步创建
```
步骤1: 管理员在每个群执行"牛牛联盟预注册"，记录 unified_msg_origin
步骤2: 在盟主群执行"牛牛联盟创建"，使用预注册的数据
```

**方案2**：假设平台并构造（风险）
```python
# 假设所有群都使用相同平台
platform_name = event.unified_msg_origin.split(':')[0]
for gid in group_ids:
    unified_origins[gid] = f"{platform_name}:GroupMessage:{gid}"
```

**方案3**：第一次收到消息时自动记录
```python
# 在 on_group_message 中
async def on_group_message(self, event):
    group_id = str(event.message_obj.group_id)
    # 自动记录 unified_msg_origin
    self._record_group_origin(group_id, event.unified_msg_origin)
    # ... 其他逻辑
```

**推荐**：方案2 + 方案3 组合
- 创建联盟时假设平台并构造（方便）
- 后台自动记录真实的 unified_msg_origin（容错）
- 广播时优先使用真实值，回退到构造值

---

## 下一步行动

1. ✅ 更新 `proposal.md`，添加 `unified_origins` 字段
2. ✅ 更新广播系统实现代码
3. ✅ 添加 unified_msg_origin 自动记录逻辑
4. ✅ 更新权限验证说明
5. ⏭️ 开始 Phase 1 实施
