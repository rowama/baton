**The article offers useful architectural heuristics, but it is not a valid grading method as written.** Its central flaw is treating determinism and inference as opposite ends of one scale. They describe different properties. Following that framing could lead a team to build systems that produce repeatable errors, approve unsupported judgments, and overstate what their controls guarantee.

The useful ideas are decomposing workflows, explicitly controlling consequential actions, and combining rules with estimation. Those ideas survive the critique; the proposed classification logic needs substantial revision.

**1. The foundational distinction is technically incorrect.**

Determinism concerns whether a computation returns the same result under the same complete conditions. Inference concerns deriving conclusions from evidence. A system can do both.

For example, a fixed statistical model can deterministically return the same estimated default probability for the same borrower data. The computation is repeatable; the prediction remains uncertain. Conversely, a randomized scheduling algorithm can produce different schedules without making uncertain judgments about the world.

| Property | Question it actually answers |
|---|---|
| Computational determinism | Will repeating the computation reproduce the output? |
| Inferential uncertainty | How well does available evidence support the conclusion? |
| Correctness | Does the output satisfy the intended requirement? |
| Action authority | What is the system permitted to do with the output? |
| Adaptation | Does the system change its behavior as evidence or conditions change? |

These properties should be assessed separately. Learned models do not necessarily adapt during operation, and inference does not necessarily produce a confidence score.

**Team risk:** A deterministic predictor gets classified as rule-based certainty, or useful predictive methods are rejected because reproducibility is required.

**2. Repeatability does not establish correctness, safety, or an outcome guarantee.**

The definition of deterministic action overreaches when it connects fixed logic to the elimination of residual uncertainty and hard guarantees on outcomes.

A deterministic calculation can use an incorrect formula, outdated policy, inaccurate measurements, or an incomplete specification. It can return the same wrong answer indefinitely.

A guarantee must identify:

- The precise property guaranteed.
- The assumptions under which it holds.
- The system boundary covered.
- The evidence supporting it.

For instance, “the payment amount never exceeds the configured limit” is a potentially enforceable property. “The payment is legitimate” requires evidence that a limit check cannot supply.

NIST treats validity, reliability, accuracy, robustness, and safety as distinct evaluation concerns, requiring evidence under intended conditions of use. Repeatability is not a substitute for that evidence. [NIST AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf)

**Team risk:** Verification budgets shrink because a component has been labeled deterministic, while specification errors and bad inputs remain unexamined.

**3. The proposed discriminators confuse requirements with implementation choices.**

Several factors identify a need for stronger assurance, but do not establish which implementation will satisfy it.

| Article guidance | Gap or counterexample | Practical risk |
|---|---|---|
| High stakes favor determinism | High stakes demand demonstrated performance and controls. A weak rule system may perform worse than a validated predictor. | Choosing a less accurate method for its apparent certainty. |
| Structured inputs favor determinism | Structured measurements can be noisy, incomplete, or predictive rather than conclusive. | Treating a database schema as evidence of truth. |
| Novel inputs favor inference | Novelty can take a model outside the conditions where its performance was established. | Automating the cases with the least supporting evidence. |
| Rapidly evolving policy favors inference | Policy changes often require explicit, versioned rule updates. | Allowing a model to improvise policy. |
| Experts can articulate rules, so use rules | Articulable rules may be inconsistent, incomplete, or poor predictors. | Encoding intuition without validating it. |
| Audit needs favor predefined rules | Reconstructing a decision, explaining it, and proving its acceptability are different requirements. | Producing detailed logs that do not justify the decision. |

Similarly, unstructured input does not automatically require learned inference: constrained document formats may be handled with parsing. Conversely, classification can be an exact lookup or an uncertain prediction.

The claim that outcome accuracy and confidence scores are “often sufficient” needs a specified task and acceptance criteria. Aggregate accuracy can conceal serious errors in particular cases or groups.

**4. A deterministic execution layer does not neutralize an incorrect upstream inference.**

The strategist/referee pattern is useful, but its protection depends on what the referee can independently establish.

Suppose a model extracts the wrong recipient from an invoice. A deterministic validator confirms that:

- The account number is well formed.
- The payment is within limits.
- The requester has payment privileges.

The system can still pay the wrong recipient. Every enforced constraint passed; the essential factual premise was false.

**Model influence on a write persists even when the model does not directly perform the write.** Structured output and schema validation do not establish semantic correctness.

Teams need to distinguish checks of format, policy, authorization, and factual evidence. Some facts require verification against an independent authoritative source; others may remain uncertain and require review or abstention.

There is also a separate execution problem: determinism does not imply idempotency. Repeating a deterministic “debit $100” operation can debit twice. AWS’s guidance treats safe retries through explicit idempotent API contracts, including request identifiers. [AWS Builders’ Library: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)

**Team risk:** Teams assume the deterministic boundary prevents harmful actions while missing wrong recipients, duplicate effects, stale state, and partial completion.

**5. Confidence-threshold gating is underspecified.**

A confidence score is not automatically a reliable probability of correctness. Some models do not provide probabilities; others provide poorly calibrated ones. Calibration requires empirical assessment. Even a calibrated score describes observed frequencies across comparable predictions, not a guarantee for one case. [scikit-learn: Probability calibration](https://scikit-learn.org/stable/modules/calibration.html)

The article leaves unanswered:

- Confidence in which event: a field extraction, a classification, or the whole proposed action?
- How was the score validated, and on which cases?
- What are the relative costs of false acceptance and false rejection?
- How does the threshold affect coverage and review workload?
- What happens with unfamiliar inputs, missing evidence, or conflicting sources?

A model’s self-reported certainty is especially weak evidence unless separately validated.

**Team risk:** Teams select an arbitrary threshold such as 95%, interpret it as a safety guarantee, and automatically accept confidently wrong outputs.

**6. Human review and conservative fallback are treated as solutions without being designed.**

Human review requires staffing, expertise, access to original evidence, decision authority, and sufficient time. Its performance must be measured. A reviewer may otherwise rubber-stamp a plausible output.

Likewise, a “conservative” fallback is not universally safe. Rejecting, delaying, stopping, and continuing can each create different harms. The fallback must be selected for the specific failure scenario.

NIST’s playbook explicitly calls for measuring oversight, overrides, complaints, response times, and accountability rather than merely documenting that humans participate. [NIST AI RMF Playbook: Measure](https://airc.nist.gov/airmf-resources/playbook/measure/)

**Team risk:** Review queues become operational bottlenecks, difficult cases receive superficial review, and fallback behavior produces unmeasured harm.

**7. Local step scoring misses process-level behavior.**

Input → transformation → output is a useful abstraction, but only if relevant state and context are included. Identical visible inputs may appropriately produce different outputs after a policy update, inventory change, authorization change, or new evidence.

The article also leaves step granularity undefined. “Approve an application” contains evidence collection, estimation, policy application, authorization, and execution. Its classification changes depending on how it is decomposed.

Local optimization can miss:

- Error propagation and correlated failures.
- Information lost between steps.
- Feedback loops that affect future inputs.
- Queue capacity and time constraints.
- Failures between validation and execution.

**Team risk:** Every component meets its local criteria while the complete process fails its business objective.

**8. The evidence claims exceed what the article establishes.**

“Tested practical discriminators,” “examined and applied,” and claims about the literature imply an evidence base that is not supplied. The article provides no validation studies, benchmark comparisons, scoring reliability, or documented failure boundaries.

Most importantly, it never supplies the requested grading mechanism: no operational scale, weighting method, conflict resolution, treatment of uncertainty, or validation procedure.

The four-question test is better interpreted as a **prompt to identify control requirements** than a method for choosing technology. A “yes” does not establish deterministic feasibility; four “no” answers do not establish inferential suitability.

**A more defensible design method**

Replace “How deterministic versus inferential should this step be?” with:

> Which implementation and controls deliver the required performance for this step, under specified operating conditions and acceptable residual risk?

For each step, record:

| Assessment | Required output |
|---|---|
| Purpose and boundaries | Intended result, inputs, state, dependencies, and downstream effects. |
| Non-negotiable constraints | Prohibited actions, required authorizations, and explicit acceptance limits. |
| Evidence and uncertainty | Missing information, data quality, rule completeness, and applicability limits. |
| Candidate implementations | Rules, predictive models, optimization, human judgment, hybrids, or process redesign. |
| Comparative validation | Error severity, coverage, latency, cost, review burden, and failure behavior on representative cases. |
| Operating controls | Verification, abstention, safe retries, recovery, monitoring, and accountable ownership. |

Apply hard constraints first. Then compare feasible alternatives using measured benefit, error losses, operating costs, and maintenance costs. Keep severe-risk limits separate from an average score so that convenience cannot compensate for an unacceptable failure mode.

**The highest-priority revision is to separate uncertainty, reproducibility, and authority.** A process may need inference to estimate what is true, deterministic rules to enforce what is permitted, and independent evidence to justify acting. None of those functions supplies the assurance missing from the others.
