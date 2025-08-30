import json

# ---- Config ----
INPUT_FILE = "single_50_20.json"
OUTPUT_PARETO = "pareto_front.json"
OUTPUT_BEST = "best_individual.json"

# Weights (positive = maximize, negative = minimize)
WEIGHTS = (
    6,   # Average Force
    3,   # Force per watt
    -4,  # Ripple Force
    -2,  # Inductance
    -1,  # Resistance
    -4,  # Time Constant
)

# ---- Helpers ----
def extract_fitness(ind):
    f = ind["fitness"]
    return (
        f["Average Force (N)"],
        f["Force Per Watt (N/W)"],
        f["Peak-to-Peak Ripple (N)"],
        f["Inductance (H)"],
        f["Resistance (Ohms)"],
        f["Time Constant (S)"],
    )

def score(ind):
    return sum(w * v for w, v in zip(WEIGHTS, extract_fitness(ind)))

def dominates(a, b):
    a_vals = [w * f for w, f in zip(WEIGHTS, a)]
    b_vals = [w * f for w, f in zip(WEIGHTS, b)]
    return all(x >= y for x, y in zip(a_vals, b_vals)) and any(x > y for x, y in zip(a_vals, b_vals))

def pareto_front(individuals):
    front = []
    for i, ind in enumerate(individuals):
        ind_vals = extract_fitness(ind)
        if not any(dominates(extract_fitness(other), ind_vals) for j, other in enumerate(individuals) if j != i):
            front.append(ind)
    return front

# ---- Main ----
def main():
    with open(INPUT_FILE, "r") as f:
        data = json.load(f)

    # Flatten out all individuals across generations/motors
    individuals = []
    for motor in data:
        for gen in motor["generations"]:
            for ind in gen["individuals"]:
                if ind["status"] == "completed":
                    # filter out junk like -1e6, 1e6
                    if all(abs(v) < 1e5 for v in extract_fitness(ind)):
                        individuals.append(ind)

    print(f"Loaded {len(individuals)} valid individuals")

    # Compute Pareto front
    pareto = pareto_front(individuals)
    print(f"Pareto front size: {len(pareto)}")

    # Best individual (scalarized)
    best = max(individuals, key=score)
    print("Best score:", score(best))

    # Save results
    with open(OUTPUT_PARETO, "w") as f:
        json.dump(pareto, f, indent=2)
    with open(OUTPUT_BEST, "w") as f:
        json.dump(best, f, indent=2)

    print(f"Results saved: {OUTPUT_PARETO}, {OUTPUT_BEST}")

if __name__ == "__main__":
    main()
