# Repository publish staging (ADR-042)

Enable `actor_mesh.distro_publish` / `KERROS_ACTOR_MESH_DISTRO_PUBLISH=1`
to stage Fake apt/yum indexes here. Soft `reprepro` / `createrepo` only
when `allow_publish`; remote mirrors require `allow_remote` + contract wiring.
