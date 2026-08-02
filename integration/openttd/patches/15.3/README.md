# OpenTTD 15.3 V1 patch series

This directory owns the ordered source-integration delta applied to OpenTTD commit
`14ec60f248547d4d062a1160f0fc26d742319888` under ADR 0009.

`series` lists one patch filename per line. Blank lines and lines beginning with
`#` are ignored. Patch names are unique basenames ending in `.patch`; traversal,
implicit globbing, unlisted patches, reordered bytes, offset application, and
working directly in `openttd-upstream` are forbidden.

Patch `0001` is the accepted GCC 13 portability correction from M01 and is
immutable. The root `series` and `openttd-source-profile.json` preserve that
accepted source identity.

M02 deltas are isolated under `m02/` and are composed after the accepted M01
source preparation by the M02 feasibility runner. This keeps the M01 evidence
auditable while retaining one explicit order for every later delta. M03, M04,
and M05 deltas are similarly isolated in their milestone directories and apply
only after the preceding accepted result tree. They freeze the synchronized
bridge, versioned observation, and explicit action/mask contracts respectively;
each directory carries its own ordered series, exact hashes, composition tests,
and gate evidence. The normal-game neural controller remains owned by M11.
