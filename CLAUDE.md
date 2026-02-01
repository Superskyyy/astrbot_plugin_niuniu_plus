<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# 开发规范

## 版本号和更新日志

**重要**: 每次修改代码后，必须更新以下内容，在获得一个相对自我 contained 改动后立刻推送符合 git 开发规范 fix: feature: 等的更新，每次加入新功能或修改命令时候，记得修改牛牛菜单。

1. **版本号** (两处必须同步！)
   - `main.py` 第33行的 `@register` 装饰器
   - `metadata.yaml` 的 `version` 字段（格式: `vX.X.X`）
   - 格式: `major.minor.patch`
   - 新功能: minor +1
   - Bug修复/小改动: patch +1
   - 重大变更: major +1

2. **更新日志** (`CHANGELOG.md`)
   - 在文件顶部添加新版本条目
   - 格式: `## [vX.X.X] - YYYY-MM-DD`
   - 分类: 新增功能、删除功能、道具调整、数值调整、Bug修复、显示优化等

示例:
```markdown
## [v2.0.4] - 2026-01-22

### 新增功能
- **道具名** (价格): 功能描述
  - 详细说明

### Bug修复
- 修复xxx问题
```


#### 游戏文本规范
不得出现不合适内容，包括但不限于：
- 涉政内容
- 涉黄内容
- 涉恐内容
- 涉毒内容
- 其他违反法律法规内容

所有 “人/别的生物” 相关文本，都应该有一个 “牛” 的替代版本，例如：
- “大家” -> “牛牛们”
- “朋友” -> “牛友”
- “人人平等” -> “牛牛平等”
- “漏网之鱼” -> “漏网之牛”

#### 游戏核心设计理念

搞怪！有趣！数值相对平衡！意想不到！