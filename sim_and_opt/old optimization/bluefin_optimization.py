"""
Filename: bluefin_optimization.py
Author: William Bowley
Version: 1.2
Date: 2025-08-17

Description:
    Input Parameters:
    - Slot axial length
    - Slot radial thickness
    - Slot axial spacing
    - Wire diameter

    Optimized Outputs:
    - Average force
    - Force per watt (efficiency)
    - Average inductance
    - Peak-to-peak force ripple

    Constraints:
    - Maximum voltage
    - Maximum power
    - Maximum inductance
    - Magnet axial length
    - Magnet radial thickness
"""

import random
from deap import base, creator, tools, algorithms

from bluefin.output.selector import OutputSelector
from single_fed_motor.motor import Tubular
from bluefin.simulations.rotational_analysis import rotational_analysis
from bluefin.simulations.alignment import phase_alignment
from bluefin.domain.physics.ripple import ripple_peak_to_peak
from bluefin.output.writer import write_output_json
from bluefin.configs import EPSILON

individuals = 50
generations = 20
weights = (5, 2, -3, -2)  # Force, Force/Watt, Inductance, Force Ripple
random.seed(232)
VERBOSE = True

# Constraints
VOLTAGE_MAX = 35  # Volts
POWER_MAX = 100  # Watts
INDUCTANCE_MAX = 0.02  # Phase inductance (H)
UPPER_BOUND = 20
LOWER_BOUND = 0.2

# Motor configuration
ALIGNMENT_SAMPLES = 10
ROTATIONAL_SAMPLES = 20

# Wire diameter candidates (mm)
candidate_wire_diameters = [0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5, 0.63, 0.8, 1, 1.25, 1.6, 2, 2.5]

motor_parameter_path = "single_fed_motor/single.yaml"
output_path = "50x40_simulation_results.json"

requested_outputs = [
    "force_lorentz",
    "phase_power",
    "phase_voltage",
    "phase_inductance"
]


# --- Feasible bounds ---
THICKNESS_BOUNDS = (0.2, 10.0)  # Slot thickness
LENGTH_BOUNDS = (0.2, 20.0)     # Slot axial length
SPACING_BOUNDS = (1.2, 5.0)    # Slot axial spacing


# --- Updated simulate function ---
def simulate(slot_thickness, slot_axial_length, slot_axial_spacing, wire_diameter):
    """
    Runs a motor simulation with given slot parameters.
    Returns [] if setup or simulation fails.
    """
    try:
        motor = Tubular(motor_parameter_path)
        motor.slot_thickness = slot_thickness
        motor.slot_axial_length = slot_axial_length
        motor.slot_axial_spacing = slot_axial_spacing
        motor.slot_wire_diameter = wire_diameter
        motor.slot_material = f"{wire_diameter}mm"
        motor.setup()

        selector = OutputSelector(requested_outputs)
        subjects = {"group": motor.moving_group, "phaseName": motor.phases}

        phase_offset = phase_alignment(motor, ALIGNMENT_SAMPLES, False)
        results = rotational_analysis(
            motor, selector, subjects, ROTATIONAL_SAMPLES, phase_offset, False
        )
        if not results:
            print(f"Simulation returned empty results for {slot_thickness=}, {slot_axial_length=}, {slot_axial_spacing=}, {wire_diameter=}")
            return []
        return results

    except Exception as e:
        print(f"Simulation FAILED for {slot_thickness=}, {slot_axial_length=}, {slot_axial_spacing=}, {wire_diameter=}")
        print("Error:", e)
        return []


def evaluate_motor(individual):
    """
    Evaluates DEAP input parameters safely, with correct inductance averaging.
    """
    slot_thickness, slot_axial_length, slot_axial_spacing, wire_index = individual
    wire_index = int(round(wire_index))
    wire_index = max(0, min(len(candidate_wire_diameters) - 1, wire_index))
    wire_diameter = candidate_wire_diameters[wire_index]

    results = simulate(slot_thickness, slot_axial_length, slot_axial_spacing, wire_diameter)
    print(results)
    if not results:
        if VERBOSE:
            print(f"[Check] No results returned from simulate() for parameters: "
                  f"{slot_thickness=}, {slot_axial_length=}, {slot_axial_spacing=}, {wire_diameter=}")
        return (0.0, 0.0, 0.0, 0.0)

    if VERBOSE:
        print(f"[Info] Evaluating: {slot_thickness=}, {slot_axial_length=}, "
              f"{slot_axial_spacing=}, {wire_diameter=}")

    total_force = 0
    total_power = 0
    phase_inductances_over_time = {}
    samples = 0
    forces = []

    for i, step in enumerate(results):
        if step is None or "outputs" not in step:
            if VERBOSE:
                print(f"[Warning] Step {i} is None or missing outputs")
            continue
        outputs = step["outputs"]

        # Voltage constraint
        voltages = outputs.get("phase_voltage")
        if voltages and any(abs(v) > VOLTAGE_MAX for v in voltages):
            if VERBOSE:
                print(f"[Constraint Fail] Step {i}: Voltage exceeded MAX ({VOLTAGE_MAX}V), voltages={voltages}")
            return (0.0, 0.0, 0.0, 0.0)

        # Force
        force_values = outputs.get("force_lorentz")
        if not force_values:
            if VERBOSE:
                print(f"[Warning] Step {i}: No force_lorentz data")
            continue
        forces.append(force_values[0])
        total_force += force_values[0]

        # Power and Inductance
        power_values = outputs.get("phase_power")
        inductance_values = outputs.get("phase_inductance")
        if power_values is None or inductance_values is None:
            if VERBOSE:
                print(f"[Warning] Step {i}: Missing power or inductance data")
            continue

        # Average power per step
        if power_values: # That probably caused problems
            total_power += sum(power_values) / len(power_values)
        
        # Inductance Averaging
        if inductance_values:
            for phase_idx, inductance in enumerate(inductance_values):
                if phase_idx not in phase_inductances_over_time:
                    phase_inductances_over_time[phase_idx] = []
                phase_inductances_over_time[phase_idx].append(inductance)

        samples += 1

    if samples == 0:
        if VERBOSE:
            print("[Check Fail] No valid simulation steps to calculate averages")
        return (0.0, 0.0, 0.0, 0.0)

    # Final averages over steps
    avg_force = total_force / samples
    avg_power = total_power / samples

    # Calculate average inductance per phase over the simulation, then average those results.
    avg_inductance_per_phase = []
    if phase_inductances_over_time:
        for phase_idx in phase_inductances_over_time:
            if phase_inductances_over_time[phase_idx]:
                avg_inductance_per_phase.append(sum(phase_inductances_over_time[phase_idx]) / len(phase_inductances_over_time[phase_idx]))

    if avg_inductance_per_phase:
        avg_inductance = sum(avg_inductance_per_phase) / len(avg_inductance_per_phase)
    else:
        avg_inductance = 0.0

    # Constraint checks
    # The constraint for avg_power should be based on its absolute value or a very small epsilon,
    # to allow for negative power (generation). A positive value for force_per_watt is often the goal,
    # which is handled later. This check now ensures useful work is being done.
    if abs(avg_power) < EPSILON:
        if VERBOSE:
            print(f"[Check Fail] Average power too close to zero: {avg_power:.3f} W")
        return (0.0, 0.0, 0.0, 0.0)
    
    if avg_power > POWER_MAX:
        if VERBOSE:
            print(f"[Constraint Fail] Average power {avg_power:.3f} W exceeds MAX {POWER_MAX} W")
        return (0.0, 0.0, 0.0, 0.0)
        
    if avg_inductance > INDUCTANCE_MAX:
        if VERBOSE:
            print(f"[Constraint Fail] Average inductance {avg_inductance:.5f} H exceeds MAX {INDUCTANCE_MAX} H")
        return (0.0, 0.0, 0.0, 0.0)

    # Force per watt calculation
    # We use the absolute value of avg_power to correctly calculate efficiency,
    # as force_per_watt is a measure of a motor's ability to convert power.
    force_per_watt = 0.0
    if abs(avg_power) > EPSILON:
        force_per_watt = avg_force / abs(avg_power)

    # Calculate ripple force
    ripple_force = ripple_peak_to_peak(forces) if forces else 0.0

    if VERBOSE:
        print(f"[Result] Avg Force={avg_force:.3f}, Force/Watt={force_per_watt:.3f}, "
              f"Ripple={ripple_force:.3f}, Avg Inductance={avg_inductance:.5f}")

    return (avg_force, force_per_watt, avg_inductance, ripple_force)


# --- DEAP Setup ---
creator.create("FitnessMulti", base.Fitness, weights=weights)
creator.create("Individual", list, fitness=creator.FitnessMulti)

toolbox = base.Toolbox()
toolbox.register("input_thickness", random.uniform, THICKNESS_BOUNDS[0], THICKNESS_BOUNDS[1])
toolbox.register("input_length", random.uniform, LENGTH_BOUNDS[0], LENGTH_BOUNDS[1])
toolbox.register("input_spacing", random.uniform, SPACING_BOUNDS[0], SPACING_BOUNDS[1])
toolbox.register("input_wire", random.randint, 0, len(candidate_wire_diameters) - 1)

toolbox.register(
    "individual",
    tools.initCycle,
    creator.Individual,
    (toolbox.input_thickness, toolbox.input_length, toolbox.input_spacing, toolbox.input_wire),
    n=1
)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluate_motor)
toolbox.register("mate", tools.cxBlend, alpha=0.5)
toolbox.register(
    "mutate",
    tools.mutPolynomialBounded,
    low=[LOWER_BOUND, LOWER_BOUND, LOWER_BOUND, 0],
    up=[UPPER_BOUND, UPPER_BOUND, UPPER_BOUND, len(candidate_wire_diameters) - 1],
    eta=20.0,
    indpb=0.2,
)
toolbox.register("select", tools.selTournament, tournsize=3)


# --- Optimization Loop ---
population = toolbox.population(n=individuals)
crossoverPB = 0.7
mutationPB = 0.5
result_output = []

for generation in range(generations):
    offspring = algorithms.varAnd(population, toolbox, cxpb=crossoverPB, mutpb=mutationPB)

    # Clamp values
    for ind in offspring:
        ind[0] = min(UPPER_BOUND, max(LOWER_BOUND, ind[0]))
        ind[1] = min(UPPER_BOUND, max(LOWER_BOUND, ind[1]))
        ind[2] = min(UPPER_BOUND, max(LOWER_BOUND, ind[2]))
        ind[3] = min(len(candidate_wire_diameters) - 1, max(0, int(round(ind[3]))))

    generation_data = {"generation": generation, "individuals": []}

    for ind in offspring:
        ind_log = {
            "Slot thickness": ind[0],
            "Slot axial length": ind[1],
            "Slot axial spacing": ind[2],
            "Wire diameter": candidate_wire_diameters[int(ind[3])],
            "status": "started"
        }
        generation_data["individuals"].append(ind_log)
        write_output_json(result_output + [generation_data], output_path)

        fit = toolbox.evaluate(ind)
        ind.fitness.values = fit

        ind_log.update({
            "fitness": {
                "Average Force": fit[0],
                "Force Per Watt": fit[1],
                "Average Inductance": fit[2],
                "Peak-to-Peak Force": fit[3]
            },
            "status": "completed"
        })
        write_output_json(result_output + [generation_data], output_path)

    result_output.append(generation_data)
    population = toolbox.select(offspring, len(population))
    best_individual = tools.selBest(population, 1)[0]
    print(f"Generation {generation}: Fitness = {best_individual.fitness.values}")

# --- Final Best Solution ---
final_best = tools.selBest(population, 1)[0]
print(
    f"Best: thickness={final_best[0]:.2f}, "
    f"axial_length={final_best[1]:.2f}, "
    f"axial_spacing={final_best[2]:.2f}, "
    f"wire_diameter={candidate_wire_diameters[int(final_best[3])]:.3f}mm, "
    f"fitness={final_best.fitness.values}"
)
