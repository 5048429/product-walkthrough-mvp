# Prodwalk Web 控制台 API 与事件契约

本文定义第一版本地 Web 控制台的前后端契约。实现目录计划为 `apps/web` 和 `src/prodwalk/server`，但当前阶段只定义文档。

## RunStatus 枚举

```json
[
  "queued",
  "starting",
  "running",
  "awaiting_verification",
  "finalizing",
  "succeeded",
  "failed",
  "canceling",
  "canceled"
]
```

## AgentStatus 枚举

```json
[
  "pending",
  "running",
  "waiting",
  "succeeded",
  "failed",
  "skipped",
  "canceled"
]
```

## AgentType 枚举

```json
[
  "director",
  "planner",
  "walker",
  "evidence_extractor",
  "product_analyst",
  "competitive_analyst",
  "reviewer",
  "report_writer",
  "evaluator",
  "auth_session"
]
```

## Artifact 类型

```json
[
  "run_manifest",
  "plan_json",
  "events_jsonl",
  "agents_json",
  "artifacts_json",
  "evidence_json",
  "report_markdown",
  "evaluation_json",
  "screenshot",
  "browser_history",
  "log_text"
]
```

敏感文件不作为可下载 artifact，例如 credential store、browser profile、storage state。

## RunEvent JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://prodwalk.local/schemas/run-event.schema.json",
  "title": "RunEvent",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "run_id", "seq", "ts", "type", "level", "message"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Globally unique event id, for example evt_01HX..."
    },
    "run_id": {
      "type": "string",
      "description": "Run id, usually run-YYYYMMDD-HHMMSS or generated id."
    },
    "seq": {
      "type": "integer",
      "minimum": 1,
      "description": "Monotonic sequence within one run."
    },
    "ts": {
      "type": "string",
      "format": "date-time"
    },
    "type": {
      "type": "string",
      "examples": [
        "run.started",
        "agent.started",
        "scenario.step.completed",
        "artifact.created",
        "run.completed"
      ]
    },
    "level": {
      "type": "string",
      "enum": ["debug", "info", "warn", "error"]
    },
    "message": {
      "type": "string"
    },
    "agent_id": {
      "type": ["string", "null"]
    },
    "agent_type": {
      "type": ["string", "null"],
      "enum": [
        "director",
        "planner",
        "walker",
        "evidence_extractor",
        "product_analyst",
        "competitive_analyst",
        "reviewer",
        "report_writer",
        "evaluator",
        "auth_session",
        null
      ]
    },
    "product": {
      "type": ["string", "null"]
    },
    "scenario_id": {
      "type": ["string", "null"]
    },
    "step_index": {
      "type": ["integer", "null"],
      "minimum": 1
    },
    "status": {
      "type": ["string", "null"],
      "description": "Optional status after this event."
    },
    "payload": {
      "type": "object",
      "additionalProperties": true
    },
    "artifact_ids": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

事件示例：

```json
{
  "id": "evt_000012",
  "run_id": "run-20260616-101500",
  "seq": 12,
  "ts": "2026-06-16T02:15:31.100Z",
  "type": "scenario.step.completed",
  "level": "info",
  "message": "Browser step completed",
  "agent_id": "agent_walker_clink_complete_continuous_walkthrough",
  "agent_type": "walker",
  "product": "Clink UAT Dashboard",
  "scenario_id": "clink_complete_continuous_walkthrough",
  "step_index": 3,
  "status": "running",
  "payload": {
    "action": "click",
    "step_status": "passed",
    "url": "https://uat-dashboard.clinkbill.com/analytics"
  },
  "artifact_ids": ["art_screenshot_step_3"]
}
```

## 基础对象

### RunSummary

```json
{
  "id": "run-20260616-101500",
  "status": "running",
  "mode": "mock",
  "research_goal": "Compare onboarding flows.",
  "run_dir": "runs/run-20260616-101500",
  "created_at": "2026-06-16T02:15:00Z",
  "started_at": "2026-06-16T02:15:01Z",
  "completed_at": null,
  "progress": {
    "total_scenarios": 6,
    "completed_scenarios": 2,
    "failed_scenarios": 0
  }
}
```

### AgentExecution

```json
{
  "id": "agent_walker_our-product_onboarding",
  "run_id": "run-20260616-101500",
  "type": "walker",
  "status": "running",
  "label": "BrowserWalker: Our Product / onboarding",
  "product": "Our Product",
  "scenario_id": "onboarding",
  "current_step": 2,
  "started_at": "2026-06-16T02:15:05Z",
  "completed_at": null,
  "metrics": {
    "step_count": 5,
    "completion_score": null
  },
  "error": null
}
```

### Artifact

```json
{
  "id": "art_report_md",
  "run_id": "run-20260616-101500",
  "type": "report_markdown",
  "title": "Product Walkthrough Research Report",
  "path": "report.md",
  "media_type": "text/markdown; charset=utf-8",
  "size_bytes": 12070,
  "created_at": "2026-06-16T02:20:00Z",
  "metadata": {
    "language": "zh"
  }
}
```

## API 列表

```text
GET  /api/health
GET  /api/plans
GET  /api/plans/{plan_id}
POST /api/runs
GET  /api/runs
GET  /api/runs/{run_id}
POST /api/runs/{run_id}/cancel
POST /api/runs/{run_id}/verification/confirm
GET  /api/runs/{run_id}/agents
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/events/stream
GET  /api/runs/{run_id}/artifacts
GET  /api/runs/{run_id}/artifacts/{artifact_id}
GET  /api/runs/{run_id}/artifacts/{artifact_id}/content
GET  /api/runs/{run_id}/report
GET  /api/runs/{run_id}/evidence
GET  /api/runs/{run_id}/evaluation
```

## API 示例

### `GET /api/health`

Request:

```http
GET /api/health HTTP/1.1
```

Response:

```json
{
  "ok": true,
  "service": "prodwalk-server",
  "version": "0.1.0",
  "time": "2026-06-16T02:10:00Z"
}
```

### `GET /api/plans`

列出可选 plan。第一版可从 `examples/*.json` 扫描。

Request:

```http
GET /api/plans HTTP/1.1
```

Response:

```json
{
  "items": [
    {
      "id": "examples/research_plan.json",
      "path": "examples/research_plan.json",
      "title": "Compare onboarding and first project creation experience for our product and two competitors.",
      "product_count": 3,
      "scenario_count": 2,
      "report_language": "en"
    }
  ]
}
```

### `GET /api/plans/{plan_id}`

Request:

```http
GET /api/plans/examples%2Fresearch_plan.json HTTP/1.1
```

Response:

```json
{
  "id": "examples/research_plan.json",
  "path": "examples/research_plan.json",
  "plan": {
    "research_goal": "Compare onboarding and first project creation experience for our product and two competitors.",
    "products": [
      {
        "name": "Our Product",
        "url": "https://example.com",
        "kind": "owned",
        "credentials_ref": "TEST_ACCOUNT_OUR_PRODUCT",
        "notes": "Replace with staging URL and a test account.",
        "tags": []
      }
    ],
    "scenarios": [],
    "evaluation": {},
    "report_language": "en"
  }
}
```

### `POST /api/runs`

启动一个 run。`config_path` 和 `plan` 二选一。

Request:

```json
{
  "config_path": "examples/research_plan.json",
  "plan": null,
  "mode": "mock",
  "out": "runs",
  "concurrency": 3,
  "report_language": "zh",
  "browser_model": null,
  "browser_max_steps": 25,
  "browser_timeout_sec": 600,
  "browser_user_data_dir": null,
  "browser_storage_state": null,
  "verification_mode": "off",
  "verification_timeout_sec": 300,
  "verification_success_url_contains": [],
  "verification_login_url_contains": "/auth/login"
}
```

Response:

```json
{
  "run": {
    "id": "run-20260616-101500",
    "status": "queued",
    "mode": "mock",
    "research_goal": "Compare onboarding and first project creation experience for our product and two competitors.",
    "run_dir": "runs/run-20260616-101500",
    "created_at": "2026-06-16T02:15:00Z",
    "started_at": null,
    "completed_at": null,
    "progress": {
      "total_scenarios": 6,
      "completed_scenarios": 0,
      "failed_scenarios": 0
    }
  }
}
```

### `GET /api/runs`

Request:

```http
GET /api/runs?limit=20 HTTP/1.1
```

Response:

```json
{
  "items": [
    {
      "id": "run-20260616-101500",
      "status": "succeeded",
      "mode": "mock",
      "research_goal": "Compare onboarding flows.",
      "run_dir": "runs/run-20260616-101500",
      "created_at": "2026-06-16T02:15:00Z",
      "started_at": "2026-06-16T02:15:01Z",
      "completed_at": "2026-06-16T02:15:08Z",
      "progress": {
        "total_scenarios": 6,
        "completed_scenarios": 6,
        "failed_scenarios": 0
      }
    }
  ],
  "next_cursor": null
}
```

### `GET /api/runs/{run_id}`

Request:

```http
GET /api/runs/run-20260616-101500 HTTP/1.1
```

Response:

```json
{
  "run": {
    "id": "run-20260616-101500",
    "status": "succeeded",
    "mode": "mock",
    "research_goal": "Compare onboarding flows.",
    "run_dir": "runs/run-20260616-101500",
    "created_at": "2026-06-16T02:15:00Z",
    "started_at": "2026-06-16T02:15:01Z",
    "completed_at": "2026-06-16T02:15:08Z",
    "progress": {
      "total_scenarios": 6,
      "completed_scenarios": 6,
      "failed_scenarios": 0
    },
    "params": {
      "mode": "mock",
      "concurrency": 3,
      "report_language": "zh"
    },
    "artifact_ids": ["art_evidence_json", "art_report_md", "art_evaluation_json"],
    "error": null
  }
}
```

### `POST /api/runs/{run_id}/cancel`

Request:

```json
{
  "reason": "User canceled from console"
}
```

Response:

```json
{
  "run_id": "run-20260616-101500",
  "status": "canceling",
  "accepted": true
}
```

### `POST /api/runs/{run_id}/verification/confirm`

用于用户在 visible browser 完成登录、Altcha、CAPTCHA、SSO 或 MFA 后通知后端继续。第一版也可以只作为状态记录接口，实际继续动作由现有 terminal/manual confirm 流程处理。

Request:

```json
{
  "confirmed": true,
  "note": "Authenticated dashboard is visible."
}
```

Response:

```json
{
  "run_id": "run-20260616-101500",
  "status": "running",
  "accepted": true
}
```

### `GET /api/runs/{run_id}/agents`

Request:

```http
GET /api/runs/run-20260616-101500/agents HTTP/1.1
```

Response:

```json
{
  "items": [
    {
      "id": "agent_director",
      "run_id": "run-20260616-101500",
      "type": "director",
      "status": "succeeded",
      "label": "ResearchDirector",
      "product": null,
      "scenario_id": null,
      "current_step": null,
      "started_at": "2026-06-16T02:15:01Z",
      "completed_at": "2026-06-16T02:15:08Z",
      "metrics": {},
      "error": null
    }
  ]
}
```

### `GET /api/runs/{run_id}/events`

Request:

```http
GET /api/runs/run-20260616-101500/events?after_seq=10&limit=100 HTTP/1.1
```

Response:

```json
{
  "items": [
    {
      "id": "evt_000011",
      "run_id": "run-20260616-101500",
      "seq": 11,
      "ts": "2026-06-16T02:15:05Z",
      "type": "scenario.completed",
      "level": "info",
      "message": "Scenario completed",
      "agent_id": "agent_walker_our-product_onboarding",
      "agent_type": "walker",
      "product": "Our Product",
      "scenario_id": "onboarding",
      "step_index": null,
      "status": "running",
      "payload": {
        "result_status": "completed",
        "completion_score": 0.88
      },
      "artifact_ids": []
    }
  ],
  "last_seq": 11
}
```

### `GET /api/runs/{run_id}/events/stream`

Request:

```http
GET /api/runs/run-20260616-101500/events/stream?after_seq=11 HTTP/1.1
Accept: text/event-stream
```

Response content type:

```text
text/event-stream
```

SSE 事件格式示例：

```text
id: 12
event: run.event
data: {"id":"evt_000012","run_id":"run-20260616-101500","seq":12,"ts":"2026-06-16T02:15:06Z","type":"artifact.created","level":"info","message":"Report artifact created","agent_id":"agent_report_writer","agent_type":"report_writer","product":null,"scenario_id":null,"step_index":null,"status":"finalizing","payload":{"artifact_type":"report_markdown"},"artifact_ids":["art_report_md"]}

```

Heartbeat 示例：

```text
event: ping
data: {"time":"2026-06-16T02:15:07Z"}

```

### `GET /api/runs/{run_id}/artifacts`

Request:

```http
GET /api/runs/run-20260616-101500/artifacts HTTP/1.1
```

Response:

```json
{
  "items": [
    {
      "id": "art_report_md",
      "run_id": "run-20260616-101500",
      "type": "report_markdown",
      "title": "report.md",
      "path": "report.md",
      "media_type": "text/markdown; charset=utf-8",
      "size_bytes": 12070,
      "created_at": "2026-06-16T02:15:08Z",
      "metadata": {
        "language": "zh"
      }
    }
  ]
}
```

### `GET /api/runs/{run_id}/artifacts/{artifact_id}`

Request:

```http
GET /api/runs/run-20260616-101500/artifacts/art_report_md HTTP/1.1
```

Response:

```json
{
  "artifact": {
    "id": "art_report_md",
    "run_id": "run-20260616-101500",
    "type": "report_markdown",
    "title": "report.md",
    "path": "report.md",
    "media_type": "text/markdown; charset=utf-8",
    "size_bytes": 12070,
    "created_at": "2026-06-16T02:15:08Z",
    "metadata": {
      "language": "zh"
    }
  }
}
```

### `GET /api/runs/{run_id}/artifacts/{artifact_id}/content`

Request:

```http
GET /api/runs/run-20260616-101500/artifacts/art_report_md/content HTTP/1.1
```

Response:

```markdown
# Product Walkthrough Research Report

...
```

对于 JSON artifact，响应可以直接返回 JSON。对于 image artifact，响应为对应 image media type。

### `GET /api/runs/{run_id}/report`

Request:

```http
GET /api/runs/run-20260616-101500/report HTTP/1.1
```

Response:

```json
{
  "run_id": "run-20260616-101500",
  "language": "zh",
  "markdown_artifact_id": "art_report_md",
  "evaluation_artifact_id": "art_evaluation_json",
  "markdown": "# Product Walkthrough Research Report\n\n...",
  "evaluation": {
    "overall_score": 1.0,
    "scores": {
      "task_completion_rate": 1.0,
      "evidence_coverage_rate": 1.0,
      "finding_grounding_rate": 1.0,
      "recommendation_actionability_rate": 1.0
    },
    "notes": [
      "MVP run meets the configured basic evaluation thresholds."
    ]
  },
  "generated_at": "2026-06-16T02:15:08Z"
}
```

### `GET /api/runs/{run_id}/evidence`

Request:

```http
GET /api/runs/run-20260616-101500/evidence HTTP/1.1
```

Response:

```json
{
  "run_id": "run-20260616-101500",
  "artifact_id": "art_evidence_json",
  "created_at": "2026-06-16T02:15:08Z",
  "report_language": "zh",
  "results": [
    {
      "product": "Our Product",
      "product_kind": "owned",
      "scenario_id": "onboarding",
      "scenario_title": "First-time onboarding",
      "status": "completed",
      "steps": []
    }
  ],
  "evidence": [
    {
      "id": "ev-our-product-onboarding-1",
      "product": "Our Product",
      "scenario_id": "onboarding",
      "kind": "observation",
      "title": "Step 1",
      "summary": "The step was observable.",
      "url": "https://example.com",
      "screenshot_artifact_id": null,
      "confidence": 0.65,
      "created_at": "2026-06-16T02:15:03Z"
    }
  ]
}
```

### `GET /api/runs/{run_id}/evaluation`

Request:

```http
GET /api/runs/run-20260616-101500/evaluation HTTP/1.1
```

Response:

```json
{
  "run_id": "run-20260616-101500",
  "artifact_id": "art_evaluation_json",
  "scores": {
    "task_completion_rate": 1.0,
    "evidence_coverage_rate": 1.0,
    "finding_grounding_rate": 1.0,
    "recommendation_actionability_rate": 1.0,
    "evidence_items": 22,
    "findings": 7
  },
  "overall_score": 1.0,
  "notes": [
    "MVP run meets the configured basic evaluation thresholds."
  ]
}
```

## 错误响应格式

所有 JSON API 错误使用统一格式：

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run not found: run-unknown",
    "details": {
      "run_id": "run-unknown"
    },
    "request_id": "req_01HX..."
  }
}
```

建议错误码：

```text
BAD_REQUEST
PLAN_NOT_FOUND
PLAN_INVALID
RUN_NOT_FOUND
RUN_NOT_CANCELABLE
ARTIFACT_NOT_FOUND
ARTIFACT_FORBIDDEN
RUN_ALREADY_ACTIVE
SERVER_ERROR
```

## mock mode 第一版约束

第一版应优先打通 mock mode：

- 不启动浏览器。
- 不读取或写入 credential 明文。
- 不执行 auth-session 或 verification preflight。
- 不依赖外部网络。
- 可以并发执行，默认 concurrency 仍与 CLI 一致为 3。
- 可以实时发送 stage 级事件。
- step 事件可以由 `MockBrowserWalker` 结果生成，允许在 scenario 完成后批量补发。
- screenshot artifact 通常为空。
- 产物仍必须生成 `evidence.json`、`report.md`、`evaluation.json`。
- mock mode 是前后端、SSE、artifact、report viewer 的端到端验收路径。
