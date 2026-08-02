# M05 explicit bus actions and masks

Apply `series` after the accepted M04 result tree. The patch adds the fixed
41-index action catalog, deterministic native mask generator, transactional
route replacement, typed action results, fixed 128-tick policy step, and the
oracle-only source projection used by the independent mask implementation.

The action compatibility identity is
`215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536`.
The native implementation is available only with `OPTION_RL_ENVIRONMENT=ON`;
the accepted M02 batch path and M03/M04 patch artifacts remain unchanged.

The policy catalog is:

| Indices | Family |
| --- | --- |
| `0` | wait |
| `1..2` | ordered town endpoint selection |
| `3` | deterministic road connector |
| `4..11` | two stop sites by four orientations |
| `12..15` | depot site by four orientations |
| `16` | fixed-engine passenger bus purchase |
| `17..24` | route assignment by direct vehicle slot |
| `25..32` | set direct vehicle slot running |
| `33..40` | set direct vehicle slot stopped |

The authoritative design is
`config/v1/m05-action-contract.json`. Route assignment is agent-atomic: prior
orders are copied, native delete/insert commands execute in order, and any
failed prefix restores the prior list through logged native rollback commands.
Rollback failure is a fatal integration failure.
