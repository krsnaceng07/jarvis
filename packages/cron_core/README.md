# JARVIS Cron Core

`jarvis-cron-core` provides cron expression parsing, schedule evaluation, and an in-process `CronRunner` for scheduled jobs following the OpenClaw architecture.

## Components

- **CronRunner**: in-process multi-job runner supporting cron expressions and one-shot ISO timestamps
- **Parser**: 5-field cron expression parser (`cron_matches`, `field_matches`)
- **Types**: `CronDecl` job definition
