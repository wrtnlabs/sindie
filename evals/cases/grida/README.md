# Grida Library GPT-Image-2 fixtures

These four static fixtures preserve selected work from [Grida Library Home](https://grida.co/library/home). Their individual asset pages identify Grida as the author, `openai/gpt-image-2` as the generator, and `LicenseRef-GridaLibrary` as the license identifier.

Each directory contains the original WebP artifact, a blinded evaluation case, and host-only provenance. Provenance keeps the durable Grida page URL, published description, license identifier, retrieval date, dimensions, byte size, and SHA-256 digest. It deliberately omits the mutable storage download URL because the artifact itself is preserved here and pinned by hash.

The published descriptions are curatorial metadata, not claimed to be original generation prompts. Each `case.json` therefore labels its intent as a host-supplied evaluation frame derived from the description and visible artifact. Contract IDs are source-neutral, and tests ensure that the Grida name, source model, page URL, license data, provenance, and expected outcomes do not enter the model-visible request.

Expected values assert only review readiness and visually checkable facts. They do not prescribe criterion ratings or taste scores. The set covers commercial typography, a repeated graphic system, restrained fine-art composition, and deliberately degraded punk-poster language.
