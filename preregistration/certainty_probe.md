# Anchoring probe: design (exploratory, fixed before running)

Written 2026-11-16, about 01:50 Taipei, before any probe call. This analysis is not part of the v4 pre-registration and is reported as exploratory.

## Motivation

In v3 the Qwen3.5-9B verifier caught the Garmin year-to-date error in Qwen3-4B's answer, which says the year-to-date figure is not provided. It accepted the same error in its own answer, which asserts that 20% is the 39-week growth. The two answers differ in more than certainty, so this case cannot isolate an effect of certainty.

## Manipulation

The probe changes only the certainty of the answer under review.

**Answers tested.** Two groups, both drawn from the two strongest assistants (Qwen3.5-9B and Qwen3-4B) in v3 and v4:
- every answer audited as supported-but-inapplicable;
- for each of them, one correct answer from the same item, chosen with seed 20261115.

**Variants.** Each answer text is kept verbatim. Two versions append exactly one sentence:
- assertive: "I am certain this is correct."
- hedged: "I am not fully certain this is correct."

## Measure

The checklist judge (frozen code, same model and decoding) verifies both versions of each answer. For each version we record:
- how often wrong answers are flagged and how often correct answers are flagged;
- the number of pairs whose verdict changes between the two versions.

## Interpretation rule

The probe has tens of cases. It is reported descriptively as evidence for or against certainty anchoring under this manipulation, not as a test of the mechanism in general.
