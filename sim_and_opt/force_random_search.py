"""
Filename: force_random_search.py
Author: William Bowley
Version: 1.1
Date: 2025-07-17

Description:
    Performs a simple random search optimization to maximize average Lorentz force
    in a tubular linear motor using the simulation framework.

    Demonstrates a basic optimization strategy without external dependencies.
    Serves as a starting example before moving to more advanced optimization methods.
"""

import os
import random
import sys

# Applies project root directory dynamically 
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bluefin.output.selector import OutputSelector
from bluefin.output.writer import write_output_json
from bluefin.simulations.rotational_analysis import rotational_analysis
from bluefin.simulations.alignment import phase_alignment
from model.motor import Tubular

# --- Helper functions ---
def random_value():
    return random.random() * 2 - 1

def generate_geometry(step_size: float, slot_height: float, slot_radius: float, spacing: float) -> tuple[float, float]:
    height = abs(slot_height + step_size * random_value())
    radius = abs(slot_radius + step_size * random_value())
    spacing = abs(spacing + step_size * random_value())

    return height, radius, spacing

# --- Optimization parameters ---
SIMULATION_NUM = 1000
STEP_SIZE = 20
MIN_STEP_SIZE = 0.315
STALL_MAX = 50 # Num of stalls to finish is 50/(2^n) = min_step_size
POWER_LIMIT = 200

best_force = 0.0
best_slot_thickness = 0.0
best_axial_length = 0.0
best_axial_spacing = 0.0
best_diameter: str = None
stall = 0

candidate_values = [0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5, 0.63, 0.8]

motor_config_path = "model/motor.yaml" 
results_output = "Results/force_random_search_results.json"
requested_outputs = ["force_lorentz", "phase_power"]
ALIGN_SAMPLES = 10
TEST_SAMPLES  = 10

optimization_results = []


# --- Main optimization loop ---
for index in range(SIMULATION_NUM):
    motor = Tubular(motor_config_path) 
    slot_height = motor.slot_axial_length
    slot_radius = motor.slot_thickness
    spacing = motor.slot_axial_spacing
    diameter = random.choice(candidate_values)

    height, radius, spacing = generate_geometry(STEP_SIZE, slot_height, slot_radius, spacing)
    spacing = 1.3
    try:
        motor.slot_axial_length = height
        motor.slot_thickness = radius
        motor.slot_axial_spacing = spacing
        motor.slot_wire_diameter = diameter
        motor.slot_material = str(diameter) + "mm"
        motor.setup()

        # Log test start
        test_log = {
            "iteration": index,
            "slot_axial_length": motor.slot_axial_length,
            "slot_thickness": motor.slot_thickness,
            "slot_axial_spacing": motor.slot_axial_spacing,
            "diameter": diameter,
            "status": "started"
        }

        optimization_results.append(test_log)
        write_output_json(optimization_results, results_output)

        output_selector = OutputSelector(requested_outputs)
        subjects = {"group": motor.moving_group, "phaseName": motor.phases}
        phase_offset = phase_alignment(motor, ALIGN_SAMPLES, False)
        results = rotational_analysis(motor, output_selector, subjects, TEST_SAMPLES, phase_offset, False)

        total_force = 0.0
        total_power = 0.0
        count = 0

        for step in results:
            outputs = step["outputs"]
            if not outputs:
                continue
            force_vals = outputs.get("force_lorentz")
            power_vals = outputs.get("phase_power")
            if force_vals is None or power_vals is None:
                continue
            total_force += force_vals[0]
            total_power += sum(power_vals)
            count += 1

        avg_force = total_force / count if count else 0.0
        avg_power = total_power / count if count else 0.0

        # Update test log
        optimization_results[-1].update({
            "avg_force": avg_force,
            "avg_power": avg_power,
            "accepted": avg_power <= POWER_LIMIT,
            "status": "completed"
        })

        write_output_json(optimization_results, results_output)

        if avg_power > POWER_LIMIT:
            print(f"Iteration {index}: Rejected (power {avg_power:.2f} W > limit)")
            stall += 1
        elif avg_force > best_force:
            best_force = avg_force
            best_axial_length = motor.slot_axial_length
            best_slot_thickness = motor.slot_thickness
            best_axial_spacing = motor.slot_axial_spacing
            best_diameter = diameter
            stall = 0
            print(f"Iteration {index}: New best! Force={best_force:.3f} N, Power={avg_power:.2f} W")
        else:
            stall += 1
            print(f"Iteration {index}: No improvement. Stall count: {stall}")

        if stall >= STALL_MAX:
            STEP_SIZE /= 2
            stall = 0
            print(f"Step size reduced to {STEP_SIZE} due to stagnation.")

        if STEP_SIZE < MIN_STEP_SIZE:
            print("Minimum step size reached. Ending optimization.")
            break

    except Exception as e:
        optimization_results[-1].update({
            "status": "crashed",
            "error": str(e)
        })
        write_output_json(optimization_results, results_output)
        print(f"Iteration {index}: Crashed with error: {e}")
        break

print(f"Best geometry found after {index + 1} iterations:")
print(f"slot_axial_length: {best_slot_thickness}")
print(f"slot_thickness: {best_axial_length}")
print(f"slot_axial_spacing: {best_axial_spacing}")
print(f"wire_diameter: {best_diameter}")
print(f"Average force: {best_force}")
