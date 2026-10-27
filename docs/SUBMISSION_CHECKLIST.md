# Submission checklist — Open Agent Hackathon 2026

Submit on **HackOS** before **27 October 2026, 23:45 UTC** (hard deadline). Requirements are from the organizer Submission Requirements and Disqualification Checklist; see `docs/INTEGRATIONS.md` for sources.

## Components

| Item | Status | Where |
|---|---|---|
| Demo video, 1–4 min | ✅ Draft recorded from the real app: 3:00, 1440×900 H.264, caption narration, no voice | `docs/demo/payproof-demo.mp4`. Upload it (unlisted YouTube or Drive). Re-record if integrations become live |
| Slide deck covering the 8 points | ✅ 14 slides: problem and users, solution, workflow, stack, Zetaris/Meterless use, uniqueness, product visuals, future | `docs/deck.html`, `docs/deck.pdf` |
| Public GitHub repo with README (setup, usage, dependencies) | ✅ Public. The only branch is `claude/funny-fermi-lw7q93` | Consider making it the default branch or merging to `main` |
| Sponsor technology explanation | ✅ Drafted | `docs/INTEGRATIONS.md`, `metadata.json` |
| Sample inputs and outputs (≥3) and logs | ✅ | `samples/`, `logs/` (generated at runtime) |
| `.env.example` with placeholders, `SAMPLE_MODE` | ✅ | `.env.example` |

## Hard requirements — open risks (ranked)

1. **Cursor (disqualification checklist).** "The project must be developed in Cursor." This codebase was produced in a Claude Code session. The team must do its remaining development in Cursor and describe that use truthfully in the form. *Highest risk, and not something code can fix.*
2. **Zetaris integration not exercised live.** The adapter follows the documented REST route but has never talked to a Zetaris instance. To close it, start Zetaris, run `scripts/export_zetaris_csv.py` and `docs/zetaris/register.sql`, set `ZETARIS_*`, then run `python3 run.py --check-integrations` until Zetaris reads LIVE. Then re-record the last video beat.
3. **Nemotron not called live.** Set `NVIDIA_API_KEY`, check the model id with `--check-integrations`, and re-run the benchmark. Not a hard requirement: NVIDIA is "wherever it contributes".
4. **Meterless.** Integrated and running in-process (World Model engine). The official TypeScript conformance runner was not run; a one-to-one Python port of its checks passes 8/8.

## Form fields

- **Track:** The Agent That Can Explain Why.
- **Pre-existing components:** none. All code and synthetic data were created on 27 Oct 2026, inside the build window.
- **Roster:** confirm before creating the first submission, because the team locks.

## Final checks before pressing submit

- [ ] Fresh clone: `python3 run.py`, `python3 -m unittest discover -s tests`, `python3 -m payproof.bench`
- [ ] No keys in repo, video or slides
- [ ] README status table matches `python3 run.py --check-integrations` on the machine you record on
