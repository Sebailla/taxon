# Skill Registry — taxon

Generated: 2026-08-09
Source: scan of `~/.config/opencode/skills/`
Skip: `sdd-*`, `_shared`, `skill-registry`

## Project Conventions
- `/Users/sebailla/Developer/taxon/AGENTS.md` — (not present yet)

## Applicable Skills (by file/task context)

| Skill                  | Path                                                              | Trigger                                                                |
| ---------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| branch-pr              | `~/.config/opencode/skills/branch-pr/SKILL.md`                    | creating, opening, or preparing PRs for review                         |
| chained-pr             | `~/.config/opencode/skills/chained-pr/SKILL.md`                   | PRs over 400 lines, stacked PRs, review slices                         |
| cognitive-doc-design   | `~/.config/opencode/skills/cognitive-doc-design/SKILL.md`         | writing guides, READMEs, RFCs, onboarding, architecture docs          |
| comment-writer         | `~/.config/opencode/skills/comment-writer/SKILL.md`               | PR feedback, issue replies, reviews, Slack messages, GitHub comments    |
| impeccable             | `~/.config/opencode/skills/impeccable/SKILL.md`                   | UI design, frontend interfaces, design review                          |
| issue-creation         | `~/.config/opencode/skills/issue-creation/SKILL.md`               | creating bug reports, feature requests, or issue approval              |
| issue-root-resolution  | `~/.config/opencode/skills/issue-root-resolution/SKILL.md`        | root audit, resolver issues de raíz, mechanism map                     |
| judgment-day           | `~/.config/opencode/skills/judgment-day/SKILL.md`                 | judgment day, dual review, adversarial review                          |
| rdd-defect-workflow    | `~/.config/opencode/skills/rdd-defect-workflow/SKILL.md`           | RDD, receipt-driven development, review authority, delivery gate       |
| sdd-apply              | `~/.config/opencode/skills/sdd-apply/SKILL.md`                    | SDD apply phase, implement tasks from specs                            |
| sdd-archive            | `~/.config/opencode/skills/sdd-archive/SKILL.md`                  | SDD archive phase, close a change, sync delta specs                    |
| sdd-design             | `~/.config/opencode/skills/sdd-design/SKILL.md`                   | SDD design phase, technical design from proposal                       |
| sdd-explore            | `~/.config/opencode/skills/sdd-explore/SKILL.md`                  | SDD explore phase, investigate before committing to a change            |
| sdd-propose            | `~/.config/opencode/skills/sdd-propose/SKILL.md`                  | SDD propose phase, create change proposal                              |
| sdd-spec               | `~/.config/opencode/skills/sdd-spec/SKILL.md`                     | SDD spec phase, write delta specs with requirements                    |
| sdd-tasks              | `~/.config/opencode/skills/sdd-tasks/SKILL.md`                    | SDD tasks phase, break down specs into implementation tasks            |
| sdd-verify             | `~/.config/opencode/skills/sdd-verify/SKILL.md`                   | SDD verify phase, validate implementation against specs                |
| skill-creator          | `~/.config/opencode/skills/skill-creator/SKILL.md`                | new skills, documenting AI usage patterns                              |
| skill-improver         | `~/.config/opencode/skills/skill-improver/SKILL.md`               | improve skills, audit skills, refactor skills                          |
| systemic-issue-triage  | `~/.config/opencode/skills/systemic-issue-triage/SKILL.md`        | new issue, triage, backlog, root cause, dead-end, blocked user         |
| work-unit-commits      | `~/.config/opencode/skills/work-unit-commits/SKILL.md`            | implementation, commit splitting, chained PRs, work units              |

## Notes

- **impeccable** is the most relevant frontend skill: covers UI design review, accessibility, typography, motion, theming. Match for the React+Tailwind UI phase.
- **sdd-apply** requires `strict_tdd: true` to enforce test-first. Already declared in `openspec/config.yaml`.
- **chained-pr** is required when `sdd-tasks` flags >400 lines or high review risk. Cached `delivery_strategy=ask-on-risk` so orchestrator asks when triggered.
