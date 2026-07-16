# Evaluating Sindie

Sindie's first evaluation system uses [Inspect AI](https://inspect.aisi.org.uk/) for live model runs and a small framework-neutral Python core for prompt extraction, JSON Schema validation, semantic validation, and host-owned score aggregation.

This split is deliberate:

- `PROMPT.md` remains the only prompt and output-schema source of truth.
- Inspect handles model providers, image transport, repeated runs, concurrency, logs, and the local result viewer.
- Sindie validates every response locally with the complete Draft 2020-12 schema and additional cross-reference checks.
- `pytest` tests the deterministic parts without API calls or model variance.

## Why this setup

Inspect is Python-first, local, open source, and supports image inputs, OpenRouter, direct model providers, and generic OpenAI-compatible endpoints. It also provides datasets, custom scorers, repeated epochs, run logs, and a visual viewer without requiring a hosted evaluation service.

The alternatives are less suitable for this first version:

- OpenAI's hosted Evals platform is [deprecated](https://developers.openai.com/api/docs/guides/evals) and scheduled to shut down on November 30, 2026. It should not become a new repository dependency.
- Vercel's [AI SDK](https://vercel.com/docs/ai-sdk) is a TypeScript toolkit. Vercel's documented [Python path](https://vercel.com/docs/ai-gateway/sdks-and-apis/python) uses the regular OpenAI or Anthropic Python SDK against AI Gateway.
- Pydantic AI and Pydantic Evals are credible Python alternatives, but adopting both would add an agent and data-model abstraction before Sindie's own evaluation semantics have stabilized.
- LiteLLM would add a second provider-routing layer on top of OpenRouter. That makes model and backend provenance harder to interpret during calibration.

Inspect's structured-output documentation does not currently list its OpenRouter provider among the supported structured-output adapters. The task therefore supplies Sindie's authoritative schema as host data in the request and always validates the returned JSON locally. Provider-side schema enforcement can be added later as an optional, measured transport optimization; it must never replace local validation.

The canonical eval does not repair malformed model output or ask the model to try again after a protocol failure. That first-pass failure is part of what the eval measures. Inspect's configured retries cover transport failures; any future product-side repair pass must be logged and scored separately from first-pass validity.

## API key

Create a repository-root `.env` file:

```bash
cp .env.example .env
```

Put the testing key only in `.env`:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-your-key-here
INSPECT_EVAL_MODEL=openrouter/openai/gpt-4o-mini
```

`.env` and `.runs/` are ignored by Git. Never put a real key in `.env.example`, a case file, a shell command committed to the repository, or an Inspect log.

The example uses [GPT-4o-mini](https://openrouter.ai/openai/gpt-4o-mini) as a cheap multimodal transport baseline, not as an endorsed design judge. Replace it with the vision model under study before quality calibration. Choose an explicit model rather than a moving alias or automatic router: model identity is part of the evaluation provenance. Keeping the model out of source code makes changes visible per run rather than silently changing the benchmark.

## Install and verify

The project uses `uv` for a reproducible Python environment:

```bash
uv sync
uv run sindie-eval validate-prompt
uv run sindie-eval validate-case evals/cases
uv run pytest
```

These commands do not call an external model or consume API credit; the test suite uses Inspect's deterministic local mock provider for its end-to-end runner check.

This is intentionally repository-local tooling. `uv sync` installs the package in editable form so every run reads the exact checked-out `PROMPT.md`, task, case manifests, and images. A built wheel or standalone `pip install` is not a supported distribution: if Sindie is packaged later, that package must carry and verify one immutable prompt-and-case snapshot rather than silently searching a caller's filesystem.

## Run the smoke evaluation

After setting the key and model in `.env`:

```bash
uv run inspect eval evals/sindie.py -T cases=evals/cases/smoke
uv run inspect view
```

The included smoke poster tests the complete transport and protocol. Its expected label checks only that a fully specified case returns a `ready` review. It is not a design-quality benchmark.

For repeated-run variance:

```bash
uv run inspect eval evals/sindie.py -T cases=evals/cases/smoke --epochs 3
```

To override the `.env` model for one run:

```bash
uv run inspect eval evals/sindie.py --model openrouter/provider/another-vision-model
```

Inspect writes the local logs under `.runs/inspect`. By default, those logs can contain the submitted images, full prompt, response, and metadata. Treat the directory as private evaluation data.

## Other providers

The Sindie task does not import OpenRouter-specific code.

Direct OpenAI:

```dotenv
OPENAI_API_KEY=...
INSPECT_EVAL_MODEL=openai/model-name
```

Any OpenAI-compatible endpoint:

```dotenv
ACME_API_KEY=...
ACME_BASE_URL=https://api.example.com/v1
INSPECT_EVAL_MODEL=openai-api/acme/model-name
```

Inspect derives the environment-variable prefix from the provider segment after `openai-api/`.

## Case format

Each case is an inspectable directory:

```text
evals/cases/poster-001/
  case.json
  artifact.png
```

Optional host-only `provenance.json` files may sit beside a case. The loader ignores sibling metadata and serializes only the exact request fields, keeping source and generator identity blinded during review.

For pairwise cases, use attachments `A` and `B`. The attachment map is host-only and never enters the model's runtime payload. Case paths, designer labels, database IDs, and source-model identities should also remain outside the model input.

`case.json` contains:

- a versioned case ID;
- the exact Sindie runtime request;
- an artifact-to-file attachment map;
- minimal expected protocol outcomes, such as an allowed review status or a designer-selected pairwise winner;
- optional expected hard-constraint statuses tied to visible, brief-grounded facts rather than taste scores.

## Run the Grida fixtures

The repository includes four hash-pinned GPT-Image-2 fixtures from Grida Library Home. They cover commercial typography, a repeated graphic system, restrained fine-art composition, and deliberately degraded punk-poster language:

```bash
uv run sindie-eval validate-case evals/cases/grida
uv run inspect eval evals/sindie.py -T cases=evals/cases/grida
```

Their source-page and license records live in [`evals/cases/grida`](evals/cases/grida). Provenance deliberately omits mutable storage URLs because the repository preserves the original bytes and SHA-256 digest. Expected labels cover only review readiness and visually verifiable hard constraints. Criterion ratings and composite quality scores remain observations to calibrate with designers.

Designer annotations should eventually live separately from cases so that labels cannot leak into the evaluator. The first useful calibration set should include conventional and unconventional work, minimal and maximal work, deliberate disorder, incomplete context, genuine hard-constraint failures, and A/B order reversals.

## What is validated

The offline validator checks:

- prompt markers and prompt/schema version agreement;
- the complete Draft 2020-12 output schema;
- unique and artifact-prefixed evidence IDs;
- evidence references resolving to the correct artifact;
- exact criterion-assessment and hard-constraint coverage;
- pairwise criterion coverage, deciding-criterion membership, and A/B evidence ownership;
- immutable supplied contract identity and contents;
- canonical supplied-contract hashes and run provenance hashes for the prompt, schema, request, and images;
- model output leaving host-owned fields null or pending.

The host scorer then computes coverage, the normalized composite, hard-constraint state, aggregation eligibility, and decision eligibility without asking the model to grade its own bookkeeping.
