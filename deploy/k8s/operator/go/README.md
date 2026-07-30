# KerrOS Go NatsBroker operator (ADR-043)

Foundation stub sources are rendered here when
`supercluster.go_operator` / `KERROS_ACTOR_MESH_GO_OPERATOR=1` and
`allow_write` are enabled. Fake build writes `bin/`; soft `go build` /
`docker build` require explicit gates — not a shipped production binary.
