# BEACON Documentation

## For Operators (deploy & run)

| Document | Description |
|----------|-------------|
| [setup.md](setup.md) | Environment setup, GCP deployment, Cloud Run |
| [operations.md](operations.md) | Day-to-day operations, MISP cache, SAGE integration |

## For Analysts (daily use)

| Document | Description |
|----------|-------------|
| [triggers.md](triggers.md) | Business trigger definitions and configuration |
| Context template | [`schema/context_template.md`](../schema/context_template.md) — security context input template |

## For Developers (contribute code)

| Document | Description |
|----------|-------------|
| [structure.md](structure.md) | Project directory layout |
| [data-model.md](data-model.md) | PIR output schema, score breakdown, actor triage model |
| [dependencies.md](dependencies.md) | Third-party dependency rationale |

## For Architects (design decisions)

| Document | Description |
|----------|-------------|
| [api-stability.md](api-stability.md) | API stability policy and BC guarantees |
| [high-level-design.md](high-level-design.md) | System design (local-only, gitignored) |
| [citations.md](citations.md) | External citations and license inventory |

## Cross-project (shared via symlink)

| Document | Canonical repo | Description |
|----------|---------------|-------------|
| [pipeline-guide.md](pipeline-guide.md) | BEACON | End-to-end CTI pipeline operations |

> IR feedback flow の計算式は [SAGE docs/ir-feedback-flow.md](../../sage/docs/ir-feedback-flow.md) を参照。

日本語版は各ファイルの `.ja.md` サフィックスで同ディレクトリに配置。
