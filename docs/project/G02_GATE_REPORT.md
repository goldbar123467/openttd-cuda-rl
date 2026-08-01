# G02 deterministic passenger-bus scenario and reset gate report

- Gate: `G02`
- Result: `PASS`
- Date: 2026-08-01
- OpenTTD: 15.3 source commit
  `14ec60f248547d4d062a1160f0fc26d742319888`
- Accepted M02 feasibility tree:
  `eba8f4bd3c37042c184d968d2f038864184e3132`
- M02 scenario/reset result tree:
  `551a99fbd33bd1b0f8c9ec35561deb0e893b81fe`
- Composed source identity:
  `edc76541bfda23c2916fc85d499e6e0d5a5cefaad09f40bf19972c2d3307385e`

## What this pass means

M02 now supplies a frozen eight-template 32 by 32 passenger-bus corpus, pairwise
disjoint training/development/final-evaluation seeds, a controlled native reset,
a complete semantic reset projection, fail-closed forbidden-scope validation,
and a non-learning native bus trajectory. The trajectory uses normal OpenTTD
commands to build two bus stops and one road depot, purchase the MPS Regal Bus,
install a two-stop order list, start service, and observe positive passenger
delivery and income.

This pass does not claim that an RL bridge, observation encoder, action/mask API,
reward implementation, PPO trainer, CUDA learning workload, production ONNX
package, evaluator, or in-game neural agent exists. Those remain downstream of
G02.

## Frozen implementation identity

| Input | SHA-256 or identity |
| --- | --- |
| Scenario contract file | `ad843638b7f1dc9920889444f564b31e13e3653387978b573430878bb5f802e7` |
| Scenario compatibility identity | `45ec1b3beb4d6d50696bf1de75094e1817c6aa7ef8e0d38fc6696999764e5b0f` |
| Scenario corpus file | `fe78f73ed301db1492aa0a82b981cfd0a3e9097e61b017d3a0813493c5ac463a` |
| Seed ledger file | `77ffd43b20d19af45d0ea556646731fe0de9e99cceed8359dccd754d4fff2b2c` |
| Reset oracle configuration | `aa9fdee7c218136803717ba466e2e3e2595d80a9b1fa21da9e89d9880a68ed2e` |
| Native ordered patch | `334edfd7b8eca1b3250a074973071905744e55b669548a293022f4d988fa9425` |
| Native scenario series | `126243b273601afd7ef6e27e9b91915ef396695b10ac531726ef4c98a55ce555` |
| Reset projection schema | `a154293c19ed4b378e6b6dab5c84aa533244d09f842f4f085b52720b19822d9a` |
| Scripted trajectory schema | `3629f785be8fbe398a9ce31c2d40850e0de0b660ec1667f9d6ed968f0e2d9399` |
| Current Ubuntu native executable | `91950be18634050d6b74cdfe08c22aba4c4f806a88c2116fa6400ac06dee2185` |
| OpenGFX 8.0 offline archive | `9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c` |

The native patch applies exactly, without fuzz or offset, after the accepted M02
feasibility tree and produces the result tree and composed identity above. It is
default-gated by `OPTION_RL_ENVIRONMENT`; the new `-Z`, `-Y`, `-R`, and `-T`
options are rejected outside that build mode.

## Reset and trajectory evidence

Two complete offline oracle campaigns are retained at:

```text
/home/thecl/.codex/artifacts/openttd-rl/m02-reset-oracle-20260801-a
/home/thecl/.codex/artifacts/openttd-rl/m02-reset-oracle-20260801-b
```

Every campaign ran all eight templates in two independent clean processes and
one same-process two-reset execution. All reset reports, trajectory reports,
scenario instances, runtime inputs, `commands.json`, and `manifest.json` are
byte-identical between the two campaign roots (`diff -qr` has no output).

| Canonical artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `8baeea1e49b04936f3403fec338392aa0ade7c8b1171a6e8fb15ce758ba869ca` |
| `commands.json` | `fff7e54f5ccd93fcec72698ceffc4c22a1b047356439ffd41633de2c0e9ef5f5` |

The trajectory identities and observed positive terminal evidence are:

| Template | Trajectory SHA-256 | Ticks | Passengers | Income |
| --- | --- | ---: | ---: | ---: |
| `m02-template-01` | `6d4d0f1fb99f03f506248c8a9fec4bc73a5e47b211142cd681f24367076d7541` | 2,727 | 19 | 106 |
| `m02-template-02` | `69d1db9ea51ec1563a625db3bda2f1380ee0b1cdcc451fbe30298d4c63a70825` | 2,784 | 22 | 123 |
| `m02-template-03` | `b736eb812bda0144ce75916c0c4b32c31de75ef7428fce9530dd020b09c630a1` | 2,822 | 27 | 151 |
| `m02-template-04` | `d3d1f99c10b3ebdc654a01be49631a8a17ba1b5c6cb9c66e53c619dc3339f561` | 2,720 | 17 | 95 |
| `m02-template-05` | `69f0a959bf903a7274a229fa4dd97642e5c431e41a66aaf92063c357ef779673` | 3,249 | 27 | 190 |
| `m02-template-06` | `b81293c4042f4841ee05cee3a786ddb86aaf136346f7aaae285a36eccf711c7f` | 3,065 | 9 | 64 |
| `m02-template-07` | `05aac7a4697fbb3f502fa812117af62b9815a0370ece3878eaab98f5c16e5b6f` | 2,993 | 31 | 186 |
| `m02-template-08` | `519719cdbd3ac6191b6babf3ed1212d7980ce686703bfc18fa522c41bd4d8be7` | 3,009 | 31 | 186 |

Every trajectory contains exactly one company, one running passenger bus, two
bus stations, one road depot, and the two declared orders. Rail, tram, airport,
water transport, industry, non-passenger cargo delivery, and additional company
counts remain zero. Every run finishes before the fixed 65,536-tick limit with a
positive balance.

## Quality gates

The current Ubuntu build passes all 96 upstream unit cases (2,193 assertions)
and both native regression tests after the M02 delta. The focused repository M02
suite passes 39 tests, including strict JSON/schema checks, exact patch and tree
identity, every scenario template and split, reset equivalence guards, and
fail-closed mutations of content, pools, transport state, commands, economy,
encoding, and trajectory semantics.

The complete project traceability gate passes: 227 requirements, 19 test-suite
mappings, 19 passing G02 requirements, 10 deferred post-V1 requirements, zero
nonclosed defects, 25 active documents, 26 validated local links, and 125 passing
repository tests. `git diff --check` is the final whitespace closure check. The
pre-existing outer dirty worktree remains intentionally preserved under the
accepted M00 snapshot; G02 does not relabel it as clean or discard user-owned
changes.

## Manual QA

1. Verify the exact OpenGFX archive and three Ubuntu binutils packages in the
   offline cache with `sha256sum`.
2. Read one template's `instance.json`, `clean-1/report.json`, and
   `clean-1/trajectory.json` in either retained campaign.
3. Run both validators on that reset/trajectory pair and require `PASS`.
4. Confirm the reset has zero vehicles/stations/depots/orders and exactly 1,024
   raw tiles with the 124-tile void border.
5. Confirm the trajectory has the eight expected normal command operations, one
   bus, two orders, two stations, one depot, positive passenger delivery, and
   positive income.
6. Compare the two retained campaign roots with `diff -qr`; require no output.
7. Run the focused M02 tests and the complete repository traceability suite.

## Next boundary

Stop at G02. M03 may next define the synchronized source-integrated headless
bridge, but no bridge or learning implementation is part of this gate.
