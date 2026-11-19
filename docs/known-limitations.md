# Known limitations (accepted)

Behaviours we reviewed and chose not to fix. Add an entry when a review finding is accepted, with the reason, so it is not re-raised.

## Dry-run translates items with an unknown Weverse member
- **What:** with no `--post`, an item whose member is missing from `formatter.MEMBER_ZH` is translated with `agy` (up to ~7 min) and only then fails at `make_title`.
- **Why accepted:** with `--post` the hand-post check (`weverse_dup_key`) raises `UnknownMemberError` before translation, so the live job never wastes `agy` time. Dry-run posts nothing.
- **Rejected alternative:** an optional `validate(item)` hook in `pipeline.run`, run on every path. More API surface for a dry-run-only cost.
- **Revisit if:** the live path starts translating before validating the member.
