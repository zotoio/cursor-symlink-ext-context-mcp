# Roadmap and design options

## Outcome

Evolve the current extension prototype into a dependable basis for native Cursor
plugin adoption without losing the properties it currently makes explicit:
versioned context packs, opt-in installation, machine-local lifecycle state, and
semantic search over installed content.

This is a planning document, not a commitment to a specific native-plugin API.
Each migration phase should be validated against the Cursor capabilities available
at implementation time.

## Guiding decisions

- Preserve the distinction between **available** extensions and **installed**
  extensions unless native plugins provide an equivalent opt-in mechanism.
- Keep context packs versioned with the primitives that rely on them.
- Make upgrades explicit and reversible.
- Treat the context service as a separate deployable concern from primitive
  packaging.
- Maintain a working compatibility path while native-plugin behavior is
  validated.

## Phased roadmap

### Phase 0 — Establish the prototype baseline

**Goal:** make current lifecycle behavior and service boundaries observable before
changing packaging.

Deliverables:

- Architecture documentation and an operator runbook for setup, recovery, and
  safe inspection of audit logs.
- A documented compatibility matrix: supported Python, Docker Compose, Cursor
  CLI, and validated Cursor versions.
- Tests for lifecycle idempotency, failure recovery, catalog validation, and
  Context MCP search/read/status behavior.
- A repeatable smoke test covering install, context readiness, search of an
  installed extension, update, and uninstall.

Exit criteria:

- A new contributor can reproduce the installed layout and understand which
  state is committed versus local.
- The normal verification suite and a documented live-service smoke test pass
  from a clean machine profile.

### Phase 1 — Harden extension packaging

**Goal:** make payloads independently verifiable and ready for alternate
installation backends.

Deliverables:

- Define and validate a payload manifest containing extension identity,
  compatible host/plugin versions, primitive inventory, context-pack version,
  and optional integrity metadata.
- Add a preflight command that reports catalog/payload mismatches without
  mutating machine state.
- Define upgrade and rollback semantics, including how the installed registry
  records the payload version applied to a machine.
- Publish authoring templates and CI checks for required payload structure.

Key design question: should the catalog remain a hand-maintained JSON file, or
should it be generated from manifests stored in each payload? See
[Design approach A](#approach-a-catalog-led-hybrid) and
[Design approach B](#approach-b-manifest-led-packages).

### Phase 2 — Improve context service operations

**Goal:** make indexing behavior predictable, observable, and safe at larger
context volumes.

Deliverables:

- Define index schema versioning and a safe rebuild/migration procedure.
- Add metrics or structured status fields for last successful scan, document
  errors, model-load duration, and index freshness.
- Establish retention/redaction rules for audit logs and document their privacy
  impact.
- Benchmark search quality, cold-start time, incremental indexing, and memory
  use against representative context packs.
- Define a testable reindex contract for payload installation, update,
  uninstallation, and direct file changes.

Exit criteria:

- Operators can distinguish an unhealthy container, an index failure, and a
  stale-but-serving index.
- A documented recovery flow can rebuild the index without deleting installed
  extensions.

### Phase 3 — Evaluate native Cursor plugin integration

**Goal:** validate the smallest useful migration slice before replacing the
current system.

Pilot scope:

1. Select one low-risk extension with a representative combination of
   primitives and context.
2. Package its supported primitives using the current native Cursor plugin
   mechanism.
3. Retain its existing context pack and expose it to the Context MCP through a
   compatibility adapter or retained installed layout.
4. Measure installation experience, discoverability, upgrade behavior, hook
   behavior, and context-search parity.

Decision gates:

- Can native plugins preserve explicit opt-in and machine-local installed state?
- Can plugin metadata provide a stable identity and version for a companion
  context pack?
- Can hooks, commands, agents, rules, and skills all be expressed or
  deliberately replaced?
- Can a user roll back safely if a plugin or context-pack update fails?

### Phase 4 — Migrate or retain the hybrid model

**Goal:** choose a sustainable long-term ownership boundary.

Possible outcomes:

- Migrate all compatible primitives to native plugins and retain a small,
  version-aware context-pack installer.
- Retain the current extension lifecycle for context-bearing bundles while
  using native plugins only for primitives.
- Keep the prototype model where native plugin behavior cannot satisfy critical
  lifecycle or context requirements.

Do not declare the migration complete until old and new paths have equivalent
operator documentation, lifecycle tests, and a tested rollback plan.

## Design approaches

### Approach A — Catalog-led hybrid

Continue using a repository-level catalog as the authoritative list of available
extensions. Native plugins package Cursor primitives where possible, while this
project still installs and indexes companion context packs.

```text
catalog entry
 ├── native-plugin artifact/reference
 ├── context-pack payload/reference
 └── compatibility and version metadata
          │
          ├── Cursor plugin installation
          └── context-pack lifecycle + MCP indexing
```

**Advantages**

- Closest to the current model and least disruptive.
- Keeps one reviewable place for availability and cross-extension policy.
- Preserves explicit context-pack installation and existing index behavior.

**Costs and risks**

- Two installation paths can drift.
- Version compatibility between plugin and context pack needs explicit checks.
- Users may find the distinction between plugin installation and context
  activation confusing.

**Best fit:** incremental migration while native-plugin packaging or lifecycle
support is still evolving.

### Approach B — Manifest-led packages

Make each extension self-describing through a manifest in its payload. A small
repository index is generated from those manifests for discovery, and an
installer resolves each extension's primitives and context as one versioned unit.

```text
extension package
 ├── manifest: identity, version, dependencies, compatibility
 ├── plugin primitive artifact or source
 └── CONTEXT pack
```

**Advantages**

- Strong co-versioning of the plugin and context pack.
- Easier to distribute, validate, and test a package independently.
- Supports future registries or signed artifacts without redesigning the
  extension boundary.

**Costs and risks**

- Requires manifest schema, validation, migration from the current catalog, and
  conflict-resolution rules.
- Generated indexes introduce another build artifact and review workflow.
- Cross-extension policy becomes less centralized unless a registry layer is
  retained.

**Best fit:** a future ecosystem with independently authored or remotely
distributed extensions.

### Approach C — Native-plugin-first with external context registry

Treat native Cursor plugins as the sole primitive package and manage context
packs in an independent registry/service. Plugin metadata identifies the desired
context-pack version; the context service resolves and indexes it.

```text
native plugin metadata ──> context registry ──> mounted/downloaded context pack
                                              └── semantic index
```

**Advantages**

- Aligns primitive installation entirely with Cursor's native model.
- Context distribution can evolve independently, including remote and
  organization-managed packs.
- Reduces repository-specific symlink behavior.

**Costs and risks**

- Requires authentication, integrity, caching, availability, and authorization
  design for the registry.
- A context pack can become unavailable independently of an installed plugin.
- It is a larger operational step than the current loopback-only service.

**Best fit:** centrally managed or multi-machine deployments that need remote
distribution and governance.

### Approach D — Keep a unified extension bundle

Retain this project's installation model and view native plugins only as an
optional export target for primitives that have a direct equivalent.

**Advantages**

- One lifecycle operation installs the context and all supported primitives.
- No uncertainty about plugin-to-context identity or compatibility.
- Existing symlink and registry semantics remain stable.

**Costs and risks**

- The project continues to own integration behavior that native plugins might
  otherwise supply.
- Some native Cursor capabilities may remain unavailable or duplicated.
- The long-term maintenance burden remains local.

**Best fit:** teams whose central requirement is tightly coupled, versioned
context rather than adoption of a specific native packaging mechanism.

## Decision framework

Score each approach against a pilot using the following criteria:

| Criterion | Evidence to collect |
| --- | --- |
| Lifecycle parity | Explicit install, update, uninstall, and rollback outcomes. |
| Context parity | Search results are limited to intended installed packs and refresh correctly. |
| Version integrity | A plugin and its context pack have an unambiguous compatible version pair. |
| Operator experience | Setup, diagnosis, recovery, and updates are understandable without editing state files. |
| Security | Access control, log exposure, artifact integrity, and remote-service posture are documented. |
| Portability | Behavior works across fresh clones and multiple repositories on one machine. |
| Maintenance cost | New extension authoring, testing, releases, and support overhead are measurable. |

Choose the approach only after a pilot records this evidence. If a native
capability is unavailable or behaves differently from the prototype, document
the gap rather than compensating through undocumented filesystem changes.

## Near-term priority

The highest-value next action is Phase 1: introduce a small, validated
extension manifest and a non-mutating preflight check. It improves packaging
integrity immediately and provides the metadata needed to compare the hybrid,
manifest-led, and native-plugin-first approaches without prematurely committing
to a migration.
