"""
Filename: bluefin_optimization.py
Author: William Bowley
Version: 1.3
Date: 2025-08-19

Description:
    Input Parameters:
    - Slot axial length
    - Slot radial thicknessthi
    - Slot axial spacing
    - Wire diameter

    Optimized Outputs:
    - Average force
    - Force per watt (efficiency)
    - Ripple force
    - Inductance
    - Resistance
    - Time constant

    Constraints:
    - Maximum voltage
    - Maximum power
    - Maximum inductance
    - Magnet axial length
    - Magnet radial thickness
"""

import random
from deap import base, creator, tools, algorithms

from models.iron_tubular.motor import Tubular
from bluefin.output.selector import OutputSelector
from bluefin.simulations.alignment import phase_alignment
from bluefin.simulations.rotational_analysis import rotational_analysis
from bluefin.domain.physics.ripple import ripple_peak_to_peak
from bluefin.output.writer import write_output_json
from bluefin.configs.constants import EPSILON

# Optimization Variables
individuals = 50
generations = 25
weights = (
    6,   # Average Force
    3,   # Force per watt
    -4,  # Ripple Force
    -2,  # Inductance
    -1,  # Resistance
    -4,  # Time Constant
)

random.seed(121)

# Constraints
Voltage_Max = 35
Power_Max = 100
Inductance_Max = 0.01
Resistance_Max = 15
Ripple_Max = 3

# Input bounds
Axial_Length_Bounds = (0.2, 10)
Axial_Spacing_Bounds = (1.2, 10)

Radial_Thickness_Bounds = (0.2, 10)

candidate_wire_diameters = [0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5, 0.63, 0.8, 1, 1.25, 1.6, 2, 2.5]

# Simulation Variables
Alignment_Samples = 20
Rotational_Samples = 20

motor_parameter_path = "models/iron_tubular/single.yaml"
output_path = "single_50_20.json"

requested_outputs = [
    "force_lorentz",
    "phase_power",
    "phase_voltage",
    "phase_current",
    "phase_inductance"
]

# Saving inital Parameters
with open(motor_parameter_path, 'r') as f:
    motor_yaml_text = f.read()

result_output = [{
    "motor_yaml": motor_yaml_text,
    "generations": []
}]
write_output_json(result_output, output_path)


def time_constant(inductance, resistance) -> float:
    """Calculates the time constant for the L/R circuit"""
    return inductance / resistance


def resistance(voltage, current) -> float:
    """Calculates the resistance of the coil using ohms rule"""
    return abs(voltage / current)


def simulate(slot_thickness: float, slot_axial_length: float,
             slot_axial_spacing: float, back_thickness: float,
             wire_diameter: float):
    """Runs a motor simulation with given slot parameters."""
    try:
        motor = Tubular(motor_parameter_path)
        motor.slot_thickness = slot_thickness
        motor.slot_axial_length = slot_axial_length
        motor.slot_axial_spacing = slot_axial_spacing
        motor.slot_wire_diameter = wire_diameter
        motor.yoke_thickness = back_thickness
        motor.slot_material = f"{wire_diameter}mm"
        motor.setup()

        selector = OutputSelector(requested_outputs)
        subjects = {"group": motor.moving_group, "phaseName": motor.phases}

        phase_offset = phase_alignment(motor, Alignment_Samples, False)
        results = rotational_analysis(
            motor, selector, subjects, Rotational_Samples, phase_offset, False
        )

        if not results:
            print(f"Simulation returned empty results for {slot_thickness=}, {slot_axial_length=}, "
                  f"{slot_axial_spacing=}, {wire_diameter=}")
            return []
        return results

    except Exception as e:
        print(f"Simulation FAILED for {slot_thickness=}, {slot_axial_length=}, "
              f"{slot_axial_spacing=}, {wire_diameter=}")
        print("Error:", e)
        return []


def evaluate_motor(individual):
    """Evaluates motor with DEAP input parameters and returns summary metrics"""
    slot_thickness, slot_axial_length, slot_axial_spacing, back_thickness, wire_index = individual
    wire_index = int(round(wire_index))
    wire_index = max(0, min(len(candidate_wire_diameters) - 1, wire_index))
    wire_diameter = candidate_wire_diameters[wire_index]

    results = simulate(slot_thickness, slot_axial_length, slot_axial_spacing, back_thickness, wire_diameter)

    if not results:
        return -1e6, -1e6, 1e6, 1e6, 1e6, 1e6

    forces = [entry['outputs']['force_lorentz'][0] for entry in results]
    powers = [sum(entry['outputs']['phase_power']) for entry in results]

    # 1. Average force
    avg_force = sum(forces) / len(forces)

    # 2. Force per watt (with EPSILON safety)
    avg_power = sum(powers) / len(powers)
    force_per_watt = avg_force / (avg_power + EPSILON)

    if avg_power > Power_Max:
        print(f"[Constraint Fail] Average power {avg_power:.3f} W exceeds MAX {Power_Max} W")
        return -1e6, -1e6, 1e6, 1e6, 1e6, 1e6

    # 3. Ripple force (peak-to-peak)
    ripple_force = ripple_peak_to_peak(forces)

    # 4 & 5. Inductance and resistance using phase with highest current
    resistances = []
    selected_inductances = []
    for entry in results:
        v_phase = entry['outputs']['phase_voltage']
        i_phase = entry['outputs']['phase_current']
        l_phase = entry['outputs']['phase_inductance']

        idx = max(range(len(i_phase)), key=lambda j: abs(i_phase[j]))
        current = i_phase[idx]
        voltage = v_phase[idx]
        inductance = l_phase[idx]

        if inductance > Inductance_Max:
            print(f"[Constraint Fail] inductance {inductance:.5f} H exceeds MAX {Inductance_Max} H")
            return -1e6, -1e6, 1e6, 1e6, 1e6, 1e6

        if voltage > Voltage_Max:
            print(f"[Constraint Fail] Voltage {voltage:.3f} V exceeds MAX {Voltage_Max} V")
            return -1e6, -1e6, 1e6, 1e6, 1e6, 1e6

        if abs(current) > EPSILON:
            resistances.append(resistance(voltage, current))
            selected_inductances.append(inductance)

    avg_resistance = sum(resistances) / len(resistances) if resistances else EPSILON
    avg_inductance = sum(selected_inductances) / len(selected_inductances) if selected_inductances else 0

    # 6. Time constant
    tau = time_constant(avg_inductance, avg_resistance) if avg_resistance > EPSILON else 0

    return avg_force, force_per_watt, ripple_force, avg_inductance, avg_resistance, tau


# --- DEAP Setup ---
creator.create("FitnessMulti", base.Fitness, weights=weights)
creator.create("Individual", list, fitness=creator.FitnessMulti)

toolbox = base.Toolbox()
toolbox.register("input_thickness", random.uniform, Radial_Thickness_Bounds[0], Radial_Thickness_Bounds[1])
toolbox.register("input_length", random.uniform, Axial_Length_Bounds[0], Axial_Length_Bounds[1])
toolbox.register("input_back", random.uniform, Radial_Thickness_Bounds[0], Radial_Thickness_Bounds[1])
toolbox.register("input_spacing", random.uniform, Axial_Spacing_Bounds[0], Axial_Spacing_Bounds[1])
toolbox.register("input_wire", random.randint, 0, len(candidate_wire_diameters) - 1)

toolbox.register(
    "individual",
    tools.initCycle,
    creator.Individual,
    (toolbox.input_thickness, toolbox.input_length, toolbox.input_spacing, toolbox.input_back, toolbox.input_wire),
    n=1
)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluate_motor)
toolbox.register("mate", tools.cxBlend, alpha=0.5)
toolbox.register(
    "mutate",
    tools.mutPolynomialBounded,
    low=[Radial_Thickness_Bounds[0], Axial_Length_Bounds[0], Radial_Thickness_Bounds[0], Axial_Spacing_Bounds[0], 0],
    up=[Radial_Thickness_Bounds[1], Axial_Length_Bounds[1], Axial_Spacing_Bounds[1], Radial_Thickness_Bounds[1], len(candidate_wire_diameters) - 1],
    eta=20.0,
    indpb=0.2,
)
toolbox.register("select", tools.selTournament, tournsize=3)

# --- Optimization Loop ---
population = toolbox.population(n=individuals)
crossoverPB = 0.7
mutationPB = 0.5

for generation in range(generations):
    offspring = algorithms.varAnd(population, toolbox, cxpb=crossoverPB, mutpb=mutationPB)

    # Clamp values
    for ind in offspring:
        ind[0] = min(Radial_Thickness_Bounds[1], max(Radial_Thickness_Bounds[0], ind[0]))
        ind[1] = min(Axial_Length_Bounds[1], max(Axial_Length_Bounds[0], ind[1]))
        ind[2] = min(Axial_Spacing_Bounds[1], max(Axial_Spacing_Bounds[0], ind[2]))
        ind[3] = min(Radial_Thickness_Bounds[1], max(Radial_Thickness_Bounds[0], ind[3]))
        ind[4] = min(len(candidate_wire_diameters) - 1, max(0, int(round(ind[4]))))

    generation_data = {"generation": generation, "individuals": []}

    for ind in offspring:
        ind_log = {
            "Slot thickness": ind[0],
            "Slot axial length": ind[1],
            "Slot axial spacing": ind[2],
            "Back Iron thickness": ind[3],
            "Wire diameter": candidate_wire_diameters[int(ind[4])],
            "status": "started"
        }
        generation_data["individuals"].append(ind_log)

        # Evaluate fitness
        fit = toolbox.evaluate(ind)
        ind.fitness.values = fit

        ind_log.update({
            "fitness": {
                "Average Force (N)": fit[0],
                "Force Per Watt (N/W)": fit[1],
                "Peak-to-Peak Ripple (N)": fit[2],
                "Inductance (H)": fit[3],
                "Resistance (Ohms)": fit[4],
                "Time Constant (S)": fit[5]
            },
            "status": "completed"
        })

    # Append generation data once per generation
    result_output[0]["generations"].append(generation_data)
    write_output_json(result_output, output_path)

    # Select next population
    population = toolbox.select(offspring, len(population))
    best_individual = tools.selBest(population, 1)[0]
    print(f"Generation {generation}: Fitness = {best_individual.fitness.values}")

# --- Pareto Front ---
pareto_front = tools.sortNondominated(population, k=len(population), first_front_only=True)[0]

print("\n--- Pareto Front ---")
print(f"{'Thickness':>10} {'Length':>10} {'Spacing':>10} {'Wire':>6} | {'Avg F':>8} {'F/W':>8} {'Ripple':>8} {'Ind':>8} {'R':>8} {'Tau':>8}")
for ind in pareto_front:
    print(f"{ind[0]:10.3f} {ind[1]:10.3f} {ind[2]:10.3f} {ind[3]:10.3f} {candidate_wire_diameters[int(ind[4])]:6.3f} | "
          f"{ind.fitness.values[0]:8.3f} {ind.fitness.values[1]:8.3f} {ind.fitness.values[2]:8.3f} "
          f"{ind.fitness.values[3]:8.5f} {ind.fitness.values[4]:8.3f} {ind.fitness.values[5]:8.5f}")

# --- Best Individual Overall ---
best_individual = tools.selBest(population, 1)[0]
print("\n--- Best Individual Overall ---")
print(f"{'Thickness':>10} {'Length':>10} {'Spacing':>10} {'Wire':>6} | {'Avg F':>8} {'F/W':>8} {'Ripple':>8} {'Ind':>8} {'R':>8} {'Tau':>8}")
print(f"{best_individual[0]:10.3f} {best_individual[1]:10.3f} {best_individual[2]:10.3f} {ind[3]:10.3f} {candidate_wire_diameters[int(best_individual[4])]:6.3f} | "
      f"{best_individual.fitness.values[0]:8.3f} {best_individual.fitness.values[1]:8.3f} {best_individual.fitness.values[2]:8.3f} "
      f"{best_individual.fitness.values[3]:8.5f} {best_individual.fitness.values[4]:8.3f} {best_individual.fitness.values[5]:8.5f}")
