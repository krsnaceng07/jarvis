# jarvis-model-catalog-core

Provider/model catalog ids, refs, and catalog shapes, ported from OpenClaw's
`packages/model-catalog-core/`. This is the single owner of provider-id
normalization, `provider/model` ref parsing, catalog row types, context-window
selection, configured-model-ref collection, model-id normalization policies,
and remote-bundle validation.

Core stays plugin-agnostic: providers own their catalogs and auth in
`extensions/`; this package only shapes the shared vocabulary (ids, refs,
rows, policies) that core runtime paths (`model_resolver`, route selection,
thinking policy) consume.
