# Project Architecture

Dev-Flow is a filesystem-backed control plane. The model or worker is an actuator; Dev-Flow owns canonical state, context boundaries, logs, verification evidence, and promotion readiness.

Architecture authority starts in [../../docs/devflow-control-loop-contracts.md](../../docs/devflow-control-loop-contracts.md). Layer-local architecture notes live under [../layers/architecture](../layers/architecture).
