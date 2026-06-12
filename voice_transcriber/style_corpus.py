"""Interactive style corpus builder.

Collects writing samples from the user and calls ``style.build_profile_from_samples``
to generate a ``style.json`` profile.

Usage:
    python transcriber.py --learn-style

The CLI prompts for 3–5 samples of the user's actual writing, then persists
the resulting profile to ``~/.config/voice-transcriber/style.json``.
"""

from __future__ import annotations

import sys

from voice_transcriber.style import build_profile_from_samples, save_style_profile


_SAMPLE_PROMPTS: list[str] = [
    "Paste a recent email or message you wrote (or a paragraph that sounds like you):\n",
    "Paste another sample — maybe a quick reply or chat message:\n",
    "One more — a slightly more formal one, like a work email or request:\n",
]


def interactive_learn() -> int:
    """Collect samples interactively and build a style profile."""
    print("=== Style Learning ===")
    print("I need 2–3 samples of your actual writing to learn your style.")
    print("Paste below and press Ctrl+D (or type 'done' on a new line) when finished.\n")

    samples: list[str] = []
    for i, prompt in enumerate(_SAMPLE_PROMPTS, start=1):
        print(f"Sample {i}/{len(_SAMPLE_PROMPTS)}:")
        print(prompt)
        try:
            lines: list[str] = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip().lower() == "done":
                    break
                lines.append(line)
            text = "\n".join(lines).strip()
            if text:
                samples.append(text)
                print(f"  ✓ Sample {i} collected ({len(text)} chars)\n")
        except (KeyboardInterrupt, EOFError):
            print()
            break

    if len(samples) < 2:
        print("Need at least 2 samples to build a reliable profile. Exiting.")
        return 1

    print(f"Building profile from {len(samples)} samples...")
    profile = build_profile_from_samples(samples)
    save_style_profile(profile)

    print(f"\n✓ Style profile saved to ~/.config/voice-transcriber/style.json")
    print(f"\nDetected style:")
    print(f"  Formality:       {profile.formality:.2f} (0=casual, 1=formal)")
    print(f"  Capitalizes 'I': {'yes' if profile.capitalizes_i else 'no'}")
    print(f"  Contractions:    {'yes' if profile.uses_contractions else 'no'}")
    print(f"  Avg sentence:    {profile.avg_sentence_length:.1f} words")
    print(f"  Trailing period: {'yes' if profile.trailing_period else 'no'}")
    print(f"  Greeting style:  {profile.greeting_style}")
    print(f"  Lower fragments: {'yes' if profile.lowercase_fragments else 'no'}")
    print(f"\nFuture transcriptions will automatically match this style.")
    print("Re-run with --learn-style anytime to update.")
    return 0
    # end interactive_learn


if __name__ == "__main__":
    sys.exit(interactive_learn())
