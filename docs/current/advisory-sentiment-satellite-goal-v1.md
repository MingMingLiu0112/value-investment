# Advisory and Sentiment Satellite Goal v1

Status: `ACTIVE`

Current stage: `D2_CANONICAL_COMPANY_DECISION_SLICE`

D0 status: `COMPLETE`

D1 status: `INTERFACE_ONLY_NOT_EXPANDED`

D2 status: `READY_TO_START`

Goal ID: `VALUE-INVESTMENT-ADVISORY-AND-SENTIMENT-SATELLITE`

This document defines the current goal envelope and the D0-D6 execution
dependencies. `docs/current-stage-goal.md` selects the current work package and
acceptance gate. `AGENTS.md`, the permanent evidence policy, architecture policy,
and immutable receipts remain higher-priority constraints.

This goal expands, rather than replaces, the historical
`VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE` roadmap. The M2-M7 milestones,
receipts, rejected states, frozen research cases, and human-review facts remain
historical evidence and must not be rewritten or reclassified to make a new
stage pass.

## 1. Target Outcome

The system should progressively become an auditable personal investment
advisory system that can:

1. screen the A-share market in layers;
2. maintain a ResearchCase for every admitted candidate;
3. explain what to buy, why it is being considered, and whether current evidence
   permits action;
4. propose how much to buy, with a target range, maximum weight and risk budget;
5. identify when to reduce, exit, or reopen research;
6. monitor financial statements, announcements, valuation, material events and
   thesis breakers continuously;
7. research a separate value-plus-sentiment swing-trading satellite sleeve;
8. reach bounded assisted use only after out-of-sample validation, Shadow
   observation and user acceptance.

The system emits `Recommendation`, not an executable order.

Permanent boundary:

```text
action = no_order
Recommendation != Order
Research Attractive != Buy Signal
High Dividend Yield != Buy Signal
Margin of Safety != Position Size
Historical Return != Future Return
```

## 2. Two-Sleeve Separation

### Core value sleeve

The core sleeve owns long-term business quality, valuation, thesis continuity,
capital allocation, dividends and portfolio-risk conclusions. Its decisions are
produced only through the evidence, research, valuation, model-validity,
price-bridge and portfolio gates.

### Value-plus-sentiment satellite sleeve

The satellite sleeve is a separate capital and decision boundary. It must:

1. admit a company only after the value gate and risk gate have passed;
2. use sentiment only for timing within a separately bounded sleeve budget;
3. never replace intrinsic value, quality or thesis evidence with sentiment;
4. never mix satellite gains, losses, capacity or position limits with the core
   sleeve;
5. remain unavailable until point-in-time data, walk-forward
   out-of-sample validation, transaction-cost modelling and Shadow evidence have
   passed.

Sentiment must not silently mutate a `ValuationResult`, a core
`DecisionRecommendation`, or a core portfolio allocation.

## 3. Required Domain Contracts

Contracts must be serializable, versioned, bound to evidence references and
created only by deterministic or explicitly reviewed application services.

### ResearchCandidate

```text
symbol
company_type
industry_profile
screening_path
quality_flags
evidence_status
research_priority
```

`research_priority` is a research queue position, not a buy signal.

### DecisionRecommendation

```text
symbol
action: BUY_CANDIDATE | ADD_CANDIDATE | HOLD | TRIM_CANDIDATE | SELL_CANDIDATE | NO_ACTION
confidence
valuation_range
current_price
margin_of_safety
entry_zone
reduce_zone
exit_conditions
thesis
counter_evidence
thesis_breakers
next_events
evidence_refs
model_validity
price_bridge_status
action = no_order
```

`current_price` is a quote observation, never an input to intrinsic value.
`BUY_CANDIDATE` and `ADD_CANDIDATE` are review states, not orders or automatic
portfolio upgrades.

### PortfolioGuidance

```text
target_weight_range
maximum_weight
initial_position
add_plan
trim_plan
risk_budget
liquidity_constraint
sector_concentration
correlation_limit
cash_floor
portfolio_input_status
```

Personalized guidance is impossible without real, user-confirmed IPS,
portfolio, cash, cost basis, liquidity and risk constraints. Until then:

```text
portfolio_input_status = BLOCKED_PRIVATE_INPUT
position_guidance = null
```

### ThesisMonitor

```text
current_thesis
confirmed_developments
counter_evidence
stale_model_events
recalculate_required
decision_invalidated
next_review_date
```

### SentimentSignal

```text
value_gate_passed
sentiment_score
feature_contributions
market_regime
crowding
price_volume_features
event_features
flow_features
source_timestamps
backtest_version
```

### SwingTradePlan

```text
symbol
core_value_evidence
entry_trigger
max_holding_days
position_range
stop_rule
profit_take_rule
time_exit
slippage_model
liquidity_limit
failure_conditions
separate_sleeve = true
```

## 4. D0-D6 Dependency Graph

The stages below are an execution graph, not permission to bypass an earlier
gate. A stage may prepare contracts in isolation, but it may not publish a
downstream conclusion that its dependencies do not support.

| Stage | Depends on | Primary output | Required boundary |
| --- | --- | --- | --- |
| D0 Baseline and goal reform | none | Stable, auditable baseline and active goal governance | Must not claim completion until Root resolves baseline blockers, passes the required tests and records the commit |
| D1 Screening interfaces and market funnel | D0 | `ResearchCandidate`, universe/profile/screening contracts, `research_priority` | Interface-first only; no buy/position output; must not delay or replace the D2 vertical slice |
| D2 Single-company vertical slice | D0 and the D1 contracts needed by the slice | One complete evidence -> ResearchCase -> FinancialFacts -> gates -> valuation -> current PriceBridge/ModelValidity -> `DecisionRecommendation` chain | This is the first end-to-end product milestone; no synthetic replacement for real evidence or current price |
| D3 Buy/sell and portfolio guidance | D2 for research/valuation; real private inputs for personalization | Candidate review logic, exit rules, `PortfolioGuidance` | Without real IPS/portfolio, return `BLOCKED_PRIVATE_INPUT` and null position guidance |
| D4 Continuous value-investing tracking | D2 and the D3 contracts that apply | `ThesisMonitor`, event/materiality tracking, dependency invalidation and bounded recalculation | Every event needs source, publication time, available-at time and hash; no future-data leakage |
| D5 Value-plus-sentiment satellite | D1-D4 and a passing value gate | `SentimentSignal`, `SwingTradePlan`, backtest and Shadow evidence | Must pass PIT, walk-forward, out-of-sample, fees, slippage and Shadow before any real swing recommendation |
| D6 Shadow and product delivery | D3-D5 as applicable | Product read models, trial, shadow evidence and user acceptance | Production authorization and final investment decisions remain separate user gates |

### D1 and D2 ordering rule

D1 may implement only the minimum interfaces needed to keep the D2 vertical
slice clean and reusable. It must not expand into a full-market research
program, a scoring leaderboard, or a BUY/position generator before D2 has
produced one complete, evidence-bound company. D2 has priority because a
complete vertical slice exposes the real contracts and failure modes; breadth
without a vertical slice is not progress toward the requested outcome.

## 5. Gate Order

Every positive recommendation must preserve this order:

```text
Evidence / PIT
-> Financial and Research Gates
-> Thesis and counter-evidence
-> ValuationResult
-> ModelValidity
-> PriceBridge
-> PortfolioGate
-> DecisionRecommendation
```

The system must fail closed on missing identity, unavailable-at data, financial
facts without provenance, stale or invalid models, unadmitted price bridges,
unknown portfolio constraints, and unresolved thesis breakers. A failed gate
blocks only the affected investment conclusion, not unrelated engineering work.

Numbers shown to the user must come from verified source data or deterministic
calculators. LLMs may interpret text, summarize evidence and propose questions;
they must not be the only source of financial calculations or the authority that
promotes a candidate.

## 6. Sentiment and Swing-Trading Gate

No real swing recommendation may be emitted unless all of the following are
true:

1. the value gate passed and remains current;
2. the affected ResearchCase has point-in-time evidence;
3. the sentiment features are reproducible from timestamped sources;
4. the backtest uses walk-forward and out-of-sample evaluation;
5. suspended trading, limit-up/limit-down, fees, slippage and liquidity capacity
   are modelled;
6. the result reports Sharpe, maximum drawdown, turnover, hit rate, payoff ratio,
   recovery time and failure regimes;
7. a Shadow record exists for the exact rule and data version;
8. the satellite sleeve has a separately authorized budget.

Otherwise the only valid result is a research or refusal state such as
`NO_TRADE`, `NOT_PROVEN`, `INSUFFICIENT_EVIDENCE` or `SHADOW_REQUIRED`.

## 7. SubAgent Governance

Root remains the sole integrator and owner of the Goal state. Root must own:

1. core domain contracts and cross-module schema;
2. integration decisions and conflict resolution;
3. final full regression and Core Gate;
4. commit, push and formal stage-status updates;
5. checkpoint and user-gate interpretation.

At most two or three bounded SubAgents may run concurrently. Preferred roles:

| Role | Allowed work | Must not do |
| --- | --- | --- |
| Repository / Dependency Agent | Inspect modules, contracts, call chains and dependencies | Change core design |
| Screening & Data Agent | Implement universe, profiles and data adapters | Change valuation or decision thresholds |
| Valuation & Decision Agent | Implement model routing, valuation and decision contracts | Change portfolio-risk policy |
| Portfolio & Risk Agent | Implement ranges, risk budgets, concentration and liquidity constraints | Read or invent real private data |
| Sentiment & Backtest Agent | Implement timestamped features, walk-forward/OOS tests and cost models | Modify the core value model |
| Adversarial Reviewer | Search for future data, PIT, hash, state-promotion, gate-bypass and overfitting failures | Approve a release or weaken a gate |
| Test Engineer | Add boundary, counterexample, recovery and regression tests after Root fixes the contract | Change business admission criteria |

No two writers may modify the same core file concurrently. SubAgents return
evidence and proposed changes; Root performs the integration, adversarial review,
full regression and commit. Parallelism must reduce elapsed time, not create
parallel Goal states or divergent branches.

## 8. D0 Gate

D0 completion is not demonstrated merely because this document exists. D0 required Root to:

1. preserve the current worktree and classify unfinished changes;
2. repair the current full-suite failures without weakening assertions;
3. repair the current workbook pointer/canonical-hash drift and make the opener
   verify the declared current version;
4. preserve M2-M7 receipts and historical evidence;
5. run the required tests and Core Gate;
6. commit and push the green baseline;
7. record the exact commit, test result and remaining external blockers.

D0 completed on code/config baseline `13f5d5d`. The completion evidence is:

```text
FULL_LOCAL_REGRESSION = 3709 passed, 41 skipped
CLEAN_WORKTREE_CORE_SUBSET = 1558 passed, 49 skipped
GITHUB_CORE_RESEARCH_GATES_RUN = 37576547521 / SUCCESS
CANONICAL_WORKBOOK_SHA256 = 5db7f3cd7651edc36505b7f7d87aa8d71550ca2150a999391778c1cbc2d23bf8
```

D0 completion does not mean the product is investment-ready. Real data admission,
strict contemporaneous PIT, private portfolio input, production Shadow and user
acceptance remain separately gated.

```text
D0_STATUS = COMPLETE
D1 = INTERFACE_ONLY_NOT_EXPANDED
D2 = READY_TO_START
INITIAL_ASSISTED_USE = NOT_REACHED
action = no_order
```

## 9. Handoff Rules

Every major node completion report must distinguish:

```text
CODE_IMPLEMENTED
AUTOMATED_TEST_PASSED
REAL_DATA_ADMITTED
USER_ACCEPTED
```

It must also state the current usable capability, what the user still cannot do,
and the single next engineering task. A node is not complete because files were
created or a UI opened; it is complete only when the relevant acceptance evidence
proves the requested behavior.
