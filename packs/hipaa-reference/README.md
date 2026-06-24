# `hipaa-reference` — reference pack, NOT a compliance control

> ⚠️ **This pack is a REFERENCE example for educational use, not a HIPAA
> compliance control.** It ships a small starting set of PHI patterns
> (MRN, SSN, NPI, partial-DOB) and a reviewer-agent prompt that you can
> fork as a STARTING POINT for your own organization's detection rules.
> The patterns are general-purpose; your real PHI may be shaped differently
> (custom MRN prefixes, internal identifier schemes, mixed alphanumerics).

## What this pack does NOT do

- Make TeamVault HIPAA-compliant. It does not.
- Certify your organization for any regime. It does not.
- Replace organizational HIPAA Security Rule controls. It does not.
- Substitute for a real compliance officer or legal counsel. It does not.
- Constitute legal advice from the TeamVault maintainers. It does not.

## What you MUST do if you fork this for PHI-bearing work

1. **Legal review.** Have your own counsel review this pack's regex set
   against your actual PHI shapes BEFORE relying on it as a defense layer.
   The shipped patterns catch common identifier shapes but were authored
   by software engineers, not a HIPAA compliance attorney.
2. **BAA arrangements.** Execute BAAs with EVERY third party your
   substrate touches: your git host, your embedding-model provider, your
   LLM provider, any external secret-management service, your hosting
   provider. TeamVault does not arrange these for you.
3. **Tune the patterns.** The defaults will miss organization-specific
   identifier shapes. Audit your actual entries and extend
   `scrubbers/phi_patterns.yaml` with patterns for your real data.
4. **Audit periodically.** Run real human review beyond automated pattern
   matching. Regex catches the easy stuff — humans catch the rest.
5. **Maintain organizational controls** outside of TeamVault: access
   controls, workforce training, audit-log retention, breach response,
   periodic risk assessments. TeamVault is one tool, not the whole program.

## What this pack DOES do

- Ships a starting regex set in `scrubbers/phi_patterns.yaml` for the
  most common PHI identifier shapes (MRN, SSN, NPI, partial-DOB, email).
- Wires those patterns into the pack runtime so they run on:
  - Every PR opened against your space repo (via the
    `.github/workflows/teamvault-review.yml` workflow + pack-runtime
    reviewer).
  - Every `/teamvault-publish` call (via the pre-publish scrubber path).
  - Every `/search` result returned under `compliance: true` (via the
    egress scrubber path — see P0.7 in `docs/ROADMAP.md`).
- Provides a reviewer-agent prompt body (`agents/hipaa-reviewer.md`)
  describing what the regex pass conceptually does. v0.1 will spawn this
  as a real LLM reviewer for nuanced cases (e.g., "is this synthetic
  or real?").

## Known gaps in the shipped patterns

- The shipped email regex is broad enough to match SSH-URL forms — that
  false-positive is tracked as a v0.1.5+ pack-tuning item (ClickUp
  GAP `86baj9jqc`). Workaround: use placeholder-host wording in docs.
- Pattern set is biased toward US identifier shapes. International
  identifiers (NHS numbers, EU national IDs, etc.) are not covered out
  of the box.
- No detection of free-text PHI (names, addresses, dates of service
  embedded in prose). The pack only catches structured identifiers.

## Disclaimer

See the repository [LICENSE](../../LICENSE) for the full disclaimer.
The pack is provided AS-IS, without warranty of any kind. The
maintainers and contributors disclaim all liability for PHI leaks via
the shipped patterns. You are responsible for your organization's
compliance posture.
