# Procedural Architecture Engine (PAE)

Blender add-on that **deterministically** generates walkable buildings for Blender and
Unreal Engine 5.8. The AI describes architecture; deterministic code produces geometry.

## Spec

- Design: [`Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md`](Docs/PROCEDURAL_ARCHITECTURE_ENGINE.md)
- Swarm kickoff: [`Docs/PAE_SWARM_PROMPT.md`](Docs/PAE_SWARM_PROMPT.md)
- Live board: [`AGENT_SYNC.md`](AGENT_SYNC.md)

## Non-negotiables

1. Specs are declarative and in **bays**, never metres / coordinates from an LLM.
2. All dimensions come from `pae/contract.py`.
3. Every stage returns `(artifact, report)` with `report.ok` and coordinate-bearing failures.
4. Never trust a declared asset size — **measure the mesh**.
5. Geometry is only created in `assemble.py` (+ the parametric primitive library it calls).
6. A check that cannot fail is not a check.

## Milestone gate (M1)

Nothing merges to `main` until the **box house** runs end-to-end and the validator passes:
one storey, 4 × 3 bays, one door, two windows, flat roof, ground slab.

## Layout

```
pae/
  contract.py          # MODULE_CM, STOREY_CM, offset rules
  spec.py              # BuildingSpec
  solver.py            # spec -> massing
  plan.py              # massing -> floor plan
  assemble.py          # plan -> placements (geometry owner)
  validate.py          # build first
  decorate.py
  primitives/          # parametric kit pieces
  assets/              # db, import, sockets, fit
  export/              # blender, fbx, manifest
  comfy/               # decorative asset pipeline
  addon/               # Blender UI
  styles/*.json
  tests/
```

## Dev

```bash
python -m pytest pae/tests -q
```

Blender 4.x / 5.x Python is the runtime for mesh ops; pure logic modules are pytest-able
without Blender when kept free of `bpy` imports.
