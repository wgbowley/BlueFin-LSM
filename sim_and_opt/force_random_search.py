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
import json
from pathlib import Path

# Applies project root directory dynamically 
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from blueshark.output.selector import OutputSelector
from blueshark.output.writer import write_output_json
from blueshark.simulations.rotational_analysis import rotational_analysis
from blueshark.simulations.alignment import phase_alignment
from model.motor import BlueFin

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
best_height = 0.0
best_radius = 0.0
best_spacing = 0.0
stall = 0

motor_config_path = "sim_and_opt/model/motor.yaml" 
results_output = "sim_and_opt/Results/force_random_search_results.json"
requested_outputs = ["force_lorentz", "phase_power"]
ALIGN_SAMPLES = 10
TEST_SAMPLES  = 10

optimization_results = []


# --- Main optimization loop ---
for index in range(SIMULATION_NUM):
    motor = BlueFin(motor_config_path) 
    slot_height = motor.slot_height
    slot_radius = motor.slot_radius
    spacing = motor.slot_spacing

    height, radius, spacing = generate_geometry(STEP_SIZE, slot_height, slot_radius, spacing)

    # Log test start
    test_log = {
        "iteration": index,
        "slot_height": height,
        "slot_radius": radius,
        "slot_spacing": spacing,
        "status": "started"
    }

    optimization_results.append(test_log)
    write_output_json(optimization_results, results_output, False)

    try:
        motor.slot_height = height
        motor.slot_radius = radius
        motor.slot_spacing = spacing
        motor.setup()

        output_selector = OutputSelector(requested_outputs)
        subjects = {"group": motor.get_moving_group(), "phaseName": motor.phases}
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

        write_output_json(optimization_results, results_output, False)

        if avg_power > POWER_LIMIT:
            print(f"Iteration {index}: Rejected (power {avg_power:.2f} W > limit)")
            stall += 1
        elif avg_force > best_force:
            best_force = avg_force
            best_height = height
            best_radius = radius
            best_spacing = spacing
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
        write_output_json(optimization_results, results_output, False)
        print(f"Iteration {index}: Crashed with error: {e}")
        break

print(f"Best geometry found after {index + 1} iterations:")
print(f"Slot radius: {best_radius}")
print(f"Slot height: {best_height}")
print(f"Slot Spacing: {best_spacing}")
print(f"Average force: {best_force}")
