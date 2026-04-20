# Version5/back/segmentation/test_pipeline_demo.py
from collections import Counter

from back.segmentation.pipeline_segmentation import run_full_pipeline
from back.scenario.scenario_generator import generate_dialogue_from_segments, save_script


def ask_resources():
    print("Entre tes ressources une par une (fichier local ou URL).")
    print("Appuie sur Entrée sur une ligne vide pour terminer.\n")

    resources = []

    while True:
        value = input("Ressource : ").strip()
        if not value:
            break
        resources.append(value)

    return resources


resources = ask_resources()

segments = run_full_pipeline(resources)

print(f"\nNombre total de segments : {len(segments)}\n")

counter = Counter(seg.get("source", "unknown_source") for seg in segments)
print("Répartition par source :")
for source, count in counter.items():
    print(f"- {source}: {count} segment(s)")

print()

for seg in segments:
    print("=" * 100)
    print(f"Segment ID : {seg.get('segment_id')}")
    print(f"Source     : {seg.get('source')}")
    print(f"Type       : {seg.get('source_type')}")
    print(f"Titre      : {seg.get('title')}")
    print(f"Longueur   : {seg.get('length')}")
    print("-" * 100)
    print(seg.get("text", ""))
    print()

print("\n" + "#" * 100)
print("SCÉNARISATION EN COURS...")
print("#" * 100 + "\n")

script = generate_dialogue_from_segments(
    segments=segments,
    podcast_duration="Court (1-3 min)",
    participants=["Voix_01", "Voix_02"]
)
print(script)

save_script(script, "podcast_script.txt")

print("\nScript sauvegardé dans podcast_script.txt")