# Custom scenes backend handoff

## Scope

- Branch: `feat/custom-scenes-backend`
- Base: `80f845f`
- Protocol prerequisite: `94b75bc` (`0.5.0`)
- Validation-handler prerequisite: `620c98b`
- Implementation paths: `apps/hub/api/local_chat.py`, `apps/hub/runtime/local_chat.py`, `apps/hub/storage/local_chat.py`, `apps/hub/storage/local_role_templates.py`, `apps/hub/storage/migrations.py`, `apps/hub/tests/test_custom_scenes.py`

## Delivered behavior

- Migration v5 adds the dedicated `local_role_templates` table without changing migrations 1–4.
- Role-template GET/POST/PUT endpoints persist server IDs, immutable base roles, full name/instructions replacement, version conflicts, and idempotent writes. Empty instructions are valid; names are trimmed and must remain nonempty.
- Custom-scene POST creates `custom_scene_*` IDs. Scene save supports incremental name/description changes while retaining builtin scene role-set constraints.
- Every scene validates one to four unique base roles from analyst/planner/developer/reviewer, including disabled roles, and requires at least one enabled role.
- `readOnly` is derived from the enabled roles' `BuiltinCatalog` filesystem policies. Clients cannot submit it.
- `original_planner` requires the enabled execution order planner, developer, reviewer. Reviewer runtime/model/reasoning settings inherit the planner settings; role permissions remain bound to the base role.
- Template provenance requires both ID and positive version, matching base role, and a source version no newer than the persisted template. Scene role name and instructions are copied values; later template edits do not mutate scenes or frozen run snapshots.
- Runtime profiles use `roleName` for display while task workflow roles and adapter role IDs remain the validated base role. Adapter instructions come from the frozen scene copy.
- Existing run snapshot and Continue comparison remain unchanged, so template-only edits continue successfully while an explicit scene-role change rejects continuation.

## Verification

```powershell
Set-Location E:\OtherPro\HQAgent-Hub-worktrees\custom-scenes-backend\apps\hub
& 'E:\OtherPro\HQAgent-Hub-worktrees\vnext-integration\.venv\Scripts\python.exe' -m pytest tests\test_custom_scenes.py tests\test_local_chat.py tests\test_planner_acceptance.py tests\test_restart_recovery.py tests\test_storage_and_drain.py tests\test_validation_response.py -q
```

Result: `44 passed, 1 warning in 10.85s`. The warning is the existing Starlette `TestClient` deprecation warning.

Coverage includes v4-to-v5 data preservation, restart persistence, template CRUD/null/length/idempotency/conflict cases, custom role validation and ordering, policy-derived read-only state, builtin constraints, template provenance, HTTP validation, real SQLite plus FakeAdapter execution, copied instructions, profile display names, template-update isolation, and Continue configuration checks.
