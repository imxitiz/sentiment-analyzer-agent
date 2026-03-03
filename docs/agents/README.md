# Agents Documentation

This folder tracks the implemented and planned behavior of each pipeline agent.

## Current docs

- [1_orchestrator.md](./1_orchestrator.md): intake, orchestration flow, run lifecycle, DB bootstrap.
- [2_1_planner.md](./2_1_planner.md): planning behavior, web-grounded context, persistence schema, fallback behavior.

## Documentation rule

For each new agent added to the project:

1. Create a new file in this folder.
2. Document scope, inputs/outputs, tools, failure handling, and checkpoint strategy.
3. Document what is implemented now vs what is planned next.
4. Update this README index.

This keeps the multi-agent architecture readable as the number of agents grows.
