---
name: handoff-steward
description: Multi-agent handoff documents 的唯一写入通道。触发词：更新 handoff、交接文档、handoff 冲突、合并 handoff、多工具协作上下文、跨工具同步进度、写交接、update handoff、merge handoff、handoff conflict。凡是需要修改由 handoff-steward 管理的 handoff 文档时，必须用 CLI 提交 proposal，禁止直接 Write/Edit canonical.json 或 handoff.md。Use when several AI tools or subagents share one handoff document.
---

# Handoff Steward：多 agent handoff 的唯一写入通道

## 硬性规则

1. **禁止直接写** handoff store 目录下的 `canonical.json` 和 `handoff.md`。
   直写会被 watchdog 回滚，你的改动会变成匿名提案重新排队，反而更慢。
2. **读取没限制**：直接读 `handoff.md`（人类友好投影）或 `canonical.json`。
3. 所有修改走 `handoff-steward submit` 提交 proposal，由 Jev 语义路由决定：
   自动入库 / 字段级选择 / 驳回 / 升级人工。

## Store 在哪里

按以下顺序确定 store 目录（`<store>`）：

1. 用户或项目文档明确给出的路径
2. 项目内现有 store：查找含 `canonical.json` + `events.jsonl` 的目录
   （常见约定：`<project>/.handoff/<goal-id>/`）
3. 都没有且确需新建：先与用户确认 goal 描述，再
   `handoff-steward --root <store> init --goal-id <goal-id> --goal "<goal>"`

## 提交流程

```bash
# 1. 读当前版本号
handoff-steward --root <store> status        # 看 version

# 2. 构造 proposal.json（base_version 填刚读到的 version）
# 3. 提交
handoff-steward --root <store> submit --proposal /path/to/proposal.json
```

Proposal 字段：

| 字段 | 说明 |
|---|---|
| `author_tool` | 你是谁：`codex` / `claude` / `kimi` / `pi` / 其他工具名 |
| `base_version` | 你基于哪个版本写的（status 里的 version） |
| `section` | `goal` / `current_state` / `decisions` / `open_questions` / `next_actions` / `evidence_log` |
| `operation` | `append`（新增）/ `update`（改写文本区；decisions 的 update = 废止旧决策） |
| `content` | 文本区用字符串；decisions 用 `{"text": "..."}`；update 决策用 `{"id": "D-1", "text": "..."}` |
| `summary` | 一句话意图说明，Jev 和人都看 |
| `author_ref` | 可选，细粒度身份：`claude:session-xxx:subagent-3`。多 session/多 subagent 并发时必填 |

## 结果处理

- `auto_commit` → 完成，version +1，无需再操作。
- `reject` → 读 reason。常见原因：内容越界、基线过时且已失效。不要换措辞重试绕过判断；
  如果你确信判断错了，在 summary 里补充上下文重提一次，仍驳回则告知用户。
- `escalate` → **停止自行处理**。brief 在 `<store>/escalations/`。把冲突双方和 Jev 理由
  简明汇报给用户，等用户裁决；用户口头裁决后，你再把裁决结果作为新 proposal 提交
  （summary 注明 "人工裁决：..."）。
- `field_select` 是中间态，CLI 会返回最终动作（accept→auto_commit 或 keep→reject），按上面处理。

## 并行子任务与多 session

主 agent 派生并行子任务时，让每个子任务各自提交自己的 proposal（各自读 version、各自提交），
不要收集后由一个人代写。同一工具的多个 session、每个 session 的多个 subagent 都可以同时提交——
steward 用进程级互斥锁（flock）串行化所有提交，后到者自动走 stale 重检，不会丢更新。
并发提交时必须给每个提交者填 `author_ref` 区分身份。

## 环境要求

- `TYPESAFE_API_KEY` 必须在环境中。用 `handoff-steward doctor` 检查；缺失时引导用户去
  https://console.typesafe.ai/settings/keys 创建并配置到 shell 环境。
- Jev API 不可用时：不要直写兜底。把 proposal 留在临时文件并告知用户 steward 暂不可用
  （steward 本身会 fail-closed：提案自动升级人工，不会丢）。
