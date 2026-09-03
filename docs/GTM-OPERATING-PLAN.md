# GTM operating plan

StepStitch is feature-complete enough to test the wedge. The next constraint is not another
adapter or framework package; it is whether a regulated engineering team can reach a useful
reproduction quickly and trust the evidence enough to keep using it.

## Six-week objective

Recruit three design partners with a recurring, user-reported bug workflow. At least one should
operate in financial services or another regulated environment. Run the same onboarding and
measurement process with each partner before changing the product surface.

## One funnel, defined in product terms

| Stage | Definition | Primary measure |
|---|---|---|
| Proof viewed | Visitor opens the red-to-green demo | `hero_demo`, `nav_demo`, and demo completion |
| Install started | Team opens self-host or quickstart | `hero_self_host` and quickstart visits |
| First trace | A scrubbed trace is accepted by the service | Time from install start to accepted trace |
| Repro ready | The trace produces a runnable Playwright test | Ready rate and time from trace to repro |
| Intended red | The generated test fails for the reported defect | Intended-red rate and named setup blockers |
| Confirmed fixed | The same frozen test passes on the fix | Confirmed-fixed rate and time from report to proof |

Do not substitute page views, repository stars, or raw trace volume for these measures. The
product succeeds when a report becomes trustworthy regression coverage.

## Weekly operating loop

1. Watch one partner complete onboarding without intervention.
2. Record the first point where documentation, configuration, or product state becomes unclear.
3. Classify the blocker as acquisition, setup, capture, replayability, execution, or trust.
4. Fix the highest-frequency blocker and add a regression check when it is an engineering defect.
5. Publish the before-and-after funnel numbers and the exact product change.

## Decision rules

- Keep the feature surface frozen until three partners complete a first trace.
- Add a framework package only when a design partner is blocked on that framework.
- Add an integration only when it shortens an observed path to first intended-red or confirmed-fixed.
- Treat a missing prerequisite as product friction even when the prerequisite is external.
- Never call a draft sent, a generated test reproduced, or a fix confirmed without measured evidence.

## Exit criteria

The wedge is validated when all three design partners reach a first repro, two reach intended-red,
and one reaches confirmed-fixed on a real defect. If the same stage blocks two partners, improve
that stage before recruiting more. If no partner reaches intended-red, revisit capture and fixture
setup before expanding distribution.
