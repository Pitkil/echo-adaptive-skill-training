# ECHO micro-detector inference package

## Contents

- `wavlm-base-plus/`: offline `microsoft/wavlm-base-plus` feature extractor.
- `behavior_prototypes.pt`: three frozen prototype vectors for hesitation, guessing, and thinking pause.
- No audio, learner identity, training set, generated embedding, optimizer state, or runtime FAISS index is included.

## Versions and provenance

- WavLM configuration revision: `4c66d4806a428f2e922ccfa1a962776e232d487b`.
- Safetensors conversion revision: `98fd61b9c652129c839c0a25a05987d8f59256a4`.
- Prototype source repository: `APolaris1217/SpeechProject`.
- Prototype source commit: `0a460502d99da04f32c63c2fa2374d18c1bcbdac`.
- ECHO detector version: `echo-wavlm-prototype-v2`.
- Default similarity threshold: `0.51`.

The service loads this directory with Transformers `local_files_only=True` and enables
`HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE`. FAISS builds an in-memory inner-product index from
the three prototype vectors at inference time; there is no persistent index artifact to ship.

## License and data boundary

WavLM is redistributed with the upstream license in `LICENSE-WAVLM.txt` and attribution to
Microsoft's WavLM/UniSpeech project. The ECHO prototype vectors are a team-owned competition
artifact. They may be shared only within the private project and the competition submission until
the team confirms a separate public-release license. Training and evaluation recordings are not
included and remain subject to the authorization boundary documented in
`docs/member-b/micro-data-authorization.md`.

## Limitations

This is an auxiliary behavioral-signal prototype, not a professional answer grader or a medical,
psychological, or identity-inference system. It must not directly change MIRT U/A/R. The frozen
evaluation currently has low recall and F1; see `docs/member-b/micro-evaluation-report.md`. Mock
results must never be presented as model results or used for detection metrics.
