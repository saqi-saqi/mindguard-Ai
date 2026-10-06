# LIMITATIONS — Roman Urdu Crisis Detection (read before quoting any number)

1. **Same-AI authorship.** The same AI assistant authored the rules, the benchmark corpus, and the TEST cases. DEV/TEST procedure is hash-frozen and skeleton-split, but authorship is shared — TEST numbers are **procedure-independent, not author-independent**. The reviewer-written TEST-2 (once returned) is the number to trust most.
2. **LLM reviewers.** Per owner decision, sheet review is done by LLMs (Claude/ChatGPT), not humans. Independence is limited; human volunteers upgrade the claim.
3. **Frozen TEST honesty.** The read-only attribute on the holdout folder is a speed bump, not a lock. The real controls are the git tags + `artifacts/test_runs.json` ledger (freeze hash, run count, failing IDs).
4. **Correlated-variant CIs.** Cases expand from skeletons; skeleton-cluster "conservative" bounds are reported, but even they are optimistic versus truly independent samples.
5. **Gates status (TEST run #1, hash baac5f33…):** Tier 1 recall 65.62% (gate ≥99% — FAIL), Tier 2 50.0% (gate ≥97% — FAIL), Tier 3 any-escalation 54.55% (gate ≥90% — FAIL), FPR 0.0% (gate ≤3% — PASS). DEV numbers (95.1/89.9/97.8) are training-adjacent and quoted separately, never as the headline.
6. **Script scope.** Urdu script (Nastaliq/Arabic-script) is out of detection scope; such input gets a gentle generic check-in with resources (never silent). Dialects and Pashto/Punjabi code-switching are not covered.
7. **ML not trained.** The parity kit (21,748 augmented samples, disjoint from all benchmarks) is built and validated; training is owner-launched. Until promotion gates pass, no ML Urdu numbers exist and none may be claimed.
8. **Helplines.** Umang 0311-7786264 verified 2026-10-06 against umang.com.pk + WHO EMRO. All other numbers: unverified, to be confirmed by Saqib before the demo.
9. **Reviewers and content.** Labeling includes crisis/self-harm text; voluntary, 18+, skip/stop anytime. This system is a safety aid, not a clinical tool, and says so in-product.
