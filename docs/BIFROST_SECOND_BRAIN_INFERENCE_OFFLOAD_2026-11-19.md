# Gufo as the optional Z13 inference worker for Bifröst Second Brain

**Date:** 2026-11-19  
**Status:** Integration proposal and benchmarking checklist, not a service configuration or deployed claim  
**Authority:** [Bifröst November 19 combined expansion](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/SECOND_BRAIN_ADDITIVE_INCREMENTAL_MULTIMODAL_GATEWAY_2026-11-19.md) and [managed folder/source-delta policy](https://github.com/hrabanazviking/bifrost-viewer/blob/docs/second-brain-incremental-multimodal-gateway-2026-11-19/docs/roadmaps/SECOND_BRAIN_MANAGED_RAW_LIBRARY_FOLDERS_2026-11-19.md).

## Mission and machine boundaries

- **G14** owns PostgreSQL/pgvector, Ingest source-instance/path/versions, RawLibrary directory hierarchy, deduplication, source graph generation, token credentials and read-only client gateway.
- **Z13** runs an independently managed Gufo model-serving service, reachable privately through an explicitly authorized Tailscale API connection. Gufo may perform only selected heavy inference jobs. It must not be an alternate master database or raw folder scanner.
- **Image generation and character inference** should retain priority over low-priority background scans and captioning; bounded queue and pause/quiet controls belong to Bifröst.
- **No automatic duplication:** Bifröst sends requests only for newly added or changed content/segments and changed dependencies. A file renamed or moved without changing content has zero Gufo work. A copy of the same file in a second folder has zero extra embedding/caption/model work; Bifröst updates both location/category links locally.
- Result payloads must be schema-validated and include source/asset ID and revision, model identity/version, request ID, status, prompt/schema version, timestamps, output provenance and appropriate uncertainty. Gufo should not autonomously write the G14 database.

## Candidate capabilities documented in this Gufo repository

| Gufo capability | Optional second-brain workload | Verification required |
| --- | --- | --- |
| Vision-language text+image models (e.g. documented Qwen3.8-27B) | Long, detailed visual descriptions, explicit visible traits, objects, clothing, pose, scene, lighting, composition, OCR candidates and structured facts | Model is actually installed/ready, correctness and throughput with reference images |
| EmbeddingGemma 2 shared cross-modal vector API | Search embeddings for text, images, audio and video in its own versioned vector space | Multi-input API shape, context caps and model-specific semantic quality |
| Qwen3-ASR | Speech transcription with segments when supported | Audio format, timestamps, hallucination rate, throughput |
| Gufo OpenAI-compatible LLM interface | Janitor/SillyTavern character responses through G14's authenticated read-only gateway | Actual Janitor stream and message schema compatibility |
| Qwen-Image-2.1 or another supported image generation model | Prompt/reference assembly from living visual lore returned by Bifröst | Model-specific image/reference capabilities, installed weights and licenses |

**Avoid invalid assumptions:** availability in Gufo documentation is not evidence of a model installed on the user's Z13. Not all modalities or models necessarily share a single server process/port; check /ready, actual service configuration and model/API list.

## Required visual-lore analysis output

For every changed image asset, when enabled by owner, produce a comprehensive text record and structured observable traits: subject count, visible appearance, face/hair/eyes where seen, attire by garment and material, shoes and accessories, expression, gaze, action, posture, object relationships, setting, visible symbols/text, background, lighting, composition, perspective, palette, artistic style and uncertainty. Avoid inventing hidden/off-frame traits or asserting a real identity solely from image appearance. Preserve owner-approved canonical design separately from per-image variable outfit/style/setting traits. Each record links back to its original image and location(s); multiple identical copies in different folders share one compatible analysis and retain all folder categories.

## Benchmark before deciding speedup

"Database updates" consist of both AI compute and transactional SQL; the Z13's faster/newer AMD hardware and much larger shared model memory do not automatically accelerate PostgreSQL writes when Postgres remains on G14.

1. Audit live G14 and Z13 runtimes and the exact models installed, including whether identical weights/quantization are available on each. Establish G14-only baseline.
2. Measure parsing, hash checks, unchanged scans, embedding vectors per second, LLM extract/caption tokens per second, caption accuracy/quality, actual graph delta recomputation, DB insert/update/index latency, and private network transfer.
3. Use 10, 100 and 1000 changed text items when feasible, plus representative image/audio/video; separately benchmark a NO-CHANGE scan, a MOVED-ONLY scan and a SAME-CONTENT-COPIED scan.
4. Compare end-to-end wall-clock, median/p95, power/acoustic costs, time to first result, batching, cold model startup and interference with interactive Janitor chat. Record both throughput and accuracy.
5. Offload stages to Gufo only when a demonstrated quality-preserving net benefit exceeds RPC and batching overhead. Do not change existing `nomic-embed-text` text-vector-space identity without a separately approved re-embedding plan.
6. Rate-limit and bound in-flight jobs, fail with observable retryable status, avoid overloading Gufo's shared GPU/UMA, and never fall back to cloud inference without explicit owner consent.
7. Keep the canonical G14 database in place by default. Full DB migration is an independent option requiring verified backups, consistency and measurements, not an inference optimization.

**Acceptance:** A new image generates a correctly attributed exhaustive visual record; a copy/move only updates G14 path categories; an unchanged scan triggers zero Gufo calls; changed text/images reprocess only relevant units; read-only characters retrieve context through G14; source/DB data stays preserved through service restart and network outage.

No code or live server modifications are part of this documentation update.
