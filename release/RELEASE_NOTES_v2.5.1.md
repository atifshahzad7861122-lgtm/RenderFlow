# RenderFlow v2.5.1 — AI Synchronization, Visual Intelligence & Preview Rendering Fix

RenderFlow v2.5.1 delivers critical algorithmic fixes, enhanced multi-provider AI resilience, real-time WebGL transition shader compositing with exact export parity, and RFC 8032 Ed25519 cryptographic security for workstation video creation.

---

## What's New in v2.5.1

### 1. Audio-to-Visual Semantic Synchronization & Unmatched Scene Rejection (BUG A Fix)
- **Neural Cosine Discrimination:** Upgraded joint 512-dimensional semantic projection engine to mathematically discriminate visual subject matter from distinct narration concepts (e.g. distinguishing cosmic astronomical photography from maritime naval scenes).
- **Safe `NEEDS_REVIEW` Status:** Unmatched or semantically ambiguous scenes are flagged with `NEEDS_REVIEW` rather than receiving arbitrary random images, protecting creator timeline integrity.
- **Archive-Order Invariance:** Upload ordering or file naming does not affect semantic timeline binding.

### 2. Built-in Preview Transition Shader Compositor (BUG B Fix)
- **Real-Time Lookahead Preview:** Real-time WebGL transition shader engine with bidirectional lookahead buffers for outgoing ($A$) and incoming ($B$) scenes.
- **Scrubbing & Seek Parity:** Seamless transition scrubbing across sub-second transition intervals without blank canvas or frozen visual glitches.
- **Pixel-Perfect Export Parity:** Verified visual parity across 9 built-in cinematic transitions against FFmpeg `xfade` exports:
  - Clean Cut, Dissolve, Fade to Black, Fade to White, Soft Wipe, Wipe Left, Wipe Right, Slide Up, Slide Down.

### 3. Resilient Multi-Provider AI Gateway & Offline Fallback
- **Multi-Provider Architecture:** Dynamic provider routing supporting Groq, Google Gemini, OpenAI, Claude, and local deterministic heuristic rules.
- **Zero-Downtime Circuit Breaker:** Automatic graceful degradation to local deterministic rules if remote API endpoints return errors or rate limits.
- **Zero Credential Leakage:** DPAPI-encrypted credential storage with masked, sanitized logging.

### 4. OpenMontage Visual Discovery Integration
- **Automated Stock Asset Discovery:** Integrated OpenMontage asset discovery adapter with license tracking and provenance metadata.
- **Graceful Local Fallback:** Transparent local asset fallback when external stock endpoints are offline.

### 5. In-App Updater & RFC 8032 Ed25519 Cryptographic Security
- **Authentic Digital Signatures:** Release manifests are cryptographically authenticated via RFC 8032 Ed25519 signatures against the RenderFlow Master Public Key.
- **Tamper Rejection:** Any manifest tampering, modified SHA-256 payload hash, or unauthorized public key causes immediate rejection.
- **Strict Downgrade Prevention:** SemVer upgrade enforcement prohibits downgrades while preserving user project databases, profiles, and media.

---

## Known Limitations & QA Evidence
- **Historical King Fixture (BLK-01):** The legacy synthetic placeholder `projects/king/images/image_2.png` is documented and isolated; core semantic discrimination is fully verified against genuine NASA photography in `qa/test_real_semantic_discrimination.py`.
- **Remote Provider Keys (BLK-03):** If a third-party API key expires or is rejected (e.g. HTTP 400), the AI Gateway automatically falls back to Groq or local offline deterministic rules without UI interruption.

---

## Release Artifacts & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.5.1.exe` | 1,500,062,583 | `469c89bb4d887998869d74520f896452f476cd6026151c60cc5b8e945c031775` |
| `update_manifest.json` | 1,665 | Signed Ed25519 (`01b80e2d54d30ac3...`) |

**Master Public Key:** `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`

