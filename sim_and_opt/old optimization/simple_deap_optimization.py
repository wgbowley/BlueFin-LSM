"""
Filename: deap_optimization.py
Author: William Bowley
Version: 1.1
Date: 2025-08-16

Description:
    Example of using the motor simulation framework with the
    DEAP evolutionary optimizer.

    Optimizes coil geometry (height, radius) and wire diameter
    for force output while considering power, voltage, and inductance constraints.
"""

import os
import sys
import random
from deap import base, creator, tools, algorithms

# Dynamically apply project root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bluefin.output.selector import OutputSelector
from single_fed_motor.motor import Tubular
from bluefin.simulations.rotational_analysis import rotational_analysis
from bluefin.simulations.alignment import phase_alignment
from bluefin.output.writer import write_output_json
from bluefin.configs.constants import EPSILON

print(EPSILON)
# Optimization Setup
individuals = 50
generations = 40
weights = (1, 5, -1)  # Power, Force, Inductance
random.seed(42)  # Improves reproducibility
VERBOSE = True  # Set to True to print every evaluation step

VOLTAGE_MAX = 56  # Max voltage (V)
POWER_MAX = 250  # Max average power (W)
INDUCTANCE_MAX = 0.05  # Max phase inductance (H)
UPPER_BOUND = 20
LOWER_BOUND = 0.2

# Wire diameter candidates (mm)
candidate_wire_diameters = [0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5, 0.63, 0.8]

# Motor configuration
ALIGNMENT_SAMPLES = 10
ROTATIONAL_SAMPLES = 10

motor_parameter_path = "single_fed_motor/single.yaml"
output_path = "50x40_simulation_results.json"

requested_outputs = [
    "force_lorentz",
    "phase_power",
    "phase_voltage",
    "phase_inductance"
]


def simulate(
    slot_thickness: float,
    slot_axial_length: float,
    wire_diameter: float
) -> tuple:
    """
    Runs a motor simulation with given slot thickness, axial length, and wire diameter.
    Returns (None, None, None, None) if setup or simulation fails.
    """
    try:
        motor = Tubular(motor_parameter_path)
        motor.slot_thickness = slot_thickness
        motor.slot_axial_length = slot_axial_length
        motor.slot_wire_diameter = wire_diameter
        motor.slot_material = f"{wire_diameter}mm"
        motor.setup()

        selector = OutputSelector(requested_outputs)
        subjects = {"group": motor.moving_group, "phaseName": motor.phases}

        phase_offset = phase_alignment(motor, ALIGNMENT_SAMPLES, False)
        results = rotational_analysis(
            motor, selector, subjects, ROTATIONAL_SAMPLES, phase_offset, False
        )
        return results

    except Exception as e:
        print(f"Simulation failed: {e}")
        return (None, None, None, None)


def evaluate_motor(individual) -> tuple[float, float, float]:
    slot_thickness, slot_axial_length, wire_index = individual
    wire_index = int(round(wire_index))  # Ensure integer index
    wire_diameter = candidate_wire_diameters[wire_index]

    results = simulate(slot_thickness, slot_axial_length, wire_diameter)

    # Handle failed simulation
    if not results or results == (None, None, None, None):
        if VERBOSE:
            print(f"Simulation failed for thickness={slot_thickness:.3f}, "
                  f"length={slot_axial_length:.3f}, wire={wire_diameter:.3f}mm")
        return (0.0, 0.0, 0.0)

    if VERBOSE:
        print(
            f"Evaluating: slot_thickness={slot_thickness:.3f}, "
            f"slot_axial_length={slot_axial_length:.3f}, "
            f"wire_diameter={wire_diameter:.3f}mm"
        )

    total_force = 0
    total_power = 0
    total_inductance = 0
    samples = 0
    total_inductance_values = 0
    print(results)
    for step in results:
        if step is None:
            continue

        outputs = step.get("outputs")
        if not outputs:
            continue

        voltages = outputs.get("phase_voltage")
        if voltages:
            for voltage in voltages:
                if abs(voltage) > VOLTAGE_MAX:
                    return (0.0, 0.0, 0.0)

        force_values = outputs.get("force_lorentz")
        power_values = outputs.get("phase_power")
        inductance_values = outputs.get("phase_inductance")

        if force_values is None or power_values is None or inductance_values is None:
            return (0.0, 0.0, 0.0)

        total_force += force_values[0]
        total_power += sum(power_values)
        total_inductance += sum(inductance_values)
        total_inductance_values += len(inductance_values)
        samples += 1

    if samples == 0:
        return (0.0, 0.0, 0.0)

    avg_force = total_force / samples
    avg_power = total_power / samples
    avg_inductance = total_inductance / total_inductance_values if total_inductance_values > 0 else 0

    if avg_power > POWER_MAX or avg_inductance > INDUCTANCE_MAX:
        return (0.0, 0.0, 0.0)

    if VERBOSE:
        print(
            f"Average Force: {avg_force:.3f}, "
            f"Average Power: {avg_power:.3f}, "
            f"Average Inductance: {avg_inductance:.3f}"
        )

    return (avg_power, avg_force, avg_inductance)


# DEAP setup
creator.create("FitnessMulti", base.Fitness, weights=weights)
creator.create("Individual", list, fitness=creator.FitnessMulti)

toolbox = base.Toolbox()
toolbox.register("input_thickness", random.uniform, LOWER_BOUND, UPPER_BOUND)
toolbox.register("input_length", random.uniform, LOWER_BOUND, UPPER_BOUND)
toolbox.register("input_wire", random.randint, 0, len(candidate_wire_diameters) - 1)

toolbox.register(
    "individual",
    tools.initCycle,
    creator.Individual,
    (toolbox.input_thickness, toolbox.input_length, toolbox.input_wire),
    n=1
)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluate_motor)
toolbox.register("mate", tools.cxBlend, alpha=0.5)
toolbox.register(
    "mutate",
    tools.mutPolynomialBounded,
    low=[LOWER_BOUND, LOWER_BOUND, 0],
    up=[UPPER_BOUND, UPPER_BOUND, len(candidate_wire_diameters) - 1],
    eta=20.0,
    indpb=0.2,
)
toolbox.register("select", tools.selTournament, tournsize=3)

# Optimization loop
population = toolbox.population(n=individuals)
crossoverPB = 0.7
mutationPB = 0.5

result_output = []

population = toolbox.population(n=individuals)
crossoverPB = 0.7
mutationPB = 0.5

result_output = []  # Full results
output_path = "50x40_simulation_results.json"

for generation in range(generations):
    offspring = algorithms.varAnd(population, toolbox, cxpb=crossoverPB, mutpb=mutationPB)

    # Clamp values
    for ind in offspring:
        ind[0] = min(UPPER_BOUND, max(LOWER_BOUND, ind[0]))
        ind[1] = min(UPPER_BOUND, max(LOWER_BOUND, ind[1]))
        ind[2] = min(len(candidate_wire_diameters) - 1, max(0, int(round(ind[2]))))

    generation_data = {"generation": generation, "individuals": []}

    for ind_index, ind in enumerate(offspring):
        ind_log = {
            "Slot thickness": ind[0],
            "Slot axial length": ind[1],
            "Wire diameter": candidate_wire_diameters[int(ind[2])],
            "status": "started"
        }
        generation_data["individuals"].append(ind_log)
        write_output_json(result_output + [generation_data], output_path)  # Save immediately

        # Evaluate individual
        fit = toolbox.evaluate(ind)
        ind.fitness.values = fit

        # Update log
        ind_log.update({
            "fitness": {
                "average power": fit[0],
                "average force": fit[1],
                "average inductance": fit[2]
            },
            "status": "completed"
        })
        write_output_json(result_output + [generation_data], output_path)  # Save after evaluation

    result_output.append(generation_data)
    population = toolbox.select(offspring, len(population))
    best_individual = tools.selBest(population, 1)[0]
    print(f"Generation {generation}: Fitness = {best_individual.fitness.values}")

# Final Best Solution
final_best = tools.selBest(population, 1)[0]
print(
    f"Best: thickness={final_best[0]:.2f}, "
    f"length={final_best[1]:.2f}, "
    f"wire_diameter={candidate_wire_diameters[int(final_best[2])]:.3f}mm, "
    f"fitness={final_best.fitness.values}"
)
