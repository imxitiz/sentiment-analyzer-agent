# Agents Documentation

This folder tracks the implemented and planned behavior of each pipeline agent.

## Current docs

- [1_orchestrator.md](./1_orchestrator.md): intake, orchestration flow, run lifecycle, DB bootstrap.
- [2_1_planner.md](./2_1_planner.md): planning behavior, web-grounded context, persistence schema, fallback behavior.
- [2_2_harvester.md](./2_2_harvester.md): link collection, multi-source fan-out, AsyncLinkWriter, URL normalization, quality scoring, SQLite schema.
- [2_3_scraper.md](./2_3_scraper.md): deep extraction, platform-aware backend routing, ScraperRecoveryAgent sub-agent, MongoDB document schema, dual persistence.

## Documentation rule

For each new agent added to the project:

1. Create a new file in this folder.
2. Document scope, inputs/outputs, tools, failure handling, and checkpoint strategy.
3. Document what is implemented now vs what is planned next.
4. Update this README index.

This keeps the multi-agent architecture readable as the number of agents grows.
