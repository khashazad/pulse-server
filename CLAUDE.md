# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout

This is a single git repo (monorepo) containing two subprojects for one product (the **Pulse** app — nutrition + weight + progress photos, single user today). Each was previously its own repo and was merged in with full history preserved under its subdirectory:

- `server/` — FastAPI + Postgres backend. Google-OAuth session/Bearer auth for the app; MCP endpoint at `/mcp` with GitHub-OAuth + service-token paths. Feature surface: food entries, meals, prep containers, custom foods, food memory, weight, progress photos (+ tags), USDA proxy. See its own `CLAUDE.md`.
- `ios/` — SwiftUI iOS 17+ client (four tabs: Intake, Meals, Prep, Measures). Identity is hardcoded to `user_key = "khash"`; base URL + API key entered in Settings. A Login/AuthSession flow is staged for the cutover to session/Bearer — both auth paths live. See its own `CLAUDE.md`.

There is no shared tooling or build at this level — `cd` into the relevant subdirectory before running anything. Each subproject keeps its own `CLAUDE.md`, `README.md`, and `.gitignore`; the root holds only cross-cutting docs (`CLAUDE.md`, `AGENTS.md`) and a root `.gitignore`.

## Cross-cutting contract

The two subprojects are coupled by a JSON-over-HTTP wire format, not a shared schema package. When you change a DTO on one side, you must update the other:

- Server DTOs: `server/src/pulse_server/models/` (Pydantic, `snake_case`).
- iOS DTOs: `ios/Pulse/Models/` (Codable structs, camelCase via explicit `CodingKeys` mapping `snake_case` JSON).
- iOS dates use `JSONDecoder.pulseDefault()` which accepts both `YYYY-MM-DD` and ISO-8601 — keep server outputs within those.
- The iOS client appends `?user_key=khash` to every request and sends `X-API-Key`. Server still accepts that for the legacy single-user path; new endpoints should keep working under the session-cookie/Bearer auth path documented in the server `CLAUDE.md`.

When extending features that span both sides, read both subprojects' `docs/superpowers/specs/` — that's where cross-cutting design decisions live.
