"""Style-aware AI rewriter — interface sketch only.

This module is intentionally **not implemented**. It exists so the rest of the
pipeline can reference the rewriter contract while the user decides:

1. **Local LLM vs cloud.** MVP.md says "no cloud APIs, no network calls".
   Local options (llama.cpp, Ollama, Apple Foundation Models on macOS) keep
   that promise but stack 1–4 GB of weights on top of the Whisper model.
   Cloud options (OpenAI, Anthropic) lift the quality ceiling significantly
   but break the offline guarantee. The interface below is provider-agnostic
   so this decision can be made later — but it MUST be made before any
   ``Rewriter`` implementation is committed.

2. **User style corpus.** Where does the rewriter learn the user's voice?
   Options under consideration:
     - A small JSON of user-supplied (rough -> polished) example pairs in
       ``~/.config/voice-transcriber/style.json``. Easy, opt-in, transparent.
     - A larger sample of the user's prior writing (sent emails, kept
       transcripts) used as few-shot context. Higher quality but a
       data-collection problem, not a code problem.
     - A LoRA / fine-tune. Out of scope for v1.
   This is a product question, not a coding question — answer it before
   wiring rewriter into the pipeline.

3. **Pipeline placement.** The rewriter slots between ``apply_glossary`` and
   ``normalize_transcript`` in ``voice_transcriber/pipeline.py``. It is
   strictly **opt-in**: glossary correction is deterministic and trustworthy,
   AI rewriting is not, so it must default off and be enabled with a flag
   (``--rewrite`` on the CLI; a config key ``rewrite_enabled`` in
   ``AppConfig``).

4. **Quality bar drift.** Existing tests are string-equality checks. Once a
   rewriter is in the loop, those checks won't survive a model swap. Any
   rewriter implementation MUST ship with a golden-file or LLM-as-judge eval
   harness — not just unit tests.

5. **Tone / intent context.** Email vs Slack vs doc-comment vs commit message
   produce very different rewrites. This maps cleanly onto the existing
   ``domain_hint`` shape in ``ProcessingOptions``: extend it (or add a
   parallel ``intent`` field) rather than inventing a new abstraction.

When the design above is settled, replace ``NotImplementedError`` below with
a real ``Rewriter`` implementation and add the matching ``RewriteOptions``
fields to ``ProcessingOptions``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RewriteOptions:
    """Options that control a single rewrite pass.

    Kept minimal on purpose. We expand this only after the local-vs-cloud
    and style-corpus questions are answered; speculative fields would just
    rot.
    """

    intent: str
    """High-level target style: ``"email"``, ``"slack"``, ``"doc"``,
    ``"commit"``, or ``"none"`` to skip rewriting."""

    style_examples_path: str
    """Path to the user's (rough -> polished) example pairs, or ``""`` to
    skip few-shot conditioning."""

    max_length_factor: float
    """Hard cap on output length as a multiple of the input length. Prevents
    a hallucinating model from turning a one-sentence transcript into a
    paragraph. ``1.5`` is a sensible default; ``0`` disables the check."""
    # end RewriteOptions


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """Result of a rewrite. Always returned, even when rewriting is skipped."""

    rewritten: str
    """The post-rewrite text. Equal to the input when rewriting is disabled
    or the rewriter declined to rewrite."""

    applied: bool
    """``True`` if the rewriter actually changed the text, ``False`` if it
    passed through unchanged (intent == "none", model unavailable, length
    cap hit, etc.)."""

    notes: tuple[str, ...]
    """Optional human-readable notes about what the rewriter did or skipped.
    Surfaced in the CLI's verbose output and the daemon error log."""
    # end RewriteResult


class Rewriter(Protocol):
    """Provider-agnostic rewriter contract.

    Concrete implementations live behind this Protocol so the pipeline
    doesn't need to care whether the rewriter is local (llama.cpp) or
    cloud-backed (OpenAI). The Protocol shape MUST stay tiny: any
    provider-specific config belongs on the implementation, not here.
    """

    def rewrite(self, text: str, options: RewriteOptions) -> RewriteResult:
        """Apply a style rewrite to ``text`` and return the result.

        Implementations MUST:
        - Return the input unchanged when ``options.intent == "none"``.
        - Honour ``options.max_length_factor`` and refuse to inflate output
          beyond it (return the input with ``applied=False`` instead).
        - Never raise on a model/provider failure: log the failure via
          ``voice_transcriber.errors.log_recording_failure("rewriter", exc)``
          and return the input unchanged so the rest of the pipeline still
          ships paste-ready text. Rewriting is opt-in polish, not a
          correctness-critical step.
        """
        ...
        # end rewrite


def build_default_rewriter() -> Rewriter:
    """Factory hook for the (eventual) default rewriter.

    Intentionally raises ``NotImplementedError`` until the design questions
    in this module's docstring are answered. Callers (CLI / daemon) should
    import this lazily so the rest of the app keeps working.
    """
    raise NotImplementedError(
        "Rewriter is not implemented yet — see the docstring of "
        "voice_transcriber.rewriter for the open design questions that "
        "must be answered first.",
    )
    # end build_default_rewriter
