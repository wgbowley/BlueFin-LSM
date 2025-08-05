"""
Filename: motor_deap_optimization.py
Author: William Bowley
Version: 1.0
Date: 2025-07-17

Description:
    Example of using the motor simulation framework with the DEAP evolutionary optimizer.
    Optimizes coil geometry (height and radius) for force output while considering
    power, voltage, and inductance constraints.
"""

# === Standard libraries ===
import os
import sys
import random
import json
from deap import base, creator, tools, algorithms

# === Add project root to sys.path for framework imports ===
projectRoot = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if projectRoot not in sys.path:
    sys.path.insert(0, projectRoot)

# === Framework imports ===
from blueshark.simulations.rotational_analysis import rotational_analysis
from blueshark.simulations.alignment import phase_alignment
from blueshark.output.selector import OutputSelector
from model.motor import BlueFin

# === Optimization Setup ===
individuals = 20
generations = 20

maxPower = 250
maxInductance = 0.1
maxVoltage = 56
maxCoilHeight = 7.5
maxCoilRadius = 7.5

# === Simulation Configuration ===
numberSamples = 10
motorConfigPath = "sim_and_opt/model/motor.yaml"
requestedOutputs = ["force_lorentz", "phase_power", "phase_voltage", "phase_inductance"]

# === Input Generation ===
def input_generation(lowerBound: float, upperBound: float) -> float:
    """Generates a random float within bounds."""
    return random.uniform(lowerBound, upperBound)

# === Simulation Runner ===
def simulate(radius, height) -> dict:
    """Runs a motor simulation with given coil radius and height."""
    motor = BlueFin(motorConfigPath)
    motor.slot_radius = abs(radius)
    motor.slot_height = abs(height)
    motor.setup()

    selector = OutputSelector(requestedOutputs)
    subjects = {"group": motor.get_moving_group(), "phaseName": motor.phases}
    phaseoffset = phase_alignment(motor, status=False)
    results = rotational_analysis(motor, selector, subjects, numberSamples, phaseoffset, False)
    return results

# === Evaluation Function ===
def evaluateMotor(individual):
    total_force = 0
    total_power = 0
    total_inductance = 0
    samples = 0

    results = simulate(individual[0], individual[1])
    print(f"Evaluating individual: height={individual[0]:.3f}, radius={individual[1]:.3f}")
    print("Simulation first step sample:", results[0])


    for step in results:
        outputs = step.get("outputs")
        if not outputs:
            continue

        # Check voltages if available
        voltages = outputs.get("circuit_voltage")
        if voltages:
            for v in voltages:
                if abs(v) > maxVoltage:
                    print('failed voltage:', v)
                    return (0.0, 0.0, 0.0)

        force_vals = outputs.get("force_lorentz")
        power_vals = outputs.get("phase_power")
        inductance_vals = outputs.get("circuit_inductance")  

        if force_vals is None or power_vals is None:
            continue

        total_force += force_vals[0]
        total_power += sum(power_vals)
        if inductance_vals:
            total_inductance += sum(inductance_vals)

        samples += 1

    if samples == 0:
        print("No valid samples found.")
        return (0.0, 0.0, 0.0)

    avg_force = total_force / samples
    avg_power = total_power / samples
    avg_inductance = total_inductance / samples if total_inductance else 0.0

    print(f"Avg Power: {avg_power}, Avg Force: {avg_force}, Avg Inductance: {avg_inductance}")

    if avg_power >= maxPower or avg_inductance > maxInductance:
        print('failed power or inductance constraints')
        return (0.0, 0.0, 0.0)

    return (avg_power, avg_force, avg_inductance)


# === DEAP Setup ===
creator.create("FitnessMulti", base.Fitness, weights=(1e-9, 5, -1))
creator.create("Individual", list, fitness=creator.FitnessMulti) 

toolbox = base.Toolbox()
toolbox.register("inputHeight", input_generation, 0.35, maxCoilHeight)
toolbox.register("inputRadius", input_generation, 0.35, maxCoilRadius)
toolbox.register("individual", tools.initCycle, creator.Individual, (toolbox.inputHeight, toolbox.inputRadius), n=1)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluateMotor)
toolbox.register("mate", tools.cxBlend, alpha=0.5)
toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=1.0, indpb=0.2)
toolbox.register("select", tools.selTournament, tournsize=3)

# === Main Optimization Loop ===
population = toolbox.population(n=individuals)
crossoverPB = 0.7
mutationPB = 0.5

output_data = []  # To save all results

for generation in range(generations):
    offspring = algorithms.varAnd(population, toolbox, cxpb=crossoverPB, mutpb=mutationPB)
    fits = list(map(toolbox.evaluate, offspring))

    generation_data = {
        "generation": generation,
        "individuals": []
    }

    for fit, ind in zip(fits, offspring):
        ind.fitness.values = fit
        generation_data["individuals"].append({
            "coil_height": ind[0],
            "coil_radius": ind[1],
            "fitness": {
                "avg_power": fit[0],
                "avg_force": fit[1],
                "avg_inductance": fit[2]
            }
        })

    output_data.append(generation_data)

    population = toolbox.select(offspring, len(population))
    best_individual = tools.selBest(population, 1)[0]
    print(f"Generation {generation}: Fitness = {best_individual.fitness.values}")

# === Save JSON Output ===
with open("deap_optimization_results.json", "w") as f:
    json.dump(output_data, f, indent=2)

# === Final Best Solution ===
final_best = tools.selBest(population, 1)[0]
print("\nBest Individual Found:")
print(f"  Coil Height: {final_best[0]:.3f}")
print(f"  Coil Radius: {final_best[1]:.3f}")
print(f"  Fitness (Power, Force, Inductance): {final_best.fitness.values}")