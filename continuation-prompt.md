# Prompt for the new chat

The run and handoff are complete. Paste the following into the new chat:

```text
/goal Continue the existing OpenTTD C++/CUDA PPO and agentic-economy project at C:\Users\imsa\Documents\OpenTTD\openttd-cuda-rl.

First read AGENTS.md, GOAL.md, docs/DEVELOPMENT.md, handoff.md, and docs/PROGRESS.md from that checkout. The previous chat was intentionally paused after completing its current run so work could continue here. Use the completed results and next-step recommendation in handoff.md; do not restart from the original zero-passenger smoke.

Preserve the existing dirty/untracked implementation, isolated qualified worktrees, model artifacts, failed experiments, and frozen release records. Never read or copy the parent OpenTTD directory's secrets.cfg/private.cfg or alter its ordinary saves and configuration. Do not commit, push, or publish unless I ask. Keep C++/LibTorch as the PPO implementation and enforce the recorded resource limits: at most two native jobs, one CUDA training job, compiler parallelism two, and no silent CPU fallback. Do not spawn subagents unless I authorize them.

Continue toward useful learning in real OpenTTD, reproducible checkpoint/export/visible play, measured CUDA improvements, useful live V2 transport and fair neural-versus-MCP-LLM economic experiments. Start with the highest-priority unresolved learning blocker described in the handoff. Select one concrete hypothesis, register a bounded comparison, implement through existing components, execute it, inspect full game outcomes and baselines, and update docs/PROGRESS.md. Keep training, development selection and held-out data separate; never tune on the closed held-out results. Preserve failed criteria instead of weakening them. Do not repeat completed qualifications without a new change or unresolved concern.

Continue this loop autonomously until the stated acceptance criteria are met, I stop you, or a genuine external prerequisite blocks progress. Give concise progress updates explaining what was learned and what the next experiment will resolve.
```
