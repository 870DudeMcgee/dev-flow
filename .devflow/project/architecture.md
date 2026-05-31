# Project Architecture

Dev-Flow is a filesystem-backed control plane. The model or worker is an actuator; Dev-Flow owns canonical state, context boundaries, logs, verification evidence, and promotion readiness.

The next architecture direction is the Agent Registry and Adapter Runtime in [../../docs/architecture/agent-registry-and-adapter-runtime.md](../../docs/architecture/agent-registry-and-adapter-runtime.md). Agents are permissioned execution contracts, not personalities. Future adapters must be bound to provider, model, role, workspace, allowed context, allowed writes, and evidence policy.

Architecture authority starts in [../../docs/devflow-control-loop-contracts.md](../../docs/devflow-control-loop-contracts.md). Layer-local architecture notes live under [../layers/architecture](../layers/architecture).
